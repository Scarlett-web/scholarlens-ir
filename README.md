# ScholarLens — 学术论文检索与研究工作台

ScholarLens 是《信息检索》课程项目（对应 Scholar IR System），连接真实论文、三模式检索、原文阅读、收藏笔记、账户与受审核上传，并提供可核验的原文证据。

**在线访问：[ScholarLens](https://scholarlens.lingion.cc.cd/)**。网站运行于华为云，经 Cloudflare Tunnel 提供 HTTPS，个人电脑关机后仍可访问。

## 汇报与文档

- [项目总报告](docs/PROJECT_REPORT_20261028.md)：现有资产、逐功能说明、检索原理、数据库、实现过程、优化、安全、测试、部署、局限和答辩。
- [PPT 逐页底稿](docs/PPT_OUTLINE_20261028.md)：22 页结构、可复制页面文字、配图和讲稿。
- [文档索引](docs/README.md)：维护入口、历史归档及清理清单。
- [当前验证与发布](docs/32_CONTINUOUS_VERIFICATION.md)、[剩余边界](docs/33_PASSIVE_CHECKS_AND_RESIDUALS.md)。

## 当前状态（2026-10-28）

| 项目 | 当前事实 |
| --- | --- |
| 正式论文 | 859 篇；215 success、644 partial；4 篇正文因严重乱码隔离，元数据保留 |
| 向量 | 49,420 个片段，384 维 MiniLM CPU ONNX；RRF k=60 |
| 原件 | 正式库 859 份 PDF 已接通，共 22,686 页；完整 999 份原包和正式元数据在独立[数据 Release](https://github.com/Scarlett-web/scholarlens-ir/releases/tag/papers-originals-2026-10-28) |
| 页面 | 搜索、论文、探索、书架、账户、助手、评测、上传、审核与 404 |
| 接口 | FastAPI 0.2.1；本轮公网 OpenAPI 列出 63 个路径、79 个操作 |
| 验证 | 最新前端 35 项；10 个独立后端模块 135 项；Chrome/Edge 44 组检查，范围见验证记录 |
| 线上应用 | `20261028T090257Z-42c81c9`；本轮只读核对服务 active/running、NRestarts=0 |
| 保留能力 | 个人 AI URL/模型/密钥自行配置；真实上游与邮件未验收；XML 未交付；GitHub CI 为待启用草稿 |

## 运行

在已配置依赖、数据和模型的 Windows 克隆根目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
```

首次运行按[后端启动与恢复](backend/BACKEND_STARTUP.md)准备环境。克隆源码不会自动得到模型、数据库、运行索引和原始论文；原件与元数据从独立数据 Release 恢复，索引按受控导入流程重建。

前端开发见[前端说明](frontend/README.md)。**正式发布必须执行 `npm run build:production`**；普通 build 默认可能生成 18 篇明确标记的虚构演示包。生产入口固定使用同源 `/api`，生成 `dist/build-info.json`；发布后同时检查页面真实数据和资源 hash。

## 代码目录

| 目录 | 职责 |
| --- | --- |
| `frontend/` | React/Vite/TypeScript 页面、状态管理、浏览器存储和交互检查 |
| `backend/` | FastAPI、BM25/向量/RRF、账户、工作区、上传、证据与转换 |
| `agent/` | Workflow、MCP 客户端配置示例 |
| `.agents/skills/` | 项目设计参考与证据 Agent 运行规则 |
| `infra/` | 本机启动、服务器 systemd/Tunnel 示例、CI 草稿 |
| `tools/audit/`、`tools/agent/` | 局部验证工具与 Harness；运行输出被忽略 |
| `docs/` | 总报告、PPT、协议、交付与归档索引 |
| `scripts/`、`data/` | 数据组约定与样本；原始大数据不进入源码历史 |

## 维护边界

源码分支为 `zjl`，不自动合并其他分支。个人密钥仅在标签页会话中保存，URL/模型偏好按用户保存在浏览器；服务器不保存个人密钥。不提交原始论文、用户库、模型、运行索引、凭据、日志或测试报告。只读验收不代表全部业务或真实供应商已成功。部署和回滚见[服务器说明](docs/11_SERVER_DEPLOYMENT.md)，历史记录从[文档索引](docs/README.md)查阅。
