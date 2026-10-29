# 真实论文数据与全量倒排检索验收

日期：2026-10-27（Asia/Shanghai）。本报告基于正式交付文件、真实 Elasticsearch 和实际 HTTP 请求。范围是859篇现有论文的文本检索，不包含补足1000篇、PDF补抽取、语义/RAG或前端页面。

## 1. 结论与服务

859篇结构有效记录均已导入，跳过0、bulk失败0。644篇partial保留，4篇严重乱码仅隔离fulltext，保留论文及元数据；855篇正文参与全文检索。8000正常开发API和8001验收API均指向real，Mock和旧generation保留。PDF未交付，返回pdf_not_available。

当前别名：`scholarlens-papers-real`；generation：`scholarlens-papers-real-090928bb1545`；Mapping：`papers-p0-v1`。独立20篇样本别名为`scholarlens-sample20-real`。正常启动的默认索引已改为real，环境变量或-Index可显式覆盖。

## 2. 来源、版本与哈希差异

- 仓库：Scarlett-web/scholarlens-ir，远程分支origin/feat/pdf-parser。
- 固定交付提交：[6e40caab5dd2ad689e3dcfaf592df2694d1fbd06](https://github.com/Scarlett-web/scholarlens-ir/commit/6e40caab5dd2ad689e3dcfaf592df2694d1fbd06)。本轮只fetch和读取，没有切换或合并。
- JSONL Git blob：`b786ea88a9e0fba8e05695e9bbea849cc23d9523`。
- 正式原件papers_final.jsonl：**39,226,615字节**，UTF-8，无BOM，859个LF换行；通过Python subprocess二进制stdout直接保存，经临时文件哈希校验后落盘，没有PowerShell文本重定向。
- 实际SHA-256：`a73e65c552264ae7dee265d1ad854ea700c9377c0e2f54bb97a49c78b1d1441c`。
- 旧声明为`1d37b56454e30ec4f7381164626b3c8c8874a7560f47025ea45eb126d5054f94`，与新上传Git原件不同；常见LF/CRLF、BOM、尾换行变体也不匹配。旧字节快照未交付，因此没有可证明的逐字段版本差异。这里验收的是固定新提交和实际哈希，没有将旧声明写成已验证相同；请数据组同步修正文档或解释版本来源。
- 来源清单SHA-256：`6828b0aa1caf44f629f5b71134af80aff1badcc8f189c30f0cc4fc6fcbf8dc43`。Git内容已核验，原始PDF哈希**尚未实物核验**。

本地数据位置由私有.env的SCHOLARLENS_REAL_DATA_DIR登记，不把原数据放入当前分支。delivery_provenance.json记录获取方式、提交、字节数和各文件摘要。

## 3. 全量结构、来源与质量

859行全部是JSON对象并通过类型校验；空行0、重复ID0、完全重复记录0、非法日期/日期年份冲突0、严重校验错误0。859个ID、来源文件、路径与清单一一对应，清单哈希格式及既有ID公式全部匹配；没有重建或改写正式ID。859个来源都有本地XML，但本轮没有执行XML转换器。

状态：success=215、partial=644、error=0。状态是交付文件中的标记，success不代表人工逐字段核实；partial不等于解析失败。

| Field | Nonempty | Rate |
|---|---:|---:|
| title | 859 | 100.00% |
| authors | 857 | 99.77% |
| date | 231 | 26.89% |
| year | 478 | 55.65% |
| affiliation | 765 | 89.06% |
| address | 681 | 79.28% |
| pages | 859 | 100.00% |
| abstract | 773 | 89.99% |
| fulltext | 859 | 100.00% |
| pdf_path | 859 | 100.00% |


缺完整日期628篇，其中仅年份247篇；年份缺失381篇。不补造月日或从正文猜年份。pages全部为物理页数count，first/last为空，不宣称是刊物页码。

| Field | Min | Median | P95 | Max |
|---|---:|---:|---:|---:|
| fulltext | 1526 | 34491 | 114019 | 220366 |
| abstract | 0 | 1177 | 2357 | 10659 |


34组相同规范化标题涉及69条记录，属于重复候选，不证明同一PDF或相同版本；全部保留，交数据组结合来源复核。自动边界/长度/替代字符启发式共标记41篇正文待核查；启发式未命中不能证明正文完整。字段异常/人工核查列见质量JSON，属于自动规则范围，未开展859篇PDF人工事实认证。

真实详情样例中还保留了原始抽取的姓名重音、机构断词等问题，例如`Matti S Ha ¨ma ¨la ¨inen`、`Massachusetts Gen- eral Hospital`。本轮不猜改这些内容。前两轮发现的标题/列表/公式遗漏和引用粘连也没有通过重跑旧转换器覆盖最终文件；检索可运行，不等于解析质量问题全部修复。

## 4. 安全清洗与数量对账

原件papers_final.jsonl保持不变。独立papers_index_ready.jsonl仍859条，SHA-256=`13f68a8c05294920d13037064a8b47cebeaf829dd5691f2f72e6c09b8a747e60`。只将以下4条fulltext在索引输入中置空，其余所有字段逐项一致；没有删除乱码字符来伪装修复。原文保留在原件，real_data_changes.json记录ID、源文件、行号、原文长度/哈希及原因，可按原件恢复。

| Source PDF filename | U+FFFD | Changed field |
|---|---:|---|
| `rystalisgsuiucedumapsdatapubisgsquadsapdffilesavabgrept.pdf` | 550 | fulltext |
| `sppsdpwgscgccaCollectionR71412004E9.pdf` | 489 | fulltext |
| `wwcsjhueduscottpllpapersmicrokernel05.pdf` | 7 | fulltext |
| `wwforgovbccahfdpubsDocsRrRr24.pdf` | 3830 | fulltext |


859接受、0排除、4正文隔离、855正文非空。Elasticsearch的exists会把空字符串视为存在，因此使用termvectors核查隔离正文零词项，而非误用exists。导入器也识别已被清洗为空但仍带乱码标记的记录，在最终导入报告计为4条隔离。

逐字段原始完整率、异常列表、来源检查、长度分布、重复标题候选在real_data_quality_report.json；不满足结构的严重错误会阻止发布。本次没有严重错误，无需擅自修正正确字段。

## 5. 20篇先行验收与全量导入

样本覆盖4条质量警告、完整元数据、缺日期、仅年份、多作者/机构、缺作者/机构/地址/摘要、长短正文。选择算法按固定ID规则确定，paper_id原样保留，选择理由见real_sample20_selection.json。

20/20导入，0失败；通过8001的7组字段查询、20篇详情逐字段比对、BM25、分页/高亮、年份、错误和PDF缺失检查后，使用同一个backend.import_jsonl导入全量，批次100，没有重写索引架构。

初代全量90c44deda57e保留。随后补正“清洗输入已为空的隔离计数”报告逻辑，建立新generation090928bb1545，并在全部bulk成功和count=859后切换real别名。Mock的6baa7d070b4f和849847beeab3均保留，不删除旧索引。没有并发向同一别名导入。

全量验收用mget逐一检查859个ID和全部_source字段，而非只看count；通过HTTP核对20篇代表详情，比较全部公开字段，检查缺PDF与空日期/数组/partial。统计接口的indexed实际调用ES count，不硬编码859。

## 6. 六字段与all实际查询

基础地址：http://127.0.0.1:8000 。下表均为实际GET /api/search，参数q与field如下；示例特意从同一份具备六字段的论文选择，以逐字段确认。响应头为X-ScholarLens-Data-Status: real。

| field | q | HTTP | Total | Expected rank |
|---|---|---:|---:|---:|
| title | `dynamic magnetic resonance inverse imaging` | 200 | 1 | 1 |
| authors | `fa hsuan lin` | 200 | 1 | 1 |
| date | `2006-09-08` | 200 | 1 | 1 |
| affiliation | `athinoula a martinos center for` | 200 | 1 | 1 |
| address | `charlestown massachusetts usa` | 200 | 1 | 1 |
| fulltext | `single shot fast mri with` | 200 | 1 | 1 |
| all | `dynamic magnetic resonance inverse imaging` | 200 | 1 | 1 |


这些查询均找回原ID `source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae`，命中字段、高亮和正分数均已检查。为避免只验证单命中排序，另用all查询the，实际命中845篇；检查前10条分数非增、同分ID稳定，以及API ID/分数与直接ES查询完全一致。排名前3的实际分数为12.895018、5.338615、5.0376735，不作为学术相关性评价或固定预期值。

分页两页无重复；年份范围筛选和升降序通过，未知年份置后；另以实际日期的年份2006查询date字段并找回目标，仅年份记录通过year范围找回且date无词项，未制造完整日期。不存在词返回200/total=0/results=[]，非法参数400，缺论文404，错误JSON结构统一。

## 7. 实际详情与PDF限制

请求：GET /api/papers/source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae。实际HTTP200，以下为响应节选，未列abstract/fulltext/chunks/actions；完整响应存在本地忽略目录real-detail-example.json：

```json
{
  "paper_id": "source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae",
  "title": "Dynamic Magnetic Resonance Inverse Imaging of Human Brain Function",
  "authors": [
    "Fa-Hsuan Lin",
    "Lawrence L Wald",
    "Seppo P Ahlfors",
    "Matti S Ha ¨ma ¨la ¨inen",
    "Kenneth K Kwong",
    "John W Belliveau"
  ],
  "date": "2006-09-08",
  "year": 2006,
  "affiliation": [
    "Athinoula A. Martinos Center for Biomedical Imaging",
    "Massachusetts Gen- eral Hospital",
    "Department of Radiology",
    "Massachusetts General Hospital"
  ],
  "address": [
    "Charlestown Massachusetts USA",
    "Bldg. 149 13th Street 149-2301 02129. Mailcode Charles- town MA"
  ],
  "pages": {
    "first": null,
    "last": null,
    "count": 16
  },
  "pdf_available": false,
  "source_status": {
    "pdf": "pdf_not_available",
    "parse_status": "success"
  }
}
```

相同ID的/pdf实际返回404/pdf_not_available。859份PDF当前路径均不存在，服务也未配置允许PDF目录；文本检索不依赖PDF就绪。不能证明PDF页面内容、物理页数、作者和发表日期与原文一致；PDF签名检查、成功传输、Range和浏览器渲染待交付后验收。

## 8. 自动测试、异常处理与重启

最终完整命令（本地数据路径由私有配置传入）：

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --tb=short --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8001
```

退出状态0，literal摘要：`90 passed, 1 warning in 44.89s`。最终stdout/stderr及命令退出码保存在backend/.runtime/real-final90-pytest.json，日志为real-final90-pytest.log。之前修复后的完整运行也是90passed。唯一警告是既有Starlette/httpx测试客户端弃用提示。ruff检查退出0（All checks passed!），format检查退出0（23 files already formatted），git diff --check退出0。

测试包含全量JSONL、来源清单、清洗前后逐字段一致性、禁止覆盖、20篇选择覆盖、全部_source、六字段/all、BM25与直接ES分数比对、分页/高亮/年份、详情/PDF缺失、Mock隔离、真实独立别名的导入/CLI回退、测试专用API8002的启动/停止/重启。真实测试需显式提供本地数据目录，缺该选项会明确skip，不能把skip算成真实验收。

初始服务未启动时基线35passed/39连接错误，恢复已有ES后74项全通过。真实测试选项首次因未显式给出backend/tests而未加载conftest，命令已纠正。新增自动API重启测试发现Windows虚拟环境启动器的子进程/继承输出管道问题；修正为停止经验证的项目进程树、等待端口释放，测试启动日志用文件而非PIPE，随后重新完整测试。失败日志保留为real-final-pytest.log，最终日志为real-complete-pytest.log，未用假数据掩盖失败。

ES实际停止再启动后cluster_uuid仍为65T3rUJHRdKST9Am6J9Oqw，健康green，Mock旧generation和真实859篇均恢复。8000、8001都继续real查询；证据real-es-restart-evidence.json。8000默认real→显式Mock回退(2篇)→恢复real的运行验证也已完成。最终进程树修复后再次重启8000并完成real-final-http-8000-v2.json验收，全部859个_source再次一致，日期年份查询及多命中BM25分数也经过HTTP与ES比对。

## 9. 次日启动、复验与恢复

所有命令在项目根目录PowerShell执行。依赖和ES已安装，不需要重复setup、导入或重新创建后端。启动前检查端口，已运行则跳过对应start：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-elasticsearch.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/search?q=dynamic%20magnetic%20resonance&field=title' | ConvertTo-Json -Depth 10
# 可选独立真实验收API
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1 -Port 8001 -Index scholarlens-papers-real
```

运行目录仍是infra/.runtime和backend/.runtime，PID按端口区分，API只监听127.0.0.1。环境变量ELASTICSEARCH_INDEX有优先级，如设置成mock应显式改real或清除；以stats.status和响应头核实实际状态。

本地数据目录已登记在私有.env中，只读取对应项，不打印其他密钥；应用本身不自动加载.env：

```powershell
$data = (Select-String -LiteralPath .env -Pattern '^SCHOLARLENS_REAL_DATA_DIR=').Line.Split('=',2)[1]
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8001
```

重新校验/清洗使用相同命令；输出存在且内容一致则验证后复用，不同则停止，不覆盖：

```powershell
backend/.venv/Scripts/python.exe -m backend.prepare_real_data --input "$data/papers_final.jsonl" --manifest "$data/paper_source_manifest.csv" --output "$data/papers_index_ready.jsonl" --report "$data/real_data_quality_report.json" --changes "$data/real_data_changes.json" --xml-root "$data/pdfXML"
```

未来修订新数据时保留本次原件、报告和摘要，先新文件名重跑全量审核与20篇测试，再使用现有导入器创建新generation，报告名也应全新。不并发导入，不清理旧索引。

```powershell
$report = 'backend/.runtime/import-real-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
backend/.venv/Scripts/python.exe -m backend.import_jsonl --input "$data/papers_index_ready.jsonl" --data-status real --index scholarlens-papers-real --report $report
# 只有需回退该次成功导入时执行；保留所有索引，仅切换别名。
backend/.venv/Scripts/python.exe -m backend.rollback_index --report $report
```

停止与恢复：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1 -Port 8001
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-elasticsearch.ps1
```

原Mock回退（无需删除real或修改ID）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1 -Index scholarlens-papers-mock
# 恢复真实服务：再次stop后使用-Index scholarlens-papers-real或清除覆盖变量后的默认start。
```

## 10. 本地证据与未决项

提交候选共50文件，扫描未发现常见私钥/OpenAI/AWS密钥格式、超过5MB文件或运行目录；.env、虚拟环境、ES运行目录与本地证据均被Git忽略。暂存区为空，分支zjl，scripts/data/frontend未改动。扫描不能代替人工review，没有执行commit/push/merge。

本轮四类可核验交付为：后端源码与数据准备/验收命令；`backend/.runtime/real-goal-changes.patch`；本报告和实际JSON/测试日志；`backend/.runtime/rollback-real-goal.py`。源代码原态在real-goal-before.zip，变更前后摘要在real-goal-change-hashes.json。补丁反向检查和回退工具在独立临时目录执行，逐文件核对恢复哈希；当前服务保持新版。回退源码前应停止API，恢复后重启；它不删除真实数据、Mock或任何旧索引，本地.env数据位置登记保留。

质量报告、原件、索引输入、账本、样本及选择说明在私有数据目录；导入/HTTP/测试/重启证据在backend/.runtime。原始数据和运行文件不提交Git。源代码变更保留前态快照、SHA-256、补丁和经过隔离恢复测试的回退脚本。

仍需数据组解释旧声明哈希，交付PDF以实物核验，复核34组标题重复候选、41条正文边界候选及姓名/机构编码问题，并修复旧转换器的提取遗漏。本次不据此擅自删除或改写论文。这些限制不妨碍按现有真实JSONL建立可运行文本检索，但会影响检索召回与后续学术质量评价。前端React、中文专用分析器、性能基准、PDF阅读均不在本轮完成声明内。
