#!/bin/zsh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${YQS_DASHBOARD_HOST:-127.0.0.1}"
PORT="${YQS_DASHBOARD_PORT:-8765}"
OPEN_HOST="$HOST"
if [ "$OPEN_HOST" = "0.0.0.0" ]; then
  OPEN_HOST="127.0.0.1"
fi
URL="http://${OPEN_HOST}:${PORT}"

cd "$PROJECT_DIR"

export DEER_FLOW_PROJECT_ROOT="$PROJECT_DIR"
export DEER_FLOW_HOME="$PROJECT_DIR/.deer-flow"
export PYTHONPATH="$PROJECT_DIR:$PROJECT_DIR/python:${PYTHONPATH:-}"
export YQS_DEERFLOW_MODE="${YQS_DEERFLOW_MODE:-agent}"
export YQS_DEERFLOW_MODEL="${YQS_DEERFLOW_MODEL:-glm-agent}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Please install Python 3 first."
  exit 1
fi

if [ ! -f "python/server.py" ]; then
  echo "Missing python/server.py. Please run this script from the project folder."
  exit 1
fi

if [ ! -f "config.yaml" ]; then
  echo "Missing config.yaml. DeerFlow cannot be initialized."
  exit 1
fi

if [ ! -d "deer-flow" ]; then
  echo "Missing deer-flow/. Please keep the DeerFlow package in the project folder."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "Notice: .env was not found. DeerFlow/GLM/Feishu will use defaults or fail gracefully."
  echo "        Copy .env.example to .env and fill GLM_API_KEY for real agent execution."
fi

echo "Preparing YQS embedded agent runtime..."
python3 -B python/deerflow_runner.py --status >/dev/null
echo "YQS project root: $DEER_FLOW_PROJECT_ROOT"
echo "YQS embedded agent mode: $YQS_DEERFLOW_MODE"

if nc -z "$OPEN_HOST" "$PORT" >/dev/null 2>&1; then
  echo "Dashboard is already running:"
  echo "$URL"
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS "$URL/api/agent-status" >/dev/null 2>&1; then
      echo "YQS embedded agent API is available: $URL/api/agent-status"
    else
      echo "Warning: dashboard port is occupied, but the embedded agent API did not respond."
      echo "         Stop the old dashboard process and run this script again."
    fi
  fi
  open "$URL" >/dev/null 2>&1 || true
  exit 0
fi

echo "Starting material dashboard..."
echo "YQS embedded agent API: ${URL}/api/agent-status"
echo "$URL"

(
  sleep 1
  open "$URL" >/dev/null 2>&1 || true
) &

python3 -B python/server.py
