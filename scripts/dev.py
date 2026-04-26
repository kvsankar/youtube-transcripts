#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Run backend + frontend together with merged, prefixed output.

  uv run scripts/dev.py                  # both
  uv run scripts/dev.py --backend        # backend only
  uv run scripts/dev.py --frontend       # frontend only
  uv run scripts/dev.py --backend-port 9000

Ctrl+C terminates both processes cleanly.
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BACKEND_DIR, FRONTEND_DIR, fail, header, info, ok  # noqa: E402


# ANSI colors per process for readable interleaved output
_PALETTE = {
    "backend":  "\033[36m",  # cyan
    "frontend": "\033[35m",  # magenta
}
_RESET = "\033[0m"
_USE_COLOR = sys.stdout.isatty()


class Tailer(threading.Thread):
    """Read a process's stdout line-by-line and print with a prefix."""

    def __init__(self, name: str, proc: subprocess.Popen) -> None:
        super().__init__(daemon=True, name=f"tail-{name}")
        self.name_label = name
        self.proc = proc
        self.color = _PALETTE.get(name, "")

    def run(self) -> None:
        prefix_color = self.color if _USE_COLOR else ""
        prefix_reset = _RESET if _USE_COLOR else ""
        prefix = f"{prefix_color}[{self.name_label:8}]{prefix_reset} "
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            sys.stdout.write(prefix + line)
            sys.stdout.flush()


def spawn(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    info(f"starting {name}: {' '.join(cmd)}  (cwd={cwd})")
    # Strip VIRTUAL_ENV from the child env so an outer `uv run --script`
    # context doesn't confuse the child's project venv detection.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,                  # line-buffered
        text=True,
        env=env,
        # On Windows, give each child its own process group so Ctrl+C in
        # the parent doesn't propagate uncontrollably; we'll send the
        # signal explicitly.
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        ),
    )


def stop(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return
    info(f"stopping {name} (pid {proc.pid})…")
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", action="store_true",
                        help="Run backend only (skip frontend)")
    parser.add_argument("--frontend", action="store_true",
                        help="Run frontend only (skip backend)")
    parser.add_argument("--backend-port", type=int, default=8000)
    args = parser.parse_args()

    run_backend = args.backend or not args.frontend
    run_frontend = args.frontend or not args.backend

    procs: list[tuple[str, subprocess.Popen]] = []
    tailers: list[Tailer] = []

    header("Starting dev servers")
    if run_backend:
        if not (BACKEND_DIR / ".venv").exists():
            fail("backend/.venv not found. Run: uv run scripts/install.py")
            return 1
        bp = spawn(
            "backend",
            ["uv", "run", "uvicorn", "app.main:app",
             "--port", str(args.backend_port), "--log-level", "info"],
            cwd=BACKEND_DIR,
        )
        procs.append(("backend", bp))
        tailers.append(Tailer("backend", bp))

    if run_frontend:
        if not (FRONTEND_DIR / "node_modules").exists():
            fail("frontend/node_modules not found. Run: uv run scripts/install.py")
            return 1
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        fp = spawn("frontend", [npm_cmd, "run", "dev"], cwd=FRONTEND_DIR)
        procs.append(("frontend", fp))
        tailers.append(Tailer("frontend", fp))

    if not procs:
        fail("Nothing to run.")
        return 1

    for t in tailers:
        t.start()

    ok("All processes started. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(0.5)
            for name, p in procs:
                if p.poll() is not None:
                    fail(f"{name} exited with code {p.returncode}; shutting down others.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print()
        info("Caught interrupt — shutting down.")
        for name, p in procs:
            stop(p, name)
        # Give tailers a moment to drain remaining output
        for t in tailers:
            t.join(timeout=2)

    bad = [code for _, p in procs if (code := p.returncode) not in (0, None)]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
