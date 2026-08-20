#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/TikTok_创意明细配置.local.md"

if [[ $# -ne 2 ]]; then
  print -u2 "用法：scripts/init_local_config.sh <artifact-node-path> <artifact-node-modules-path>"
  exit 64
fi

NODE_PATH="$1"
NODE_MODULES_PATH="$2"
if [[ ! -x "$NODE_PATH" || ! -d "$NODE_MODULES_PATH" ]]; then
  print -u2 "artifact-tool 的 Node 或 node_modules 路径无效。"
  exit 65
fi

umask 077
{
  print '# TikTok 创意明细本机配置'
  print ''
  print '此文件只保存在本机，已被 `.gitignore` 排除。不要在这里填入 App Secret、Access Token 或 OAuth 授权码；这些值应通过 macOS Keychain 保存。'
  print ''
  print '```ini'
  print "TIKTOK_ARTIFACT_NODE=$NODE_PATH"
  print "TIKTOK_ARTIFACT_NODE_MODULES=$NODE_MODULES_PATH"
  print 'TIKTOK_OUTPUT_FILE=output/TikTok_创意明细.xlsx'
  print '```'
} > "$CONFIG_FILE"

print "已创建本机配置：$CONFIG_FILE"
