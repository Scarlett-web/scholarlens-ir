# 个人 AI API 配置

默认供应商、URL、模型和密钥均为空。登录后进入 AI 助手，展开“个人 API 设置”，填写自己的 OpenAI 兼容 Base URL、模型和密钥。无需修改源码或 Vite 环境变量。

- URL、模型和 token 参数按账号 ID 保存为本浏览器偏好，不同步到其他设备。
- 密钥按账号隔离，仅存当前标签页 sessionStorage；退出或认证失效时清除。刷新可保留，结束标签页会话后需重新填写。共享设备使用后应退出。
- 不在 localStorage、数据库、Git 或构建变量中保存密钥。请求通过同源后端转发，后端在该请求内使用凭据，不改变全站配置。
- 保存配置只证明格式已填写；真实连通性、额度和引用质量由实际问答验证，不伪造成功状态。

## 接口

POST /api/ask、POST /api/ai/summarize、POST /api/ai/compare 使用已有 JSON 请求和引用响应契约，额外支持四个请求头：

| 请求头 | 内容 |
| --- | --- |
| X-ScholarLens-AI-URL | 公共 HTTPS Base URL，例如以 /v1 结尾 |
| X-ScholarLens-AI-Model | 用户指定模型 |
| X-ScholarLens-AI-Key | 用户密钥，不记日志、不回显 |
| X-ScholarLens-AI-Token-Parameter | max_completion_tokens 或 max_tokens |

个人配置须已登录且完整；只允许公共 HTTPS 443 地址。后端拒绝私网、保留 IP、混合 DNS 答案、URL 凭据、查询参数、跳转；连接固定到校验后的 IP 并保留 TLS 验证。自建私网和其他端口暂不支持。

服务端按原文片段检索，模型引用必须匹配真实片段及 chunk ID；证据不足明确返回不足。原文证据检索无需 AI 密钥。摘要/比较可从收藏选择论文；研究对话按用户存于服务器，临时对话仅在页面内。

原服务器 AI 环境变量保留兼容，但本次交付不填真实值。VITE_AI_ENDPOINT 继续默认空且仅接受同源 /api 路径，个人配置不依赖它。邮件服务、原始 PDF/XML 留作后续接入。
