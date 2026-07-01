#!/bin/zsh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR"

echo "Starting YQS dashboard..."
./start_dashboard.command &

echo "Starting DeerFlow web..."
./start_deerflow_web.command
