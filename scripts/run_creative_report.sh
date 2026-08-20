#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/TikTok_创意明细配置.local.md"

if [[ ! -f "$CONFIG_FILE" ]]; then
  print -u2 "缺少本机配置：$CONFIG_FILE"
  print -u2 "请先让 Codex 调用 load_workspace_dependencies，并运行 scripts/init_local_config.sh。"
  exit 64
fi

config_value() {
  /usr/bin/awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$CONFIG_FILE"
}

export TIKTOK_ARTIFACT_NODE="$(config_value TIKTOK_ARTIFACT_NODE)"
ARTIFACT_NODE_MODULES="$(config_value TIKTOK_ARTIFACT_NODE_MODULES)"
export TIKTOK_OUTPUT_FILE="$(config_value TIKTOK_OUTPUT_FILE)"
export TIKTOK_METADATA_SOURCE_XLSX="$(config_value TIKTOK_METADATA_SOURCE_XLSX)"

if [[ -z "$TIKTOK_ARTIFACT_NODE" || ! -x "$TIKTOK_ARTIFACT_NODE" || -z "$ARTIFACT_NODE_MODULES" || ! -d "$ARTIFACT_NODE_MODULES" ]]; then
  print -u2 "本机配置中的 artifact-tool 路径无效。"
  exit 65
fi

if [[ ! -e "$ROOT_DIR/node_modules" ]]; then
  ln -s "$ARTIFACT_NODE_MODULES" "$ROOT_DIR/node_modules"
fi

export TIKTOK_ADVERTISER_ID="$(/usr/bin/security find-generic-password -s com.codex.tiktok-workflow.advertiser-id -a default -w)"
unset TIKTOK_APP_ID TIKTOK_APP_SECRET TIKTOK_ACCESS_TOKEN

if [[ -z "$TIKTOK_OUTPUT_FILE" ]]; then
  export TIKTOK_OUTPUT_FILE="output/TikTok_创意明细.xlsx"
fi
if [[ "$TIKTOK_OUTPUT_FILE" != /* ]]; then
  export TIKTOK_OUTPUT_FILE="$ROOT_DIR/$TIKTOK_OUTPUT_FILE"
fi

cd "$ROOT_DIR"
exec /usr/bin/python3 src/start_oauth_export.py
