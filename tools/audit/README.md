# ScholarLens 项目内审计工具链

这里是本项目专用的审计工具目录。依赖安装在 `tools/audit/node_modules`，不会修改全局 npm 配置，也不会上传扫描结果。

## 已纳入的工具

| 工具 | 用途 | 默认状态 |
| --- | --- | --- |
| Squirrelscan | 页面、SEO、无障碍和响应头初筛 | 本地安装，需显式指定目标后运行 |
| Playwright CLI | 独立浏览器流程和截图 | 本地安装，优先使用测试账号 |
| Lighthouse | 性能、SEO、可访问性基线 | 本地安装，默认只扫本机预览 |
| Semgrep | 代码执行、SQL 拼接、不安全反序列化、TLS、DOM/React 原始 HTML 等模式 | 复用已有命令，关闭 metrics，不上传云端 |
| Gitleaks 8.30.1 | 当前分支全部可达历史中的凭据线索 | `bin/gitleaks.exe`，官方 release SHA-256 校验，100% 脱敏 |
| pip-audit 2.9.0 | 后端锁文件已知依赖公告 | 独立 `.venv`，只查公告，不安装或升级应用依赖 |
| OWASP ZAP | 动态安全 | 不随项目启动；只在隔离测试环境被动运行 |

## 运行

局部工具可重建，命令不会改全局配置：

```powershell
python tools/audit/install-gitleaks.py
uv venv tools/audit/.venv
uv pip install --python tools/audit/.venv/Scripts/python.exe -r tools/audit/requirements.txt
```

Gitleaks 安装器固定官方 Windows x64 压缩包和可执行文件哈希，已有不同文件时拒绝覆盖。pip-audit 按完全锁定版本使用 `--no-deps --disable-pip`，查询 PyPI 公告会发送公开包名/版本，不发送源码或凭据。Semgrep 规则命中必须人工追踪输入边界；无命中不证明不存在漏洞。

在仓库根目录执行：

```powershell
pwsh -File tools/audit/run-audit.ps1 -TargetUrl http://127.0.0.1:4173
```

线上只读检查必须显式加 `-AllowLive`，脚本不会登录、提交表单、上传文件、删除数据或启动主动攻击扫描：

```powershell
pwsh -File tools/audit/run-audit.ps1 -TargetUrl https://scholarlens.lingion.cc.cd/ -AllowLive
```

报告输出到 `tools/audit/reports/<timestamp>/`，默认被 Git 忽略。缺少 Semgrep 或 Gitleaks 时会标记 `not_installed`，不会伪造通过。

## PDF 工作区与审核界面回归

复用本目录锁文件中局部 Playwright CLI 带入的 Playwright；使用已安装的 Chrome，无需全局安装。先启动真实 API 模式的前端预览，再在仓库根运行：

```powershell
$env:SCHOLARLENS_URL='http://127.0.0.1:4175'
node tools/audit/upload-workflow-browser.mjs
```

脚本只接受 localhost 地址，所有 API 请求被明确的 fixture 拦截，未知请求使检查失败。覆盖游客/研究账户/管理员权限界面、上传确认、状态与操作、失败恢复、串行刷新和账户失效隔离，报告和截图写入忽略目录。它验证界面与接口契约，不代表真实登录、PDF 解析、入库或生产审批已经端到端通过；真实 API 游客回归独立使用 `frontend/` 的 `npm run test:browser`。

## 证据与原文定位回归

在真实 API 模式的本机前端预览启动后运行：

```powershell
$env:SCHOLARLENS_URL='http://127.0.0.1:4175'
node tools/audit/evidence-workflow-browser.mjs
```

此脚本同样只接受 localhost，并显式拦截全部 API。覆盖逐字核对、Unicode 偏移、来源上下文、复制、笔记追加与容量、独立阅读页定位、坏定位、停止与迟到响应、账户失效隔离，以及同帧布局测量和滚动时的阅读位置保存。合成论文和账户仅用于界面契约验证，不会写入真实服务，也不代表供应商生成或真实账户持久化已通过。报告与桌面/390px 截图保存在忽略目录；契约及真实 API 验收见 `docs/24_EVIDENCE_READING_WORKFLOW.md`。

## 搜索记录流与账户读取回归

```powershell
$env:SCHOLARLENS_URL='http://127.0.0.1:4175'
node tools/audit/search-account-browser.mjs
```

仅访问 localhost，全部 API 使用明确 fixture，未知调用使检查失败。检查记录行、真实字段与零评分、条件移除和分页参数、游客收藏、登录输入和失败恢复、动态暂停、账户资料/通知/用户列表的失败重试、历史清空与迟到分页隔离，以及编辑资料不重复读取头像。不会向真实服务注册、登录、上传或清空历史；头像内容与账户写入均为接口 fixture，不能据此声称后端端到端通过。契约及发布证据见 `docs/25_SEARCH_ACCOUNT_WORKFLOW.md`。

## 研究书架与账户同步边界回归

```powershell
$env:SCHOLARLENS_URL='http://127.0.0.1:4175'
node tools/audit/library-shelf-browser.mjs
```

仅接受 localhost 并明确拦截所有 API，未知调用或浏览器异常使检查失败。覆盖分类、排序、相邻笔记、真实本机阅读位置、备份、账户首次读取失败/重试、同步失败保留和导出草稿、账户过期的迟到响应隔离及动态暂停；报告与桌面/390px截图写入忽略目录。不会操作生产账户或真实索引，不能代替真实后端写入和跨设备同步验收。说明与本轮证据见 `docs/27_LIBRARY_RESEARCH_SHELF.md`。

## 真实账户二次凭证与会话边界验收

```powershell
node tools/audit/account-security-browser.mjs
```

脚本不接受服务URL，也不使用 `SCHOLARLENS_URL`。它自行启动随机回环端口的隔离服务，以实例挑战核对身份后才写入；生产账户/工作区路由和SQLite是真实实现，论文为明确标注的单篇测试夹具。覆盖UI注册、笔记持久化、密码/停用确认错误的重试、真实撤销令牌清理、迟到401保护新会话、成功修改密码撤销全部会话和停用/用户隔离。测试服务不加载生产配置，不连接ES、邮件或供应商；结束时关闭本轮浏览器与服务，运行目录和报告保留在忽略路径。

旧 `frontend/tests/account-browser-smoke.mjs` 会写账户和上传，现强制要求匹配隔离实例挑战，禁止指向生产或普通本地代理。其搜索/上传旧流程尚未整体迁移，不作为本轮通过的证据。以上新工具只验收列明的账户和工作区边界，不能代替全产品端到端验收。见 `docs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md`。
