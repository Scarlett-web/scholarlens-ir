# 文档维护与本次整理记录

整理日期：2026-10-29。范围仅 Markdown、目录和文档截图；保留用户最新外观 `d7cfc56`，不修改代码、依赖、配置、数据库、索引和运行资源。

## 固定入口与命名

- 根 README 负责介绍与指路；`docs/README.md` 为唯一分类目录。
- `docs/PROJECT_REPORT.md`、`docs/PPT_OUTLINE.md`、`docs/operations/STATUS.md` 固定路径持续更新，不为每次修订创建新“当前版”。
- `specs/` 放规则，`operations/` 放操作，`development/` 放开发手册，`assets/` 放有日期/来源的素材，`archive/` 放过去的结论。
- 历史测试、接口规模、真实供应商和公网检查分别标注日期、版本与环境；不相加为一个测试总数。

## 本次做了什么

集中迁移 68 份文档，补充固定总报告、22 页 PPT 底稿、当前状态和最新有效素材；修正旧的 API 未接通、AI 未验收、DOCX 主下载、侧栏导航和旧发布版本等描述。旧报告和失败证据继续归档，未删除项目历史。

六份 `frontend/docs/` 短跳转保留给未修改的结构检查；`docs/03_DATA_SCHEMA.md` 保留给项目指令。模块 README 只指向集中正文，避免再生另一套手册。运行时 Skill、AGENTS 与摄影许可文件保留原位置，不当普通说明迁走。

## 服务器文档同步

文档同步与应用部署分开。Git 当前 Markdown 和 `docs/assets/` 镜像到服务器独立版本目录 `/opt/scholarlens/documentation/releases/`，入口为 `/opt/scholarlens/documentation/current`。先归档旧文档及旧入口，校验文件清单和 SHA-256 后再原子切换文档入口。文档修订号记录在服务器回执；运行 release 仍为 `20261029T022557Z-d7cfc56`，其发布清单和原目录完整保留。

本轮不构建、不切应用 current、不重启 API/Tunnel/ES，不读取或复制用户库和环境文件。同步前后核对 current、PID、构建和静态资源字节哈希、论文数。失败按文档备份恢复，不能借文档整理执行数据回滚。

## 检查与恢复材料

整理前全部跟踪 Markdown 已备份到本机忽略目录 `output/docs-20261029/documents-before.tar.gz`；非文档文件有 SHA-256 基线，图片有原图来源和衍生图记录。文档链接检查、结构校验、Git 差异范围和服务器同步回执均保存在同一忽略目录，不把凭据或运行报告上传源码。

## 旧路径到新路径

下表用于找原记录，旧相对链接已按新目录更新；七个兼容入口除外，其余正文只保留一份。

| 原路径 | 集中路径 |
| --- | --- |
| `backend/AI_CONFIGURATION.md` | [docs/development/backend/AI_CONFIGURATION.md](../development/backend/AI_CONFIGURATION.md) |
| `backend/BACKEND_STARTUP.md` | [docs/development/backend/BACKEND_STARTUP.md](../development/backend/BACKEND_STARTUP.md) |
| `backend/FRONTEND_API_GUIDE.md` | [docs/development/backend/FRONTEND_API_GUIDE.md](../development/backend/FRONTEND_API_GUIDE.md) |
| `backend/FRONTEND_API_GUIDE_V21.md` | [docs/development/backend/FRONTEND_API_GUIDE_V21.md](../development/backend/FRONTEND_API_GUIDE_V21.md) |
| `backend/SEARCH_EVALUATION.md` | [docs/development/backend/SEARCH_EVALUATION.md](../development/backend/SEARCH_EVALUATION.md) |
| `backend/archive/20261026-27/BACKEND_V2_GOAL.md` | [docs/archive/backend/20261026-27/BACKEND_V2_GOAL.md](../archive/backend/20261026-27/BACKEND_V2_GOAL.md) |
| `backend/archive/20261026-27/BACKEND_V2_VERIFICATION.md` | [docs/archive/backend/20261026-27/BACKEND_V2_VERIFICATION.md](../archive/backend/20261026-27/BACKEND_V2_VERIFICATION.md) |
| `backend/archive/20261026-27/FRONTEND_HANDOFF.md` | [docs/archive/backend/20261026-27/FRONTEND_HANDOFF.md](../archive/backend/20261026-27/FRONTEND_HANDOFF.md) |
| `backend/archive/20261026-27/README.md` | [docs/archive/backend/20261026-27/README.md](../archive/backend/20261026-27/README.md) |
| `backend/archive/20261026-27/REAL_DATA_GOAL.md` | [docs/archive/backend/20261026-27/REAL_DATA_GOAL.md](../archive/backend/20261026-27/REAL_DATA_GOAL.md) |
| `backend/archive/20261026-27/REAL_DATA_VERIFICATION.md` | [docs/archive/backend/20261026-27/REAL_DATA_VERIFICATION.md](../archive/backend/20261026-27/REAL_DATA_VERIFICATION.md) |
| `backend/archive/20261026-27/V21_PARITY_GOAL.md` | [docs/archive/backend/20261026-27/V21_PARITY_GOAL.md](../archive/backend/20261026-27/V21_PARITY_GOAL.md) |
| `backend/archive/20261026-27/V21_PARITY_VERIFICATION.md` | [docs/archive/backend/20261026-27/V21_PARITY_VERIFICATION.md](../archive/backend/20261026-27/V21_PARITY_VERIFICATION.md) |
| `backend/archive/20261026-27/VERIFICATION.md` | [docs/archive/backend/20261026-27/VERIFICATION.md](../archive/backend/20261026-27/VERIFICATION.md) |
| `backend/archive/20261026-27/VERIFICATION_STAGE2.md` | [docs/archive/backend/20261026-27/VERIFICATION_STAGE2.md](../archive/backend/20261026-27/VERIFICATION_STAGE2.md) |
| `docs/01_REQUIREMENTS.md` | [docs/specs/01_REQUIREMENTS.md](../specs/01_REQUIREMENTS.md) |
| `docs/02_ARCHITECTURE.md` | [docs/specs/02_ARCHITECTURE.md](../specs/02_ARCHITECTURE.md) |
| `docs/03_DATA_SCHEMA.md` | [docs/specs/03_DATA_SCHEMA.md](../specs/03_DATA_SCHEMA.md) |
| `docs/04_API_CONTRACT.md` | [docs/specs/04_API_CONTRACT.md](../specs/04_API_CONTRACT.md) |
| `docs/05_UI_SPEC.md` | [docs/specs/05_UI_SPEC.md](../specs/05_UI_SPEC.md) |
| `docs/06_TEAM_PLAN.md` | [docs/specs/06_TEAM_PLAN.md](../specs/06_TEAM_PLAN.md) |
| `docs/07_TEST_DEMO.md` | [docs/operations/07_TEST_DEMO.md](07_TEST_DEMO.md) |
| `docs/08_MEETING_DECISIONS.md` | [docs/specs/08_MEETING_DECISIONS.md](../specs/08_MEETING_DECISIONS.md) |
| `docs/10_RELEASE_AND_PERSONAL_AI.md` | [docs/operations/10_RELEASE_AND_PERSONAL_AI.md](10_RELEASE_AND_PERSONAL_AI.md) |
| `docs/11_SERVER_DEPLOYMENT.md` | [docs/operations/11_SERVER_DEPLOYMENT.md](11_SERVER_DEPLOYMENT.md) |
| `docs/12_RELEASE_ACCEPTANCE.md` | [docs/archive/releases-20261028-29/12_RELEASE_ACCEPTANCE.md](../archive/releases-20261028-29/12_RELEASE_ACCEPTANCE.md) |
| `docs/13_ORIGINAL_PDF_DELIVERY.md` | [docs/operations/13_ORIGINAL_PDF_DELIVERY.md](13_ORIGINAL_PDF_DELIVERY.md) |
| `docs/18_AGENT_RUNTIME_CONTRACT.md` | [docs/specs/18_AGENT_RUNTIME_CONTRACT.md](../specs/18_AGENT_RUNTIME_CONTRACT.md) |
| `docs/22_RESEARCH_MAP_AND_METRICS.md` | [docs/specs/22_RESEARCH_MAP_AND_METRICS.md](../specs/22_RESEARCH_MAP_AND_METRICS.md) |
| `docs/23_UPLOAD_REVIEW_WORKFLOW.md` | [docs/specs/23_UPLOAD_REVIEW_WORKFLOW.md](../specs/23_UPLOAD_REVIEW_WORKFLOW.md) |
| `docs/24_EVIDENCE_READING_WORKFLOW.md` | [docs/specs/24_EVIDENCE_READING_WORKFLOW.md](../specs/24_EVIDENCE_READING_WORKFLOW.md) |
| `docs/25_SEARCH_ACCOUNT_WORKFLOW.md` | [docs/specs/25_SEARCH_ACCOUNT_WORKFLOW.md](../specs/25_SEARCH_ACCOUNT_WORKFLOW.md) |
| `docs/26_AGENT_PROVIDER_BOUNDARIES.md` | [docs/specs/26_AGENT_PROVIDER_BOUNDARIES.md](../specs/26_AGENT_PROVIDER_BOUNDARIES.md) |
| `docs/27_LIBRARY_RESEARCH_SHELF.md` | [docs/specs/27_LIBRARY_RESEARCH_SHELF.md](../specs/27_LIBRARY_RESEARCH_SHELF.md) |
| `docs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md` | [docs/specs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md](../specs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md) |
| `docs/29_GOAL_REQUIREMENTS_AND_EVIDENCE.md` | [docs/archive/releases-20261028-29/29_GOAL_REQUIREMENTS_AND_EVIDENCE.md](../archive/releases-20261028-29/29_GOAL_REQUIREMENTS_AND_EVIDENCE.md) |
| `docs/30_ADMIN_TRANSACTION_BOUNDARIES.md` | [docs/specs/30_ADMIN_TRANSACTION_BOUNDARIES.md](../specs/30_ADMIN_TRANSACTION_BOUNDARIES.md) |
| `docs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md` | [docs/specs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md](../specs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md) |
| `docs/32_CONTINUOUS_VERIFICATION.md` | [docs/archive/releases-20261028-29/32_CONTINUOUS_VERIFICATION.md](../archive/releases-20261028-29/32_CONTINUOUS_VERIFICATION.md) |
| `docs/33_PASSIVE_CHECKS_AND_RESIDUALS.md` | [docs/archive/releases-20261028-29/33_PASSIVE_CHECKS_AND_RESIDUALS.md](../archive/releases-20261028-29/33_PASSIVE_CHECKS_AND_RESIDUALS.md) |
| `docs/34_VISUAL_GLASS_20261028.md` | [docs/archive/releases-20261028-29/34_VISUAL_GLASS_20261028.md](../archive/releases-20261028-29/34_VISUAL_GLASS_20261028.md) |
| `docs/35_GLASS_RELEASE_ACCEPTANCE_20261028.md` | [docs/archive/releases-20261028-29/35_GLASS_RELEASE_ACCEPTANCE_20261028.md](../archive/releases-20261028-29/35_GLASS_RELEASE_ACCEPTANCE_20261028.md) |
| `docs/36_RESEARCH_USABILITY_AND_CHINESE_READINESS.md` | [docs/archive/releases-20261028-29/36_RESEARCH_USABILITY_AND_CHINESE_READINESS.md](../archive/releases-20261028-29/36_RESEARCH_USABILITY_AND_CHINESE_READINESS.md) |
| `docs/37_SEARCH_RESULTS_POLISH.md` | [docs/archive/releases-20261028-29/37_SEARCH_RESULTS_POLISH.md](../archive/releases-20261028-29/37_SEARCH_RESULTS_POLISH.md) |
| `docs/38_ASSISTANT_CHAT_AND_API.md` | [docs/archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md](../archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md) |
| `docs/39_PREMIUM_GLASS_AND_3D_UX.md` | [docs/archive/releases-20261028-29/39_PREMIUM_GLASS_AND_3D_UX.md](../archive/releases-20261028-29/39_PREMIUM_GLASS_AND_3D_UX.md) |
| `docs/DOCUMENT_CLEANUP_20261028.md` | [docs/archive/releases-20261028-29/DOCUMENT_CLEANUP_20261028.md](../archive/releases-20261028-29/DOCUMENT_CLEANUP_20261028.md) |
| `docs/PPT_OUTLINE_20261028.md` | [docs/archive/releases-20261028-29/PPT_OUTLINE_20261028.md](../archive/releases-20261028-29/PPT_OUTLINE_20261028.md) |
| `docs/PROJECT_REPORT_20261028.md` | [docs/archive/releases-20261028-29/PROJECT_REPORT_20261028.md](../archive/releases-20261028-29/PROJECT_REPORT_20261028.md) |
| `frontend/docs/AI_API_INTEGRATION.md` | [docs/development/frontend/AI_API_INTEGRATION.md](../development/frontend/AI_API_INTEGRATION.md) |
| `frontend/docs/BACKEND_INTEGRATION.md` | [docs/development/frontend/BACKEND_INTEGRATION.md](../development/frontend/BACKEND_INTEGRATION.md) |
| `frontend/docs/DESIGN_SKILL_AUDIT.md` | [docs/development/frontend/DESIGN_SKILL_AUDIT.md](../development/frontend/DESIGN_SKILL_AUDIT.md) |
| `frontend/docs/DESIGN_SYSTEM.md` | [docs/development/frontend/DESIGN_SYSTEM.md](../development/frontend/DESIGN_SYSTEM.md) |
| `frontend/docs/FEATURE_SPEC.md` | [docs/development/frontend/FEATURE_SPEC.md](../development/frontend/FEATURE_SPEC.md) |
| `frontend/docs/FULL_STACK_CONTRACT.md` | [docs/development/frontend/FULL_STACK_CONTRACT.md](../development/frontend/FULL_STACK_CONTRACT.md) |
| `frontend/docs/QA_CHECKLIST.md` | [docs/development/frontend/QA_CHECKLIST.md](../development/frontend/QA_CHECKLIST.md) |
| `frontend/docs/archive/20261027-28/DESKTOP_API_ACCEPTANCE.md` | [docs/archive/frontend/20261027-28/DESKTOP_API_ACCEPTANCE.md](../archive/frontend/20261027-28/DESKTOP_API_ACCEPTANCE.md) |
| `frontend/docs/archive/20261027-28/GLOBAL_AUDIT_20261028.md` | [docs/archive/frontend/20261027-28/GLOBAL_AUDIT_20261028.md](../archive/frontend/20261027-28/GLOBAL_AUDIT_20261028.md) |
| `frontend/docs/archive/20261027-28/QA_CHECKLIST_20261027.md` | [docs/archive/frontend/20261027-28/QA_CHECKLIST_20261027.md](../archive/frontend/20261027-28/QA_CHECKLIST_20261027.md) |
| `frontend/docs/archive/20261027-28/README.md` | [docs/archive/frontend/20261027-28/README.md](../archive/frontend/20261027-28/README.md) |
| `frontend/docs/archive/20261027-28/UI_AUDIT_20261027.md` | [docs/archive/frontend/20261027-28/UI_AUDIT_20261027.md](../archive/frontend/20261027-28/UI_AUDIT_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_CLEAR_GLASS_20261027.md` | [docs/archive/frontend/20261027-28/UI_CLEAR_GLASS_20261027.md](../archive/frontend/20261027-28/UI_CLEAR_GLASS_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_GLACIER_OBSERVATORY_20261027.md` | [docs/archive/frontend/20261027-28/UI_GLACIER_OBSERVATORY_20261027.md](../archive/frontend/20261027-28/UI_GLACIER_OBSERVATORY_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_MOTION_20261027.md` | [docs/archive/frontend/20261027-28/UI_MOTION_20261027.md](../archive/frontend/20261027-28/UI_MOTION_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_READING_DECK_20261027.md` | [docs/archive/frontend/20261027-28/UI_READING_DECK_20261027.md](../archive/frontend/20261027-28/UI_READING_DECK_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_REFRESH_20261027.md` | [docs/archive/frontend/20261027-28/UI_REFRESH_20261027.md](../archive/frontend/20261027-28/UI_REFRESH_20261027.md) |
| `frontend/docs/archive/20261027-28/UI_REFRESH_V6_20261027.md` | [docs/archive/frontend/20261027-28/UI_REFRESH_V6_20261027.md](../archive/frontend/20261027-28/UI_REFRESH_V6_20261027.md) |
| `frontend/docs/archive/20261027-28/UX_POLISH_20261028.md` | [docs/archive/frontend/20261027-28/UX_POLISH_20261028.md](../archive/frontend/20261027-28/UX_POLISH_20261028.md) |
