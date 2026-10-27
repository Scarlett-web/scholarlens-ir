# 前端发布与个人 AI 配置契约

负责人：当前项目维护者。输入为现有 React 前端、V2.1 API 和已验收的本机数据；输出为可克隆的 frontend 源码、个人 API 配置入口和单域名部署入口。

## 个人 API

- 登录用户可以在助手页自行填写 OpenAI 兼容的 API Base URL、模型、密钥及 token 参数。默认均为空，不预填供应商密钥。
- URL/模型为该账号在本浏览器的偏好；密钥仅保存在该标签页 sessionStorage，退出或会话失效时清除，不进入 Git、构建变量、SQLite 或服务器配置。
- `/ask`、`/ai/summarize`、`/ai/compare` 接受可选 `X-ScholarLens-AI-URL`、`X-ScholarLens-AI-Model`、`X-ScholarLens-AI-Key`、`X-ScholarLens-AI-Token-Parameter` 请求头。个人参数必须齐全且用户已登录，按请求生效，不影响其他用户。没有这些头时保留原服务器配置兼容行为。
- 个人 endpoint 仅支持公共 HTTPS，禁止 URL 账号密码、查询参数、片段和私网目的地；连接固定到已验证的公共 IP，保留 Host/TLS SNI 和证书校验，禁止跳转与环境代理。错误不返回凭据和上游内容。
- 引用校验、证据不足与对话归属校验沿用已有实现。实际配置前不声称外部模型已运行成功。

## 发布

- 保持 `zjl` 分支，提交后端改动与 frontend 源码，不合并 main 或数据分支，不上传原始论文、数据库、模型、QA账户、日志和真实配置。
- FastAPI 可通过 `FRONTEND_DIST` 提供 production build，前端与 `/api` 共用一个 HTTPS 域名。未知 API 不回退为 HTML；静态路径不得穿越目录。
- Cloudflare Tunnel 仅转发该应用的 loopback HTTP 端口，使用独立隧道与子域名，不修改已有服务或 DNS。电脑托管需要保持电脑、API、ES 和隧道运行；服务器托管不依赖个人电脑。CF Pages 本身不运行现有 Python/Elasticsearch 后端。
- 邮件服务、原 PDF/XML 可以以后补接；缺失依赖保持真实状态。

验收：个人配置的两用户隔离、退出清理、私网/重绑定/跳转限制、密钥不进入响应、原有问答契约回归；前端 build/unit/structure/browser；同源主页、深层路由、静态文件及 API 错误边界；推送后核对远端提交。
