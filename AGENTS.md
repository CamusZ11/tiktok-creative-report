# TikTok 创意明细导出项目

- 默认用中文沟通和写计划。
- 任何 TikTok Business API 的接口、权限、参数和版本判断，都先参考官方 SDK：<https://github.com/tiktok/tiktok-business-api-sdk>；优先查看 README、Changelog、对应语言 SDK 和 yml_files。
- 本项目只允许 OAuth 令牌交换和 TikTok 只读 API 请求；不得加入创建、修改、删除广告或店铺资源的接口。
- 不得把 App Secret、Access Token、OAuth 授权码、广告账号/店铺敏感数据写入仓库、日志、测试夹具或 Markdown。凭据仅存在 macOS Keychain。
- `TikTok_创意明细配置.local.md` 是本机配置，必须保持 Git 忽略；不可把它纳入提交。
- 报表生成必须通过 `@oai/artifact-tool`，以临时文件完成校验后原子替换正式 XLSX；失败时保留上一份成功文件。
