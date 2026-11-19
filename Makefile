# Convenience wrappers around the standalone uv-run scripts.
# All targets work on Linux, macOS, WSL, and Git Bash on Windows.

.PHONY: install dev backend frontend build test doctor wipe clean help

help:
	@echo "Available targets:"
	@echo "  make install    Install backend (auto-detects GPU/CPU) + frontend"
	@echo "  make doctor     Check prerequisites (uv, node, ffmpeg, claude CLI, GPU)"
	@echo "  make dev        Run backend + frontend together (Ctrl+C stops both)"
	@echo "  make backend    Run backend only"
	@echo "  make frontend   Run frontend only"
	@echo "  make build      Build the frontend into frontend/dist"
	@echo "  make test       Run the backend tests"
	@echo "  make wipe       Delete all runtime data (audio, transcripts, db)"
	@echo "  make clean      Delete venv + node_modules + caches"

install:
	uv run scripts/install.py

dev:
	uv run scripts/dev.py

backend:
	uv run scripts/dev.py --backend

frontend:
	uv run scripts/dev.py --frontend

build:
	cd frontend && npm run build

test:
	cd backend && uv run pytest -q

doctor:
	uv run scripts/doctor.py

wipe:
	rm -rf data/

clean:
	rm -rf backend/.venv frontend/node_modules backend/__pycache__ backend/app/__pycache__ frontend/dist
