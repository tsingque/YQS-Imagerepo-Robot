#!/bin/zsh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${DEERFLOW_REPO_DIR:-}" ] && [ -d "$PROJECT_DIR/deer-flow/.git" ]; then
  DEERFLOW_REPO_DIR="$PROJECT_DIR/deer-flow"
else
  DEERFLOW_REPO_DIR="${DEERFLOW_REPO_DIR:-$PROJECT_DIR/deer-flow-web}"
fi
DEERFLOW_REPO_URL="${DEERFLOW_REPO_URL:-https://github.com/bytedance/deer-flow.git}"
DEERFLOW_WEB_URL="${DEERFLOW_WEB_URL:-http://127.0.0.1:2026}"

cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found. Please install Docker Desktop first."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running, or this terminal cannot access Docker."
  echo "Please start Docker Desktop and run this script again."
  exit 1
fi

if [ ! -d "$DEERFLOW_REPO_DIR/.git" ]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "git was not found. Please install git first."
    exit 1
  fi
  echo "Full DeerFlow web repo was not found."
  echo "Cloning: $DEERFLOW_REPO_URL"
  echo "Target:  $DEERFLOW_REPO_DIR"
  git clone "$DEERFLOW_REPO_URL" "$DEERFLOW_REPO_DIR"
fi

cd "$DEERFLOW_REPO_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp ".env.example" ".env"
  echo "Created DeerFlow .env from .env.example."
  echo "Please fill model keys and Feishu/Lark settings in:"
  echo "$DEERFLOW_REPO_DIR/.env"
fi

echo "Starting DeerFlow web with Docker..."
echo "Repo: $DEERFLOW_REPO_DIR"

if [ -f "Makefile" ] && grep -q "^docker-start:" "Makefile"; then
  make docker-start
elif [ -f "docker/docker-compose.yaml" ]; then
  docker compose -f docker/docker-compose.yaml up -d --build
elif [ -f "docker/docker-compose.yml" ]; then
  docker compose -f docker/docker-compose.yml up -d --build
elif [ -f "docker-compose.yaml" ]; then
  docker compose -f docker-compose.yaml up -d --build
elif [ -f "docker-compose.yml" ]; then
  docker compose -f docker-compose.yml up -d --build
else
  echo "Could not find DeerFlow Docker startup files."
  echo "Expected Makefile docker-start or docker-compose yaml."
  exit 1
fi

echo "DeerFlow web should be available at:"
echo "$DEERFLOW_WEB_URL"
open "$DEERFLOW_WEB_URL" >/dev/null 2>&1 || true
