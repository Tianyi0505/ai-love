#!/bin/bash
# 发布 Nacos 配置

set -e

require_env() {
  local name
  local missing=()
  for name in "$@"; do
    if [ -z "${!name:-}" ]; then
      missing+=("$name")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "未配置必填环境变量: ${missing[*]}" >&2
    exit 1
  fi
}

require_env \
  AILOVE_NACOS_ADDRS \
  AILOVE_NACOS_USER \
  AILOVE_NACOS_PASSWORD \
  AILOVE_NACOS_GROUP \
  AILOVE_NACOS_HTTP_TIMEOUT_SEC \
  AILOVE_AI_ID \
  AILOVE_AGENT_CONFIG_FILE

NACOS_ADDR="$AILOVE_NACOS_ADDRS"
NACOS_USER="$AILOVE_NACOS_USER"
NACOS_PASSWORD="$AILOVE_NACOS_PASSWORD"
NACOS_GROUP="$AILOVE_NACOS_GROUP"
NACOS_HTTP_TIMEOUT_SEC="$AILOVE_NACOS_HTTP_TIMEOUT_SEC"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

echo "=== 登录 Nacos ($NACOS_ADDR) ==="
TOKEN=$(curl -s -m "$NACOS_HTTP_TIMEOUT_SEC" -X POST "http://${NACOS_ADDR}/nacos/v1/auth/login" \
  -d "username=${NACOS_USER}&password=${NACOS_PASSWORD}")
ACCESS=$(echo "$TOKEN" | grep -o '"accessToken":"[^"]*"' | cut -d'"' -f4)
if [ -z "$ACCESS" ]; then
  echo "登录失败: $TOKEN"
  exit 1
fi
echo "登录成功"

publish() {
  local data_id="$1"
  local content="$2"
  curl -fsS -m "$NACOS_HTTP_TIMEOUT_SEC" -X POST "http://${NACOS_ADDR}/nacos/v1/cs/configs" \
    -H "Authorization: Bearer ${ACCESS}" \
    -d "dataId=${data_id}" -d "group=${NACOS_GROUP}" --data-urlencode "content=${content}" > /dev/null
  echo "  [OK] ${data_id}"
}

render_config() {
  local path="$1"
  local content
  local placeholder
  local name
  content=$(<"$path")
  while read -r placeholder; do
    [ -z "$placeholder" ] && continue
    name="${placeholder#__}"
    name="${name%__}"
    require_env "$name"
    content="${content//"$placeholder"/"${!name}"}"
  done < <(grep -oE '__[A-Z][A-Z0-9_]+__' "$path" | sort -u)
  printf '%s' "$content"
}

publish_file() {
  local data_id="$1"
  local path="$2"
  publish "$data_id" "$(render_config "$path")"
}

require_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "缺少必填配置文件: ${path}" >&2
    exit 1
  fi
}

echo "=== 写入配置 ==="

# 发布服务配置
for service_name in gateway director ai-agent tts stream memory avatar extension-host; do
  publish_file "service.${service_name}" "${SCRIPT_DIR}/nacos/service.${service_name}.yaml"
done

# 发布 AI 定义
publish_file "ailove.config" "${SCRIPT_DIR}/nacos/ailove.config.yaml"
publish_file "agent.catalog" "${SCRIPT_DIR}/nacos/agent.catalog.yaml"
AGENT_CONFIG_PATH="${SCRIPT_DIR}/${AILOVE_AGENT_CONFIG_FILE}"
require_file "$AGENT_CONFIG_PATH"
publish_file "agent.${AILOVE_AI_ID}" "$AGENT_CONFIG_PATH"

# 发布导演配置
publish_file "director.session-default" "${SCRIPT_DIR}/nacos/director.session-default.yaml"

echo "=== 配置初始化完成 ==="
