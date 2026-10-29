# ScholarLens 桌面前后端验收

日期：2026-10-27。入口：`http://127.0.0.1:4173/`。后端提交：`63789ca`，2026-10-27 22:14:06 +08:00。

## 当前结果

- 前端 production build、15 项单元/接口契约测试、结构检查通过。
- 最终后端回归：**152 passed，1 deselected，0 skipped**，耗时 151.29 秒。包含真实向量维度/余弦分数、三模式、RRF融合、向量分页/年份、证据定位、认证账户、上传和完整交付数据回归。唯一未运行的是另起独立 API 的重启测试；不据此声明重启恢复已验收。
- 完整交付目录另跑 15 passed、1 deselected，验证源数据、可重复预处理、字段检索及独立模拟库隔离；独立 API 重启测试未运行，没有以其证明重启恢复。
- 真实 API 浏览器回归通过，含 BM25、片段高亮、建议、分页、年份过滤与排序、详情、游客收藏笔记、最近阅读、服务器随机换批、缺失论文、桌面与 390px 几何检查。
- 账户浏览器回归 13 项通过：注册登录、原生收藏/笔记/阅读持久化、退出撤销令牌、两用户隔离、重新登录恢复、服务端上传/鉴权 PDF 预览、普通账户管理员门槛、资料修改、研究对话创建/重开/删除、翻页搜索历史去重、服务器撤销会话后的自动退出和游客恢复、账户页面 390px 几何、本机 PDF 持久化/预览/审核隔离。两 QA 账户已停用，记录保留。
- 基础向量于 23:35:34 +08:00 完成发布：859 篇、49,420 个片段、384 维。关键词、语义、混合真实 HTTP 检索通过；语义与混合各 4 条证据逐字对应原文，片段详情可访问。
- 发布后浏览器强制要求向量 ready，语义/混合选项可用，页面排序与真实接口一致，翻页无重复；两模式均通过，桌面截图已检查。最终后端回归也已通过。

## 证据

| 证据 | 路径 |
| --- | --- |
| 真实 859 条逐条来源一致性、7 类字段查询、20 篇详情、11 类行为 | 后端 `backend/.runtime/desktop-data/v21-http-verification.json` |
| 账户浏览器结果及 QA 停用状态 | `output/api-integration/account-e2e-report.json` |
| 页面三模式结果与分页 | `output/api-integration/search-modes-browser.json`；必须检查 status，`unavailable-shown` 只证明正确禁用 |
| 账户与助手截图 | `output/api-integration/account-authenticated.png`、`account-mobile.png`、`assistant-evidence-desktop.png` |
| 最终三模式 HTTP 与证据定位 | `output/api-integration/final-live-check.json` |
| 最终后端回归 | 后端 `backend/.runtime/desktop-final-acceptance.log`（152 passed，1 deselected） |
| 完整交付回归 | 后端 `backend/.runtime/desktop-delivery-final.log` |
| 上传真实解析、鉴权、审批、DOCX、索引、向量与归档 | `backend/tests/test_desktop_upload.py` |
| 并发向量断点重放与输出一致性 | `backend/tests/test_vector_workers.py`、后端 `.runtime/vector-workers-tests.log` |
| 向量构建与发布 checkpoint | 后端 `backend/.runtime/desktop-vector-build.json` |

早期诊断日志可能包含测试启动器或缺少 fixture 导致的失败，不应代替上表中的修正后记录。测试启动器只在测试模块内适配默认 desktop aliases，保留显式 Settings 和 from_env 行为，不更改服务器正式 alias。

## 可复现命令

在项目根目录运行，服务需已经启动：

```powershell
npm run build
npm run test
npm run verify:structure
$env:SCHOLARLENS_REQUIRE_VECTORS='1'
npm run test:browser
Remove-Item Env:SCHOLARLENS_REQUIRE_VECTORS -ErrorAction SilentlyContinue
npm run test:account-browser
& dev/scholarlens-ir/zjl/backend/.venv/Scripts/python.exe tests/run-desktop-backend.py backend/tests --real-data-dir=backend/.runtime/desktop-delivery --real-alias=scholarlens-desktop-real --real-api=http://127.0.0.1:8000 --basetemp=backend/.runtime/pytest-desktop-acceptance -k 'not own_api_restart' -q --tb=short
```

`test:account-browser` 会创建专用普通 QA 账号并上传 `tests/fixtures/browser-upload.pdf`，最后停用 QA 账号，保留测试记录与原件。它使用独立 Chrome 临时 profile。后端集成测试使用临时 SQLite 和自行创建的测试 alias；完整交付目录是本机原数据及预处理结果的副本，不包含缺失的 PDF/XML。

## 启动与数据边界

运行 `powershell -NoProfile -File dev/start-desktop.ps1`，使用已有服务与索引，不自动导入重建、不停止无关进程。改前端代码后需先 build。Python 3.11 独立虚拟环境，Elasticsearch 8.19.23 ZIP 校验过 SHA-512，仅 loopback。Windows 脚本与 Chrome 测试未做 macOS 验收。

AI 与邮件配置保持空，外部生成和邮件投递不算通过；原859篇 PDF/XML 未交付，原 PDF 缺失状态保留。未修改真实用户角色、未创建默认管理员、未提交推送、未替换正式索引。`main` 工作树 `.git` 仍被其他分支共用，不能删除。
