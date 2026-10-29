# 当前项目状态与证据

核对日期：2026-10-29（北京时间）。应用基线 `d7cfc56`；本次仅整理文档。历史测试不自动覆盖后续外观提交。

## 本次在线只读核对

| 来源 | 结果 | 解释 |
| --- | --- | --- |
| Huawei current | `20261029T022557Z-d7cfc56` | 用户最新外观已经部署 |
| systemd | ScholarLens API 正常运行 | 本次文档同步不需要重启 |
| `/build-info.json` | `data_source=api`、`api_base=/api` | 正式数据构建；本次不重新构建 |
| `/api/stats` | 859 indexed，success 215、partial 644 | 论文数与交付质量状态 |
| `/api/metrics` | 49,420 chunks、384 维、MiniLM CPU ONNX、RRF k=60 | 正式库向量与融合配置 |
| `/api/metrics` | approved_uploads=0，P@5/nDCG@10=null | 隔离上传测试不当生产入库；尚无最终相关性分数 |
| `/api/data-quality` | 日期 231、年份 478 | 缺失保持缺失 |
| `/api/capabilities` | 三种检索、账户、上传解析、PDF 等 ready | 依赖声明不能代替每个业务请求验收 |
| `/api/capabilities` | 共享 AI、邮件找回 not_configured | 个人 API 另按账户配置；邮件真实投递未验收 |
| `/openapi.json` | FastAPI 0.2.1；65 路径、81 操作 | 接口规模快照，不等于本轮测试数量 |

当前构建资源为 `index-A4OqeJGO.css`、`index-wp995q4h.js`、`PaperConstellation-DLMLySgK.js`。本轮保留同步前 build-info 与资源字节哈希，用于同步后比对，不改变浏览器缓存或页面内容。

## 已有验证，保留日期和版本范围

- 助手修订：前端 38 项、结构、类型、生产构建，以及独立 Chrome 桌面与 390px 检查；后端 72 项协议/个人配置检查。实际范围见[助手验收](../archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md)。
- 真实供应商：华为云应用代码 + 临时账户库；指定模型两协议生成成功，单篇总结约 1052 字、3 条引用核验。未将密钥写入源码、用户库或报告；本轮未重发收费调用。
- 2026-10-28：独立后端 135 项、桌面 44 组、关系动效 13 项，以及上传/证据/账户专项，见[连续验证历史](../archive/releases-20261028-29/32_CONTINUOUS_VERIFICATION.md)。这些不是 `d7cfc56` 的新全量测试。
- 最新外观：按 Git 提交和 2026-10-29 已有有效截图核对；本轮不宣称重做应用验收。

## 本次文档检查与服务器同步

本轮检查相对链接、文档归档映射、兼容入口、Markdown 格式和图片有效性，并比较全部非文档受保护文件的 SHA-256。前端结构检查用于保证原来的文档入口仍在，不因整理而修改测试脚本。

服务器同步采用文档白名单，备份旧文档后更新 Markdown 和 `docs/assets/`。同步前后核对应用 current、API/Tunnel PID、build-info、静态资源和论文数。应用、用户库、环境、索引与模型不属于同步目标；同步不运行数据库操作，也不重启服务。

本地原始快照、检查和同步回执在工作区外层忽略目录 `output/docs-20261029/`，不将运行报告或凭据提交 Git。发布文档 revision 以该批提交与服务器同步回执为准，应用 release 仍单独记录。

## 尚未完成

邮件真实投递、原始 XML、中文正式入库/多语言语义、金标准相关性评价、托管 CI、并发容量和完整无障碍验证。详见[总报告](../PROJECT_REPORT.md)；不以历史性能或单次 HTTP 成功替代这些验收。
