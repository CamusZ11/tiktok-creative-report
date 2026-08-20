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

首次使用需要由拥有广告账号权限的 TikTok for Business 用户在浏览器完成 OAuth。成功交换得到的 Marketing API 长期 Access Token 会写入当前 macOS 用户的 Keychain；后续手动或定时导出直接复用，不再每次打开浏览器。只有 Token 被撤销、失效或账号授权关系变化时才需要重新授权。

如需主动替换已保存的 Token，运行 `TIKTOK_FORCE_OAUTH=1 ./scripts/run_creative_report.sh`，再完成一次浏览器授权。日常运行不会把 App Secret 注入报表构建子进程。

## 本机配置与凭据边界

运行 `scripts/init_local_config.sh` 后，会生成未提交的 `TikTok_创意明细配置.local.md`。它只保存本机 artifact-tool 运行时路径和输出文件位置，且被 `.gitignore` 排除。

App ID、App Secret、Advertiser ID 和长期 Access Token 均保存在当前 macOS 用户的 Keychain。配置 Markdown、输出目录、Node 运行时软链接和 SDK 本地副本都不会上传到 GitHub。

如需补齐 API 当前不再返回的历史作品元数据，可在本机配置中填写 `TIKTOK_METADATA_SOURCE_XLSX`，指向已有的创意明细工作簿，或 TikTok Ads Manager 导出的 Creative Data 工作簿。构建器会按作品 ID 合并静态元数据，并继续复用上一份成功工作簿中已有的商品、授权与计划信息；探索状态不会从历史工作簿回填；本机源文件不会提交到 GitHub。

若目标 XLSX 已存在，构建器只重建其中的 `11_creative_daily_report`（或兼容旧版的 `创意明细`）Sheet，其他 Sheet 原样保留；整个临时工作簿通过检查后才原子替换正式文件。
刷新前请关闭目标 XLSX；检测到 Excel 的同目录锁文件时，任务会停止并保留上一份成功文件。

## 产出字段

工作簿只有一个 `创意明细` sheet，字段顺序固定为。报表按“日期 + 作品 ID”输出；每天独立请求 API，同日相同作品的重复原始行会汇总可加指标，探索状态取商品广告曝光最高的原始行，曝光相同再取成本最高的一行：

1. 日期
2. 创意素材
3. 作品 ID
4. 商品名称
5. 商品 ID
6. TikTok 账号
7. 授权类型
8. 探索状态
9. 发布时间
10. 广告计划名称
11. 成本
12. SKU 订单数
13. 平均下单成本
14. 总收入
15. 商品广告曝光数
16. 商品广告点击数
17. 商品广告点击率
18. 广告转化率
19. 广告视频播放达 2 秒播放率
20. 广告视频播放达 6 秒播放率
21. 广告视频播放达 25% 播放率
22. 广告视频播放达 50% 播放率
23. 广告视频播放达 75% 播放率
24. 广告视频完播率

嵌套 JSON 会拆成独立字段。App ID/Secret 只标识应用，Access Token 只代表一次已授予的账号授权；具体接口仍受开发者应用已审批权限与广告账号/店铺资源关系约束。若当前应用未获“Get products within a TikTok Shop”读取权限，`商品名称` 无法由该 Token 自动补齐，但其余可读取字段仍会生成。

## 开发与验证

运行全部离线测试：

```zsh
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

测试使用模拟 API，不会访问 TikTok，也不会读取 Keychain。工作簿使用 `@oai/artifact-tool` 生成，并在写入正式文件前检查公式错误。

涉及 TikTok Business API 的后续修改，先查看官方 [TikTok Business API SDK](https://github.com/tiktok/tiktok-business-api-sdk)。如需要本地参考副本，可克隆到被忽略的 `tiktok-business-api-sdk/`，不要提交该目录。
