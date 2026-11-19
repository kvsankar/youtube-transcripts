#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""One-shot installer.

  uv run scripts/install.py            # auto-detect GPU vs CPU
  uv run scripts/install.py --gpu      # force CUDA 12.1 wheels
  uv run scripts/install.py --cpu      # force CPU-only wheels

Picks the right torch extra (gpu/cpu), runs `uv sync` for the backend,
`npm install` for the frontend, then runs the doctor for a final check.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    BACKEND_DIR, FRONTEND_DIR, fail, has_command, has_nvidia_gpu,
    header, info, ok, run, warn,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--gpu", action="store_true", help="Force CUDA 12.1 torch wheels")
    g.add_argument("--cpu", action="store_true", help="Force CPU-only torch wheels")
    parser.add_argument(
        "--no-frontend", action="store_true",
        help="Skip frontend npm install (backend-only setup)",
    )
    args = parser.parse_args()

    # 1. Verify the absolute prerequisites
    header("Checking prerequisites")
    missing = []
    for cmd in ("uv", "git"):
        if has_command(cmd):
            ok(f"{cmd} found")
        else:
            fail(f"{cmd} not found on PATH")
            missing.append(cmd)
    if not args.no_frontend:
        for cmd in ("node", "npm"):
            if has_command(cmd):
                ok(f"{cmd} found")
            else:
                fail(f"{cmd} not found on PATH")
                missing.append(cmd)
    if missing:
        fail(f"Install missing prerequisites first: {', '.join(missing)}")
        return 1

    # 2. Decide on the torch extra
    header("Choosing torch wheel variant")
    if args.gpu:
        extra = "gpu"
        info("Forced via --gpu")
    elif args.cpu:
        extra = "cpu"
        info("Forced via --cpu")
    elif has_nvidia_gpu():
        extra = "gpu"
        ok("NVIDIA GPU detected -> installing CUDA 12.1 torch wheels (~5.2 GB venv)")
    else:
        extra = "cpu"
        info("No NVIDIA GPU detected -> installing CPU torch wheels (~1.2 GB venv)")
        info("(Override with --gpu if you have CUDA drivers but nvidia-smi is unavailable.)")

    # 3. Backend sync
    header(f"Installing backend dependencies (--extra {extra})")
    rc = run(["uv", "sync", "--extra", extra], cwd=BACKEND_DIR)
    if rc != 0:
        fail("Backend uv sync failed.")
        return rc
    ok("Backend installed.")

    # 4. Frontend install
    if not args.no_frontend:
        header("Installing frontend dependencies")
        rc = run(["npm", "install"], cwd=FRONTEND_DIR)
        if rc != 0:
            fail("Frontend npm install failed.")
            return rc
        ok("Frontend installed.")

    # 5. Run doctor for the final picture
    doctor = Path(__file__).with_name("doctor.py")
    if doctor.exists():
        header("Health check")
        run(["uv", "run", "--script", str(doctor)])

    header("Next steps")
    info("Start both servers with: uv run scripts/dev.py")
    info("Or individually:")
    info("  Backend  : (cd backend && uv run uvicorn app.main:app --reload --port 8765)")
    info("  Frontend : (cd frontend && npm run dev)")
    if extra == "gpu" and not has_nvidia_gpu():
        warn("You forced --gpu but nvidia-smi isn't available — runtime will fall back to CPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
