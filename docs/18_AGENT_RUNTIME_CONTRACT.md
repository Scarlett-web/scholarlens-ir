# 证据智能体运行契约

输入：当前问题、问答/总结/比较/证据检索操作、至多 10 篇论文范围，以及本次登录用户的个人 API 配置。输出：真实来源片段、已校验的回答、实际工具执行记录和依赖状态。负责人：项目维护者。

## 必须成立的行为

1. 运行时读取项目 Skill 和 Workflow。Workflow 限制查询数、工具调用次数、证据数量和修复次数；工具不能由论文、用户问题或模型返回任意扩展。
2. 有模型时生成结构化的检索计划，在白名单内执行；计划无效时回到用户原问题，并把降级记入轨迹。无模型也能检索原文。
3. 所有调用记录真实开始/结束时间、成功/空结果/失败状态及结果数量。没有调用的步骤不能显示“完成”；不记录密钥、端点或模型内部推理。
4. 证据必须来自当前范围的真实原文片段。生成后校验引用 ID、逐字引文和比较覆盖；引用失败至多修复一次，仍失败只显示原文，不泄漏未校验草稿。
5. 个人 API 配置保持请求隔离、公共 HTTPS 和 DNS 固定保护。模型错误保留已经检索到的证据。没有新数据库迁移、索引写入或全局工具配置。
6. 提供可运行的本地 stdio MCP 插件，暴露论文检索、详情和原文证据等只读工具，以及 Skill/Workflow 资源。使用官方 Python SDK，依赖只装在 `tools/agent/.venv`，不监听公网端口，不接受密钥或任意 URL。
7. Harness 读取案例清单，实际执行并输出可解析结果和失败退出码。模型部分使用明确标记的受控响应；MCP 协议验收必须经过真实 SDK 客户端与子进程，不把 JSON 配置当作运行证明。
8. 浏览器的证据模式和回答模式使用同一运行入口。轨迹、来源、依赖降级和错误均可读；保留现有账户、会话与论文操作。

## 验收范围

包括：范围校验、无模型检索、模型检索计划、错误计划降级、空结果、非法引用不泄漏、比较逐篇覆盖、依赖故障保留证据、调用预算、个人配置隔离、真实 MCP initialize/list/call/resource 和现有浏览器业务回归。

真实个人供应商成功生成需要用户自行配置 API；隔离模型夹具不证明供应商、模型或网络可用。生产环境仅部署验证后的代码并检查页面/只读 API；不在生产进行主动扫描或创建审计索引。

## 实现与本轮检查

- `backend/agent_runtime.py` 执行真实回调；已删除旧的预填完成轨迹模块。默认最多 3 次检索、10 次工具调用、10 段证据、1 次引用修复。模型 HTTP 调用使用剩余时间预算，各步骤和响应读取检查 120 秒截止时间；同步底层 I/O 的退出仍受各客户端超时控制，不能将其描述为可中断任意系统调用的沙箱。
- 问答、总结、比较和 `operation=evidence` 共用 `/api/agent/run`。证据模式不调用模型；比较证据不全时保留已有片段但不生成结论；供应商故障和引用失败均不返回未验证草稿。已保存对话可重新打开失败时的证据，遵守账户所有权。
- 前端显示真实步骤、结果数量、完成/空结果/错误状态和耗时。个人 API 填写状态不等同于真实供应商验收。
- 本轮后端针对性检查 38 项通过，另 1 项需要本机 Elasticsearch 的旧个人配置集成测试未执行；前端 17 项测试、build、结构检查和本机真实 API 浏览器回归通过。没有将历史全量结果移用为本轮结果。
- Harness 8 个案例实际运行并全部通过，JSON、JUnit 与原始输出位于本机忽略目录 `tools/agent/reports/`。MCP 通过真实 SDK 客户端与 stdio 子进程的 initialize、工具调用、资源、提示词以及私有 ID/非法参数拒绝检查；首次 HTTP 数据源明确为受控夹具，真实线上只读结果在发布记录中单独登记。

## 局部安装和运行

在仓库根目录执行（Windows）：

```powershell
uv venv tools/agent/.venv
uv pip install --python tools/agent/.venv/Scripts/python.exe -r tools/agent/requirements.txt
.\tools\agent\.venv\Scripts\python.exe tools/agent/mcp_smoke.py
.\backend\.venv\Scripts\python.exe tools/agent/run_harness.py
```

Linux/macOS 对应解释器为 `.venv/bin/python`。可选 MCP SDK 不加入 Web 主进程依赖，不安装到全局。`mcp_smoke.py --api-base-url http://127.0.0.1:4174` 可检查已连接真实后端的本机预览；只发送只读请求。

外部 MCP 客户端可参考 `agent/mcp.json`。该示例以本仓库为工作目录；客户端从其他目录启动时，须把 `tools/agent/launch_mcp.py` 改成这份克隆的绝对路径，Python 命令也按本机安装位置配置。启动器自行定位项目，不依赖外部 cwd。插件仅连接明确指定的本机 HTTP origin，不监听公网，不接收登录令牌和供应商密钥。

应用发布包必须包含 `agent/workflows/evidence-grounded-answer.yaml` 和 `.agents/skills/scholarlens-evidence-agent/SKILL.md`，切换版本前运行 `resources()` 检查。MCP 的局部虚拟环境、Harness 运行输出、用户库和密钥不打包。

## 当时的后续计划（历史快照）

此处保留运行时初次更新后的计划时间点。棱镜、关系图、专注阅读、评测图形和上传时间线后来已有对应实现及限定验收，最新以[项目总报告](PROJECT_REPORT_20261028.md)、[持续验证](32_CONTINUOUS_VERIFICATION.md)和[剩余边界](33_PASSIVE_CHECKS_AND_RESIDUALS.md)为准。不能据本页旧release描述当前线上，也不据后续发布声称全局审计或真实个人模型生成全部完成。

## 线上发布记录（2026-10-28 11:06 北京时间）

- 已推送应用提交 `0d3be7bad096ca70b7d5f92253af4876fab97801` 至 `origin/zjl`，部署至 https://scholarlens.lingion.cc.cd/ 。当前 release 为 `/opt/scholarlens/releases/20261028T030645Z-0d3be7b`。
- 保留上一 release `20261028T023631Z-a73155e`。一致性 SQLite 备份、环境副本与回滚脚本位于 `/opt/scholarlens/backups/20261028T030645Z-0d3be7b`，目录 0700、数据库和环境副本 0600，备份库完整性检查通过。回滚只切换应用并重启 ScholarLens API，不覆盖用户库。
- 发布包 1,992,907 字节、205 个文件逐一 SHA-256 校验；包含实际 Workflow/Skill，切换前 `resources()` 校验通过。服务器未安装 MCP SDK、未升级主应用依赖。
- 切换前后均为 859 篇论文、24 个用户记录。环境哈希一致；搜索库容器及隧道 PID/启动时间不变。应用和隧道 active，应用 `NRestarts=0`，ES 无 OOM、无重启。
- 公网 JS `index-DVmbihDe.js`、CSS `index-znisI4n3.css` 哈希与本地构建一致。真实关键词 `magnetic` 返回 61 条；原 PDF Range 返回 206、`%PDF-` 及合法 Content-Range。
- 公网 `operation=evidence` 返回 5 段真实证据、Agent 0.2.0 和实际检索/原文核对两步，模型为 `not_called`。MCP 官方 SDK 客户端通过本机预览代理实际检索线上论文、读取片段和运行证据模式；三工具、两资源、一提示词及私有 ID/参数边界均通过。
- Ego 独立浏览器实际输入问题、提交、展开执行记录，得到 5 张原文卡片、2 个完成步骤，无页面报错或横向溢出。登录页显示“欢迎回来”，首页 1366×768 搜索框首屏可见；没有进行生产账户注册、写入或扫描。Ego 截图接口两次超时，未把未生成的截图标成视觉验收通过；DOM、实际交互及原有浏览器布局回归作为本轮证据。
- 本次追加 6 项旧 RAG 适配器兼容测试通过；连同上述 38 项针对性测试共 44 项通过，不等同于后端全量。完整账户浏览器回归本轮未在生产执行；认证、个人配置及对话所有权使用隔离 HTTP/SQLite 夹具验证。
- 本机预览源与交付仓库同步，构建资源一致。本机证据目录 `C:/Users/lenovo/Desktop/zjl/output/deploy-runtime-20261028/`；MCP 真实 API 验收报告位于忽略目录 `tools/agent/reports/mcp-real-api.json`。本发布记录只改文档，无需再重启服务。
