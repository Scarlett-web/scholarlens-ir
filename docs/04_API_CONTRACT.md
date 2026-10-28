# 04 HTTP API 契约

> 当前前缀 `/api`，本地端口8000、ES8.19.23、个人功能采用Bearer认证；公开搜索不需登录。V2实际接口以本页V2约定及backend/FRONTEND_API_GUIDE.md为准。下方早期Mock示例仅展示历史协议形状，不代表当前数据状态。

## 1. 通用约定

### V2.1 业务与AI增补（负责人组长）

输入/输出、认证和验收以backend/archive/20261026-27/V21_PARITY_GOAL.md及FRONTEND_API_GUIDE_V21.md为准。新增profile/avatar/password、绑定邮箱验证与密码找回、收藏夹、七日浏览记录、随机推荐、受控DOCX下载、管理员用户管理、审核预览/通知、我的文献、AI会话/总结/比较，以及上传向量化。原搜索/收藏接口保持兼容。SQLite使用幂等加法迁移、迁移前backup与本地恢复命令；不删除旧索引或原数据。邮件/AI未配置503，不伪造发送、生成、解析或原PDF读取。stream=true采用校验完整回答后分段SSE，未通过引用校验不发送内容；不冒充上游token流。用户及会话数据隔离、转换限时/清理、双路真实上传召回须通过新增测试。

### 2026-10-28 二次凭证确认与会话失效

负责人：项目维护者。`POST /api/auth/password` 与 `POST /api/auth/deactivate` 先验证 Bearer 会话；仅在会话有效但当前密码或确认用户名错误时，返回 `401 invalid_credentials`，不撤销会话、不更改密码或停用状态。前端显示原错误并允许重试，保留账户空间与当前会话个人配置。缺失、过期、已撤销或已停用的令牌仍返回 `401 unauthenticated`，前端清除当前会话及会话个人密钥；迟到的旧令牌响应不得清除更新后的令牌。

成功修改密码仍撤销该用户所有会话并要求重新登录；成功停用仍禁用登录、撤销所有会话并保留数据。HTTP 状态保持兼容，细分错误码只用于这两个已认证的二次确认接口。验收须在临时 SQLite 和真实账户路由上覆盖错误重试、成功撤销、真实会话失效、用户隔离与资料保留，并以独立浏览器核对界面。测试脚本必须自行启动隔离服务并核对实例挑战，不接受生产服务或本地转发作为写入目标。见 `docs/28_ACCOUNT_CREDENTIAL_BOUNDARIES.md`。

### 2026-10-28 管理员并发变更

负责人：项目维护者。`PATCH /api/admin/users/{id}` 与 `POST /api/auth/deactivate` 必须在同一SQLite写事务中读取最新角色、计数有效管理员并执行变更；并发降级/停用或混合操作至少保留一名有效管理员，拒绝请求沿用 `409 invalid_state`，不改变账户和会话。管理员写事务还需重新确认操作者有效角色。已经停用的管理员不计入有效人数，降级该停用记录不能误触最后管理员保护。详见 `docs/30_ADMIN_TRANSACTION_BOUNDARIES.md`。

### 2026-10-28 API独立部署的响应保护

负责人：项目维护者。无论是否配置FRONTEND_DIST，认证、个人资料/工作区、上传、管理员和私有对话等响应均启用既有浏览器边界，私有API或带Authorization的响应强制Cache-Control: no-store；不得被路由的可缓存设置覆盖。公开PDF Range、正文与SSE不缓冲改写；前端未挂载时根路径仍404。验收使用真实路由和隔离ES/SQLite，见 `docs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md`。现有同源前端部署已有此保护，本轮补齐独立API模式。

### 2026-10-27 V2（优先于下方历史阶段标记）

负责人组长。输入现有真实索引、可配置CPU模型和用户请求；输出沿用search全部字段及统一error结构。新增GET /api/suggest(q,limit=8)、GET /api/discover(limit=6)、GET /api/capabilities；建议来自真实title/authors，发现来自确定性真实论文与年份聚合，不编造热度。semantic/hybrid使用独立片段向量索引与真实BM25，RRF k=60；候选窗口1000，超出返回400；semantic只支持field=all/title/fulltext，hybrid关键词侧支持六字段；phrase/fuzzy只用于keyword/hybrid关键词侧，semantic拒绝。semantic/highlight不虚构精确词项；返回匹配片段与model/version解释。一路缺失时503，不静默降级。year/sort对两路及最终论文排序生效，total为候选论文数量，非全库精确语义命中数。

POST /api/ask接收question、paper_ids、mode、top_k；POST /api/evidence接收同样请求提供证据调试，不调用生成模型；AI_API_KEY/AI_BASE_URL/AI_MODEL未配置返回503 ai_not_configured。证据包含真实chunk_id、字符区间locator和quote，生成后验证引用，仅接受证据集合内ID与原文片段。证据不足返回200 insufficient_evidence，无来源不生成。

GET /api/papers/{id}/content(offset=0,limit=8000)按需正文；详情增加include_fulltext参数（默认true保持兼容），来源仅公开安全文件名及质量标志。PDF路径保持受控，source_file只在明确配置PDF根目录且无已存路径时用于根目录直接映射。

POST /api/auth/register/login/logout，GET /api/auth/me；登录返回短期不透明Bearer令牌，服务器仅存哈希。GET /api/me/favorites，GET/PUT/DELETE /api/me/favorites/{id}；GET/POST/DELETE /api/me/history，DELETE /api/me/history/{id}。注册不授管理员权限；管理员通过本地CLI提升。个人数据均需登录并隔离用户。

POST /api/uploads使用multipart文件，GET /api/uploads及/{id}只读本人；管理员GET /api/admin/uploads、POST /api/admin/uploads/{id}/review(decision=approve|reject,reason)、POST /api/admin/uploads/{id}/process触发显式解析，GROBID未配置503且任务状态明确。审核通过后解析到隔离目录，增量索引发布到独立上传别名，不覆盖859篇；失败可重试且旧generation保留。GET /api/evaluation返回固定查询性能结果，人工标注缺失时相关性指标为null。

新增模块均使用Pydantic输入输出和同一错误对象；无身份401、无权限403、重复409、上传过大413、文件内容错误400、依赖未就绪503。CORS仅显式配置来源；公开检索不需登录。完整路径/样例以backend/FRONTEND_API_GUIDE.md为V2实施手册；自动测试和真实运行验收见BACKEND_V2_VERIFICATION.md。

GET /api/metrics独立报告base/approved_uploads/vector索引数量、三模式状态与版本；既有/api/stats仍专门对账859篇基础语料，避免改变已约定统计含义。审核上传只加入keyword查询与详情，语义/RAG向量语料覆盖范围以独立向量构建报告为准；新增上传向量化前不可宣称已支持其语义召回。上传请求体上限21MiB（文件20MiB，剩余为multipart开销）；登录前拒绝上传且文件不落盘。AI兼容服务的token限制参数默认max_completion_tokens，可通过AI_TOKEN_PARAMETER=max_tokens切换旧供应商，接口不接受客户端更改服务地址或密钥。

GET /api/papers/{id}/chunks(page,page_size)提供稳定片段分页，返回chunk_id/field/offset_start/offset_end/locator/text等真实字段；不依赖向量构建，便于前端按引用定位。GET /api/chunks/{chunk_id}读取已发布向量片段的原文，排除embedding并再次核对当前论文字符区间，缺片段404 chunk_not_found，版本不符503；它不猜测PDF页码。

PDF字节Range成功206；不合法范围416 range_not_satisfiable、格式错误400 invalid_parameter也使用统一error JSON，保留必要Content-Range头。

SQLite个人列表/上传列表page上限10000，page_size上限100，超大页码统一400，避免超出SQLite整数范围。

V2 all多词检索允许查询词分布在不同的六字段：普通查询采用cross_fields AND，短语仍要求完整短语在同一字段，模糊查询按词进行跨字段AND（最多20个词）。matched_fields报告包含实际查询词的字段，不要求每个命中字段独自覆盖整条跨字段查询。指定单字段的BM25行为不变。

### P0 实现约定（2026-10-26）

2026-10-27真实数据Goal：组长放行20篇隔离验收后全量导入；接口字段不变，real通过导入元数据和X-ScholarLens-Data-Status标记，stats数值来自真实索引。正式开发启动默认alias切换为scholarlens-papers-real，Mock可显式指定scholarlens-papers-mock；8001先验收再重启8000。PDF未交付仍404，不扩展阅读能力；责任人组长，验收记录见backend/archive/20261026-27/REAL_DATA_VERIFICATION.md。

负责人：组长；输入为下述 search 参数和通过校验的 JSONL 索引，输出沿用本页 JSON 结构。历史P0仅实现keyword，当时semantic/hybrid返回503；V2已实现三模式，依赖状态见/api/capabilities。search 响应通过 `X-ScholarLens-Data-Status: mock|real` 标记数据来源，保持 JSON 顶层字段不变；stats 的 status 使用同一来源标记。Mock 表示论文内容为模拟数据，检索引擎仍是真实 Elasticsearch。page_size 上限固定为 100，分页窗口上限 10000；非法参数（包括 FastAPI 类型校验失败）、反向年份范围以及 phrase/fuzzy 同时启用统一返回 400 invalid_parameter。仅允许本页六字段，all 不搜索 abstract。date 使用标准文本分析支持年份/日期词项；year_from/year_to 使用整数 year 过滤。排序缺失年份置后，同分以 paper_id 稳定排序；高亮使用 HTML 转义，仅添加 em 标签。

stats 的 papers 表示本次输入非空行数，indexed 为当前实际文档数；parser 保留 success/failed，并增加 partial/unknown，unknown 表示输入没有解析状态。fields_completeness 为已索引文档的六字段及摘要、年份非空率；正文隔离后按实际入索引值统计。index.last_built_at、mapping_version 来自导入元数据。ES 未启动或索引尚未导入返回 503；服务内部错误返回 500 统一结构，不返回路径、密钥或堆栈。验收命令与实际结果见 backend/README.md 和 backend/archive/20261026-27/VERIFICATION.md。

- 请求与响应使用 `application/json; charset=utf-8`；时间为 ISO-8601。
- 成功响应直接包含业务字段；错误统一为 `{"error":{"code":"...","message":"...","details":{}}}`。
- `page` 从 1 开始，默认 `page_size=20`，建议上限 100；超限返回 `400 invalid_parameter`。
- `mode`：`keyword`（BM25）、`semantic`、`hybrid`；`field`：六字段之一或 `all`。

## 2. 搜索

### `GET /api/search`

参数：`q`（必填，查询字符串）、`field=all|title|authors|date|affiliation|address|fulltext`、`mode=keyword|semantic|hybrid`、`page`、`page_size`、`sort=relevance|year_desc|year_asc`、`year_from`、`year_to`、`phrase=true|false`、`fuzzy=true|false`。

Mock 请求：`GET /api/search?q=computer&field=title&mode=keyword&page=1&page_size=2&sort=relevance`

Mock 响应：

```json
{
  "query":{"q":"computer","field":"title","mode":"keyword","page":1,"page_size":2,"sort":"relevance","year_from":null,"year_to":null,"phrase":false,"fuzzy":false},
  "total":1,"page":1,"page_size":2,"took_ms":6,
  "results":[
    {"paper_id":"mock-0002","title":"Mock Computer Vision Survey","authors":["Mock Author C"],"year":2025,"abstract_snippet":"Mock abstract snippet for search response testing.","highlights":{"title":["Mock <em>Computer</em> Vision Survey"]},"score":2.0794415,"matched_fields":["title"],"explanation":{"retrieval":"bm25","reason":"title match"}}
  ]
}
```

### 语义/混合附加字段

`mode=semantic|hybrid` 时响应 `explanation` 增加 `vector_rank`、`keyword_rank`、`rrf_score`（适用时）和 `model_name`；不得把不同模式的分数直接当作同一尺度。

## 3. 统计

### `GET /api/stats`

返回数据与索引状态：

```json
{"papers":1000,"indexed":1000,"fields_completeness":{"title":0.99,"authors":0.96,"abstract":0.91,"fulltext":0.88},"parser":{"success":980,"failed":20},"index":{"last_built_at":"2026-10-28T12:00:00Z","mapping_version":"pending"},"status":"mock"}
```

真实值必须来自质量报告；示例中的 `status=mock` 明确表示占位。

## 4. 论文详情与 PDF

- `GET /api/papers/{paper_id}`：返回统一 schema 的公开字段、`source_status`、`chunks` 摘要和可用操作；不存在返回 `404 paper_not_found`。
- `GET /api/papers/{paper_id}/pdf`：成功时返回 `application/pdf` 或受控重定向；文件缺失返回 JSON `404 pdf_not_available`，不暴露服务器绝对路径。

### P0 第二阶段详情约定（2026-10-26）

组长明确放行 D-12 的后端读取部分；负责人组长。输入为当前 alias 中的 paper_id；输出为下列字段，验收为现有 Mock 详情可读、缺论文/缺 PDF 分别404、错误结构统一、响应不含本地路径，测试与样例见 backend/archive/20261026-27/FRONTEND_HANDOFF.md。

详情固定返回 paper_id/title/authors/date/year/affiliation/address/abstract/fulltext/pages，以及 pdf_available（boolean）、source_status（对象：pdf=available或pdf_not_available，parse_status=success/partial/error/unknown）、chunks（本阶段为空数组）、available_actions（PDF 可访问时为["view_pdf"]，否则[]）。保留各核心字段的原类型和缺失约定；不返回内部 pdf_path、source_file、date_value 或原始 errors，避免泄露文件系统信息。论文正文来自当前已索引版本；已隔离正文为空，不用猜测文本替代。

详情不附加虚构 PDF URL；前端仅在 pdf_available=true 时使用既有 /api/papers/{paper_id}/pdf 路由。现有两条 Mock 的 PDF 均未交付，详情200且 pdf_available=false，PDF 路由404 pdf_not_available。两个路由均先验证论文存在；不存在返回404 paper_not_found。无效 paper_id（空白、超长、路径分隔符或控制字符）返回400 invalid_parameter。详情与成功 PDF 响应沿用 X-ScholarLens-Data-Status 头。

PDF 访问默认关闭，只有配置 SCHOLARLENS_PDF_ROOT 后才允许读取。索引 pdf_path 仍按项目根目录解释，可用 SCHOLARLENS_PDF_PATH_BASE 显式调整解析基准；最终解析路径必须位于配置的根目录内、是可读的 .pdf 文件且有 PDF 文件签名。拒绝绝对路径、远程 URI、越界路径和指向根目录外的链接；找不到文件或未配置根目录一律404 pdf_not_available，不回传内部原因或路径。迁移需显式配置路径基准并先对账来源清单，不按文件名猜测替换文件。

search 的 query 回显全部已验证参数（包括 year_from/year_to/phrase/fuzzy 默认值），其余已约定字段不改名。非法参数统一400；未知路由404 not_found、错误HTTP方法405 method_not_allowed也使用同一 error 对象。先完成输入校验再请求ES。前端开发优先使用Vite /api代理，无需开放ES或添加全域CORS。

## 5. 问答

### 发现摘要与可核对机构（2026-10-28）

负责人：项目维护者。`GET /api/discover?limit=1..20` 和 `GET /api/discover/random?limit=1..20&seed=...&exclude=...` 的 `recommendations` 继续返回原有论文摘要，并增加可选来源字段 `affiliation: string[]`；无机构元数据时返回 `[]`。不返回本地路径、解析错误或其他内部来源字段。输入仍为当前索引与只读查询，不修改索引或论文。

用途是前端详情及探索图解释共同机构；共同机构不表示引用关系或语义相关度。验收同时覆盖两条路由的机构保留、缺失值兼容和内部字段不外泄，并保留原有 seed、exclude 与返回封装。隔离契约测试使用显式合成文档和模拟搜索客户端，不冒充真实 ES 验收。

### `POST /api/ask`

请求：

```json
{"question":"What does the paper say about retrieval evaluation?","paper_ids":["mock-0001"],"mode":"hybrid","top_k":5,"conversation_id":null}
```

响应：

```json
{"answer":"Mock answer grounded in the selected paper.","evidence_status":"sufficient","citations":[{"paper_id":"mock-0001","title":"Mock: Information Retrieval Evaluation","chunk_id":"mock-0001-c01","locator":"p.1","quote":"Mock evidence sentence."}],"retrieval":{"mode":"hybrid","top_k":5},"model":{"name":"configured-at-runtime","status":"mock"}}
```

证据不足时返回 `200` 业务状态 `evidence_status=insufficient_evidence` 和空/保守答案；不得伪造 citation。问题为空或 `top_k` 超限返回 `400`。

## 6. 用户与上传接口（V2已实现，取代早期计划）

| 阶段 | 方法与路径 | 用途 |
|---|---|---|
| V2 | `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me` | 注册登录 |
| V2 | `GET /api/me/favorites`、`GET/PUT/DELETE /api/me/favorites/{paper_id}` | 收藏 |
| V2 | `GET/POST/DELETE /api/me/history`、`DELETE /api/me/history/{id}` | 搜索历史 |
| V2 | `GET/POST /api/uploads`、`GET /api/uploads/{id}` | 受控上传与本人状态 |
| V2 | `GET /api/admin/uploads`、`POST /api/admin/uploads/{id}/review`、`POST /api/admin/uploads/{id}/process` | 审核及可恢复解析/独立增量索引 |

用户/收藏/历史和上传审核已有SQLite实现与测试；真实GROBID未配置时处理任务明确503，不伪造自动解析成功。实际功能状态以/api/capabilities为准。

## 7. 错误码

`400 invalid_parameter`、`401 unauthenticated`、`401 invalid_credentials`（仅已认证的密码/停用二次确认错误）、`403 forbidden`、`404 paper_not_found`、`404 pdf_not_available`、`409 duplicate_record`、`413 file_too_large`、`429 rate_limited`、`500 internal_error`、`503 dependency_unavailable`。错误 `details` 只放可诊断的非敏感信息。

