"""Tiny helpers shared by the standalone setup scripts."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Windows defaults stdout to cp1252 which can't print most non-ASCII chars.
# Reconfigure to UTF-8 so we can use whatever symbols we like in messages.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


# ---- pretty output ---------------------------------------------------------

# Disable colors when stdout isn't a tty (CI logs, redirected output).
_USE_COLOR = sys.stdout.isatty() and platform.system() != "Windows" or (
    sys.stdout.isatty() and "TERM" in __import__("os").environ
)


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def info(msg: str) -> None:
    print(_c("36", ">"), msg)


def ok(msg: str) -> None:
    print(_c("32", "[OK]"), msg)


def warn(msg: str) -> None:
    print(_c("33", "[WARN]"), msg)


def fail(msg: str) -> None:
    print(_c("31", "[FAIL]"), msg)


def header(msg: str) -> None:
    print()
    print(_c("1", msg))
    print(_c("2", "-" * len(msg)))


# ---- environment detection ------------------------------------------------

def has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def has_nvidia_gpu() -> bool:
    """Detect an NVIDIA GPU usable for CUDA. Conservative — false negatives
    are fine (user can override with --gpu). False positives are bad."""
    if not has_command("nvidia-smi"):
        return False
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def cmd_version(cmd: str, args: list[str] = ["--version"]) -> str | None:
    try:
        r = subprocess.run([cmd, *args], capture_output=True, text=True, timeout=10)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


# ---- subprocess runner ----------------------------------------------------

def run(cmd: list[str], cwd: Path | None = None, env_extra: dict | None = None) -> int:
    """Run a command, streaming output to the terminal.

    Resolves the command via shutil.which so Windows .cmd/.bat shims
    (npm, npx, etc.) work without shell=True.
    """
    import os
    resolved = shutil.which(cmd[0])
    if resolved is None:
        fail(f"command not found on PATH: {cmd[0]}")
        return 127
    full = [resolved, *cmd[1:]]
    info(f"$ {' '.join(cmd)}" + (f"   (in {cwd})" if cwd else ""))
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.call(full, cwd=str(cwd) if cwd else None, env=env)
