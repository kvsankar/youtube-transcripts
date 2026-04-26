# YouTube Transcripts

Paste YouTube URLs into the web UI; the backend downloads each video, transcribes it locally with `faster-whisper` (CUDA if available, CPU otherwise), restructures the raw narration into readable Markdown via Claude (Sonnet) without summarising, then produces an actionable practitioner-style digest via Claude (Opus).

## Stack

- **Backend**: Python 3.12, FastAPI, `yt-dlp`, `faster-whisper` (CPU or CUDA 12.1 — pick at install time), the `claude` CLI for structuring (Sonnet) and summarising (Opus). State persisted to SQLite.
- **Frontend**: Vite + React + TypeScript, with Server-Sent Events for live progress, a resizable splitter, and a Markdown / HTML viewer.
- **Pipeline** (single async worker, serial): `queued → downloading → transcribing → structuring → summarizing → done`. Each stage caches its output on disk and short-circuits on a re-submit. Claude calls are wrapped in a per-call timeout + retry-with-backoff so transient API failures and hung subprocesses don't kill a job.

## Prerequisites

`make doctor` will tell you which of these you're missing:

| What | Why | Install |
| ---- | --- | ------- |
| `uv`     | Python project + script runner | <https://docs.astral.sh/uv/> |
| `node` 20+, `npm` | frontend build/run                | <https://nodejs.org/> |
| `ffmpeg` | yt-dlp + faster-whisper need it   | <https://ffmpeg.org/download.html> |
| `claude` CLI | Sonnet/Opus calls               | <https://docs.claude.com/en/docs/claude-code/overview> |
| NVIDIA GPU + drivers (optional) | fast Whisper transcription | (CPU fallback works automatically) |

## Authentication for Claude

The structurer (Sonnet) and summarizer (Opus) shell out to the `claude` CLI. Either auth path works:

- **API key** *(recommended for headless / CI / multi-user setups)* — set `ANTHROPIC_API_KEY` in your environment before starting the backend. The CLI is invoked with `--bare`, which uses the key directly and skips the per-call init of hooks, plugins, MCP, and CLAUDE.md auto-discovery — a few seconds faster per call.
- **Subscription / OAuth** — run `claude login` once. With no `ANTHROPIC_API_KEY` set, the CLI uses the cached OAuth credentials. Slower per-call startup since the full Claude Code init runs.

The choice is made at backend startup by reading the env var; restart the backend after changing.

## Setup

One command does everything — auto-detects GPU vs CPU, installs both Python and Node deps, and runs a final health check:

```bash
make install              # or: uv run scripts/install.py
```

What it picks:

| Environment                     | torch wheel chosen | venv size |
| ------------------------------- | ------------------ | --------- |
| `nvidia-smi` returns a GPU      | CUDA 12.1 wheels   | ~5.2 GB   |
| no GPU detected (incl. macOS)   | CPU-only wheels    | ~1.2 GB   |

Override or skip steps:

```bash
uv run scripts/install.py --gpu              # force CUDA wheels
uv run scripts/install.py --cpu              # force CPU wheels
uv run scripts/install.py --no-frontend      # backend only (no npm install)
```

The transcriber also falls back to CPU at runtime if a GPU load fails, so a `--gpu` install is safe on a borderline machine.

To check prerequisites without installing: `make doctor` (or `uv run scripts/doctor.py`). It verifies `uv`, `node`/`npm`, `ffmpeg`, the `claude` CLI, GPU presence, and Anthropic auth.

Cold install on a fresh Ubuntu VM (no uv cache, no node_modules) takes ~20 s for CPU; warm reinstall is single-digit seconds.

## Run

```bash
make dev                  # or: uv run scripts/dev.py
```

That starts both the backend (`:8000`) and frontend (Vite, picks `5173` or next free port) in one terminal, with output prefixed `[backend ]` / `[frontend]`. Ctrl+C stops both cleanly. To run just one side: `make backend` / `make frontend`, or pass `--backend` / `--frontend` directly to `dev.py`. The backend port is configurable via `--backend-port`.

Open the URL Vite prints. Paste one or more YouTube URLs (one per line), optionally add tags, click Submit. Progress streams live; click a row to view its outputs in the right panel. Drag the splitter to resize.

## Repo layout

```
youtube-transcripts/
├── Makefile                     # make install / dev / doctor / wipe / clean
├── scripts/                     # standalone uv-run scripts
│   ├── install.py               # GPU-aware installer
│   ├── dev.py                   # runs both servers, prefixed output
│   ├── doctor.py                # prerequisite checker
│   └── _common.py
├── backend/                     # FastAPI service (uv-managed)
│   ├── pyproject.toml, uv.lock  # cpu/gpu extras pick the torch wheel index
│   └── app/
│       ├── main.py              # routes + SSE + lifespan
│       ├── pipeline.py          # async worker driving each job through stages
│       ├── jobs.py              # Job dataclass, SQLite-backed JobStore, dedup
│       ├── db.py                # connection + schema + migrations
│       ├── paths.py             # data/, audio/, transcripts/ resolution
│       ├── downloader.py        # yt-dlp wrapper (m4a-only, cached)
│       ├── transcriber.py       # faster-whisper (medium), GPU-or-CPU
│       ├── structurer.py        # Sonnet, chunked, retry+timeout
│       ├── summarizer.py        # Opus, single call, retry+timeout
│       └── retry.py             # tiny async retry helper
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

To wipe state completely: `make wipe` (or `rm -rf data/`). Use `make clean` to also drop the venv and node_modules.

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

- **Re-submitting a URL** does not create a duplicate row — the existing job is returned, and any new tags are merged. If it was `failed`, it's reset and re-queued (the cache short-circuits below mean any work that did complete the first time isn't repeated). If it's already `done`, no work happens.
- **Cache short-circuits** are checked before every stage by video id: cached audio skips download, cached `.raw.txt` skips transcription, cached `.structured.md` skips structuring, cached `.summary.md` skips summarisation. So re-running an old URL after, say, prompt changes only redoes the affected stage — delete just that file (e.g. `data/transcripts/<id>.summary.md`) to force one stage.
- **Whisper device**: tries CUDA first if `torch.cuda.is_available()`; on any load failure falls back to CPU. CPU works but is much slower (think real-time playback speed on `medium`). Whisper model defaults to `medium`; change in `backend/app/transcriber.py` (`_model_name`).
- **Structurer chunking**: long transcripts are split at sentence boundaries into ~5k-word chunks (`TARGET_CHUNK_WORDS` in `structurer.py`) so each Claude call stays well within the output window and surfaces per-chunk progress.
- **Resilience layer** (`backend/app/retry.py` plus per-stage timeouts):
  - Each `claude` call has a hard timeout — 10 min per Sonnet chunk, 15 min per Opus summary. On timeout the subprocess is `kill()`'d.
  - Up to 3 attempts per call, with 30 s / 90 s backoff between them. Retries surface in the job's `stage_label` as `… (retry 2/3)`.
  - yt-dlp uses 10 whole-download retries, 10 fragment retries, 5 extractor retries, 30 s socket timeout, exponential backoff.
- **The `claude` CLI** is invoked with `--system-prompt` (replaces the default — also suppresses dynamic prompt sections like cwd / git status / memory paths), `--tools ""` (no tools, no permission prompts), `--no-session-persistence`, `--disable-slash-commands`. `--bare` is added when `ANTHROPIC_API_KEY` is set (see Authentication).
- **Restart semantics** (handled by `JobStore.recover_interrupted()` in lifespan): `queued` jobs are re-submitted to the worker automatically; jobs that were mid-stream (`downloading`/`transcribing`/`structuring`/`summarizing`) when the process died are marked `failed` with the error `"Interrupted by server restart"`. Re-submit the URL to retry — cache hits make it cheap.
- **Duplicate cleanup**: on every startup the store also de-duplicates rows that point to the same URL, keeping the most-complete one and merging tags from the rest.
