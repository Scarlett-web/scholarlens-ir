# ScholarLens V2.1 前端接口增补

本页优先于V2手册中同名功能的旧限制。负责人组长，日期2026-10-27；本机API为`http://127.0.0.1:8000`，机器契约`/openapi.json`、交互文档`/docs`。没有修改或依赖React代码。V2原有搜索、统计、建议、详情、登录、收藏、历史、上传接口继续有效，完整基础示例见FRONTEND_API_GUIDE.md。

所有私人接口发送`Authorization: Bearer TOKEN`。服务器从令牌识别用户，客户端不能通过user_id越权。统一错误形状：`{"error":{"code":"...","message":"...","details":{}}}`。新增响应均以实际OpenAPI为准；不向前端返回磁盘路径、密钥、密码/令牌哈希。

## 用户资料与账号

| 方法与地址 | 请求 | 返回/行为 |
|---|---|---|
| GET /api/me/profile | 登录 | id/username/role/display_name/email/email_verified/avatar_available/created_at/updated_at |
| PATCH /api/me/profile | `{username?,display_name?,email?}` | 更新本人资料；账号唯一；修改邮箱后必须重新验证 |
| POST /api/me/avatar | multipart `file` | PNG/JPEG≤2MiB、≤400万像素，解码后重新编码，返回资料 |
| GET /api/me/avatar | 登录 | 本人PNG字节；尚无头像404 |
| POST /api/auth/password | `{current_password,new_password}` | 校验旧密码，新密码10..128字符；成功撤销全部登录状态，需重新登录 |
| POST /api/auth/deactivate | `{username,password}` | 验证本人凭据后停用账号、撤销会话；数据保留；最后一名管理员不能自行停用 |

用户名3..64字符（ASCII字母/数字/下划线/点/短横线）；display_name≤120字符。匿名基础搜索保持可用。资料更新不能修改role、disabled等管理字段。不要用拼接的头像URL泄露服务器文件名，直接请求`/me/avatar`。

## 邮箱验证与密码找回

| 方法与地址 | 请求 | 说明 |
|---|---|---|
| POST /api/me/email/request | `{email}` | 登录；邮箱须已存入本人资料；向配置的邮件API请求验证码 |
| POST /api/me/email/verify | `{email,code}` | 登录；校验8位验证码并绑定邮箱，已由其他用户验证的邮箱409 |
| POST /api/auth/password-reset/request | `{email}` | 匿名；仅已验证且未停用账号可找回，统一返回accepted不暴露是否存在 |
| POST /api/auth/password-reset/verify | `{email,code,new_password}` | 验证成功后重置密码并撤销全部会话 |

验证码10分钟有效，同邮箱同用途请求间隔至少60秒，最多5次校验、单次使用；数据库仅存加盐哈希。邮箱更改、用途不同、其他用户及过期验证码均无效。邮件未配置返回503 `email_not_configured`，发送失败503 `email_service_unavailable`，验证码失败400 `invalid_code`，频率限制429。不能把HTTP accepted写成“已送达收件箱”。

服务器私有.env配置`EMAIL_BASE_URL`和可选`EMAIL_API_KEY`。该端点接收JSON `{to,subject,purpose,code}`并返回2xx表示接受；开发可对接自己的邮件网关，不由浏览器调用网关。实际邮箱发送尚无外部服务验收，测试中仅使用明确的受控替身。未验证的自填邮箱不允许重置账号密码。

## 收藏文件夹和浏览历史

| 方法与地址 | 输入 | 行为 |
|---|---|---|
| GET/POST /api/me/favorite-folders | POST `{name}` | 列出/创建本人收藏夹，名称不可空白或重复 |
| PATCH /api/me/favorite-folders/{id} | `{name}` | 重命名 |
| DELETE /api/me/favorite-folders/{id} | 无 | 删除分类及分类关联，保留全局收藏 |
| GET /api/me/favorite-folders/{id}/papers | page/page_size | 分类下论文分页，含title/authors/year/available |
| PUT /api/me/favorite-folders/{id}/papers | `{paper_id}` | 幂等归类，同时加入旧全局收藏 |
| DELETE /api/me/favorite-folders/{id}/papers/{paper_id} | 无 | 移出此分类，不移除全局收藏 |
| POST /api/me/browsing-history | `{paper_id}` | 明确记录一次访问，时间由服务器生成 |
| GET /api/me/browsing-history | days=7（1..30）、page/page_size | 近七天默认；id/paper_id/accessed_at/title |
| DELETE /api/me/browsing-history/{id} | 记录整数ID | 删除本人单条记录 |
| DELETE /api/me/browsing-history | 无 | 清空本人浏览记录 |

page默认1、上限10000，page_size默认20、上限100。浏览记录最多保留本人最新500条；“搜索历史”仍使用旧`/api/me/history`，两者含义不同。前端在用户真实打开论文后POST一次，补全请求、列表加载不要自动记浏览。其他用户的收藏夹/记录返回404，不泄露拥有者。

旧PUT/GET/DELETE `/api/me/favorites/{paper_id}`保持兼容；旧取消收藏会一并移除该论文的所有本人分类关联。删除文件夹不会删论文、PDF或其他用户数据。

## 真正随机推荐和日期提示

`GET /api/discover/random?limit=3`返回`seed/recommendations/excluded_count/status`。每次省略seed会产生新种子；相同seed和相同exclude可复现。将已展示ID以逗号连接传`exclude`即可换一批，仍有足够候选时不会重复；候选已耗尽时重新开始一轮。推荐没有虚构热度或阅读量。旧`/api/discover`仍为确定性的首页发现。

`GET /api/data-quality`返回`indexed/date_complete/date_missing/year_present/year_missing/date_filter_note/status`。真实基库完整date为231篇、year为478篇，二者不可混用。`field=date`搜索真实完整日期词项，`year_from/year_to`按整数年份筛选；无年份的论文无法确定是否属于年份区间，默认查询仍保留。禁止从year补造月份和日期。

## PDF阅读与PDF转DOCX

原PDF路径逻辑仍受`SCHOLARLENS_PDF_ROOT`、`SCHOLARLENS_PDF_PATH_BASE`和可选`SCHOLARLENS_PDF_MANIFEST`控制。清单按paper_id/source_file/pdf_sha256核验，未提供PDF仍404 `pdf_not_available`。本轮没有重写原859篇路径或假装已获得原文。

| 方法与地址 | 身份 | 输出 |
|---|---|---|
| GET /api/papers/{paper_id}/docx | 公开论文 | DOCX附件；来源PDF缺失404 |
| GET /api/uploads/{upload_id}/docx | 上传者或管理员 | 本人/审核允许的隔离PDF转DOCX；越权404 |
| GET /api/admin/uploads/{upload_id}/pdf | 管理员 | 审核前预览，PDF字节及Range；普通用户403，匿名401 |

DOCX是真实OOXML文档，**当前为文本提取转换**，不保证复原复杂表格、图片、双栏和公式排版。PDF≤20MiB、1..300页，子进程墙钟超时30秒，文本总量上限500万字符；扫描件没有文本层返回422 `ocr_required`。超时504 `conversion_timeout`，非法文件400 `conversion_failed/invalid_file`。下载响应`Content-Type=application/vnd.openxmlformats-officedocument.wordprocessingml.document`、`X-ScholarLens-Conversion=text-only`。不要把二进制响应当JSON。

每次转换在随机临时目录执行，成功下载完成后清理，失败/超时也清理；进程崩溃遗留目录在下次请求清理超过1小时的旧任务。转换不修改原PDF，不调用外部转换站点。上传源文件和清单路径都须通过边界及哈希验证。

## 管理员与我的文献

| 方法与地址 | 输入/行为 |
|---|---|
| GET /api/admin/users | page/page_size；返回用户公开管理资料，不含密码、salt、会话 |
| GET /api/admin/users/{id} | 单用户详情 |
| PATCH /api/admin/users/{id} | `{disabled?,role?}`；仅管理员，至少保留一名有效管理员 |
| POST /api/admin/uploads | multipart file；管理员专用、同等文件校验，自动记录批准审计，再显式process |
| GET /api/me/uploads | 与旧`/api/uploads`兼容的本人上传分页 |
| GET /api/me/papers | 本人文献与状态，paper_available/review_status及上传字段 |
| GET /api/uploads/{id}/result | 本人审核结果及处理状态 |
| GET /api/me/notifications | 本人审核/索引通知分页 |
| POST /api/me/notifications/{id}/read | 标记本人通知已读 |
| DELETE /api/admin/uploads/{id} | 从审核队列归档，保留源PDF、审计和已存在索引；处理中的任务409 |

管理员仍需本地CLI提升已有账号，不开放管理员自行注册。普通用户给注册请求添加role返回400。禁用用户不能登录或继续使用原令牌；管理员可受控解禁。审核预览验证实际文件及SHA；未批准上传不会进入检索。原件归档不代表论文已从索引撤回；UI应使用archived字段区别。

上传状态：pending → approved/rejected → processing → indexed/failed/dependency_unavailable。审核通知隔离保存；GROBID未配置503且保留原件。前端应轮询状态，不把202当作解析成功。归档后的记录不再接受review/process，仍可由本人查看结果。

## 上传论文的语义与混合检索

批准并解析成功后，关键词输入发布到独立上传代，再生成384维MiniLM片段到`UPLOAD_VECTOR_INDEX`。独立上传向量别名与上传关键词generation绑定，必须版本一致，原859篇/49420基础片段保持不变。语义、混合和RAG从基础与上传向量共同召回；结果再读取正确的论文索引，不能把chunk_id当paper_id。

`POST /api/admin/uploads/vectorize`可在向量依赖修复后重试；仅管理员。按稳定chunk_id和完全相同原文复用前代向量，仅为新增/修改片段编码；响应含reused_chunks/embedded_chunks，完整计数验证后发布新的上传向量代。失败保留已批准关键词代和全部旧向量代，返回明确依赖状态；不伪造向量完成。`/api/metrics`的uploaded_semantic_status以实际版本匹配为准。新上传真实GROBID尚未配置，本轮用受控TEI验证解析流程、用真实CPU模型和真实ES验证三模式召回；不冒充真实外部解析。

## AI总结、比较和多轮会话

AI服务器端仍配置`AI_API_KEY/AI_BASE_URL/AI_MODEL`，未配置统一503 `ai_not_configured`，不将Key发前端。原单篇/多篇`POST /api/ask`保留`question/paper_ids/mode/top_k/conversation_id`，增加`stream=false`。多篇选择时top_k须至少等于不同论文数，最多10个证据片段。

新增 `POST /api/agent/run` 作为证据 Agent 入口。请求在原字段外增加 `operation=ask|summarize|compare`，服务端按 route → retrieve_evidence → grounded_answer → citation_guard 执行，返回原有回答字段并增加 `agent`：名称、版本、工作流、工具列表、步骤状态、证据数量和 `grounded` 标志。该入口始终返回经过引用校验的完整 JSON，不接受流式半成品；个人 API 仍通过本次请求的会话头传入，不落库。

| 方法与地址 | 请求/输出 |
|---|---|
| POST /api/ai/summarize | `{paper_ids:[ID],question?:重点,mode?,top_k?,conversation_id?,stream?}`；只接受一篇 |
| POST /api/ai/compare | 同上，2..10篇不同论文，必须逐篇提供并验证引用 |
| POST /api/ai/conversations | 登录，`{title}`；返回id/title/created_at/updated_at/message_count |
| GET /api/ai/conversations | 登录；本人会话列表 |
| GET /api/ai/conversations/{id}/messages | 登录；本人role/content/citations/created_at历史 |
| DELETE /api/ai/conversations/{id} | 登录；删除本人会话及消息 |

创建会话不需要AI Key；实际问答需要。匿名仍可单次问答；持久化会话必须登录。最多取最近12条消息、每条最多1000字符作为上下文；历史是语境，不是新的论文证据。跟进问题利用前次用户问题辅助检索，生成仍只能引用当前真实片段，不能复用无法定位的旧事实。请求失败不保存伪造回答。

总结和比较优先覆盖每篇的真实摘要、正文及末尾片段，不用一段标题替代全篇依据；这些是受上下文长度限制的摘要，并非完整逐页审阅。任一所选论文没有可用正文/摘要时返回insufficient_evidence。多篇比较的回答必须包含每篇的真实引用，否则502 ai_invalid_citations。引用包含paper_id/paper_title/chunk_id/quote/locator/relevance_score；已确认前不得猜PDF页码。前端可用`/api/chunks/{chunk_id}`定位基础或上传片段。

成功JSON保持answer/evidence_status/citations/retrieval/model，增加operation及conversation_id。retrieval含evidence_count、scope_paper_ids、context_messages。总结/比较默认top_k=10，question可省略；ask的question仍必填。

stream=true返回`text/event-stream`，事件顺序metadata→answer（text段）→done（完整JSON）。**当前先缓冲完整上游结果并通过引用校验，再分段发送**，不是上游逐token传输，因此首段前仍需等待模型完成。引用验证失败时仍是HTTP502 JSON，不泄露半段未验证答案。未配置AI时503 JSON。前端先检查HTTP和Content-Type再读取流。

```text
event: metadata
data: {"operation":"ask","buffered":true}

event: answer
data: {"text":"经引用验证的回答片段"}

event: done
data: {"answer":"...","evidence_status":"sufficient","citations":[],"retrieval":{},"model":{}}
```

以上是形状示例，不是真实AI生成结果。受控模型替身测试与真实证据链测试分开报告；当前没有真实AI Key。

## 复现与联调

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1 -RestartApi
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/discover/random?limit=3'
Invoke-RestMethod 'http://127.0.0.1:8000/api/data-quality'
$data = (Select-String -LiteralPath .env -Pattern '^SCHOLARLENS_REAL_DATA_DIR=').Line.Split('=',2)[1]
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --tb=short --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8000
backend/.venv/Scripts/python.exe -m backend.porter_compare --output backend/.runtime/porter-comparison.json
```

React继续通过Vite同源`/api`代理，不直接连接9200或SQLite。localhost只表示当前电脑，跨电脑连接方式需另外安排。新增功能验收与状态矩阵见V21_PARITY_VERIFICATION.md，不把按钮存在、HTTP202、邮件accepted或模型替身回答当真实业务成功。
