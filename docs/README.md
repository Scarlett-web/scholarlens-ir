# 文档入口

按用途阅读，避免在一堆过程快照里找当前结论。

## 汇报与当前证据

- [项目总报告与汇报底稿](PROJECT_REPORT_20261028.md)：当前功能、架构、数据、优化、测试、部署、边界、演示脚本和答辩口径。
- [PPT 逐页大纲](PPT_OUTLINE_20261028.md)：22 页以内的页面结构、素材、讲述重点。
- [持续验证](32_CONTINUOUS_VERIFICATION.md) + [被动检查与剩余边界](33_PASSIVE_CHECKS_AND_RESIDUALS.md)：最新证据、失败保留和未完成项。
- [文档整理清单](DOCUMENT_CLEANUP_20261028.md)：27 份归档说明的旧路径、新路径和保留原因。
- [汇报截图](assets/report-20261028/README.md)：3 张真实公开页面，可用于 PPT。
- [白玻璃实现](34_VISUAL_GLASS_20261028.md) + [独立复核与线上发布](35_GLASS_RELEASE_ACCEPTANCE_20261028.md)：明亮冰川外观、三档透明度、功能回归及回滚位置。
- [研究功能修复与中文准备](36_RESEARCH_USABILITY_AND_CHINESE_READINESS.md)：自由问答、对话区比例、六字段高亮、PDF 原件下载及 CJK 检索兼容。
- [检索结果整理](37_SEARCH_RESULTS_POLISH.md)：高亮纠错、完整作者展开、提示精简和分页省略号。

## 按主题查阅

| 主题 | 入口 |
| --- | --- |
| 需求、架构、数据、API、UI | [需求](01_REQUIREMENTS.md)、[架构](02_ARCHITECTURE.md)、[Schema](03_DATA_SCHEMA.md)、[API](04_API_CONTRACT.md)、[UI](05_UI_SPEC.md) |
| 部署、发布、原件 | [服务器](11_SERVER_DEPLOYMENT.md)、[首次交付](12_RELEASE_ACCEPTANCE.md)、[PDF](13_ORIGINAL_PDF_DELIVERY.md) |
| Agent 与运行时 | [运行契约](18_AGENT_RUNTIME_CONTRACT.md)、[供应商边界](26_AGENT_PROVIDER_BOUNDARIES.md) |
| 研究与交互 | [关系/指标](22_RESEARCH_MAP_AND_METRICS.md)、[上传](23_UPLOAD_REVIEW_WORKFLOW.md)、[证据台](24_EVIDENCE_READING_WORKFLOW.md)、[检索/账户](25_SEARCH_ACCOUNT_WORKFLOW.md)、[书架](27_LIBRARY_RESEARCH_SHELF.md) |
| 权限与真实链路 | [会话](28_ACCOUNT_CREDENTIAL_BOUNDARIES.md)、[管理员事务](30_ADMIN_TRANSACTION_BOUNDARIES.md)、[上传所有权](31_ISOLATED_UPLOAD_AND_OWNERSHIP.md) |
| 目标账本 | [总目标与证据](29_GOAL_REQUIREMENTS_AND_EVIDENCE.md) |
| 后端操作 | [后端入口](../backend/README.md)、[启动](../backend/BACKEND_STARTUP.md)、[基础手册](../backend/FRONTEND_API_GUIDE.md)、[V2.1](../backend/FRONTEND_API_GUIDE_V21.md) |
| 前端接入与设计 | [设计规范](../frontend/docs/DESIGN_SYSTEM.md)、[集成契约](../frontend/docs/FULL_STACK_CONTRACT.md)、[当前 QA](../frontend/docs/QA_CHECKLIST.md) |

## 历史过程快照

[公共过程归档](archive/20261028-process-notes/README.md)保存 7 份审计、UX、线上发布、棱镜阅读和工具覆盖记录；[后端归档](../backend/archive/20261026-27/README.md)保存 9 份阶段目标/验收；[前端归档](../frontend/docs/archive/20261027-28/README.md)保存 11 份设计和验收快照。当前状态以项目总报告、持续验证和被动检查为准。

清理规则：只归档重复/过时的过程说明，不删除需求、协议、数据、部署、回滚、失败证据、测试报告、原件、数据库或技能文件。
