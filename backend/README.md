# ScholarLens 后端

FastAPI 0.2.1，连接 Elasticsearch 8.19.23、MiniLM CPU ONNX、SQLite 和独立 PDF 文件存储。当前正式网站已接通 859 篇论文与原始 PDF；旧 P0/Mock/V2 阶段快照保存在 `archive/20261026-27/`，其中“未交付/仅本机”等描述不能覆盖当前状态。

## 当前能力

- 六字段 BM25、跨字段查询、年份/排序/分页/高亮、建议/随机发现。
- 49,420 个基础向量片段、384 维 MiniLM、RRF(k=60)；上传独立关键词/向量代。
- 详情、正文窗口、原文片段、PDF Range、受限文本 DOCX 转换。
- 注册/登录/退出、会话撤销、用户资料/头像/改密/停用、角色管理。
- 收藏、分类、工作区/笔记、搜索/浏览历史、通知和对话。
- 登录上传、管理员审核、解析、独立索引、归档与所有权检查。
- 证据 Agent、引用核验、受限个人兼容 API、同源静态托管。

当前完整现状、数据边界和 PPT 材料看[项目总报告](../docs/PROJECT_REPORT_20261028.md)。

## 操作入口

- [Windows 启动/首次安装/模型/备份恢复](BACKEND_STARTUP.md)
- [基础接口手册](FRONTEND_API_GUIDE.md)和[V2.1 增补](FRONTEND_API_GUIDE_V21.md)
- [个人与服务器 AI 配置](AI_CONFIGURATION.md)
- [检索评价与旧基准的适用范围](SEARCH_EVALUATION.md)
- [服务器部署](../docs/11_SERVER_DEPLOYMENT.md)和[原始 PDF 交付](../docs/13_ORIGINAL_PDF_DELIVERY.md)

已有环境日常启动，在当前克隆根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/capabilities' | ConvertTo-Json -Depth 8
```

首次安装与重建索引需要明确准备数据；日常启动不重新导入 859 篇或重建向量。API 默认本机 8000，ES 默认 9200；生产端口独立。配置示例不含真实密钥。

## 协议与验证

- [论文数据格式](../docs/03_DATA_SCHEMA.md)、[HTTP API 契约](../docs/04_API_CONTRACT.md)、运行中的 `/openapi.json` 和 `/docs`。
- [最新持续验证](../docs/32_CONTINUOUS_VERIFICATION.md)、[审计边界](../docs/33_PASSIVE_CHECKS_AND_RESIDUALS.md)。
- [历史验收索引](archive/20261026-27/README.md)：包含真实 JSONL 接收、20 篇先行、全量导入、V2/V2.1 结果。

不要对生产服务运行历史固定数据集测试；不要把 `pytest backend/tests` 的历史依赖条件忽略。当前独立模块清单见 `infra/ci/verify.yml`，真实 ES/MiniLM 上传链入口见[隔离验收](../docs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md)。CI 尚未启用，不能用本机结果代替三平台 Actions。

## 数据与故障边界

正式 Mapping 为 `papers-p0-v1`，BM25(k1=1.2,b=0.75)、单分片/0副本，动态字段严格。正式 JSONL 不改，严重乱码正文隔离而保留元数据；新 generation 完整成功后才切 alias，旧代保留。搜索/正文字符偏移不等于原 PDF 页码。

SQLite 使用一致性 backup，不在写入时只复制主文件而丢掉 WAL。账户、文件和对话按当前用户拥有者隔离；管理员不自动拥有他人的私人对话。原始 PDF 不由正文重新生成。扫描件 DOCX 需要 OCR；上传默认可使用本地文本解析，不伪造学术字段。

真实个人 AI、邮件和 XML 当前仍分别保留依赖边界。现有公开网站状态以 API/发布证据为准，任何单次 HTTP 200 都不能替代端到端验收。
