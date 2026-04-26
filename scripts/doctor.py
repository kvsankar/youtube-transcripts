#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Pre-flight check.

  uv run scripts/doctor.py

Verifies every prerequisite the app needs at runtime: uv, node/npm,
ffmpeg, the claude CLI, GPU presence, and the Anthropic auth path.
Exits non-zero if any *required* check fails.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    cmd_version, fail, has_command, has_nvidia_gpu, header, ok, warn,
)


def check_required(label: str, cmd: str) -> bool:
    if has_command(cmd):
        v = cmd_version(cmd) or "(version unknown)"
        ok(f"{label}: {v}")
        return True
    fail(f"{label}: not found on PATH ({cmd!r})")
    return False


def check_optional(label: str, cmd: str, why: str) -> bool:
    if has_command(cmd):
        v = cmd_version(cmd) or "(version unknown)"
        ok(f"{label}: {v}")
        return True
    warn(f"{label}: not found ({why})")
    return False


def main() -> int:
    header("Required toolchain")
    ok_all = True
    ok_all &= check_required("uv         ", "uv")
    ok_all &= check_required("git        ", "git")
    ok_all &= check_required("node       ", "node")
    ok_all &= check_required("npm        ", "npm")
    ok_all &= check_required("ffmpeg     ", "ffmpeg")

    header("Anthropic auth (need ONE of these)")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_cli = has_command("claude")
    if has_key:
        ok("ANTHROPIC_API_KEY is set — claude CLI will run with --bare")
    if has_cli:
        v = cmd_version("claude") or "(version unknown)"
        ok(f"claude CLI: {v}")
    if not has_cli and not has_key:
        fail("Neither ANTHROPIC_API_KEY nor `claude` CLI is available.")
        fail("Install the CLI (`npm i -g @anthropic-ai/claude-code` then `claude login`)")
        fail("OR export ANTHROPIC_API_KEY=...")
        ok_all = False
    elif not has_cli and has_key:
        fail("ANTHROPIC_API_KEY is set but the `claude` CLI is missing — install it.")
        ok_all = False

    header("GPU / acceleration (optional — falls back to CPU)")
    if has_nvidia_gpu():
        ok("NVIDIA GPU detected via nvidia-smi")
    else:
        warn("No NVIDIA GPU detected -> Whisper will run on CPU (much slower)")

    header("Result")
    if ok_all:
        ok("All required checks passed.")
        return 0
    fail("One or more required checks failed. Address the items above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
