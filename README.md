# ScholarLens — 智能学术论文检索与分析平台

ScholarLens 是《信息检索》课程大作业的规划项目，目标是将约 1000 篇学术论文处理为可检索、可解释、可问答的学术搜索系统。项目名称与课程要求中的 **Scholar IR System** 对应，最终以真实论文数据驱动课堂演示。

## 当前状态（2026-10-22，开发第七周）

- 当前 Git 分支：`zjl`（组长个人开发分支）。
- 本次仅完成项目规划、协议文档和目录初始化；尚未安装依赖、启动服务、下载 PDF、解析数据或创建索引。
- GROBID、Elasticsearch、Sentence Transformers、模型 API、SQLite 以及 Lucene 调用方式均为拟议方案，须在会议中确认。
- 文档中的 Mock 数据只用于前后端并行开发，不能作为真实检索结果或实验结论。

## 目标与范围

1. 批量解析约 1000 篇 PDF，提取标题、作者、日期、机构、地址、页数、摘要和正文，生成可追溯的 XML/JSONL 数据。
2. 基于 Elasticsearch（Lucene）建立六字段倒排索引，提供字段检索、BM25、分页、高亮、筛选和排序。
3. 在数据和依赖条件满足后增加标题/摘要语义检索、BM25+向量的 RRF 混合检索，以及带来源引用的 RAG 问答。
4. 提供 React 现代化 Web 界面和真实数据演示，并用 Precision@5、nDCG@10、延迟等指标比较检索方法。

## 拟议技术栈（均待会议确认）

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
├── backend/                  # 组长：FastAPI、检索、RAG（当前仅占位）
├── frontend/                 # 组员 B：React UI（当前仅占位）
├── scripts/                  # 组员 A：解析、清洗、评测脚本（当前仅占位）
├── infra/                    # 组长：Docker/Elasticsearch/GROBID 配置（当前仅占位）
└── data/
    └── sample/               # 可提交的少量 Mock JSONL（当前仅占位）
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

## 本次初始化边界

本次提交范围只包含文档、`.gitkeep` 占位文件和 `.gitignore` 规则。不要把原始 PDF、数据库、模型缓存、依赖目录、密钥或临时输出加入仓库；不自动执行安装、Docker、Git commit、push 或 merge。
