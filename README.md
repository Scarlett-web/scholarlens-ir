# ScholarLens — 学术论文检索与研究工作台

ScholarLens 是信息检索课程项目，将真实论文检索、原文阅读、收藏笔记、账户、受审核上传与证据助手连接成完整研究流程。

在线访问：[scholarlens.lingion.cc.cd](https://scholarlens.lingion.cc.cd/)。华为云运行，经 Cloudflare Tunnel 提供 HTTPS，个人电脑关机后仍可访问。

## 从这里了解项目

| 你要做什么 | 阅读入口 |
| --- | --- |
| 了解项目做了什么、有什么、原理和边界 | [项目总报告](docs/PROJECT_REPORT.md) |
| 做课堂 PPT、准备讲稿和答辩 | [PPT 逐页底稿](docs/PPT_OUTLINE.md) |
| 找技术规范、运行手册和历史记录 | [文档中心](docs/README.md) |
| 核对当前线上版本和证据时间 | [当前状态](docs/operations/STATUS.md) |

## 当前事实（2026-10-29）

| 项目 | 已核对内容 |
| --- | --- |
| 数据 | 859 篇正式论文、49,420 个向量片段；正式库原 PDF 已接通 |
| 检索 | 六字段 BM25、MiniLM CPU ONNX、RRF 混合与筛选高亮 |
| 用户功能 | 注册/登录/退出、收藏分类、笔记、历史、对话、上传审核 |
| 研究助手 | 原文检索、引用核验、个人 API 两协议、模型列表与连接测试 |
| 最新外观 | 冰川白玻璃、顶部 Dock、三档材质、3D 最近阅读与大对话区 |
| 在线应用 | `20261029T022557Z-d7cfc56`；同源 `/api` 正式构建 |
| 接口 | FastAPI 0.2.1，公网 OpenAPI 65 路径、81 操作 |
| 已有外部验收 | 指定个人模型真实生成与引用链已验收；全站共享 AI 仍默认未配置 |
| 待办 | 邮件、XML、正式中文导入/多语言向量、相关性金标准、托管 CI 和容量验证 |

原包 999 份 PDF 与正式元数据存于独立[数据 Release](https://github.com/Scarlett-web/scholarlens-ir/releases/tag/papers-originals-2026-10-28)。原包数量、正式库数量、向量片段数是不同概念。

## 开发和运行

已有数据、模型和依赖的 Windows 克隆根目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
```

首次准备环境看[后端启动手册](docs/development/backend/BACKEND_STARTUP.md)，前端命令看[前端入口](frontend/README.md)。克隆代码不会自动得到用户库、索引、模型和原论文。

正式应用发布使用 `npm run build:production`，同源 `/api` 并核对 `build-info.json`；普通 build 可能生成明确标记的 18 篇演示包。文档修改不需要重新构建或重启应用。

## 目录与维护

`frontend/` 为页面与浏览器交互，`backend/` 为 API/检索/账户/上传，`agent/` 为运行工作流，`infra/` 为启动和部署示例，`tools/` 为限定范围验证，`docs/` 为统一文档中心。模块 README 和少量兼容入口只负责指路，正文集中维护。

持续使用 `zjl` 分支，不自动合并其他分支。用户库、原件、模型、索引、密钥、日志和运行报告不进入源码提交。个人 API key 仅在标签页会话中使用，不能放进 Vite 变量。发布、恢复和文档同步见[操作手册](docs/operations/11_SERVER_DEPLOYMENT.md)与[文档维护](docs/operations/DOCUMENTATION.md)。
