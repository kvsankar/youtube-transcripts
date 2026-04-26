"""Claude-based transcript structurer.

Invokes the `claude` CLI in non-interactive print mode (`-p`). The CLI
handles whichever auth the user has configured:

- If `ANTHROPIC_API_KEY` is set in the environment, we add `--bare` so the
  CLI runs in a minimal mode that uses the key directly (no plugin, hook,
  or MCP loading — faster startup too).
- Otherwise the CLI falls back to the OAuth credentials from
  `claude login`.

The model is given strict instructions: re-flow the raw narration into
paragraphs, headings, and proper punctuation. Do NOT summarize, paraphrase,
add, or remove words.

Long transcripts are split into ~5k-word chunks at sentence boundaries and
processed serially. This keeps each call comfortably within Sonnet's output
window and gives the UI per-chunk progress.

Notes on the other flags:
- `--system-prompt` (replace, not append) is used so dynamic per-machine
  prompt sections (cwd, env info, git status, memory paths) are suppressed.
- `--tools ""` disables every built-in tool, so no permission decisions are
  ever made — there's no need for `--permission-mode`.
- `--disable-slash-commands` skips skill resolution at startup.
- `--no-session-persistence` keeps this one-shot call out of the session log.
"""

import asyncio
import os
from pathlib import Path
from typing import Callable

from .paths import TRANSCRIPTS_DIR


# `--bare` makes the CLI use ANTHROPIC_API_KEY exclusively and skips the
# slow per-call init (hooks, MCP, plugins, auto-memory). Computed at import
# time — env changes require a restart.
_AUTH_FLAGS: tuple[str, ...] = (
    ("--bare",) if os.environ.get("ANTHROPIC_API_KEY") else ()
)


SYSTEM_PROMPT = """You are a transcript editor. The user message contains the raw output of an automatic speech-to-text transcription of a YouTube video. The text is a single block with no paragraphs, weak punctuation, and no structure. The text may be a chunk from the middle of a longer transcript — do not assume it begins or ends at a topic boundary.

Your job is to restructure this text for readability. You MUST follow these rules strictly:

1. PRESERVE EVERY WORD. Do not summarize. Do not paraphrase. Do not condense. Do not omit. Do not add new content of your own.
2. You MAY fix obvious transcription errors only when the correction is unambiguous from context (e.g. clear homophone slips). When in doubt, leave the original word.
3. You MAY add and adjust punctuation: periods, commas, question marks, quotation marks, dashes.
4. You MAY split the text into paragraphs at natural topic or speaker shifts.
5. You MAY add Markdown headings (## Section title) where the speaker clearly transitions to a new topic. Headings must be drawn from words actually said in the text — do not invent topic names.
6. You MAY normalize capitalization (sentence case, proper nouns).
7. Do not add a preamble, summary, or commentary. Output only the restructured transcript.

Return Markdown."""

CLAUDE_MODEL = "claude-sonnet-4-6"

# Target ~5k words per chunk (~6.5k tokens). Max ~7k before forcing a split.
TARGET_CHUNK_WORDS = 5000
MAX_CHUNK_WORDS = 7000


async def structure_transcript(
    raw_path: Path,
    on_progress: Callable[[float, str], None] | None = None,
) -> Path:
    """Run the raw transcript through Claude. Returns path to structured file."""
    stem = raw_path.name.removesuffix(".raw.txt")
    out_path = TRANSCRIPTS_DIR / f"{stem}.structured.md"
    if out_path.exists() and out_path.stat().st_size > 0:
        if on_progress:
            on_progress(100.0, f"Using cached structured transcript ({out_path.name})")
        return out_path

    raw_text = raw_path.read_text(encoding="utf-8")
    chunks = _chunk_text(raw_text, TARGET_CHUNK_WORDS, MAX_CHUNK_WORDS)

    structured_pieces: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        if on_progress:
            on_progress(
                (idx - 1) / len(chunks) * 100.0,
                f"Structuring chunk {idx}/{len(chunks)}…",
            )
        piece = await _call_claude(chunk)
        structured_pieces.append(piece)

    structured = "\n\n".join(structured_pieces).strip()
    if not structured:
        raise RuntimeError("claude returned empty output for every chunk")

    out_path.write_text(structured, encoding="utf-8")
    if on_progress:
        on_progress(100.0, "Structuring complete")
    return out_path


async def _call_claude(text: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        *_AUTH_FLAGS,
        "--model", CLAUDE_MODEL,
        "--system-prompt", SYSTEM_PROMPT,
        "--output-format", "text",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--tools", "",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_bytes, stderr_bytes = await proc.communicate(input=text.encode("utf-8"))

    if proc.returncode != 0:
        err = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {err or '(no stderr)'}"
        )

    out = stdout_bytes.decode("utf-8", errors="replace").strip()
    if not out:
        raise RuntimeError("claude CLI returned empty output for a chunk")
    return out


def _chunk_text(text: str, target_words: int, max_words: int) -> list[str]:
    """Split text into chunks of roughly target_words, preferring sentence
    boundaries. Falls back to a hard cut at max_words if no boundary appears.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks: list[str] = []
    i = 0
    while i < len(words):
        end_cap = min(i + max_words, len(words))
        if end_cap == len(words):
            chunks.append(" ".join(words[i:end_cap]))
            break

        # Look for a sentence-ending word in [target, max). Word ending with
        # '.', '?', '!' marks a natural break point.
        cut = end_cap  # fallback: hard cut at max
        for j in range(i + target_words, end_cap):
            if words[j - 1].endswith((".", "?", "!")):
                cut = j
                break
        chunks.append(" ".join(words[i:cut]))
        i = cut

    return chunks
