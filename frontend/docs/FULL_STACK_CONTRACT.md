# ScholarLens 完整工作流联调

本机验收日期：2026-10-27。前端为项目根目录 React/Vite，后端为 `dev/scholarlens-ir/zjl` FastAPI，SQLite 存账户数据，Elasticsearch 存论文与独立向量索引。

## 接入基线

后端已快进到用户 22:14:06 +08:00 的提交 `63789ca`（`feat(backend): complete V2.1 workflows and AI contracts`）。`backend/accounts.py` 保持该版本原样；注册、登录、退出复用上游实现。未提交或推送本地修改，未更改正式索引别名。

| 页面与功能 | 接口及实际行为 |
| --- | --- |
| 论文检索、建议、详情、探索 | `/search`、`/suggest`、`/papers/{id}`、`/discover/random`；使用真实 859 篇数据，换一批从服务器重取；排序映射为 `year_desc/year_asc` |
| 注册、登录、退出 | `/auth/register`、`/auth/login`、`/auth/logout`、`/auth/me`；令牌仅在 sessionStorage；退出会撤销服务器令牌，401 清理当前会话 |
| 账户资料与安全 | `/me/profile`、`/me/avatar`、`/auth/password`、`/auth/deactivate`、邮箱验证与找回密码；修改密码会要求重新登录，停用需用户名、密码及确认 |
| 账户阅读空间 | `/me/workspace` 聚合收藏、分类、笔记及最近阅读；复用原生 favorites、favorite_folders、browsing_history 表；事务版本号防覆盖；改笔记不重复记阅读 |
| 搜索历史与审核通知 | `/me/history`、`/me/notifications`；分页、清空搜索历史、标记通知已读；翻页与排序不重复保存同一次查询 |
| 服务端上传 | `/uploads`；20 MiB / 300 页限制；鉴权 PDF Blob 预览和 DOCX 文本转换；待审核文件仅本人和管理员可访问 |
| 服务端审核 | `/admin/uploads`、review/process/vectorize；只有真实管理员角色可使用；批准、拒绝、解析、重试、归档及上传向量发布保留真实状态 |
| 本机 PDF | `/upload?storage=local`、`/admin?storage=local`；IndexedDB 保存字节，localStorage 保存本机备注和审核；刷新保持选中工作区；本机审核不会发布到服务器 |
| 研究助手 | `/evidence`、`/ask`、`/ai/summarize`、`/ai/compare`；真实片段、引用及定位；支持指定论文及多篇比较参数，不发送演示 ID 冒充真实论文 |
| 研究对话 | `/ai/conversations` 与 messages；登录后创建、重开、删除本人对话；AI 未配置也能管理已有对话 |
| 管理员账户管理 | `/admin/users`；真实角色校验，禁止页面自改角色，保留后端最后一个管理员保护；未给真实用户自动提升权限 |

## 数据隔离与兼容

- 真实基础别名 `scholarlens-desktop-real`：859 篇；4 篇有不可读字符的正文单独隔离，原数据与 ID 保留。
- 基础向量已于 23:35:34 +08:00 发布，49,420 片段、859 篇、384 维，三种检索模式及可追溯证据通过最终验收。基础向量别名 `scholarlens-vectors-desktop-real`；上传关键词别名 `scholarlens-uploads-desktop-real`；上传向量别名 `scholarlens-vectors-uploads-desktop-real`。它们不覆盖上游默认正式别名。
- 游客收藏、笔记与阅读记录不自动上传。登录切换到账户空间，退出恢复游客空间；本机 PDF 不因登录而移动或删除。
- 账户保存使用短暂防抖与串行队列，保存时阻止过早退出；发生冲突会停止覆盖并提示重新加载，恢复草稿留在本机，可导出当前阅读空间备份。
- 空查询最多浏览服务器提供的 20 篇候选，分页和筛选只作用于这些候选；不冒充全库分页。演示模式仍明确标注 18 篇虚构样例。
- MiniLM 模型固定 SHA 版本；向量 generation 完整核验后才发布。前端每 30 秒及窗口获得焦点时重新检查 capabilities，不把失败降级成关键词冒充语义成功。

## 解析与外部服务的边界

GROBID 未配置时，使用 pypdf 提取实际 PDF 文本并标记 partial。标题优先读取 PDF 元数据，否则标注来自文件名；作者仅读取元数据，不推断年份、机构或摘要。扫描件无文本时明确报告需要 OCR。显式配置但不可用的 GROBID 会保留失败状态供重试。

AI 供应商、模型、端点和密钥保持未配置，前端没有保存供应商密钥。原文证据检索可以运行，AI 回答、总结和比较的外部生成未验收；页面明确禁用。邮件服务未配置，验证码与找回密码不会假装发送成功。

859 篇原始 PDF/XML 未交付，详情文本可读不代表原 PDF 可下载；缺失原件的访问保持真实 404。测试用 PDF 只验证上传与转换，不替代原件。

## 验收与恢复

最终结果、命令与证据见 `docs/archive/20261027-28/DESKTOP_API_ACCEPTANCE.md`。认证已在现有本机服务上通过独立 Chrome 临时 profile 完成端到端验收，不访问用户原 Chrome 的账户或 Cookie。QA 只创建普通测试账户，完成后停用，不创建默认管理员；管理员流程在临时 SQLite 与测试索引内验证。

回滚副本在 `output/backups/full-integration-20261027-222417/`、`output/backups/upstream-v21-20261027/`、`output/backups/completion-20261027-224934/`。前者含 SQLite 在线备份。不要覆盖已有数据库或删除上传原件来回退界面。
