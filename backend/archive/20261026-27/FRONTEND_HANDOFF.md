# ScholarLens 前端联调交接

> 2026-10-27 V2更新：本页保留P0历史记录，当前完整接口请使用[FRONTEND_API_GUIDE](../../FRONTEND_API_GUIDE.md)及运行中的/docs。V2新增建议/发现、语义/RRF、证据/AI配置、SQLite与审核上传；实际可用状态以/api/capabilities及BACKEND_V2_VERIFICATION为准，不用下方历史Mock说明推断当前状态。

> 2026-10-27更新：8000正常API已切换真实859篇，8001亦提供真实验收服务；stats.status与响应头应为real。下方Mock响应保留为协议形状示例，重启Mock需显式指定`-Index scholarlens-papers-mock`。真实查询可用`/api/search?q=dynamic%20magnetic%20resonance&field=title`；真实ID和限制见[REAL_DATA_VERIFICATION](REAL_DATA_VERIFICATION.md)。PDF尚未交付，接口如实返回不可用状态。

以下为2026-10-26的P0历史快照；当前请使用V2手册。历史记录配合 [API Contract](../../../docs/04_API_CONTRACT.md) 使用。当前是真实 Elasticsearch + FastAPI，只有 **2条Mock论文**，正式JSONL和PDF尚未交付。下列响应来自当前索引的实际HTTP请求，耗时随请求变化。

## 1. 启动后端

项目根目录PowerShell；复用已安装环境，不重新搭建ES、不重复导入：

```powershell
Set-Location F:\scholarlens-ir
# 已有ES正在运行时跳过这一条。
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-elasticsearch.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
```

端口占用先检查已有服务，避免重复启动。API基础地址：`http://127.0.0.1:8000`；交互文档：`http://127.0.0.1:8000/docs`。先请求`/api/stats`，预期papers=2、indexed=2、status=mock。API重启先执行`infra/stop-backend.ps1`再start-backend，索引保留。全新电脑安装见[README](../../README.md)。

## 2. Vite代理与localhost

在组员自己的现有vite.config.ts中合并server配置，保留React插件及其他原配置；本轮没有改动frontend/：

```ts
import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

前端统一fetch相对地址`/api/...`。不加rewrite，因为后端路由包含/api。浏览器请求Vite同源地址，再由Vite转发，因此无需开放全域CORS。依据：[Vite官方代理文档](https://vite.dev/config/server-options#server-proxy)。示例尚未在项目React页面实跑，待前端组员联调。

**localhost指各进程所在的电脑。** 组员另一台电脑的127.0.0.1不是组长电脑。优先在同一电脑启动Vite和后端，或组员本机运行同一Mock后端。跨电脑可另行安排SSH端口转发，再将组员本机8000转发至组长API；当前没有配置SSH、局域网监听或防火墙，不要假设将target换成组长IP即可使用。React不直接连接9200；生产部署另配同源反向代理。

## 3. 搜索

```http
GET /api/search?q=computer&field=title&mode=keyword&page=1&page_size=2&sort=relevance
```

HTTP200，响应头`X-ScholarLens-Data-Status: mock`，实际JSON：

```json
{
  "query": {
    "q": "computer", "field": "title", "mode": "keyword",
    "page": 1, "page_size": 2, "sort": "relevance",
    "year_from": null, "year_to": null, "phrase": false, "fuzzy": false
  },
  "total": 1, "page": 1, "page_size": 2, "took_ms": 6,
  "results": [{
    "paper_id": "mock-0002", "title": "Mock Computer Vision Survey",
    "authors": ["Mock Author C"], "year": 2025,
    "abstract_snippet": "Mock abstract snippet for search response testing.",
    "highlights": {"title": ["Mock <em>Computer</em> Vision Survey"]},
    "score": 2.0794415, "matched_fields": ["title"],
    "explanation": {"retrieval": "bm25", "reason": "title match"}
  }]
}
```

field=all或六字段，mode当前只开放keyword。page从1开始；page_size默认20、上限100；窗口10000。sort=relevance/year_desc/year_asc，year_from/year_to可选整数。phrase/fuzzy可单独开启，多词在同一字段AND。q必填且不接受纯空白。

无结果HTTP200、total=0、results=[]。authors始终数组，score不是百分比；highlights仅包含实际高亮字段，缺少时展示原文。后端转义原始HTML并仅添加em，前端仍应将高亮限制为em标签，其余字段使用普通React文本节点。不要依赖固定score或took_ms。

## 4. 论文详情

```http
GET /api/papers/mock-0002
```

HTTP200、mock头，实际JSON：

```json
{
  "paper_id": "mock-0002", "title": "Mock Computer Vision Survey",
  "authors": ["Mock Author C"], "date": "2025-06-01", "year": 2025,
  "affiliation": ["Mock Institute"], "address": ["Mock City"],
  "abstract": "Mock abstract snippet for search response testing.",
  "fulltext": "Mock fulltext used only for front-end development.",
  "pages": {"first": 1, "last": 12, "count": 12},
  "pdf_available": false,
  "source_status": {"pdf": "pdf_not_available", "parse_status": "unknown"},
  "chunks": [], "available_actions": []
}
```

字符串缺失为""，数组为[]，year/pages可为null；pages子字段也可为null。unknown表示输入没有解析状态，不能当作解析成功。partial可读取已有字段。正文来自当前索引，已隔离正文为空，chunks本阶段总是[]。

没有本地pdf_path/source_file、内部date_value、原始errors或虚构PDF链接。空字段显示“原文未提供”，不猜测作者/年份。

```ts
const id = encodeURIComponent(result.paper_id)
const detail = await getJson(`/api/papers/${id}`)
// 仅在detail.pdf_available为true时显示“查看PDF”。
```

## 5. PDF访问

```http
GET /api/papers/mock-0002/pdf
```

当前HTTP404、application/json：

```json
{"error":{"code":"pdf_not_available","message":"原始 PDF 尚未交付或暂不可访问","details":{}}}
```

将来文件就绪后该路由返回application/pdf、inline响应，可用同源链接或iframe；不要对PDF成功响应调用json()。详情显示可用后文件仍可能丢失，PDF路由404时保留详情并提示原文不可用。

后端只有显式配置`SCHOLARLENS_PDF_ROOT`才允许读取；pdf_path默认按项目根目录解释，可用`SCHOLARLENS_PDF_PATH_BASE`迁移基准。路径必须落在允许目录内且是带PDF签名的实际文件，不按文件名猜测匹配、不获取远程URL。签名检查不是完整内容认证，交付时仍须核对来源哈希。本轮没有生成任何假PDF，真实PDF成功传输和浏览器阅读待交付后验收。

## 6. 错误与请求封装

统一错误形状：`{"error":{"code":"...","message":"...","details":{}}}`。

| HTTP/code | 含义及前端处理 |
|---|---|
| 400 invalid_parameter | 输入错误，显示提示，不无限重试 |
| 404 paper_not_found | 论文不存在，展示404状态 |
| 404 pdf_not_available | 保留详情，禁用PDF操作 |
| 404 not_found / 405 method_not_allowed | 检查路由或HTTP方法 |
| 503 dependency_unavailable | ES/索引未就绪或P1模式未开放，显示暂不可用 |
| 500 internal_error | 服务异常，显示错误提示 |

`GET /api/papers/mock-never-existed`实际返回：

```json
{"error":{"code":"paper_not_found","message":"论文不存在","details":{}}}
```

前端API模块可参考以下代码，不在页面散落基础地址：

```ts
async function getJson(path: string) {
  const response = await fetch(path)
  const body = await response.json()
  if (!response.ok) {
    throw Object.assign(new Error(body.error?.message ?? '请求失败'), {
      status: response.status, code: body.error?.code, details: body.error?.details,
    })
  }
  return body
}

const params = new URLSearchParams({
  q: 'computer', field: 'title', mode: 'keyword', page: '1', page_size: '20',
})
const result = await getJson(`/api/search?${params}`)
const stats = await getJson('/api/stats')
// stats.status==='mock'时保留明显Mock标记。
```

网络断开/代理未启动可能使fetch直接抛错，不一定有JSON，需与HTTP错误分开显示。生产页面不硬编码127.0.0.1。

## 7. 联调验收

搜索computer→命中mock-0002→详情字段完整→PDF禁用；搜索不存在词→空状态；不存在ID→404；page_size=101→400。检查浏览器请求走Vite同源/api，并保留Mock标记。实际React页面本轮未验收。

后端测试命令：`backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml -q`，要求现有ES运行，使用唯一临时索引，不覆盖业务alias。正式数据接入见README，不重建994篇ID。
