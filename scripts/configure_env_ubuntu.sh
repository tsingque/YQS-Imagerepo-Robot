#!/usr/bin/env bash
set -euo pipefail

# Web-based .env configurator for Ubuntu 24.04 workstations.
# Run from the project root:
#   bash scripts/configure_env_ubuntu.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 $PYTHON_BIN，请先安装 Python 3："
  echo "  sudo apt update && sudo apt install -y python3"
  exit 1
fi

exec "$PYTHON_BIN" scripts/configure_env_web.py
