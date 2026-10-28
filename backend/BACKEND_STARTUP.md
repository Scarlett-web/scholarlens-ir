# Windows 后端启动与恢复

## V2.1 增补

当前入口版本0.2.1，完整新增接口见[FRONTEND_API_GUIDE_V21](FRONTEND_API_GUIDE_V21.md)，历史验收见[V21_PARITY_VERIFICATION](archive/20261026-27/V21_PARITY_VERIFICATION.md)。日常启动不重导基础859篇或49420向量。2026-10-28 正式库原 PDF 已交付并部署到华为云；新电脑仍需恢复原件、模型与索引。真实 AI、邮件和外部 GROBID 未验收；当前支持本地文本 PDF 解析。最新状态见[总报告](../docs/PROJECT_REPORT_20261028.md)。

私有.env新增`EMAIL_BASE_URL`、`EMAIL_API_KEY`（邮件HTTP网关）及`UPLOAD_VECTOR_INDEX=scholarlens-vectors-uploads-real`。一键脚本按白名单加载，不执行.env文本，不输出密钥。EMAIL端点的JSON协议和验证码限制见V2.1手册；不要将真实Key填写到.env.example。

SQLite当前schema_version=4。启动先以SQLite backup API保存迁移前一致性副本至runtime/db-backups，记录SHA，再幂等新增字段/表，不删除旧用户记录。测试证明旧账号字段/哈希、收藏和历史可保留；本机初次审计的实际用户/收藏/上传表均为0行，主库没有用于存储验收账号。

早期原型的第1次加法字段迁移已发生在首次快照前，现有observed快照记录了该事实；随后v3/v4升级有迁移前自动备份。测试另用旧V2字段的独立数据库执行完整升级/恢复，不把observed副本伪称为第一次字段变更前的备份。

数据库恢复须先停止所有使用同一runtime的API/任务。恢复会保留恢复前数据库，**不要把测试数据库覆盖主库**：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
backend/.venv/Scripts/python.exe -m backend.db_migrations --database backend/.runtime/scholarlens.sqlite3 --restore PATH_TO_YOUR_VERIFIED_BACKUP
```

恢复旧schema后若重新启动V2.1会再次执行加法迁移；要回退应用版本也需恢复对应源码。恢复旧备份会撤回备份后的业务写入，应先审阅时间及保留的副本，不能作为日常重启步骤。源代码回退不自动替换用户数据库。

DOCX转换使用本地受限子进程（30秒），没有额外后台服务；扫描PDF需要外部OCR。当前转换仅文本层，复杂排版不保证还原。审批成功的上传使用独立关键词/向量generation，失败重试和管理员向量重试都保留旧代；Porter对照只使用新建的专用测试索引。

本指南描述 Windows 开发环境，分支zjl；请在实际克隆根目录执行，旧 `F:\scholarlens-ir` 是历史示例。已有Python3.11虚拟环境和ES8.19.23 ZIP时跳过首次安装。API/ES仅loopback，SQLite不提供独立网络端口；线上 Linux 独立部署见服务器说明。

## 日常一键启动

```powershell
# 当前终端先进入自己的 ScholarLens 克隆根目录
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

已恢复正式数据时stats应为859、real；不要在URL末尾复制顿号。向量构建完成后semantic/hybrid为ready；PDF、模型和配置以当前机器实际能力为准，不能因线上就绪就假定新克隆也具备。读取/api/metrics区分基础论文、审核上传和向量片段数量。

## 新电脑依赖与模型（仅首次）

```powershell
uv venv --python 3.11 backend/.venv
uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements-lock.txt
powershell -NoProfile -ExecutionPolicy Bypass -File infra/setup-elasticsearch.ps1
```

安装ES需要官方ZIP下载与SHA-512校验；不将本机运行目录复制入Git。正式 JSONL/来源 CSV/原包从独立[数据 Release](https://github.com/Scarlett-web/scholarlens-ir/releases/tag/papers-originals-2026-10-28)恢复，克隆源码不会自动得到索引。来源验证和首次导入见[历史真实数据验收](archive/20261026-27/REAL_DATA_VERIFICATION.md)，原 PDF 恢复见[原件交付](../docs/13_ORIGINAL_PDF_DELIVERY.md)，日常启动不重复导入。

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

上传文件默认在backend/.runtime/uploads/files，解析/索引输入与审计也在runtime；自定义目录以配置为准。管理员批准后才能process。当前未配置 GROBID 时可使用本地文本 PDF 解析，不提供 OCR、不猜学术字段；配置外部 GROBID 时才检查其 `/api/isalive` 和 `POST /api/processFulltextDocument`。文件≤20MiB、1..300页，失败受控返回并保留原件。所有上传generation保留；如需回退使用对应报告与rollback_index CLI，不删除旧索引。真实隔离链见[上传验收](../docs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md)。

## PDF 迁移

原数据组pdf_path保留不改。有同样相对目录结构时配置SCHOLARLENS_PDF_ROOT与SCHOLARLENS_PDF_PATH_BASE。若所有PDF平铺到一个新目录，显式设置SCHOLARLENS_PDF_MANIFEST为来源CSV（paper_id/source_file/pdf_sha256）和PDF_ROOT；服务按paper_id+source_file+SHA核验后从根目录直接取文件。未配置清单不猜basename、不访问远程URI、拒绝越界链接。路径和密钥只填私有.env。

正式库859份原 PDF 已有独立交付和线上验证；新本机是否已恢复仍需逐份配置/核验，不能因源码克隆成功就宣称本机已具备原文。恢复与Range证据见[原件交付](../docs/13_ORIGINAL_PDF_DELIVERY.md)。

## 停止与故障

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-elasticsearch.ps1
```

不要在向量或上传索引写入时主动停止ES；先等待检查点或任务停止。日志在backend/.runtime/api-8000.*.log及infra/.runtime/elasticsearch.*.log。8000无监听为API停止；503依赖未就绪时先查9200；404查完整路径和标点。启动脚本遇PID被Windows重用时保留旧PID记录并避开无关系统进程，不按过期PID杀进程。

历史验证记录见[BACKEND_V2_VERIFICATION](archive/20261026-27/BACKEND_V2_VERIFICATION.md)；任何回退都保留原始JSONL、XML、PDF、SQLite和旧ES索引。当前持续交付约定以仓库AGENTS及用户授权为准，不从旧阶段“不推送”文字推断当前权限；不自动合并其他分支。
