#!/usr/bin/env bash
set -euo pipefail

# Interactive .env configurator for Ubuntu 24.04 workstations.
# Run from the project root:
#   bash scripts/configure_env_ubuntu.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

timestamp() {
  date +"%Y%m%d_%H%M%S"
}

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "${line:0:1}" == "#" || "$line" != *"="* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    value="${value%$'\r'}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    export "$key=$value"
  done < "$file"
}

mask_value() {
  local value="${1:-}"
  if [[ -z "$value" ]]; then
    printf "<empty>"
  elif (( ${#value} <= 8 )); then
    printf "********"
  else
    printf "%s…%s" "${value:0:4}" "${value: -4}"
  fi
}

prompt_value() {
  local var="$1"
  local label="$2"
  local default="${3:-}"
  local secret="${4:-0}"
  local value=""

  if [[ "$secret" == "1" ]]; then
    printf "%s [%s]: " "$label" "$(mask_value "$default")"
    IFS= read -rs value || true
    printf "\n"
  else
    printf "%s [%s]: " "$label" "${default:-<empty>}"
    IFS= read -r value || true
  fi

  if [[ -z "$value" ]]; then
    printf -v "$var" "%s" "$default"
  else
    printf -v "$var" "%s" "$value"
  fi
}

random_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

write_env_file() {
  local file="$1"
  local content="$2"
  mkdir -p "$(dirname "$file")"
  if [[ -f "$file" ]]; then
    cp "$file" "${file}.bak.$(timestamp)"
  fi
  printf "%s\n" "$content" > "$file"
  chmod 600 "$file"
}

echo "YQS Material Repository - Ubuntu 24.04 .env 配置向导"
echo "项目目录: $ROOT_DIR"
echo
echo "说明：直接回车会保留括号中的默认值；密钥输入不会回显。"
echo

load_env_file ".env"
load_env_file "deer-flow/.env"
load_env_file "deer-flow/frontend/.env"

DEFAULT_AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-$(random_secret)}"
DEFAULT_INTERNAL_TOKEN="${DEER_FLOW_INTERNAL_AUTH_TOKEN:-$(random_secret)}"

echo "== 1/4 AI 识图配置 =="
prompt_value AI_PROVIDER "AI_PROVIDER，识图供应商 glm/kimi" "${AI_PROVIDER:-kimi}"
prompt_value GLM_API_KEY "GLM_API_KEY" "${GLM_API_KEY:-}" 1
prompt_value GLM_MODEL "GLM_MODEL" "${GLM_MODEL:-glm-5v-turbo}"
prompt_value GLM_API_BASE "GLM_API_BASE" "${GLM_API_BASE:-https://open.bigmodel.cn/api/paas/v4/chat/completions}"
prompt_value GLM_OPENAI_BASE_URL "GLM_OPENAI_BASE_URL" "${GLM_OPENAI_BASE_URL:-https://open.bigmodel.cn/api/paas/v4}"
prompt_value GLM_TIMEOUT_SECONDS "GLM_TIMEOUT_SECONDS" "${GLM_TIMEOUT_SECONDS:-120}"
prompt_value GLM_BATCH_INTERVAL_SECONDS "GLM_BATCH_INTERVAL_SECONDS" "${GLM_BATCH_INTERVAL_SECONDS:-0.5}"
prompt_value KIMI_API_KEY "KIMI_API_KEY / MOONSHOT API Key" "${KIMI_API_KEY:-${MOONSHOT_API_KEY:-}}" 1
prompt_value KIMI_MODEL "KIMI_MODEL" "${KIMI_MODEL:-kimi-k2.6}"
prompt_value KIMI_API_BASE "KIMI_API_BASE" "${KIMI_API_BASE:-https://api.moonshot.cn/v1/chat/completions}"
prompt_value KIMI_TIMEOUT_SECONDS "KIMI_TIMEOUT_SECONDS" "${KIMI_TIMEOUT_SECONDS:-120}"
prompt_value AI_TOKEN_WARN_TOTAL "AI_TOKEN_WARN_TOTAL，0 表示不告警" "${AI_TOKEN_WARN_TOTAL:-0}"
echo

echo "== 2/4 YQS / 飞书多维表格配置 =="
prompt_value YQS_DEERFLOW_MODE "YQS_DEERFLOW_MODE，建议 direct" "${YQS_DEERFLOW_MODE:-direct}"
prompt_value YQS_DEERFLOW_MODEL "YQS_DEERFLOW_MODEL" "${YQS_DEERFLOW_MODEL:-glm-agent}"
prompt_value YQS_DASHBOARD_TOKEN "YQS_DASHBOARD_TOKEN，Dashboard 写操作口令" "${YQS_DASHBOARD_TOKEN:-}" 1
prompt_value YQS_DASHBOARD_HOST "YQS_DASHBOARD_HOST" "${YQS_DASHBOARD_HOST:-127.0.0.1}"
prompt_value YQS_DASHBOARD_PORT "YQS_DASHBOARD_PORT" "${YQS_DASHBOARD_PORT:-8765}"
prompt_value YQS_AI_TIMEOUT_SECONDS "YQS_AI_TIMEOUT_SECONDS" "${YQS_AI_TIMEOUT_SECONDS:-120}"
prompt_value FEISHU_APP_ID "FEISHU_APP_ID" "${FEISHU_APP_ID:-}" 1
prompt_value FEISHU_APP_SECRET "FEISHU_APP_SECRET" "${FEISHU_APP_SECRET:-}" 1
prompt_value FEISHU_RECEIVE_ID_TYPE "FEISHU_RECEIVE_ID_TYPE" "${FEISHU_RECEIVE_ID_TYPE:-chat_id}"
prompt_value FEISHU_RECEIVE_ID "FEISHU_RECEIVE_ID，可留空" "${FEISHU_RECEIVE_ID:-${FEISHU_CHAT_ID:-}}"
prompt_value FEISHU_NOTIFY_ON_RECOGNITION "FEISHU_NOTIFY_ON_RECOGNITION" "${FEISHU_NOTIFY_ON_RECOGNITION:-true}"
prompt_value FEISHU_BITABLE_APP_TOKEN "FEISHU_BITABLE_APP_TOKEN" "${FEISHU_BITABLE_APP_TOKEN:-}" 1
prompt_value FEISHU_BITABLE_TABLE_ID "FEISHU_BITABLE_TABLE_ID" "${FEISHU_BITABLE_TABLE_ID:-}"
prompt_value FEISHU_BITABLE_VIEW_ID "FEISHU_BITABLE_VIEW_ID" "${FEISHU_BITABLE_VIEW_ID:-}"
prompt_value FEISHU_BITABLE_FIELD_NAME "FEISHU_BITABLE_FIELD_NAME" "${FEISHU_BITABLE_FIELD_NAME:-名字}"
prompt_value FEISHU_BITABLE_FIELD_DESCRIPTION "FEISHU_BITABLE_FIELD_DESCRIPTION" "${FEISHU_BITABLE_FIELD_DESCRIPTION:-描述}"
prompt_value FEISHU_BITABLE_FIELD_FILE "FEISHU_BITABLE_FIELD_FILE" "${FEISHU_BITABLE_FIELD_FILE:-文件}"
prompt_value FEISHU_BITABLE_FIELD_SOURCE "FEISHU_BITABLE_FIELD_SOURCE" "${FEISHU_BITABLE_FIELD_SOURCE:-来源}"
prompt_value FEISHU_BITABLE_FIELD_USABLE "FEISHU_BITABLE_FIELD_USABLE" "${FEISHU_BITABLE_FIELD_USABLE:-是否可用}"
prompt_value FEISHU_BITABLE_MAX_RECORDS "FEISHU_BITABLE_MAX_RECORDS" "${FEISHU_BITABLE_MAX_RECORDS:-20000}"
prompt_value FEISHU_BITABLE_WARN_RATIOS "FEISHU_BITABLE_WARN_RATIOS" "${FEISHU_BITABLE_WARN_RATIOS:-0.5,0.75,0.9}"
prompt_value YQS_BITABLE_BATCH_LIMIT "YQS_BITABLE_BATCH_LIMIT" "${YQS_BITABLE_BATCH_LIMIT:-100}"
echo

echo "== 3/4 DeerFlow 后端模型与认证配置 =="
prompt_value DEEPSEEK_API_KEY "DEEPSEEK_API_KEY，DeerFlow 普通聊天模型" "${DEEPSEEK_API_KEY:-}" 1
prompt_value SERPER_API_KEY "SERPER_API_KEY，可留空" "${SERPER_API_KEY:-}" 1
prompt_value TAVILY_API_KEY "TAVILY_API_KEY，可留空" "${TAVILY_API_KEY:-}" 1
prompt_value JINA_API_KEY "JINA_API_KEY，可留空" "${JINA_API_KEY:-}" 1
prompt_value INFOQUEST_API_KEY "INFOQUEST_API_KEY，可留空" "${INFOQUEST_API_KEY:-}" 1
prompt_value GATEWAY_CORS_ORIGINS "GATEWAY_CORS_ORIGINS，可留空" "${GATEWAY_CORS_ORIGINS:-}"
prompt_value GATEWAY_ENABLE_DOCS "GATEWAY_ENABLE_DOCS" "${GATEWAY_ENABLE_DOCS:-true}"
prompt_value AUTH_JWT_SECRET "AUTH_JWT_SECRET" "$DEFAULT_AUTH_JWT_SECRET" 1
prompt_value DEER_FLOW_INTERNAL_AUTH_TOKEN "DEER_FLOW_INTERNAL_AUTH_TOKEN" "$DEFAULT_INTERNAL_TOKEN" 1
prompt_value DEER_FLOW_AUTH_DISABLED "DEER_FLOW_AUTH_DISABLED，生产建议 0" "${DEER_FLOW_AUTH_DISABLED:-0}"
echo

echo "== 4/4 前端/SSR 配置 =="
prompt_value NEXT_PUBLIC_BACKEND_BASE_URL "NEXT_PUBLIC_BACKEND_BASE_URL，统一 nginx 留空" "${NEXT_PUBLIC_BACKEND_BASE_URL:-}"
prompt_value NEXT_PUBLIC_LANGGRAPH_BASE_URL "NEXT_PUBLIC_LANGGRAPH_BASE_URL，统一 nginx 留空" "${NEXT_PUBLIC_LANGGRAPH_BASE_URL:-}"
prompt_value DEER_FLOW_INTERNAL_GATEWAY_BASE_URL "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL" "${DEER_FLOW_INTERNAL_GATEWAY_BASE_URL:-http://gateway:8001}"
prompt_value DEER_FLOW_TRUSTED_ORIGINS "DEER_FLOW_TRUSTED_ORIGINS" "${DEER_FLOW_TRUSTED_ORIGINS:-http://localhost:2026,http://127.0.0.1:2026}"
echo

ROOT_ENV_CONTENT=$(cat <<EOF
AI_PROVIDER=$AI_PROVIDER
GLM_API_KEY=$GLM_API_KEY
GLM_MODEL=$GLM_MODEL
GLM_API_BASE=$GLM_API_BASE
GLM_OPENAI_BASE_URL=$GLM_OPENAI_BASE_URL
GLM_TIMEOUT_SECONDS=$GLM_TIMEOUT_SECONDS
GLM_BATCH_INTERVAL_SECONDS=$GLM_BATCH_INTERVAL_SECONDS

KIMI_API_KEY=$KIMI_API_KEY
KIMI_MODEL=$KIMI_MODEL
KIMI_API_BASE=$KIMI_API_BASE
KIMI_TIMEOUT_SECONDS=$KIMI_TIMEOUT_SECONDS
AI_TOKEN_WARN_TOTAL=$AI_TOKEN_WARN_TOTAL

YQS_DEERFLOW_MODE=$YQS_DEERFLOW_MODE
YQS_DEERFLOW_MODEL=$YQS_DEERFLOW_MODEL
YQS_DASHBOARD_TOKEN=$YQS_DASHBOARD_TOKEN
YQS_DASHBOARD_HOST=$YQS_DASHBOARD_HOST
YQS_DASHBOARD_PORT=$YQS_DASHBOARD_PORT
YQS_AI_TIMEOUT_SECONDS=$YQS_AI_TIMEOUT_SECONDS

FEISHU_APP_ID=$FEISHU_APP_ID
FEISHU_APP_SECRET=$FEISHU_APP_SECRET
FEISHU_RECEIVE_ID_TYPE=$FEISHU_RECEIVE_ID_TYPE
FEISHU_RECEIVE_ID=$FEISHU_RECEIVE_ID
FEISHU_NOTIFY_ON_RECOGNITION=$FEISHU_NOTIFY_ON_RECOGNITION

FEISHU_BITABLE_APP_TOKEN=$FEISHU_BITABLE_APP_TOKEN
FEISHU_BITABLE_TABLE_ID=$FEISHU_BITABLE_TABLE_ID
FEISHU_BITABLE_VIEW_ID=$FEISHU_BITABLE_VIEW_ID
FEISHU_BITABLE_FIELD_NAME=$FEISHU_BITABLE_FIELD_NAME
FEISHU_BITABLE_FIELD_DESCRIPTION=$FEISHU_BITABLE_FIELD_DESCRIPTION
FEISHU_BITABLE_FIELD_FILE=$FEISHU_BITABLE_FIELD_FILE
FEISHU_BITABLE_FIELD_SOURCE=$FEISHU_BITABLE_FIELD_SOURCE
FEISHU_BITABLE_FIELD_USABLE=$FEISHU_BITABLE_FIELD_USABLE
FEISHU_BITABLE_MAX_RECORDS=$FEISHU_BITABLE_MAX_RECORDS
FEISHU_BITABLE_WARN_RATIOS=$FEISHU_BITABLE_WARN_RATIOS
YQS_BITABLE_BATCH_LIMIT=$YQS_BITABLE_BATCH_LIMIT
EOF
)

DEER_ENV_CONTENT=$(cat <<EOF
SERPER_API_KEY=$SERPER_API_KEY
TAVILY_API_KEY=$TAVILY_API_KEY
JINA_API_KEY=$JINA_API_KEY
INFOQUEST_API_KEY=$INFOQUEST_API_KEY
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY

FEISHU_APP_ID=$FEISHU_APP_ID
FEISHU_APP_SECRET=$FEISHU_APP_SECRET

AUTH_JWT_SECRET=$AUTH_JWT_SECRET
DEER_FLOW_INTERNAL_AUTH_TOKEN=$DEER_FLOW_INTERNAL_AUTH_TOKEN
DEER_FLOW_AUTH_DISABLED=$DEER_FLOW_AUTH_DISABLED
DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=$DEER_FLOW_INTERNAL_GATEWAY_BASE_URL
DEER_FLOW_TRUSTED_ORIGINS=$DEER_FLOW_TRUSTED_ORIGINS
GATEWAY_CORS_ORIGINS=$GATEWAY_CORS_ORIGINS
GATEWAY_ENABLE_DOCS=$GATEWAY_ENABLE_DOCS
EOF
)

FRONTEND_ENV_CONTENT=$(cat <<EOF
NEXT_PUBLIC_BACKEND_BASE_URL=$NEXT_PUBLIC_BACKEND_BASE_URL
NEXT_PUBLIC_LANGGRAPH_BASE_URL=$NEXT_PUBLIC_LANGGRAPH_BASE_URL
DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=$DEER_FLOW_INTERNAL_GATEWAY_BASE_URL
DEER_FLOW_TRUSTED_ORIGINS=$DEER_FLOW_TRUSTED_ORIGINS
EOF
)

write_env_file ".env" "$ROOT_ENV_CONTENT"
write_env_file "deer-flow/.env" "$DEER_ENV_CONTENT"
write_env_file "deer-flow/frontend/.env" "$FRONTEND_ENV_CONTENT"

echo
echo "已写入："
echo "  $ROOT_DIR/.env"
echo "  $ROOT_DIR/deer-flow/.env"
echo "  $ROOT_DIR/deer-flow/frontend/.env"
echo
echo "下一步建议："
echo "  python3 python/setup_bitable.py       # 校验/创建多维表格"
echo "  cd deer-flow && make docker-start     # 启动 DeerFlow"
