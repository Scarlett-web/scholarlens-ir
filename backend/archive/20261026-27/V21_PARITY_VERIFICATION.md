# ScholarLens V2.1 功能对齐验收

日期2026-10-27（Asia/Shanghai），负责人组长。当前分支zjl，V2.1版本0.2.1。完整原测试131项与新增18项共**149项全部通过**，没有skip。开发验收阶段未提交推送；组长随后明确要求继续目标并上传全部项目代码，本次按该指令验收后提交、推送origin/zjl，不合并。正常本机8000仍使用859篇基础语料及49420个基础向量片段。

## 对照来源与范围

已读取当前V2代码、BACKEND_V2_VERIFICATION、FRONTEND_API_GUIDE、BACKEND_STARTUP及公共API契约。学长报告为根目录introduction.pdf，共39物理页；PDF文本层存在字体映射乱码，功能判断依据渲染页面，未根据乱码文本猜测。

核心用例位于PDF物理页7—13（页脚6—12，表1—16）；接口位于物理页21—29（表21—46）；物理页31—33的用户/管理员截图和测试表还显示取消账号、移出审核队列。这些补为凭据确认的停用账号及保留原件/审计的归档，不照搬公开管理员注册或MD5密码设计。详细初始对照保留在V21_PARITY_GOAL.md，以下是最终矩阵。

状态含义：**实际通过**表示有真实本机HTTP、真实ES/SQLite或明确受控文件的运行证据；**已实现、缺外部资源**表示代码和受控测试完成但真实外部服务/原文件尚缺；**未实测**指特定部署、人工界面或质量场景尚无证据，不暗示功能已经真实上线。

## P0 业务完成矩阵

| 学长/本轮功能 | 真实API | 最终状态 | 证据与边界 |
|---|---|---|---|
| 六字段关键词、分页、高亮、模糊/短语 | GET /api/search | 实际通过 | 原131项和实际论文；三模式保留 |
| 输入建议 | GET /api/suggest | 实际通过 | 真实标题/作者前缀，无虚构热度 |
| 随机推荐/换一批 | GET /api/discover/random | 实际通过 | 新种子、seed复现、exclude换批；真实HTTP两批不重叠 |
| 详情/摘要/正文 | GET /api/papers/{id}、/content、/chunks | 实际通过 | 不暴露绝对路径，缺字段保留 |
| 日期/年份筛选与提示 | /api/search、GET /api/data-quality | 实际通过 | 231篇完整date、478篇有year；不补造日期 |
| 注册/登录/退出 | /api/auth/* | 实际通过 | 保留scrypt、哈希令牌、权限隔离 |
| 个人资料/用户名/显示名称/邮箱 | GET/PATCH /api/me/profile | 实际通过 | 唯一用户名，修改邮箱撤销验证标记 |
| 更改/读取头像 | POST/GET /api/me/avatar | 实际通过 | 真PNG/JPEG解码、像素/大小限制、重编码，私人访问 |
| 安全修改密码 | POST /api/auth/password | 实际通过 | 旧密码验证、撤销所有会话、新密码登录 |
| 邮箱验证及验证码 | /api/me/email/* | 已实现、缺外部资源 | 受控邮件网关验证；实际邮件未配置 |
| 邮箱找回密码 | /api/auth/password-reset/* | 已实现、缺外部资源 | 仅已验证邮箱、限次/限时/防重放；无服务503 |
| 取消账号 | POST /api/auth/deactivate | 实际通过 | 校验用户名密码后停用/撤销会话，保留数据，禁止最后管理员自停用 |
| 收藏/取消收藏 | 旧 /api/me/favorites/* | 实际通过 | 兼容旧客户端，全局取消同时移除分类关联 |
| 收藏分类创建/查看/重命名/删除 | /api/me/favorite-folders/* | 实际通过 | 用户隔离、去重、删除分类保留全局收藏 |
| 分类下论文 | /api/me/favorite-folders/{id}/papers | 实际通过 | 加入/移出/分页，不能读取他人分类 |
| 搜索历史 | 旧 /api/me/history | 实际通过 | 原行为保留，与浏览记录分离 |
| 近七日浏览记录/删除/清空 | /api/me/browsing-history/* | 实际通过 | 服务端访问时间，实际进程重启后保留，超期排除 |
| PDF在线阅读/下载 | /api/papers/{id}/pdf | 已实现、缺原PDF | 原论文仍404；受控PDF、Range和清单SHA映射通过 |
| PDF转Word/DOCX | /api/papers/{id}/docx、/api/uploads/{id}/docx | 实际通过（受控PDF） | HTTP生成真实DOCX，重开核对文字；仅文本层，不保证复杂布局 |
| 用户上传/我的上传/我的文献 | /api/uploads、/api/me/uploads、/api/me/papers | 实际通过 | 状态和审核结果可查，未审核不检索 |
| 管理员登录/权限 | 原登录+本地提升CLI | 实际通过 | 不能公开自注册admin |
| 管理员用户列表/详情/受控更新 | /api/admin/users/* | 实际通过 | 不返回密码/哈希，禁用生效，至少保留一名管理员 |
| 管理员上传 | POST /api/admin/uploads | 实际通过 | 复用文件校验、自动批准审计、显式process |
| 审核前PDF预览 | GET /api/admin/uploads/{id}/pdf | 实际通过 | 实际HTTP206，普通用户403、匿名401，源SHA校验 |
| 审核批准/拒绝/上传者通知 | /review、/api/me/notifications/* | 实际通过 | 每用户隔离结果、已读状态、真实SQLite |
| 移出审核队列 | DELETE /api/admin/uploads/{id} | 实际通过 | 归档而非删源文件/旧索引，处理中的任务409 |
| GROBID解析、失败重试 | 原 /process | 已实现、缺外部资源 | 原受控成功/失败/重试测试保留；未伪造真实解析 |

## P1 AI完成矩阵

| 功能 | API/实现 | 最终状态 | 验收 |
|---|---|---|---|
| 单篇/多篇论文问答 | POST /api/ask，paper_ids | 已实现、缺真实AI Key | 真实词项/向量证据，受控生成和引用校验通过 |
| 单篇总结 | POST /api/ai/summarize | 已实现、缺真实AI Key | 摘要、正文与后部片段覆盖，不用标题假装整篇证据 |
| 多篇方法/结论比较 | POST /api/ai/compare | 已实现、缺真实AI Key | 2..10篇、逐篇证据和逐篇引用；缺证据明确弃答 |
| 原文引用与定位 | /api/evidence、/api/chunks/{id} | 实际通过 | 基础与上传chunk逐字核对字符区间，不猜页码 |
| 多轮上下文和持久化 | /api/ai/conversations/* | 实际通过（SQLite与受控生成） | 最近12消息传给适配器，不只是存记录；持久化、重启、越权404 |
| 可选stream=true | /ask、/summarize、/compare | 已实现并受控测试通过 | 先校验完整结果再分段SSE，不是未经校验的上游token流 |
| 缺配置状态 | /api/capabilities、问答响应 | 实际通过 | 真实服务无Key时503 ai_not_configured |
| 超时/认证/额度/格式/引用错误 | 原兼容适配器 | 受控自动测试通过 | 未把替身调用当真实云端验收，Key不返回前端 |

会话持久化需登录，匿名仍可单次问答。question和paper_ids按每次请求指定，论文范围不自动继承；历史回答是语境而非新证据。总结/比较受上下文长度限制，不宣称逐页读完整PDF或完全验证模型事实。没有真实Key，本轮没有真实外部AI生成成功记录。

## P2 增量向量与Porter

批准并索引的新上传，使用独立scholarlens-uploads-*和scholarlens-vectors-uploads-*；模型/分块版本一致、稳定chunk_id和原文字段完全一致时复用旧向量，仅为新增/变化片段编码。测试断言第二次同输入reused_chunks等于全部块、embedded_chunks为0，所有旧generation保留；真实MiniLM384维和真实ES证明新论文可参加keyword/semantic/hybrid，结果含正确authors/year，片段路由能取回上传原文。

上传向量构建失败时保留关键词结果及旧向量；generation不匹配会明确503，不伪装语义就绪。管理员可通过vectorize接口重试。此过程未重新计算或覆盖原49420个基础向量。真实新PDF的GROBID解析尚未配置，解析结果测试使用明确TEI夹具，不冒充外部服务。

Porter独立新建测试索引结果：standard将`retrieval retrieving retrieved`保留为3个不同词，porter将其都变为`retriev`；retrieve查询命中1条受控英文记录。实际记录在porter-comparison.json。该实验是分析器行为对照，不是对859篇人工相关性的排名提升证明；没有修改正式standard映射。自建临时测试索引由脚本自行清理，既有索引未删除。

## 最终测试和实际HTTP

完整命令（本机数据路径在私有.env，使用原真实API）：

```powershell
$data = (Select-String -LiteralPath .env -Pattern '^SCHOLARLENS_REAL_DATA_DIR=').Line.Split('=',2)[1]
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --tb=short --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8000
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m ruff format --check backend
git diff --check
backend/.venv/Scripts/python.exe -m backend.accept_v21_http
```

最终字面结果：`149 passed in 124.61s (0:02:04)`，退出0，无skip。原131项文件未被修改或削弱，新增18项在test_v21.py和test_v21_flows.py。精确命令、字面输出和退出状态在backend/.runtime/v21-final-pytest.json/log；上一次149项通过的127.66秒记录作为pre-incremental保留，不累加测试数量。

新增测试覆盖资料改名/头像/密码，邮件未配置/发送失败/验证码限次过期/防重放，分类与七日记录，实际DOCX/超时/清理，管理权限/停用账号/归档，审核预览/通知，真实上传向量三模式/复用/前代保留，多轮上下文/总结/比较/SSE引用错误，SQLite升级和恢复。原测试继续覆盖六字段、全部_source、真实RRF和基础数据质量。

独立8004实际HTTP验收使用专用runtime：注册登录、修改资料、创建收藏夹/浏览记录/会话，停止后重新启动，再用原令牌读取确认持久化。随后上传受控PDF、下载DOCX并重开核对文本、确认转换临时目录已清理；本地CLI提升后预览PDF Range206，匿名401/普通用户403；审核通知可查，GROBID未配置503，随机两批不重复。该服务已停止，不在主用户数据库留下测试账号。证据v21-http-verification.json。

实际DOCX样本为runtime/v21-http-converted.docx，读取后包含“Controlled PDF conversion evidence”，是实际接口产物而非改扩展名；python-docx和OOXML结构重开验证通过。本机没有可用的Word/LibreOffice可视渲染环境，**未实测桌面Word界面和复杂布局保真度**；不把结构验证伪称为桌面视觉验收。原论文PDF仍未交付，原论文DOCX请求明确404，不伪造原文。

正常8000版本0.2.1，OpenAPI60个路径；stats仍859/859、real。基础代仍scholarlens-papers-real-090928bb1545，基础向量仍49420。V2.1审计快照中81个既有索引的UUID/文档数均保留。date完整231、year存在478。最新运行核对在v21-main-runtime.json及完成审计中。

## 数据库迁移与回退

schema_version=4，所有新字段/表为加法迁移，不删除原用户字段或历史记录。迁移前通过SQLite backup保存一致性副本和SHA，恢复CLI另保存恢复前副本；独立旧schema的id42账号/密码哈希迁移后逐项保持，恢复后旧字段与旧哈希一致，重复启动不会重复升级或清空数据。

第一轮原型字段新增先于首次observed快照，已明确记录这一限制；后续v3/v4迁移有自动备份。主库审计时users/sessions/favorites/history/uploads均为0，最终仍为0；验收用户均在临时数据库，不能把临时数据替换成正式用户数据。若已有真实用户，备份后新增的业务写入必须另外保留，不应无条件回退旧备份。

恢复步骤、字段和配置详见BACKEND_STARTUP.md。不自动对主库执行恢复；源码回退和数据库回退分开管理，避免恢复代码时丢失用户新写入。

## 交付与剩余资源

接口手册FRONTEND_API_GUIDE_V21.md，阶段与来源映射V21_PARITY_GOAL.md；主要代码在accounts.py、email_codes.py、db_migrations.py、docx_convert.py/docx_worker.py、rag.py、upload_vector.py、uploads.py、retrieval.py、discovery.py/capabilities.py及新增HTTP验收脚本和测试。

发布前还需要真实AI Key/模型服务、邮件网关、原论文PDF及正确清单、运行中的GROBID；扫描件另需OCR。真实邮件送达、外部AI生成、真实新PDF自动解析、桌面Word视觉和React页面联调均未实测。上述缺失不影响当前已验证的后端代码及明确状态交付；不是把未配置模块标为真实成功。

本轮原件、基础索引/向量和用户数据保留，保护目录frontend/scripts/data未修改；开发基线为88e796b。源码补丁、前后摘要、验证和隔离回退结果在runtime的v21-*记录中，最终完成审计逐项核对后才关闭Goal。本次发布仅上传源码、测试、配置示例与文档，实际提交和远程一致性记录在本地v21-publication.json；密钥、论文、数据库、模型和运行文件留在本地。

## 可核验交付与源码恢复

工作区中的实现是修改后源码；本轮相对已提交V2的变更共33文件，完整补丁为backend/.runtime/v21-changes.patch，前后SHA为v21-source-manifest.json，原Git源码快照为v21-baseline/source-head.zip。补丁已执行git apply --check --reverse，退出0；没有对工作区应用补丁。

验证记录包括v21-final-pytest.json/log、v21-http-verification.json、v21-main-final-http.json、v21-main-runtime.json、porter-comparison.json，以及v21-rollback-verification.json。最终聚合为v21-completion-audit.json。全部位于Git忽略的runtime，不上传密钥、真实数据、数据库、模型、上传和日志。

复用通用哈希保护的rollback_v2.py，仅显式指定本轮快照和manifest；名称沿用V2但恢复输入为V2.1记录。本轮已在独立目录实际执行--apply，33文件全部还原为基线哈希。它不对主工作区或数据库执行恢复，也不删除ES代。

```powershell
# 仅读检查当前源码是否仍匹配本轮结束时的摘要
backend/.venv/Scripts/python.exe -m backend.rollback_v2 --snapshot backend/.runtime/v21-baseline/source-head.zip --manifest backend/.runtime/v21-source-manifest.json --check
# 只有组长决定源码回退时：先停止API，检查通过后自行使用同一参数加--apply。
```

源码回退和SQLite恢复是两项操作。回退到旧V2源码会失去V2.1禁用账号/邮箱验证等新规则，不应在真实新用户已开始使用后随意回退；先保留当前数据库和源码快照。运行依赖和原始文件不由源码恢复器删除，具体数据库恢复见BACKEND_STARTUP.md。
