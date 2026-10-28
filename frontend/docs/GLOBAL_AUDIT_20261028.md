# 全局检查与优化验收（2026-10-28）

本轮输入是现有桌面网站、真实 API 契约及线上只读检查。用户要求全局检查并优化。工作已形成可审核的本地修改；未提交、推送或发布，公网网站仍运行原有代码。没有修改论文索引、原件、既有用户资料或其他业务服务。

## 已修复

| 范围 | 发现的问题 | 当前行为 |
| --- | --- | --- |
| 论文详情 | source ID 撑出横向滚动条，1440px 页面实际宽度1653px | 侧栏允许收缩，长编号和引用换行；1440/1366/1024以及390px回归均无横向溢出 |
| 分享检索链接 | page=1.5请求错误，page=999显示虚假的末页空结果 | 非整数/无穷/非法页码恢复1，超过真实结果范围自动定位末页并重新检索 |
| 语义检索 | authors等不支持字段可从深链接或建议进入 | 统一规范为all；保留关键词和混合模式的支持字段 |
| 搜索建议 | 无完整键盘操作；Escape后不能重新展开 | 上下键选择，Enter确认，Escape收起，下方向键重新展开；Tab能到最近搜索清空按钮；增加combobox/listbox语义并保留输入法行为 |
| 本地最近搜索 | 损坏或非数组数据可导致崩溃 | 只接收字符串数组，异常值回退为空，不清除其他本地数据 |
| 阅读导航 | 直接进入论文后返回可能离开本站 | 有应用内历史则返回，无历史则回检索页 |
| 文案与错误状态 | AI入口仍称预留/需配置；网络错误含本机开发提示 | AI入口显示可配置，解析状态中文，缺文本时引导原PDF；超时/网络错误使用面向使用者的提示 |
| 依赖 | React Router6出现2项moderate生产依赖告警 | 锁定react-router-dom7.18.5；本轮npm audit --omit=dev为0。此结果不代表完整安全审计 |
| 托管响应头 | 缺少浏览器边界，哈希资源缓存短 | 同源托管时补nosniff、SAMEORIGIN、Referrer-Policy及Permissions-Policy；哈希JS/CSS一年immutable，HTML保持no-cache |
| 私密缓存 | 账户、个人上传、对话和AI回答缺少统一缓存约束 | 相关API及带Authorization的API响应no-store；不缓冲PDF及流响应，Range206保留 |

保留冰岛照片、玻璃风格、现有CSS层及所有功能入口。主要优化桌面布局，390px仅回归。没有新加营销区块或动效层。

## 仓库交付完整性修复

最终Git检查发现，通用Python忽略规则lib/同时排除了frontend/src/lib下6个源码文件，其中5个是原有功能必需文件：evaluation.ts、pdfStore.ts、search.ts、serverHighlight.ts、storage.ts，另1个为本轮searchParams.ts。给此目录及其TypeScript源码增加精确例外，不取消Python lib忽略，不修改原有5个文件。6个文件现均可随本地待提交修改交付；尚未推送。

## 当前验证

- Node24.18.0 / React18.3.1 / Vite6.4.5。build、17项单元测试、结构检查通过。测试直接导入TypeScript，项目Node要求已标为 ^22.18.0 || >=24.0.0；Node22本轮未另行运行。
- 标准真实API浏览器回归通过：859篇、关键词magnetic实际61条、建议、分页、排序/年份、详情、收藏笔记、最近阅读、随机发现、空查询、缺失详情，以及semantic/hybrid实际排名与第二页。使用本机新前端通过独立SSH转发访问线上API，不是公网新版本验收。
- 交付目录原有node_modules仍为Router6，已npm ci --ignore-scripts按新锁文件更新到7.18.5；随后在交付目录重新build、17项单元和结构检查通过，npm安装审计0。API模式构建的JS/CSS与编辑源最终构建SHA-256一致。
- 14项账户浏览器流程通过：注册、退出及令牌失效、二用户隔离、收藏/笔记恢复、受控上传及鉴权PDF预览、普通用户管理门禁、资料更新、对话创建/删除、个人API会话保存与退出清理、搜索历史去重、本地PDF/review隔离。只创建本轮QA账户，两个账户均通过原停用接口清理200；未指定管理员。
- 手动Ego浏览器验证：1440/1366/1024和390px详情无横向溢出；非法page链接恢复、semantic作者字段归一；建议方向键/Enter/Escape重新展开与Tab操作；暂停动效不隐藏搜索。首页搜索框在1440x900首屏可见。原生PDF显示18页并切到第4页，彩色图可见。截图已人工查看。
- 后端最终针对性命令：test_ingest.py、test_pdf_access.py、test_web.py、test_desktop_workspace.py、test_personal_ai.py，排除需要ES夹具的personal_request，44 passed / 1 deselected。Ruff检查本轮web.py、test_web.py通过。
- 线上最终只读复核：ScholarLens API/隧道与WorkBuddy服务/隧道均active，PID与本轮开始一致；ES running，restart0，OOMKilled=false。没有生产代码发布或服务重启。

## 验证边界与未完成项

- 本机未运行Elasticsearch，扩展后端套件曾有1项ES集成夹具连接9200拒绝（同轮37项通过）。未连接真实索引刷测试；不能称全部后端集成测试通过。
- 首次附加测试误用了系统Python（缺ES包/ruff），随后改用现有backend/.venv；pytest全局临时目录权限失败后，使用本轮独立basetemp，未修改系统ACL或清除其他临时数据。最终44项结果来自正确环境。
- 浏览器核心回归在Escape修复后的源码上通过。随后将手动验证过的键盘流程加入tests/browser-smoke.mjs；最后一次运行因临时预览进程消失在首页加载阶段超时，未执行到新增断言。恢复SSH转发和Vite预览的命令被自动审批以blocked by policy拒绝，没有绕过重试。因此新增自动断言本轮未完成运行，保留真实失败边界。
- Ego任务空间5随后不可用，无法继续最后的故障注入/返回按钮人工验证，也无法对已消失空间执行finish或恢复窗口；未创建替代空间。错误提示及返回兜底目前有构建/静态验证，故障注入验收未完成。
- 个人API真实上游生成、邮件、XML原件和首次管理员指定仍待后续；本轮未配置真实供应商/密钥、发送邮件或更改权限。没有做压力、长稳或整机重启验收。

## 证据与回滚

本机证据：output/global-audit-20261028/，包含修改前备份、before/after截图、targeted-browser-report.json、keyboard-motion-report.json、motion-report.json与所有分轮脚本。output/api-integration/保留本轮账户与检索报告；原报告已先备份到before-browser-artifacts/。

前端编辑源为工作区根目录，交付源为dev/scholarlens-ir/zjl/frontend；按明确文件清单同步并逐文件SHA-256核对，不复制node_modules、dist、output、环境变量或用户数据。后端修改在交付源backend/web.py及backend/tests/test_web.py。对应备份位于本轮before-*目录，按文件选择恢复后重新build即可；不要整库reset。完整源同步清单记录在delivery-manifest.json。

Git发布规则见frontend/AGENTS.md：Do not commit, push, publish or modify a real index without explicit direction. 本轮结果停在本地可复核状态，后续发布需要明确指令。
