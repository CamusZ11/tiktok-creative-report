#!/bin/zsh
set -euo pipefail

read 'app_id?TikTok App ID: '
read -s 'app_secret?TikTok App Secret: '
print
read 'advertiser_id?TikTok Advertiser ID: '

if [[ -z "$app_id" || -z "$app_secret" || -z "$advertiser_id" ]]; then
  print -u2 "App ID、App Secret 和 Advertiser ID 都不能为空。"
  exit 64
fi

/usr/bin/security add-generic-password -U -s com.codex.tiktok-workflow.app-id -a default -w "$app_id" >/dev/null
/usr/bin/security add-generic-password -U -s com.codex.tiktok-workflow.app-secret -a default -w "$app_secret" >/dev/null
/usr/bin/security add-generic-password -U -s com.codex.tiktok-workflow.advertiser-id -a default -w "$advertiser_id" >/dev/null
print "已将 TikTok 凭据写入当前 macOS 用户的 Keychain。"
