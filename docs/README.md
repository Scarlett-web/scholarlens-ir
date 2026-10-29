# 文档中心

更新于 2026-10-29。正文集中在本目录，按用途阅读；旧记录保留日期，不作为当前状态。

## 先读这三份

| 文档 | 用途 |
| --- | --- |
| [项目总报告](PROJECT_REPORT.md) | 做了什么、现有资产、逐功能、数据、算法、AI、最新外观、贡献、限制、演示与答辩 |
| [PPT 逐页底稿](PPT_OUTLINE.md) | 22 页标题、正文、配图、讲稿和裁剪建议 |
| [当前状态与证据](operations/STATUS.md) | 当前应用版本、在线快照、历史验收范围及本次文档检查 |

## 目录怎么分

```text
docs/
  PROJECT_REPORT.md       总报告，固定文件名持续维护
  PPT_OUTLINE.md          PPT 底稿，固定文件名持续维护
  README.md              唯一文档目录
  specs/                 需求、协议、技术和业务规则
  operations/            部署、数据交付、状态和维护
  development/backend/   后端安装、接口与配置手册
  development/frontend/  前端设计、接入与 QA 手册
  assets/                有来源和日期的汇报截图
  archive/               阶段目标、旧汇报和历史验收
```

根目录的 `03_DATA_SCHEMA.md` 和 `frontend/docs/` 中六份短入口为兼容现有指令/结构检查保留，不再放第二份正文。

## 技术规范

| 主题 | 文档 |
| --- | --- |
| 基础规范 | [需求](specs/01_REQUIREMENTS.md)、[架构](specs/02_ARCHITECTURE.md)、[数据 Schema](specs/03_DATA_SCHEMA.md)、[API](specs/04_API_CONTRACT.md)、[UI](specs/05_UI_SPEC.md) |
| 协作和决策 | [团队计划](specs/06_TEAM_PLAN.md)、[决策记录](specs/08_MEETING_DECISIONS.md) |
| Agent | [运行契约](specs/18_AGENT_RUNTIME_CONTRACT.md)、[供应商边界](specs/26_AGENT_PROVIDER_BOUNDARIES.md) |
| 研究交互 | [关系与指标](specs/22_RESEARCH_MAP_AND_METRICS.md)、[证据阅读](specs/24_EVIDENCE_READING_WORKFLOW.md)、[搜索账户](specs/25_SEARCH_ACCOUNT_WORKFLOW.md)、[书架](specs/27_LIBRARY_RESEARCH_SHELF.md) |
| 权限和上传 | [上传审核](specs/23_UPLOAD_REVIEW_WORKFLOW.md)、[凭证边界](specs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md)、[管理员事务](specs/30_ADMIN_TRANSACTION_BOUNDARIES.md)、[上传隔离](specs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md) |

## 操作与开发手册

| 目的 | 文档 |
| --- | --- |
| 启动后端/恢复依赖 | [后端启动](development/backend/BACKEND_STARTUP.md) |
| 接口接入 | [基础 API](development/backend/FRONTEND_API_GUIDE.md)、[V2.1](development/backend/FRONTEND_API_GUIDE_V21.md)、[全栈契约](development/frontend/FULL_STACK_CONTRACT.md) |
| 前端规范 | [当前设计](development/frontend/DESIGN_SYSTEM.md)、[功能范围](development/frontend/FEATURE_SPEC.md)、[QA](development/frontend/QA_CHECKLIST.md) |
| 个人 AI | [前端使用](development/frontend/AI_API_INTEGRATION.md)、[后端配置](development/backend/AI_CONFIGURATION.md)、[发布契约](operations/10_RELEASE_AND_PERSONAL_AI.md) |
| 评测 | [检索评价](development/backend/SEARCH_EVALUATION.md)、[测试演示约定](operations/07_TEST_DEMO.md) |
| 服务器 | [部署与回滚](operations/11_SERVER_DEPLOYMENT.md)、[原始 PDF 交付](operations/13_ORIGINAL_PDF_DELIVERY.md) |
| 文档维护 | [目录迁移、命名和服务器同步](operations/DOCUMENTATION.md) |

## 汇报素材和历史

当前外观素材看 [2026-10-29](assets/report-20261029/README.md)；[2026-10-28](assets/report-20261028/README.md)为旧版对比。摄影许可见[图片来源](../frontend/public/images/SOURCES.md)。

[历史总索引](archive/README.md)收纳前后端阶段记录、旧版总报告/PPT、各轮外观与功能发布验收。历史中的“未接 API”“未交付 PDF”“未验证供应商”等结论只在原日期成立，最新事实请回到总报告和当前状态。
