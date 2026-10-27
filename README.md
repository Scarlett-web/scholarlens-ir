# ScholarLens — 智能学术论文检索与分析平台

ScholarLens 是《信息检索》课程大作业，实现真实学术论文的关键词、语义和混合检索，以及可追溯问答的后端接口。项目名称与课程要求中的 **Scholar IR System** 对应。

## 完整网站交付（2026-10-28）

在线访问：[ScholarLens](https://scholarlens.lingion.cc.cd)。已部署到华为云，电脑关机后仍可访问。公网三模式检索与14项账户浏览器流程通过；首次使用请注册，测试用户未迁移。详细证明和未测边界见 [验收记录](docs/12_RELEASE_ACCEPTANCE.md)。

- frontend/ 已纳入冰岛玻璃风格的完整 React 界面，连接检索、账户、收藏笔记、最近阅读、上传审核和研究助手；源码默认 demo，真实部署设置 VITE_DATA_SOURCE=api。
- 每个登录用户可独立填写 OpenAI 兼容 URL、模型及密钥；密钥只保存在标签页 sessionStorage，退出清除，按请求使用，不写服务器数据库。默认配置空，未做真实供应商调用。
- 本轮本机后端 161 passed、1 deselected；前端 build、15 tests、structure、真实检索浏览器和14项账户流程通过。被排除的是独立 API 重启测试，不把历史结果当本轮证明。
- FastAPI 支持 FRONTEND_DIST 同源托管，服务器与 Cloudflare 独立部署见 [部署说明](docs/11_SERVER_DEPLOYMENT.md)。本机测试不代表外网已发布，外网状态以实际部署验收为准。
- 邮件、原始 PDF/XML 后续补接；正文可读不代表原 PDF 可下载，缺失时明确返回状态。

## 上一版本后端状态（2026-10-27，历史）

- 已在组长Windows本机验收859篇真实论文、49420个向量片段，完整测试131项通过。
- Elasticsearch 8.19.23、Python 3.11、FastAPI、MiniLM CPU ONNX与SQLite；本地运行无需Docker。
- 提供六字段BM25、语义/RRF、建议/发现、详情/片段、用户/收藏/历史、审核上传与独立增量索引。
- RAG证据链和模型适配器已有实现；真实AI Key、原论文PDF、运行中的GROBID仍需配置，能力接口如实返回状态。受控测试不代表这些外部资源已经交付。
- 当前代码在组长分支`zjl`，数据组和前端分支不自动合并；本仓库没有部署公网API。

已有本机环境日常启动（不重新导入论文）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
```

本机接口文档为`http://127.0.0.1:8000/docs`，能力状态为`/api/capabilities`。首次在新电脑使用时，先按[Windows启动说明](backend/BACKEND_STARTUP.md)安装依赖、配置数据与索引；GitHub代码不包含虚拟环境、原论文、数据库、ES索引或模型缓存，克隆后不会自动拥有本机859篇数据。

- [后端说明](backend/README.md)
- [前端API手册](backend/FRONTEND_API_GUIDE.md)
- [V2完整验收与分阶段文件清单](backend/BACKEND_V2_VERIFICATION.md)
- [AI服务配置](backend/AI_CONFIGURATION.md)
- [三模式评价与限制](backend/SEARCH_EVALUATION.md)

## 历史阶段记录

> 2026-10-27：859篇正式JSONL已完成结构与来源清单验收，真实倒排检索API已运行，启动默认real索引，Mock保留。详见[真实数据验收](backend/REAL_DATA_VERIFICATION.md)和[持续任务](backend/REAL_DATA_GOAL.md)。PDF尚未实物交付，数据质量限制已记录。

> 2026-10-26 更新：组长已启动后端 P0，Elasticsearch 8.19.23 + FastAPI 的 Mock 检索链路和运行说明见 [backend/README.md](backend/README.md)，实测见 [backend/VERIFICATION.md](backend/VERIFICATION.md)。下方 2026-10-22 内容保留为初始化阶段记录，不能代表当前后端状态。真实论文 JSONL 尚未交付，数据组 PR 未合并。

- 当前 Git 分支：`zjl`（组长个人开发分支）。
- 本次仅完成项目规划、协议文档和目录初始化；尚未安装依赖、启动服务、下载 PDF、解析数据或创建索引。
- GROBID、Elasticsearch、Sentence Transformers、模型 API、SQLite 以及 Lucene 调用方式均为拟议方案，须在会议中确认。
- 文档中的 Mock 数据只用于前后端并行开发，不能作为真实检索结果或实验结论。

## 目标与范围

1. 批量解析约 1000 篇 PDF，提取标题、作者、日期、机构、地址、页数、摘要和正文，生成可追溯的 XML/JSONL 数据。
2. 基于 Elasticsearch（Lucene）建立六字段倒排索引，提供字段检索、BM25、分页、高亮、筛选和排序。
3. 在数据和依赖条件满足后增加标题/摘要语义检索、BM25+向量的 RRF 混合检索，以及带来源引用的 RAG 问答。
4. 提供 React 现代化 Web 界面和真实数据演示，并用 Precision@5、nDCG@10、延迟等指标比较检索方法。

## 初始拟议技术栈（历史规划，当前实现以上文为准）

| 层次 | 方案 | 选择理由 | 关键条件/风险 |
|---|---|---|---|
| 数据处理 | Python + GROBID + XML/JSONL | GROBID 对学术 PDF 结构化解析成熟，Python 便于批处理和统计 | PDF 版式差异、GROBID 服务资源占用、字段缺失 |
| 关键词检索 | Elasticsearch（基于 Lucene）+ BM25 | 提供倒排索引、字段权重、高亮和分页，满足课程要求 | 版本兼容、内存、是否必须直接调用 Java Lucene API待确认 |
| 语义检索 | Sentence Transformers + Elasticsearch 向量能力 | 复用现有索引基础，支持标题/摘要和分块向量 | 模型下载与中文/英文效果、向量维度和存储成本 |
| 混合检索 | BM25 + 向量 + RRF | 无需手工标定分数，便于对比实验 | 候选集大小与融合参数需通过验证集确定 |
| API/RAG | FastAPI + 可配置大模型 API | 类型约束清晰、适合异步接口和 Python RAG 编排 | API Key、网络可用性、幻觉与引用完整性 |
| 用户数据 | SQLite | 课程项目部署简单、零额外服务 | 并发与迁移能力有限 |
| 前端 | React + Vite + Tailwind CSS + shadcn/ui | 组件化、响应式和快速原型 | 需要统一设计令牌和 API Mock 契约 |
| 部署 | Docker | 固化运行条件，便于课堂复现 | 镜像体积、Windows 资源分配、服务编排待确认 |

## 目录

```text
.
├── AGENTS.md                 # 持续执行规则与协作约束
├── README.md
├── docs/                     # 需求、架构、协议、UI、计划和验收文档
├── backend/                  # 组长：FastAPI、检索、RAG、SQLite、测试与交接文档
├── frontend/                 # 组员 B：React UI（当前仅占位）
├── scripts/                  # 组员 A：解析、清洗、评测脚本（当前仅占位）
├── infra/                    # 组长：Windows Elasticsearch与后端启动/停止配置
└── data/
    └── sample/               # 可提交的少量Mock JSONL，正式数据在本机忽略路径
```

## 文档入口

- [需求清单与验收标准](docs/01_REQUIREMENTS.md)
- [技术架构与流程](docs/02_ARCHITECTURE.md)
- [统一论文数据格式](docs/03_DATA_SCHEMA.md)
- [HTTP API 契约](docs/04_API_CONTRACT.md)
- [UI 规范](docs/05_UI_SPEC.md)
- [团队计划与 GitHub 规则](docs/06_TEAM_PLAN.md)
- [测试、指标与课堂演示](docs/07_TEST_DEMO.md)
- [会议决策表](docs/08_MEETING_DECISIONS.md)

## 初始化边界（历史）

本次提交范围只包含文档、`.gitkeep` 占位文件和 `.gitignore` 规则。不要把原始 PDF、数据库、模型缓存、依赖目录、密钥或临时输出加入仓库；不自动执行安装、Docker、Git commit、push 或 merge。
