# TikTok 创意明细导出

这个项目让 Codex 在 macOS 上完成一次可验证的 TikTok GMV Max 创意明细导出：授权后只调用只读接口，生成一个 XLSX，不生成 CSV。

默认拉取最近 7 个完整自然日（不含今天），输出到 `output/TikTok_创意明细.xlsx`。授权、接口或工作簿生成失败时，已有 XLSX 不会被覆盖。

## 给同事的使用方式

把下面这段话和仓库链接一起发给同事；他只需要把它交给本机 Codex：

```text
请按仓库的 AGENTS.md 操作，不要把任何凭据提交到 Git。先用 Codex 的 load_workspace_dependencies 找到 bundled Node 和 node_modules 路径，再运行：
scripts/init_local_config.sh <node路径> <node_modules路径>
随后运行 scripts/save_tiktok_credentials_to_keychain.sh，把我提供的 App ID、App Secret、Advertiser ID 只写入 macOS Keychain。最后运行 scripts/run_creative_report.sh，打开终端显示的本机 OAuth 链接完成授权。确认 output/TikTok_创意明细.xlsx 已生成，并报告日期范围、行数、未能获取的只读字段权限和验证结果；不要上传本机配置、输出文件、Token 或 Secret。
```

首次使用需要由拥有广告账号权限的 TikTok for Business 用户在浏览器完成 OAuth。每次手动导出会重新授权；本项目不在文件或 Git 中持久化 Access Token。

## 本机配置与凭据边界

运行 `scripts/init_local_config.sh` 后，会生成未提交的 `TikTok_创意明细配置.local.md`。它只保存本机 artifact-tool 运行时路径和输出文件位置，且被 `.gitignore` 排除。

App ID、App Secret、Advertiser ID 由 `scripts/save_tiktok_credentials_to_keychain.sh` 写入当前 macOS 用户的 Keychain。配置 Markdown、输出目录、Node 运行时软链接和 SDK 本地副本都不会上传到 GitHub。

## 产出字段

工作簿只有一个 `创意明细` sheet，字段顺序固定为：

1. 创意素材
2. 作品 ID
3. 商品名称
4. 商品 ID
5. TikTok 账号
6. 授权类型
7. 探索状态
8. 发布时间
9. 广告计划名称
10. 成本
11. SKU 订单数
12. 平均下单成本
13. 总收入
14. 商品广告曝光数
15. 商品广告点击数
16. 商品广告点击率
17. 广告转化率
18. 广告视频播放达 2 秒播放率
19. 广告视频播放达 6 秒播放率
20. 广告视频播放达 25% 播放率
21. 广告视频播放达 50% 播放率
22. 广告视频播放达 75% 播放率
23. 广告视频完播率

嵌套 JSON 会拆成独立字段。若当前 TikTok 应用未获商品读取权限，`商品名称` 保持空白，但其余可读取字段仍会生成。

## 开发与验证

运行全部离线测试：

```zsh
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

测试使用模拟 API，不会访问 TikTok，也不会读取 Keychain。工作簿使用 `@oai/artifact-tool` 生成，并在写入正式文件前检查公式错误。

涉及 TikTok Business API 的后续修改，先查看官方 [TikTok Business API SDK](https://github.com/tiktok/tiktok-business-api-sdk)。如需要本地参考副本，可克隆到被忽略的 `tiktok-business-api-sdk/`，不要提交该目录。
