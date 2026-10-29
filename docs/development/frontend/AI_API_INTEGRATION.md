# 个人 AI API 使用与接入

更新：2026-10-29。每位登录用户填写自己的 URL、密钥、模型和协议；全站默认不设置共享供应商，不预填密钥。

## 使用步骤

1. 登录后进入研究助手，点击“API 设置”。
2. 填公共 HTTPS Base URL（通常以 `/v1` 结束）与密钥，明确选 Chat Completions 或 Responses。
3. 点击“读取模型列表”，从返回目录选择模型或手工填写；列表不是可用性承诺。
4. 点击“测试连接”，它会发送一次简短真实生成，可能产生少量供应商费用。
5. 保存个人配置，再提问；原文证据模式始终可独立使用。

保存成功不等于调用成功。模型不存在或退役、认证、限流、超时等错误不会被写成“问题格式错误”；不会自动替换模型。Responses 请求设 `store:false`，个人读取至少 60 秒，仍受 120 秒 Agent 总预算约束，连接小测试为 25 秒。

## 数据与凭据

URL/模型/协议/token 参数按用户保存为本浏览器偏好；API key 只在当前标签页 sessionStorage，退出或认证失效清除，不同步其他设备。个人请求经同源后端转发，服务端不把 key 写入 SQLite、全局环境或日志。不要放进 Vite 环境变量。

## 接口

| 接口 | 职责 |
| --- | --- |
| `GET /api/ai/models` | 读取供应商模型目录；不要求已有模型名 |
| `POST /api/ai/test` | 简短生成测试，不落对话库 |
| `POST /api/agent/run` | 当前页面使用的有限步骤 Agent |
| `/api/ask`、`/api/ai/summarize`、`/api/ai/compare` | 兼容问答、总结、比较 |

个人头为 `X-ScholarLens-AI-URL`、`-Model`、`-Key`、`-Token-Parameter`、`-Protocol`；完整前缀均为 `X-ScholarLens-AI-`。协议只允许 `chat_completions` / `responses`；旧配置默认前者。完整 `/responses` 或 `/chat/completions` 地址会拆分为 Base URL 和对应协议。

仅支持公共 HTTPS 443；拒绝私网、URL 内凭据、查询参数、混合 DNS 和重定向，固定校验后 IP 并保留 TLS。上游认证错误不等于网站会话失效。

有文献依据时逐字核验引用；通用回答显示未由本库验证，不伪造引用。总结限定一篇，比较需 2–10 篇且覆盖每篇。对话本人隔离。

真实供应商限定验收已经完成，见[原始记录](../../archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md)。该记录不等于所有模型长期可用；capabilities 的共享 AI 未配置不否定个人 API。邮件与 XML 尚未验收，正式 PDF 已接通。
