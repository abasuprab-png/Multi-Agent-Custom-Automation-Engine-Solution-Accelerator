#!/usr/bin/env bash
# Idempotent dependency setup for the Multi-Agent Custom Automation Engine.
# Runs after the repository is checked out. Safe to run repeatedly.
set -euo pipefail

# Install uv (Python toolchain / package manager) if it is not already present.
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

echo "==> Backend: uv sync (pins CPython 3.11, installs FastAPI + agent framework)"
( cd src/backend && uv sync --frozen )

echo "==> MCP server: uv sync (with dev extra so pytest is available)"
( cd src/mcp_server && uv sync --frozen --extra dev )

echo "==> Frontend Python server: uv sync"
( cd src/App && uv sync --frozen )

echo "==> Frontend Node dependencies: npm ci"
( cd src/App && npm ci )

echo "Setup complete."
