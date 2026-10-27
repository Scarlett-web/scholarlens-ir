# Windows 后端启动与恢复

2026-10-27。工作区F:\scholarlens-ir，分支zjl。已有Python3.11虚拟环境和ES8.19.23 ZIP，不需要Docker或重新安装。API/ES仅loopback，SQLite不提供独立网络端口。

## 日常一键启动

```powershell
Set-Location F:\scholarlens-ir
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1
```

已有健康ES和API会复用；停机时启动隐藏后台进程，不要求保持两个可见终端。它读取私有.env的白名单设置，不自动导入JSONL、不下载模型、不重建索引。检查输出版本和papers/status，再打开http://127.0.0.1:8000/docs 。代码或配置更新后：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1 -RestartApi
```

重启只停止经项目PID、命令和路径校验的API进程树。ES不会随API重启。电脑关机、重启或休眠后需再次检查服务，之前任务结束时的“运行中”不是永久状态。

## 验证

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/metrics' | ConvertTo-Json -Depth 8
Invoke-RestMethod 'http://127.0.0.1:8000/api/capabilities' | ConvertTo-Json -Depth 8
Invoke-RestMethod 'http://127.0.0.1:8000/api/search?q=magnetic&field=title' | ConvertTo-Json -Depth 10
```

基础stats为859、real；不要在URL末尾复制顿号。向量构建完成后semantic/hybrid为ready；AI Key和真实PDF未交付时如实标记。读取/api/metrics区分基础论文、审核上传和向量片段数量。

## 新电脑依赖与模型（仅首次）

```powershell
uv venv --python 3.11 backend/.venv
uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements-lock.txt
powershell -NoProfile -ExecutionPolicy Bypass -File infra/setup-elasticsearch.ps1
```

安装ES需要官方ZIP下载与SHA-512校验；不将本机运行目录复制入Git。真实JSONL需另行交付，不能仅靠仓库得到859篇数据。原件验证和正式索引首次导入沿用REAL_DATA_VERIFICATION.md，日常启动不重复导入。

嵌入模型选用固定revision的sentence-transformers/all-MiniLM-L6-v2 ONNX，384维、mean pooling、L2归一化，CPU2线程、最大256 tokens、批次8。模型约90MB，免装PyTorch/CUDA；依据[模型卡](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)和[ONNX线程配置](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)。全库900字符块、重叠100字符，标题/摘要/855份安全正文，原4份乱码正文不进入向量。

```powershell
backend/.venv/Scripts/python.exe -m backend.embeddings
backend/.venv/Scripts/python.exe -m backend.vector_index --state backend/.runtime/vector-build.json --batch-size 8
# 或隐藏后台续建同一检查点，日志/PID记录在runtime，不重复启动已有任务：
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-vector-build.ps1
```

第二条可在同一检查点断点续建；已确认bulk成功才推进completed，重复未确认批次使用同一chunk_id覆盖本代对应片段。输入、模型、分块或基础generation不同会拒绝旧检查点，使用新的state文件名重建独立generation；只有全部count核对后才切换向量alias，不更改BM25。不要并发运行相同检查点；上一构建进程是否退出须查看实际进程，不能只凭“没输出”重启。

精确cosine使用ES8.19 dense_vector/script_score，无需付费RRF/模型推理服务。向量index=false，按当前约5万片段全量扫描，属于课程规模方案；更大规模需要重新基准后考虑HNSW。官方依据：[script_score](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/query-dsl-script-score-query.html)。

## 用户、管理员与本地数据

先通过/api/auth/register注册自己的账号，再由运行这台机器的组长执行：

```powershell
backend/.venv/Scripts/python.exe -m backend.accounts --promote your_existing_username
```

没有默认管理员或硬编码密码。该CLI直接操作本地SQLite，不接受公网调用。若使用自定义SCHOLARLENS_RUNTIME_DIR，CLI与API须使用同一变量。数据库默认backend/.runtime/scholarlens.sqlite3，SQLite WAL、会话、收藏、历史和上传记录重启后保留。备份时使用sqlite3.Connection.backup()，不要在写入时只复制主库丢掉WAL。

上传文件backend/.runtime/uploads/files，解析/索引输入与审计也在隔离目录。管理员批准后才能process；GROBID缺失时503，配置GROBID_URL后可重试。依赖健康检查/api/isalive，实际解析POST /api/processFulltextDocument。文件≤20MiB、1..300页，任务处理超时后可重试。所有上传generation保留；如需回退使用该次import报告与既有rollback_index CLI，禁止删除旧索引。

## PDF 迁移

原数据组pdf_path保留不改。有同样相对目录结构时配置SCHOLARLENS_PDF_ROOT与SCHOLARLENS_PDF_PATH_BASE。若所有PDF平铺到一个新目录，显式设置SCHOLARLENS_PDF_MANIFEST为来源CSV（paper_id/source_file/pdf_sha256）和PDF_ROOT；服务按paper_id+source_file+SHA核验后从根目录直接取文件。未配置清单不猜basename、不访问远程URI、拒绝越界链接。路径和密钥只填私有.env。

真实PDF尚未交付，不能宣称本机已有859篇原文阅读。PDF接口和Range仅通过受控文件测试。

## 停止与故障

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-elasticsearch.ps1
```

不要在向量或上传索引写入时主动停止ES；先等待检查点或任务停止。日志在backend/.runtime/api-8000.*.log及infra/.runtime/elasticsearch.*.log。8000无监听为API停止；503依赖未就绪时先查9200；404查完整路径和标点。启动脚本遇PID被Windows重用时保留旧PID记录并避开无关系统进程，不按过期PID杀进程。

源代码回退、补丁和验证记录见BACKEND_V2_VERIFICATION.md；任何回退都保留原始JSONL、XML、PDF、SQLite和旧ES索引。当前分支保持zjl，无自动Commit/Push/Merge。
