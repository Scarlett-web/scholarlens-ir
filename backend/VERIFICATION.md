# 后端 P0 实际验证记录

日期：2026-10-26（Asia/Shanghai）。论文内容为 **Mock**，检索、导入和HTTP请求使用真实进程；没有用Mock引擎替代Elasticsearch。当前分支zjl，数据组PR保持未合并，未执行commit/push/merge。

## 环境与输入

- Windows 11 专业版64位；Python3.11.9；物理内存15.24GB，初检空闲2.52GB；F盘初检空闲428.21GB；Docker未安装。
- Elasticsearch8.19.23，Lucene9.12.2，Windows ZIP自带JDK，堆512MB；Python elasticsearch8.19.3，FastAPI0.162.0，Uvicorn0.54.0。完整锁定版本见requirements-lock.txt。
- 官方ZIP大小525602278字节，setup已下载并核对官方SHA-512，退出0。
- 初始backend仅.gitkeep，8000/9200/9300未监听，FastAPI/ES Python依赖未安装。此为开发前基线，不存在可返回搜索结果的旧业务服务。
- 输入命令：`backend/.venv/Scripts/python.exe -m backend.import_jsonl --input data/sample/mock_papers.jsonl --data-status mock --index scholarlens-papers-mock --report backend/.runtime/import-mock-initial.json`
- 输入原文件SHA-256：`40036eb9c579b87c9b62ab9b75382f657b231929ecda2c43cb5563ad8d9ae8f7`；原文件未修改。
- 退出0，literal输出：

```json
{"data_status":"mock","input_sha256":"40036eb9c579b87c9b62ab9b75382f657b231929ecda2c43cb5563ad8d9ae8f7","input_records":2,"accepted_records":2,"parser":{"success":0,"partial":0,"failed":0,"unknown":2},"fields_completeness":{"title":1.0,"authors":1.0,"date":1.0,"affiliation":1.0,"address":1.0,"fulltext":1.0,"abstract":1.0,"year":1.0},"skipped":[],"body_quarantined":[],"last_built_at":"2026-10-26T09:26:20Z","alias":"scholarlens-papers-mock","generation":"scholarlens-papers-mock-6baa7d070b4f","previous_generations":[],"indexed":2,"bulk_failed":0}
```

JSON对象空白已压缩，字段值来自实际命令，不是期望值。报告文件保留命令原始字段。Mock未提供解析状态，unknown=2，未记作success。

## HTTP 实测

启动命令：`powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1`，退出0。使用Python urllib发送以下GET请求并JSON解析，采集命令退出0。完整实际响应见`.runtime/http-verification.json`。

`http://127.0.0.1:8000/api/search?q=computer&field=title`：HTTP200，响应头`X-ScholarLens-Data-Status: mock`，实际响应：

```json
{"query":{"q":"computer","field":"title","mode":"keyword","page":1,"page_size":20,"sort":"relevance","year_from":null,"year_to":null,"phrase":false,"fuzzy":false},"total":1,"page":1,"page_size":20,"took_ms":4,"results":[{"paper_id":"mock-0002","title":"Mock Computer Vision Survey","authors":["Mock Author C"],"year":2025,"abstract_snippet":"Mock abstract snippet for search response testing.","highlights":{"title":["Mock <em>Computer</em> Vision Survey"]},"score":2.0794415,"matched_fields":["title"],"explanation":{"retrieval":"bm25","reason":"title match"}}]}
```

`http://127.0.0.1:8000/api/stats`：HTTP200、mock头，实际响应：

```json
{"papers":2,"indexed":2,"fields_completeness":{"date":1.0,"address":1.0,"affiliation":1.0,"year":1.0,"fulltext":1.0,"abstract":1.0,"title":1.0,"authors":1.0},"parser":{"success":0,"failed":0,"partial":0,"unknown":2},"index":{"last_built_at":"2026-10-26T09:26:20Z","mapping_version":"papers-p0-v1"},"status":"mock"}
```

`/api/search?q=absentterm`：HTTP200、total=0、results=[]；`/api/search?q=x&page_size=101`：HTTP400，实际body：

```json
{"error":{"code":"invalid_parameter","message":"请求参数不符合契约","details":{"fields":["query.page_size"]}}}
```

## 自动检查

命令：

```powershell
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m ruff format --check backend
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml -q
```

ruff检查退出0：`All checks passed!`。pytest退出0：`32 passed, 1 warning in 3.54s`。

警告为已安装Starlette测试客户端对httpx的弃用提示；没有测试失败。测试覆盖六字段各两条查询、BM25排序、分页、年份过滤/排序、短语/模糊、高亮HTML转义、空结果、非法参数400、未实现模式503、缺索引503、BOM与类型/日期/重复ID校验、partial/error、乱码隔离、真实bulk映射失败不切换alias，以及重导入/回退。

## 重导入与回退实测

```powershell
backend/.venv/Scripts/python.exe -m backend.import_jsonl --input data/sample/mock_papers.jsonl --data-status mock --index scholarlens-papers-mock --report backend/.runtime/import-mock-reimport.json
backend/.venv/Scripts/python.exe -m backend.rollback_index --report backend/.runtime/import-mock-reimport.json
```

均退出0。第二次generation=`scholarlens-papers-mock-849847beeab3`，previous_generations为初始generation；回退命令literal输出：

```json
{"alias":"scholarlens-papers-mock","restored":"scholarlens-papers-mock-6baa7d070b4f","indexed":2}
```

`infra/stop-backend.ps1`、`infra/stop-elasticsearch.ps1`均实际执行退出0，随后重新启动核查持久化；最终状态见本文件末尾复核。停止脚本仅处理记录的本项目进程，保留索引文件；ES停止使用Windows进程树终止，启动后依靠持久化日志恢复，不用于生产运维。

## 限制

这些结果证明最小后端能够运行，不代表真实论文质量、1000篇规模性能、中文检索或PDF阅读已验收。最终JSONL尚未交付。当前使用standard分析器，后续真实语料需单独评价；服务限本机开发使用。

## 最终复核

停止再启动ES与API后，实际HTTP再次返回indexed=2、status=mock，computer标题查询仍命中mock-0002、score=2.0794415；持久化验证命令退出0，结果见`.runtime/restart-verification.json`。启动ES增加等待集群恢复到yellow/green，避免节点刚监听但尚未恢复时就报告就绪。服务最终保留运行，API http://127.0.0.1:8000 ，ES http://127.0.0.1:9200 。

`ruff format --check backend`退出0：`11 files already formatted`；`git diff --check`退出0。scripts/、data/和frontend/没有修改。源代码及必要公共文件的可审阅差异保存在`.runtime/p0-changes.patch`，Git基线文件和SHA-256清单保存在`.runtime/baseline.zip`、`.runtime/change-hashes.json`，这些本地审核产物不提交Git。
