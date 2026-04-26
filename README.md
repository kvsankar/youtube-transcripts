# YouTube Transcripts

Paste YouTube URLs into the web UI; the backend downloads each video, transcribes it locally with `faster-whisper` on the GPU, restructures the raw narration into readable Markdown via Claude (Sonnet), then produces an actionable practitioner-style summary via Claude (Opus).

## Stack

- **Backend**: Python 3.12, FastAPI, `yt-dlp`, `faster-whisper` (CUDA 12.1), the `claude` CLI for structuring (Sonnet) and summarising (Opus). State persisted to SQLite.
- **Frontend**: Vite + React + TypeScript, with Server-Sent Events for live progress, a resizable splitter, and a Markdown / HTML viewer.
- **Pipeline** (single async worker, serial): `queued → downloading → transcribing → structuring → summarizing → done`. Each stage caches its output on disk and short-circuits on a re-submit.

## Prerequisites

- `uv` (Python project manager).
- `node` 20+ and `npm`.
- `ffmpeg` on `PATH` (used by `yt-dlp` and `faster-whisper`).
- An NVIDIA GPU with CUDA 12.1+ drivers (CPU works but is much slower).
- The [`claude` CLI](https://docs.claude.com/en/docs/claude-code/overview) installed.

## Authentication for Claude

The structurer (Sonnet) and summarizer (Opus) shell out to the `claude` CLI. Either auth path works:

- **API key** *(recommended for headless / CI / multi-user setups)* — set `ANTHROPIC_API_KEY` in your environment before starting the backend. The CLI is invoked with `--bare`, which uses the key directly and skips the per-call init of hooks, plugins, MCP, and CLAUDE.md auto-discovery (≈ 5–10 s faster per call).
- **Subscription / OAuth** — run `claude login` once. With no `ANTHROPIC_API_KEY` set, the CLI uses the cached OAuth credentials. Slower per-call startup since the full Claude Code init runs.

The choice is made at backend startup by reading the env var; restart the backend after changing.

## Setup

```bash
cd backend && uv sync
cd ../frontend && npm install
```

> **CPU-only / non-NVIDIA machine?** The default `pyproject.toml` pins `torch` to the CUDA 12.1 wheel index (Linux & Windows only — these wheels still run fine on a CPU box, just bigger). On macOS or for a slimmer CPU-only install, remove the `[[tool.uv.index]]` and `[tool.uv.sources]` blocks from `backend/pyproject.toml` before running `uv sync`. The transcriber detects at runtime whether to use GPU or CPU and falls back automatically; CPU transcription works but is much slower.

## Run

Two terminals:

```bash
# Backend on http://localhost:8000
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend (Vite picks 5173 or next free port)
cd frontend && npm run dev
```

Open the URL Vite prints. Paste one or more YouTube URLs (one per line), optionally add tags, click Submit. Progress streams live; click a row to view its outputs in the right panel. Drag the splitter to resize.

## Repo layout

```
youtube-transcripts/
├── backend/                     # FastAPI service (uv-managed)
│   ├── pyproject.toml, uv.lock
│   └── app/
│       ├── main.py              # routes + SSE + lifespan
│       ├── pipeline.py          # async worker driving each job through stages
│       ├── jobs.py              # Job dataclass, SQLite-backed JobStore, dedup
│       ├── db.py                # connection + schema + migrations
│       ├── paths.py             # data/, audio/, transcripts/ resolution
│       ├── downloader.py        # yt-dlp wrapper (m4a-only, cached)
│       ├── transcriber.py       # faster-whisper (medium, CUDA), cached
│       ├── structurer.py        # Sonnet, chunked, no summarisation
│       └── summarizer.py        # Opus, single call, structured digest
└── frontend/                    # Vite + React + TypeScript
    └── src/
        ├── App.tsx              # main page: submit + jobs table + splitter
        ├── Splitter.tsx         # drag-to-resize horizontal splitter
        ├── Viewer.tsx           # RHS panel with tabs + Markdown/HTML toggle
        ├── api.ts, types.ts, styles.css, main.tsx
```

Runtime artifacts live under a single `data/` directory (gitignored):

```
data/
├── audio/                       # <videoId>.m4a (yt-dlp output)
├── transcripts/
│   ├── <videoId>.raw.txt        # whisper output, single block
│   ├── <videoId>.structured.md  # Sonnet, restructured (every word preserved)
│   └── <videoId>.summary.md     # Opus, actionable digest
└── jobs.db                      # SQLite (WAL mode)
```

To wipe state completely: `rm -rf data/`.

## API surface

| Method | Path                              | Purpose                                              |
| ------ | --------------------------------- | ---------------------------------------------------- |
| POST   | `/api/jobs`                       | Body `{urls, tags?}` → enqueue or revive jobs        |
| GET    | `/api/jobs?tag=a&tag=b`           | List jobs (ANY-match tag filter)                     |
| GET    | `/api/jobs/{id}`                  | One job's full state                                 |
| PATCH  | `/api/jobs/{id}/tags`             | Body `{tags}` → replace job's tags                   |
| DELETE | `/api/jobs/{id}`                  | Remove from store (files on disk are kept)           |
| GET    | `/api/jobs/{id}/raw`              | Raw transcript text                                  |
| GET    | `/api/jobs/{id}/structured`       | Structured transcript Markdown                       |
| GET    | `/api/jobs/{id}/summary`          | Practitioner-style summary Markdown                  |
| GET    | `/api/tags`                       | Distinct tag values currently in use                 |
| GET    | `/api/events`                     | SSE stream of job lifecycle events                   |

## Behaviour notes

- **Re-submitting a URL** does not create a duplicate row — the existing job is returned, and its tags are merged. If it was `failed`, it's reset and re-queued. If it's already `done`, no work happens.
- **Cache short-circuits** are checked before every stage by video id: cached audio skips download, cached `.raw.txt` skips transcription, cached `.structured.md` skips structuring, cached `.summary.md` skips summarisation. So re-running an old URL after, say, prompt changes only redoes the affected stage if you delete the cached file.
- **Whisper model** defaults to `medium`. Change in `backend/app/transcriber.py` (`_model_name`); options: `tiny`, `base`, `small`, `medium`, `large-v3`.
- **Structurer chunking**: long transcripts are split at sentence boundaries into ~5k-word chunks (configurable in `structurer.py`) so each Claude call stays well within the output window and surfaces per-chunk progress.
- **The `claude` CLI** is invoked with `--system-prompt` (replaces the default — also suppresses dynamic prompt sections like cwd / git status / memory paths), `--tools ""` (no tools, no permission prompts), `--no-session-persistence`, `--disable-slash-commands`. `--bare` is added when `ANTHROPIC_API_KEY` is set (see Authentication).
- **Restart semantics**: `queued` jobs auto-resume; jobs that were mid-stream when the process died are marked `failed` (re-submit the URL to retry — it will skip everything that was already cached).
