# ScholarLens 全局审计、Agent 与设计优化（2026-10-28）

本轮结合两份外部聊天记录完成：

- `ChatGPT_网站审计工具推荐_20261028-0844.pdf`：本地优先的 Playwright、Semgrep、Gitleaks、Lighthouse 组合，Squirrelscan 做页面初筛，ZAP 仅在隔离环境被动使用。
- `ChatGPT_设计优化建议_20261028-0922.pdf`：深色冰川外壳、明亮冰纸内容、首页研究棱镜、论文关系空间、阅读页专注模式，以及把 AI 助手改为证据台。

附件内容是审计参考，不是对生产环境进行主动攻击或修改的授权。本项目继续保留原用户、论文、PDF、索引、模型和密钥边界。

## 已落地

### 项目内工具链

工具安装在 `tools/audit/node_modules`，没有修改全局 npm 配置：

- Squirrelscan 0.0.138：页面初筛。当前 npm 包的 Windows native binary 未完成安装，因此运行器会明确标记 `not_available`，不冒充通过。
- Playwright CLI 0.1.22：独立浏览器操作和截图。
- Lighthouse 13.6.0：本机预览或明确允许的线上只读性能基线。
- Semgrep：只探测机器上已有命令，扫描配置位于 `tools/audit/semgrep.yml`，不上传云端。
- Gitleaks：只探测机器上已有命令，缺失时报告 `not_installed`。
- OWASP ZAP：未自动启动，项目配置中明确关闭，等待隔离测试环境。

运行入口是 `tools/audit/run-audit.ps1`。默认目标是 `http://127.0.0.1:4173`，线上域名必须显式传 `-AllowLive`，且只做低频只读页面检查。报告写入被忽略的 `tools/audit/reports/`。

### 证据 Agent

新增 `backend/agent.py` 与 `/api/agent/run`：

1. route：确定问答、总结或比较任务和论文范围；
2. retrieve_evidence：从真实索引取片段，并复核原文定位；
3. grounded_answer：使用用户本次请求的个人 API 生成回答；
4. citation_guard：只保留本次证据中的引用。

响应会返回 Agent 名称、版本、工作流、工具名、步骤状态和证据数量。没有个人 API 时，原文证据检索仍可用；不会用猜测补齐答案。项目内的 `agent/mcp.json`、`agent/workflows/evidence-grounded-answer.yaml`、`agent/harness/cases.json` 和 `.agents/skills/scholarlens-evidence-agent/SKILL.md` 分别记录 MCP 边界、工作流、验收夹具和 Agent 行为约束。MCP 不接收密钥，不暴露公网；ZAP 默认关闭。

前端助手改名为“证据助手”，回答中增加可展开的 Agent 执行轨迹，展示检索、核对、生成、引用四步，不把它伪装成无来源的通用聊天机器人。

### 设计优化

- 外层照片降亮度并增加深色冰川夜环境，侧栏改为深色透明玻璃。
- 主工作区保留明亮冰纸表面，阅读页和正文不被背景噪声干扰。
- 证据助手增加状态胶囊、检索/核对/引用能力提示和可读的步骤追踪。
- 保留现有暂停动效、系统减少动画和移动端静态降级。

## 验证

本轮至少执行：

- `npm run build`
- `npm run test`
- `npm run verify:structure`
- 后端 Agent 纯函数测试及现有后端针对性测试
- 工具版本和项目内路径检查

本轮实际结果：前端 build、17 项单元测试、结构检查、真实 API 浏览器回归和账户浏览器回归均通过；账户回归 17 项全部通过。后端 `test_agent.py` 与不依赖 Elasticsearch 的个人 API 安全测试共 14 项通过，包括新接口的 HTTP 契约、证据数与引用数分离、无证据禁止调用模型及操作范围校验。检索和模型在这 4 项 HTTP 验收中使用隔离夹具，不能据此声称真实模型生成已通过。另 1 项需要本机 Elasticsearch 的集成测试因 9200 未监听未执行，不能把它写成后端全量通过。pytest 默认临时目录曾因权限报错，使用项目输出目录中的独立临时目录后重跑通过，未修改全局权限。项目内审计运行器在本机预览 `http://127.0.0.1:4174` 上完成 npm audit、Semgrep（16 条规则命中，0 个解析错误）和 Lighthouse；本轮 manifest 位于 `tools/audit/reports/20261028-102925/manifest.json`。审计脚本已改为使用 Semgrep `--json-output`，报告文件可直接解析。Gitleaks 未安装，Squirrelscan npm 包已在项目内但 Windows native binary 不可用，均已在 manifest 中如实标记。

线上更新仍遵守既有流程：验证后提交并推送到 `origin/zjl`，应用修改再部署至既有华为云服务，保留上一 release、SQLite 一致性备份和环境副本；仅文档变化不重启。

## 未覆盖与风险

- 本轮没有对生产执行 ZAP 主动扫描、模糊测试、爆破、越权尝试或写操作。
- Squirrelscan 的 native binary 在 Windows 本地安装不完整，需在官方安装器可用或 Linux/WSL 隔离环境补齐后再运行。
- 真实个人 API 生成仍取决于用户在账户页填写的 URL、模型和密钥；密钥只保留在当前会话。
- 当前是复用 RAG 的有界工作流；MCP 文件、Skill 与 Harness 是项目内声明和验收材料，没有启动新的 MCP 服务或通用自主代理。
- Semgrep 当前只有调试输出规则，16 条命中属于人工复核线索，不能据此宣称已完成全面漏洞扫描。Lighthouse 本机移动模拟基线：性能 79、可访问性 100、最佳实践 100、SEO 91；结果会随设备和网络变化。
