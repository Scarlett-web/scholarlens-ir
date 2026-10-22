# 04 HTTP API 契约

> 路径前缀暂定 `/api`，具体端口、认证方案、ES 版本和分页上限待会议确认。以下示例展示协议形状；数据可为 Mock，不能宣称服务已运行。

## 1. 通用约定

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
  "query":{"q":"computer","field":"title","mode":"keyword","page":1,"page_size":2,"sort":"relevance"},
  "total":2,"page":1,"page_size":2,"took_ms":12,
  "results":[
    {"paper_id":"mock-0001","title":"Mock: Information Retrieval Evaluation","authors":["Mock Author A","Mock Author B"],"year":2026,"abstract_snippet":"...retrieval evaluation...","highlights":{"title":["Mock: Information <em>Retrieval</em> Evaluation"]},"score":4.82,"matched_fields":["title"],"explanation":{"retrieval":"bm25","reason":"title match"}},
    {"paper_id":"mock-0003","title":"Mock Computer Vision Survey","authors":["Mock Author C"],"year":2025,"abstract_snippet":"Mock abstract snippet.","highlights":{"title":["Mock <em>Computer</em> Vision Survey"]},"score":3.17,"matched_fields":["title"],"explanation":{"retrieval":"bm25","reason":"title match"}}
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

## 5. 问答

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

## 6. 计划接口（阶段标记）

| 阶段 | 方法与路径 | 用途 |
|---|---|---|
| P2 | `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout` | 注册登录 |
| P2 | `GET/POST/DELETE /api/me/favorites/{paper_id}` | 收藏 |
| P2 | `GET /api/me/history`、`POST /api/me/history` | 搜索历史 |
| P2 | `POST /api/uploads` | 论文上传，需大小/类型/权限限制 |
| P2 | `GET /api/admin/uploads`、`POST /api/admin/uploads/{id}/review` | 管理员审核 |

这些接口在认证、SQLite schema 和上传安全方案确认前仅保留契约，不得在 UI 中暗示已经可用。

## 7. 错误码

`400 invalid_parameter`、`401 unauthenticated`、`403 forbidden`、`404 paper_not_found`、`404 pdf_not_available`、`409 duplicate_record`、`413 file_too_large`、`429 rate_limited`、`500 internal_error`、`503 dependency_unavailable`。错误 `details` 只放可诊断的非敏感信息。

