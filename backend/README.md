# ScholarLens 后端

FastAPI 0.2.1，Elasticsearch 8.19.23、MiniLM CPU ONNX、SQLite 与独立原 PDF。已接通 859 篇正式论文、49,420 个基础向量片段，API 主流程覆盖六字段 BM25、语义/RRF、阅读、账户、私人工作区、审核上传及证据助手。

## 运行与配置

已有模型/数据/依赖时，在克隆根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens1.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
```

日常启动不重导数据或重建向量。应用、ES、SQLite 各自独立；生产端口与本机端口分开。个人 API 同时支持 Chat Completions/Responses，按请求生效，密钥不进正式库。默认共享 AI 与邮件仍不配置。

## 集中手册

- [项目总报告](../docs/PROJECT_REPORT.md)、[当前状态](../docs/operations/STATUS.md)。
- [启动/依赖/模型/备份恢复](../docs/development/backend/BACKEND_STARTUP.md)。
- [基础 API](../docs/development/backend/FRONTEND_API_GUIDE.md)、[V2.1](../docs/development/backend/FRONTEND_API_GUIDE_V21.md)、[HTTP 契约](../docs/specs/04_API_CONTRACT.md)。
- [AI 配置](../docs/development/backend/AI_CONFIGURATION.md)、[检索评价](../docs/development/backend/SEARCH_EVALUATION.md)。
- [部署回滚](../docs/operations/11_SERVER_DEPLOYMENT.md)、[原件交付](../docs/operations/13_ORIGINAL_PDF_DELIVERY.md)。
- [历史验收](../docs/archive/backend/20261026-27/README.md)、[隔离上传边界](../docs/specs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md)。

SQLite 使用一致性 backup，不能只复制写入中的主文件。基础正式 mapping 仍为 `papers-p0-v1`，新代 CJK 能力不等于正式库已迁移。上传索引/向量分代，禁止覆盖原件或正式数据。后端保留兼容 text-only DOCX API，页面主下载为 PDF。不要对生产库直接运行历史全量测试；测试范围、依赖和日期见对应记录。CI 草稿不等于 Actions 已运行。
