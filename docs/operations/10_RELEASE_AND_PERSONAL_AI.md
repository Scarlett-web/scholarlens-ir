# 前端发布与个人 AI 配置契约

负责人：当前项目维护者。输入为现有 React 前端、V2.1 API 和已验收的本机数据；输出为可克隆的 frontend 源码、个人 API 配置入口和单域名部署入口。

## 2026-10-28 连接与对话页修订（负责人：当前项目维护者）

- 输入：登录用户填写的公共 HTTPS Base URL、密钥、模型与协议。保留旧配置默认 Chat Completions；新增 Responses，使用 `input`、`max_output_tokens`、`store:false`，不自动替换模型或重发到另一协议。
- `GET /api/ai/models`：按当前用户的临时请求头读取供应商模型名（不产生回答），返回 `models:string[]`，最多 300 个；不要求已填写模型。`POST /api/ai/test`：按所填模型发送一次简短生成请求，成功返回 `{status:"ready",model,protocol}`；测试不保存对话、不检索文献、不修改全局配置。
- 新请求头 `X-ScholarLens-AI-Protocol` 仅允许 `chat_completions` / `responses`，缺省兼容旧版。完整 `/responses` 或 `/chat/completions` URL 自动拆为 Base URL 与对应协议。所有个人接口仍需登录，URL、DNS、跳转、体积、超时、凭据隔离与引用校验边界不变。
- 上游认证错误继续为网站 502，不触发账户退出；模型或路径 404 给出独立提示。读取模型列表、保存本地配置与真实生成成功分别报告，不把保存当连接成功。
- 个人问答单次读取超时至少 60 秒，仍受 Agent 总共 120 秒预算约束；连接测试保持 25 秒小请求，不重复切换协议或模型。慢模型超时保留证据并明确提示，不归咎于问题格式。
- UI：保留白玻璃、冰川和三档通透度。助手以居中对话、底部输入区为主体；阅读方式、对话记录、API 设置改为三个工具按钮，一次展开一个侧面板，可关闭、Escape 关闭并返回焦点。保留论文范围、总结/比较、临时/账户对话、停止、只查原文、引用核对与原文入口。Enter 发送，Shift+Enter 换行，中文输入法选词不发送。
- 验收：两协议的规划和回答、严格响应解析、错误脱敏/认证隔离、连接测试不落库；工具面板键盘操作、账户配置隔离、原功能与桌面/390px 回归；构建、单元、结构、浏览器以及少量真实供应商生成。上线前保留一致性数据库备份、环境副本和上一 release。

## 个人 API

- 登录用户可以在助手页自行填写 OpenAI 兼容的 API Base URL、模型、密钥及 token 参数。默认均为空，不预填供应商密钥。
- URL/模型为该账号在本浏览器的偏好；密钥仅保存在该标签页 sessionStorage，退出或会话失效时清除，不进入 Git、构建变量、SQLite 或服务器配置。
- `/ask`、`/ai/summarize`、`/ai/compare` 接受可选 `X-ScholarLens-AI-URL`、`X-ScholarLens-AI-Model`、`X-ScholarLens-AI-Key`、`X-ScholarLens-AI-Token-Parameter` 请求头。个人参数必须齐全且用户已登录，按请求生效，不影响其他用户。没有这些头时保留原服务器配置兼容行为。
- 个人 endpoint 仅支持公共 HTTPS，禁止 URL 账号密码、查询参数、片段和私网目的地；连接固定到已验证的公共 IP，保留 Host/TLS SNI 和证书校验，禁止跳转与环境代理。错误不返回凭据和上游内容。
- 引用校验、证据不足与对话归属校验沿用已有实现。实际配置前不声称外部模型已运行成功。

## 发布

- 保持 `zjl` 分支，提交后端改动与 frontend 源码，不合并 main 或数据分支，不将原始论文写入源码历史，不上传数据库、模型、QA账户、日志和真实配置；本批原件仅按后续明确授权发布于独立数据 Release。
- FastAPI 可通过 `FRONTEND_DIST` 提供 production build，前端与 `/api` 共用一个 HTTPS 域名。未知 API 不回退为 HTML；静态路径不得穿越目录。
- Cloudflare Tunnel 仅转发该应用的 loopback HTTP 端口，使用独立隧道与子域名，不修改已有服务或 DNS。电脑托管需要保持电脑、API、ES 和隧道运行；服务器托管不依赖个人电脑。CF Pages 本身不运行现有 Python/Elasticsearch 后端。
- 2026-10-28：正式库 859 份原 PDF 已接通；完整 999 份原包、正式 JSONL 与来源 CSV 在独立 [数据 Release](https://github.com/Scarlett-web/scholarlens-ir/releases/tag/papers-originals-2026-10-28) 存档，仍不写入源码 Git 历史。恢复与回滚见 [原件交付说明](13_ORIGINAL_PDF_DELIVERY.md)。邮件服务和 XML 仍待后续；指定个人 API 已完成真实供应商验收，详见[助手验收记录](../archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md)。共享 AI 默认仍未配置，缺失依赖保持真实状态。

验收：个人配置的两用户隔离、退出清理、私网/重绑定/跳转限制、密钥不进入响应、原有问答契约回归；前端 build/unit/structure/browser；同源主页、深层路由、静态文件及 API 错误边界；推送后核对远端提交。
