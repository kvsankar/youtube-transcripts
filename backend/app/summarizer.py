"""Opus-backed summarizer.

Runs after the Sonnet structurer. Takes the structured transcript and
produces an actionable, structured extraction following a fixed template
(core concepts, mental models, decision rules, procedures, key insights,
pitfalls, examples, compact takeaways).

Single Opus call — no chunking. Summarisation needs the whole document in
context to synthesise across sections, and Opus's 200k context easily fits
a 60k-token transcript. Output is short (a structured digest, not the full
text) so output limits are not a concern.

Auth handling matches structurer.py: `ANTHROPIC_API_KEY` in env triggers
`claude --bare`; otherwise the CLI uses OAuth from `claude login`.
"""

import asyncio
import os
from pathlib import Path
from typing import Callable, Optional

from .paths import TRANSCRIPTS_DIR
from .retry import with_retry


_AUTH_FLAGS: tuple[str, ...] = (
    ("--bare",) if os.environ.get("ANTHROPIC_API_KEY") else ()
)

# Summarizer makes one call (no chunking). Generous timeout — Opus is
# slower than Sonnet and the input is the full structured transcript.
PER_CALL_TIMEOUT_SECONDS = 900.0  # 15 min
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (30.0, 90.0)


SYSTEM_PROMPT = """You are summarizing a technical lecture for an experienced practitioner.

Do NOT produce a generic summary. Extract actionable understanding.

Structure your response as follows:

1. CORE CONCEPTS
- List the key concepts introduced.
- For each: define it in 1–2 lines and explain why it matters.

2. MENTAL MODELS & INTUITION
- What are the underlying ideas or ways of thinking?
- Any analogies or simplifications that help understanding?

3. WHEN TO USE WHAT (DECISION FRAMEWORK)
- Extract any decision rules, trade-offs, or heuristics.
- Present as:
  - If X → do Y
  - If constraint A → prefer B over C

4. HOW TO DO IT (PROCEDURES / METHODS)
- Step-by-step processes, workflows, or patterns.
- Include commands, architecture patterns, or algorithms if mentioned.

5. KEY INSIGHTS (NON-OBVIOUS TAKEAWAYS)
- Things that are easy to miss but important.
- Surprising or counterintuitive points.

6. PITFALLS & FAILURE MODES
- What can go wrong?
- Common mistakes or limitations.

7. EXAMPLES / APPLICATIONS
- Real or implied use cases.
- Map concepts → practical scenarios.

8. COMPACT TAKEAWAYS
- 5–10 bullet points max.
- Must be sharp, memorable, and actionable.

Rules:
- Avoid filler and repetition.
- Prefer bullets over paragraphs.
- Be precise and technical where needed.
- Do not invent content not present in the lecture.
- If something is unclear or missing, explicitly say so."""

CLAUDE_MODEL = "claude-opus-4-7"


async def summarize_transcript(
    structured_path: Path,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """Summarize the structured transcript with Opus. Returns path to summary."""
    stem = structured_path.name.removesuffix(".structured.md")
    out_path = TRANSCRIPTS_DIR / f"{stem}.summary.md"
    if out_path.exists() and out_path.stat().st_size > 0:
        if on_progress:
            on_progress(100.0, f"Using cached summary ({out_path.name})")
        return out_path

    text = structured_path.read_text(encoding="utf-8")

    def on_retry(next_attempt: int, total: int) -> None:
        if on_progress:
            on_progress(0.0, f"Asking Opus to summarize (retry {next_attempt}/{total})…")

    summary = await with_retry(
        "summarizer",
        lambda: _call_claude(text),
        attempts=RETRY_ATTEMPTS,
        backoff_seconds=RETRY_BACKOFF_SECONDS,
        on_retry=on_retry,
    )

    out_path.write_text(summary, encoding="utf-8")
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

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=text.encode("utf-8")),
            timeout=PER_CALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        raise RuntimeError(
            f"claude (opus) exceeded {PER_CALL_TIMEOUT_SECONDS:.0f}s timeout"
        )

    if proc.returncode != 0:
        err = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"claude (opus) exited with code {proc.returncode}: {err or '(no stderr)'}"
        )

    summary = stdout_bytes.decode("utf-8", errors="replace").strip()
    if not summary:
        raise RuntimeError("claude (opus) returned empty summary")
    return summary
