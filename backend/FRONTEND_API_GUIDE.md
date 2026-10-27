# ScholarLens V2 前端接口手册

2026-10-27，负责人组长。后端独立于React开发，未修改frontend。此文配合docs/04_API_CONTRACT.md和运行中的/docs使用。历史FRONTEND_HANDOFF的Mock示例不代表当前真实状态。验收状态以BACKEND_V2_VERIFICATION.md为准。

## 启动与地址

Windows项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/capabilities' | ConvertTo-Json -Depth 8
```

API基础地址http://127.0.0.1:8000；Swagger为/docs，机器协议为/openapi.json。业务路径带/api。示例URL末尾不要带中文标点。数据头X-ScholarLens-Data-Status=real，stats基础语料859篇。原始PDF、AI Key、GROBID是否就绪必须检查能力接口，不能由按钮存在推断。

127.0.0.1始终表示当前电脑。另一台电脑访问自己localhost不会到达组长后端。当前API、ES、SQLite均不开放公网；开发优先将Vite和后端放同机，或由组长单独配置受控端口转发，不向React开放9200或本地数据库。

## 全部业务接口

| 方法/路径 | 输入 | 成功响应 | 身份 |
|---|---|---|---|
| GET /api/stats | 无 | 基础论文数、字段完整率、解析统计、版本、status | 匿名 |
| GET /api/metrics | 无 | 基础/审核上传/向量数量及版本、RRF参数 | 匿名 |
| GET /api/capabilities | 无 | modules模块状态、data_status | 匿名 |
| GET /api/evaluation | 无 | 已测三模式延迟或not_evaluated，相关性指标无标注时null | 匿名 |
| GET /api/suggest | q，limit=8（1..20） | query、suggestions数组 | 匿名 |
| GET /api/discover | limit=6（1..20） | papers、recommendations、example_searches、years、status | 匿名 |
| GET /api/discover/random | limit、seed、exclude | 随机推荐批次与seed，换一批时传回已见paper_id | 匿名 |
| GET /api/search | 下表查询参数 | query/total/page/page_size/took_ms/results | 匿名 |
| GET /api/papers/{id} | include_fulltext=true | 元数据、正文、质量、来源和PDF状态 | 匿名 |
| GET /api/papers/{id}/content | offset=0，limit=8000（1..20000） | 正文字符窗口 | 匿名 |
| GET /api/papers/{id}/chunks | page/page_size | 稳定原文片段分页，不依赖向量 | 匿名 |
| GET /api/chunks/{chunk_id} | 完整chunk:哈希 | 已发布片段原文与locator，不含embedding | 匿名 |
| GET /api/papers/{id}/pdf | 可选Range头 | PDF字节或明确JSON错误 | 匿名 |
| POST /api/evidence | AskInput | 真实Citation数组，不调用AI | 匿名 |
| POST /api/ask | AskInput | answer/evidence_status/citations/retrieval/model | 匿名 |
| POST /api/auth/register | username、password | PublicUser（201） | 匿名 |
| POST /api/auth/login | username、password | user/access_token/token_type/expires_in | 匿名 |
| POST /api/auth/logout | 无 | logged_out | 登录 |
| GET /api/auth/me | 无 | id/username/role | 登录 |
| GET /api/me/favorites | page/page_size | 分页收藏 | 登录 |
| GET /api/me/favorites/{id} | 无 | paper_id/is_favorite | 登录 |
| PUT /api/me/favorites/{id} | 无 | paper_id/is_favorite=true | 登录 |
| DELETE /api/me/favorites/{id} | 无 | paper_id/is_favorite=false | 登录 |
| POST /api/me/history | q/field/mode | id/q/field/mode/created_at（201） | 登录 |
| GET /api/me/history | page/page_size | 分页历史 | 登录 |
| DELETE /api/me/history/{id} | 历史整数ID | deleted | 登录 |
| DELETE /api/me/history | 无 | cleared | 登录 |
| POST /api/uploads | multipart字段file | UploadResponse（201），先待审核 | 登录 |
| GET /api/uploads | page/page_size | 本人上传分页 | 登录 |
| GET /api/uploads/{id} | 上传UUID | 本人上传状态 | 本人/管理员 |
| GET /api/admin/uploads | page/page_size | 全部上传分页 | 管理员 |
| POST /api/admin/uploads/{id}/review | decision、reason | 审核后UploadResponse | 管理员 |
| POST /api/admin/uploads/{id}/process | 无 | processing状态（202），轮询上传状态 | 管理员 |

所有分页page从1开始，page_size默认20，上限100；个人与上传列表page上限10000。成功直接返回业务JSON，错误统一为error对象。不要给PDF字节响应调用json()。路由中的paper_id使用encodeURIComponent；正式ID含冒号，这不是磁盘路径。

## 搜索参数与结果

| 参数 | 类型/默认 | 规则 |
|---|---|---|
| q | 必填string | 1..500字符，拒绝纯空白 |
| field | all | all/title/authors/date/affiliation/address/fulltext |
| mode | keyword | keyword/semantic/hybrid |
| page/page_size | 1/20 | page_size≤100；keyword窗口10000；其余窗口1000 |
| sort | relevance | relevance/year_asc/year_desc，未知年份置后 |
| year_from/year_to | 可空整数 | 1..9999且前者≤后者 |
| phrase | false | keyword或hybrid关键词侧精确短语 |
| fuzzy | false | keyword或hybrid关键词侧AUTO模糊匹配 |

phrase和fuzzy不能同时启用，fuzzy最多20个词。all在BM25侧只查询六字段，普通多词AND可以分布在不同字段，短语须在同一字段完整出现；语义模型覆盖标题、摘要和安全正文。semantic只支持field=all/title/fulltext，拒绝phrase/fuzzy及其他字段。hybrid的作者/日期/机构/地址限定作用于BM25侧，向量侧查询all；选择title/fulltext时两路都限定对应字段。这些限制有400响应，不静默忽略参数。

```http
GET /api/search?q=magnetic&field=title&mode=keyword&page=1&page_size=20
GET /api/search?q=How%20can%20MRI%20measure%20brain%20function&mode=semantic
GET /api/search?q=brain%20imaging&mode=hybrid&year_from=2000&year_to=2009
```

实际关键词结果的主要字段（耗时和分数可能变化）：

```json
{
  "query":{"q":"magnetic","field":"title","mode":"keyword","page":1,"page_size":20,"sort":"relevance","year_from":null,"year_to":null,"phrase":false,"fuzzy":false},
  "total":1,"page":1,"page_size":20,"took_ms":5,
  "results":[{
    "paper_id":"source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae",
    "title":"Dynamic Magnetic Resonance Inverse Imaging of Human Brain Function",
    "authors":["Fa-Hsuan Lin","Lawrence L Wald","Seppo P Ahlfors","Matti S Ha ¨ma ¨la ¨inen","Kenneth K Kwong","John W Belliveau"],
    "year":2006,"abstract_snippet":"MRI is widely used for noninvasive hemodynamic-based functional brain imaging.",
    "highlights":{"title":["Dynamic <em>Magnetic</em> Resonance Inverse Imaging of Human Brain Function"]},
    "score":21.500313,"matched_fields":["title"],"explanation":{"retrieval":"bm25","reason":"title match"}
  }]
}
```

上例摘要为展示节选，真实abstract_snippet最多240字符。语义与混合复用同一结果结构；explanation增加model_name/model_revision/vector_rank/keyword_rank/chunk_id/locator/evidence；hybrid另有rrf_k/rrf_score。explanation的值为字符串，便于保留既有协议。semantic分数为cosine+1，hybrid分数为两路论文排名的1/(60+rank)之和；不要跨模式直接比较分数。

total在keyword是精确匹配论文数，在semantic/hybrid是去重候选论文数，上限受1000候选窗口影响，不是“所有相关论文”的事实判断。向量是精确cosine扫描后按paper_id折叠，以最高片段分数代表论文。语义片段高亮为已转义文本，不伪造em词项；关键词高亮只有em标签，其余原文HTML已转义。React仍须白名单处理em，不把任意字段直接当HTML。

上传批准后加入独立上传BM25索引、统一关键词搜索与详情；原859篇基础统计不改变。上传论文尚未向量化，不属于当前semantic/hybrid向量语料，见metrics的semantic_scope。不要向用户暗示其已具备语义召回。

## 建议和发现

suggest的建议字段为text/field/paper_id，field为title或authors，按词前缀匹配并去重；输入空或仅特殊字符返回空数组，不使用虚构热门词。客户端建议防抖200~300ms，失败时保留手动搜索。

随机推荐使用`/api/discover/random?limit=3`。响应返回seed和recommendations；前端把已展示的paper_id逗号拼接到下一次`exclude`，即可稳定换一批，服务端不编造热度或阅读量。seed相同且exclude相同可复现，省略seed会生成新批次。

```json
{"query":"magnet","suggestions":[{"text":"Dynamic Magnetic Resonance Inverse Imaging of Human Brain Function","field":"title","paper_id":"source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"}]}
```

这是形状节选，实际还可能有其他前缀命中。discover按已知年份降序再paper_id排序，返回真实论文和年份计数；example_searches由返回论文标题生成。它没有阅读量、引用次数或个性化热度，不能标成“热门榜”。学科字段未交付，不编造学科分类。

## 详情、正文和PDF

详情返回paper_id/title/authors/date/year/affiliation/address/abstract/fulltext/pages/pdf_available/source_status/chunks/available_actions/source_info/quality。数组缺失为[]，字符串为""，year/pages可null。partial仍可查看。source_info只含安全来源文件名及正文字符数，quality含parse_status/body_quarantined/missing_fields，不暴露本地路径或原始errors。

默认include_fulltext=true兼容旧接口；详情页面建议传false，再按需请求/content。offset/limit为Python Unicode字符位置，不是字节、PDF页码或浏览器UTF-16索引。应按服务器返回text顺序拼接，不在JS用其偏移切其他编码字符串。

```json
{"paper_id":"...","offset":0,"limit":8000,"total_characters":34491,"text":"真实正文窗口","has_more":true,"locator":"fulltext:chars:0-8000"}
```

此例text是形状说明，不代表真实窗口字面内容。已隔离正文返回空字符串。chunks字段为兼容保留，不表示PDF页码已知；问答引用的片段定位见evidence。

只有pdf_available=true时显示原文按钮，iframe或链接使用/api/papers/{id}/pdf。支持Range头、206、Content-Range；不手工拼本地PDF路径。真实PDF尚未交付，当前原论文PDF返回404 pdf_not_available。受控生成的测试PDF只是测试文件，不是真实论文原文。文件在检查后仍可能丢失，前端须容忍404。

## 问答与证据

```json
{"question":"How is magnetic resonance used for brain imaging?","paper_ids":["source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"],"mode":"hybrid","top_k":5,"conversation_id":null}
```

question为1..2000字符；top_k为1..10；paper_ids省略表示基础论文库，提供时最多20个且每个ID必须存在，空数组拒绝。conversation_id当前不维护会话上下文，仅保留兼容槽位，前端传null。默认hybrid，keyword不依赖向量就可调试证据。

POST /api/evidence返回Citation数组，每条含paper_id/paper_title/chunk_id/quote/locator/relevance_score。quote必须能从该论文的指定字段字符区间逐字取出；没有确认页码时locator例如abstract:chars:0-900。引用可用paper_id打开详情，再按locator显示摘要/正文区间，不编造PDF页数。

POST /api/ask在未配置AI时返回503 ai_not_configured；证据调试仍可用。配置后流程是真实召回、证据筛选、兼容模型调用、引用集合和原文子串校验；模型返回未知引用或改造quote时502 ai_invalid_citations。成功结构：

```json
{"answer":"受证据支持的答案 [chunk:完整哈希]","evidence_status":"sufficient","citations":[{"paper_id":"...","paper_title":"...","chunk_id":"chunk:完整哈希","quote":"原文逐字引用","locator":"abstract:chars:0-900","relevance_score":0.6}],"retrieval":{"mode":"hybrid","top_k":5,"evidence_count":3},"model":{"name":"服务器配置模型","status":"generated"}}
```

该例为协议模板，不是实际AI生成。证据不足为200、answer=""、evidence_status=insufficient_evidence、citations=[]、model.status=not_called（或生成模型自行弃答后无引用）。当前没有真实Key，不宣称真实生成已验收；受控模型替身测试单独报告。

## 登录与个人数据

```json
{"username":"your_account","password":"由用户设置的至少10字符密码"}
```

username为3..64位ASCII字母、数字、下划线、点、短横线，唯一且不区分大小写；密码10..128字符。注册不自动登录且永远不授管理员权限。login返回user={id,username,role}、access_token、token_type=bearer、expires_in=604800。

后续个人请求发送Authorization: Bearer TOKEN。服务器仅存令牌哈希，退出撤销该令牌；重启不丢会话。不要把TOKEN放URL，不记录到控制台，不把密码/令牌提交Git。开发可放内存或sessionStorage；真实公网部署需进一步HTTPS、速率限制与部署审查，当前仅本机课程开发。

收藏PUT幂等，DELETE幂等；GET单篇返回is_favorite；收藏列表results包含paper_id/created_at/title/authors/year/available，已下线论文仍保留收藏但available=false。历史由前端在用户确实提交查询后POST保存，不因自动补全或后台请求自动生成；只保留本人最新200条。其他用户看不到、删不了本人历史和收藏。

匿名论文搜索、详情、建议和公开检索不要求登录。401时清理前端登录态并提示登录；不要让登录失败阻止基础搜索。

## 上传与管理员

上传FormData字段名file，不要手动设置multipart Content-Type，浏览器自动设置boundary。文件最大20MiB；请求体最大21MiB；未加密、1..300页、合法PDF结构才接收。随机内部文件名隔离存储，不使用用户文件名作为磁盘路径。同一用户同一PDF哈希重复上传409。

UploadResponse固定字段id/original_name/sha256/size/status/reason/created_at/updated_at/paper_id/attempts，不包含stored_name、磁盘绝对路径或数据库用户密码。用户只读本人记录；管理员通过本地CLI提升已有账号，见BACKEND_STARTUP.md。普通用户调用admin接口403。

状态流：pending → approved或rejected；approved → processing → indexed或failed；GROBID缺失为dependency_unavailable，原件保留。审核决策POST {"decision":"approve","reason":"核对来源后批准"}。拒绝同理decision=reject。只有已批准状态可处理；未审核文件不参与任何论文搜索。

process返回202后前端轮询GET /api/uploads/{id}，不要将202当作已索引成功。GROBID未配置返回503，状态仍可查询。失败记录仅包含安全原因码；配置修复后管理员重试process。处理状态超过10分钟可显式重试，稳定上传ID和文件SHA保证不重复制造论文ID。上传任务与解析产物只影响独立上传索引，不替换859篇基础别名，所有旧generation保留。

## 能力状态与错误处理

capabilities.modules包含keyword_search/semantic_search/hybrid_search/ai_qa/pdf_preview/favorites/history/authentication/uploads/upload_parsing。状态ready/not_configured/dependency_unavailable/disabled；必须按返回值启用按钮。向量索引未发布时不标ready；AI已配置但尚未成功调用时也不直接标ready，可显示“配置后待验证”并允许试问。AI ready要求近5分钟实际生成和引用验证成功；PDF须逐篇检查pdf_available。

统一错误示例：

```json
{"error":{"code":"pdf_not_available","message":"原始 PDF 尚未交付或暂不可访问","details":{}}}
```

| HTTP/code | 前端动作 |
|---|---|
| 400 invalid_parameter/invalid_file | 显示参数/文件问题，修正后重试 |
| 401 unauthenticated | 提示登录或登录过期 |
| 403 forbidden | 隐藏管理员动作并显示权限提示 |
| 404 not_found/paper_not_found/pdf_not_available | 区分地址、论文、PDF缺失 |
| 409 duplicate_record/invalid_state | 刷新状态，不重复提交 |
| 413 file_too_large | 提示20MiB文件上限 |
| 416 range_not_satisfiable | PDF字节窗口越界，重置Range后重新读取 |
| 429 rate_limited | 减少请求，登录失败5次后等待5分钟 |
| 502 ai_authentication_failed/ai_upstream_error/ai_invalid_response/ai_invalid_citations | 不展示未通过验证的答案，提示管理员检查 |
| 503 ai_not_configured/ai_rate_limited/dependency_unavailable | 如实显示功能未就绪，保留关键词搜索 |
| 504 ai_timeout | 提示模型超时，允许用户稍后重试 |
| 500 internal_error | 显示统一异常，不重复无限重试 |

fetch网络异常不一定有JSON。成功和错误都不含服务器本地路径或密钥。不存在的/api/stats、（末尾顿号）会404，不是服务缺路由。

## React/Vite接入示例

可复制的命令行请求（Windows使用curl.exe避免PowerShell别名）：

```powershell
curl.exe -G 'http://127.0.0.1:8000/api/search' --data-urlencode 'q=magnetic' --data-urlencode 'field=title'
curl.exe -G 'http://127.0.0.1:8000/api/suggest' --data-urlencode 'q=magnet' --data-urlencode 'limit=5'
$credentials = @{username='your_account';password='replace-with-your-password'} | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/auth/login' -ContentType 'application/json' -Body $credentials
$headers = @{Authorization=('Bearer ' + $session.access_token)}
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/me/favorites' -Headers $headers
$question = @{question='How is magnetic resonance used for brain imaging?';mode='keyword';top_k=3} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/evidence' -ContentType 'application/json' -Body $question | ConvertTo-Json -Depth 8
```

上面不会打印令牌；不要把真实登录请求体、$session或$headers截图给其他人。上传可使用curl.exe -H "Authorization: Bearer TOKEN" -F "file=@PATH_TO_YOUR_PDF" http://127.0.0.1:8000/api/uploads，但请自行替换TOKEN且留意终端历史；React优先用FormData。

在现有vite.config.ts中合并，不替换组员已有插件：

```ts
server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } } }
```

```ts
async function api(path: string, init: RequestInit = {}) {
  const response = await fetch(`/api${path}`, init)
  const data = await response.json()
  if (!response.ok) throw Object.assign(new Error(data.error?.message ?? '请求失败'), {
    status: response.status, code: data.error?.code, details: data.error?.details,
  })
  return data
}
const params = new URLSearchParams({ q: 'magnetic', field: 'title', mode: 'keyword' })
const hits = await api(`/search?${params}`)
const detail = await api(`/papers/${encodeURIComponent(hits.results[0].paper_id)}?include_fulltext=false`)
// token来自login响应；不要硬编码。
const favorites = await api('/me/favorites', { headers: { Authorization: `Bearer ${token}` } })
```

同源Vite代理不需要CORS。若浏览器直接请求8000，服务器通过CORS_ORIGINS设置准确来源，例如http://localhost:5173；默认不开放所有来源。最终部署地址可调整，不假设组员前端目录或端口已确定。

## 联调验收清单

1. stats为real、基础indexed=859；capabilities准确区分外部依赖。
2. 搜索magnetic/title命中真实论文，高亮和BM25分数存在；无结果和非法参数正确处理。
3. 相同query切换keyword/semantic/hybrid并重置page，显示不同评分含义。
4. 详情省略正文后按/content加载，PDF缺失保留详情。
5. 无AI Key时提示未配置；/evidence能追溯真实片段。
6. 注册登录、收藏、历史刷新后仍存在；退出后个人接口401。
7. 普通用户上传后pending，不能审核；管理员批准后依赖缺失不伪造indexed。
8. 所有请求走/api；不把9200、数据库、服务器磁盘路径或AI Key发给React。

当前未在真实React页面执行上述操作，前端同学到位后按此清单接入；后端自动与HTTP验收单独记录。
