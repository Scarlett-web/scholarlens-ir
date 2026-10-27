# ScholarLens 后端

## V2.1 功能对齐入口

对标学长报告的新功能与状态见[V21_PARITY_GOAL](V21_PARITY_GOAL.md)和[V21_PARITY_VERIFICATION](V21_PARITY_VERIFICATION.md)，前端使用[FRONTEND_API_GUIDE_V21](FRONTEND_API_GUIDE_V21.md)。V2接口继续兼容，本轮不提交推送、不改React，不删除既有索引/用户数据。AI和邮件密钥留在服务器私有.env。

## 当前 V2 开发入口（2026-10-27）

本次组长已放行语义/RRF/RAG、SQLite用户与审核上传，历史P0限制不再代表当前范围。进度见[BACKEND_V2_GOAL](BACKEND_V2_GOAL.md)，实际验收见[BACKEND_V2_VERIFICATION](BACKEND_V2_VERIFICATION.md)。前端以[FRONTEND_API_GUIDE](FRONTEND_API_GUIDE.md)和/docs为准；一键启动见[BACKEND_STARTUP](BACKEND_STARTUP.md)，AI设置见[AI_CONFIGURATION](AI_CONFIGURATION.md)，评价见[SEARCH_EVALUATION](SEARCH_EVALUATION.md)。原859篇、Mock和旧generation保留，AI Key与真实PDF/GROBID未提供时如实标记。

> 2026-10-27：859篇正式JSONL已验收并导入，正常启动默认scholarlens-papers-real。实际质量、查询、回退及限制见 [真实验收报告](REAL_DATA_VERIFICATION.md)，持续进度见 [REAL_DATA_GOAL](REAL_DATA_GOAL.md)。下方两条Mock示例保留为历史/隔离调试用，需显式`-Index scholarlens-papers-mock`。普通启动不需再次导入。PDF尚未交付。

2026-10-26：真实 Elasticsearch 上运行 Mock 论文。实现六字段 BM25、分页、高亮、年份筛选/排序、JSONL 导入、FastAPI search/stats、论文详情和受控 PDF 访问。前端阅读 [FRONTEND_HANDOFF](FRONTEND_HANDOFF.md)；本轮实测见 [VERIFICATION_STAGE2](VERIFICATION_STAGE2.md)。数据组 PR 保持未合并。协议：[数据格式](../docs/03_DATA_SCHEMA.md)、[API](../docs/04_API_CONTRACT.md)；第一阶段记录：[VERIFICATION](VERIFICATION.md)。

## 环境与版本

正常体验真实数据（现有索引不需重导入）：

```powershell
# 项目根目录；对应服务已经运行时跳过start。
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-elasticsearch.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/search?q=dynamic%20magnetic%20resonance&field=title' | ConvertTo-Json -Depth 10
```

应返回status=real、indexed=859。8001是同一真实索引的独立验收服务，通过`-Port 8001 -Index scholarlens-papers-real`启动；停止脚本同样接收-Port，PID/日志按端口保存。Windows停止会核实项目路径、命令和端口后终止所属进程树，避免虚拟环境子进程残留。

全量真实数据回归（本地数据变量已登记私有.env；先确保8001服务在运行）：

```powershell
$data = (Select-String -LiteralPath .env -Pattern '^SCHOLARLENS_REAL_DATA_DIR=').Line.Split('=',2)[1]
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8001
```

上一轮真实数据Goal实测为90项通过，当前V2完整131项见BACKEND_V2_VERIFICATION.md，包括原74项和16项真实交付/实际HTTP/服务重启测试；省略真实数据路径时，这16项会明确skip，不代表真实验收。数据质量统计、清洗重放及导入/回退命令以REAL_DATA_VERIFICATION.md为准。

- Windows 11 x64、Python 3.11.9、Elasticsearch 8.19.23 Windows ZIP（自带 JDK）、Elasticsearch Python 8.19.3。无需系统 Java 8、Docker 或系统服务。
- 选择固定 8.19 API 和同系列客户端，已经覆盖 P0 倒排索引/BM25，不为本阶段引入大版本迁移。官方依据：[Windows ZIP](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/zip-windows.html)、[客户端兼容](https://www.elastic.co/docs/reference/elasticsearch/clients/python)、[BM25](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/index-modules-similarity.html)。
- ZIP 为 525602278 字节；安装、ES数据和日志位于被忽略的 `infra/.runtime/`；Python环境位于 `backend/.venv/`；报告/PID位于 `backend/.runtime/`。不移动 PDF。
- ES 单节点、1分片、0副本、512 MB堆，仅绑定127.0.0.1。本机开发配置关闭ES认证；API也只绑定本机。不用于公网部署。

## 运行命令（项目根目录 PowerShell）

首次安装：

```powershell
Set-Location F:\scholarlens-ir
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
powershell -NoProfile -ExecutionPolicy Bypass -File infra/setup-elasticsearch.ps1
```

setup 下载官方运行包并核对 SHA-512。依赖锁文件记录本次实际安装版本，requirements.txt 表达兼容范围。已有虚拟环境及运行包时跳过安装。

历史Mock调试流程（仅在需要重新构建Mock索引时）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-elasticsearch.ps1
$report = 'backend/.runtime/import-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
backend/.venv/Scripts/python.exe -m backend.import_jsonl --input data/sample/mock_papers.jsonl --data-status mock --index scholarlens-papers-mock --report $report
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
```

服务已启动时直接查询；重复启动会报告端口占用。每次导入使用新的报告名，已有报告不覆盖。ES冷启动超时可检查 `infra/.runtime/elasticsearch.*.log`。

```powershell
Invoke-RestMethod 'http://127.0.0.1:9200'
Invoke-RestMethod 'http://127.0.0.1:8000/api/search?q=computer&field=title' | ConvertTo-Json -Depth 10
Invoke-RestMethod 'http://127.0.0.1:8000/api/stats' | ConvertTo-Json -Depth 10
```

预期ES版本8.19.23；搜索total=1，命中mock-0002，高亮Computer、score为真实ES BM25分数；stats papers=2、indexed=2、status=mock。输入没有parse_status，统计unknown=2，不能记为解析成功。搜索头 `X-ScholarLens-Data-Status: mock` 标记内容来源；JSON结构沿用API契约。浏览器文档：http://127.0.0.1:8000/docs 。

## Mapping 与检索约定

`mapping.py` 为唯一映射定义，版本papers-p0-v1：六字段和abstract使用standard text、显式BM25(k1=1.2,b=0.75)；paper_id keyword；year integer；派生date_value strict_date；pages整数对象；pdf_path/source_file/errors不参与检索。date保留文本用于日期词项检索，空日期省略，不补假日期。dynamic=strict。

all只搜索六字段，title权重3、authors权重2、其余1；multi_match best_fields，同一字段多查询词AND。phrase/fuzzy可分别使用。分页窗口10000、page_size上限100；非法参数400；缺年份排序最后，同分以paper_id稳定排序。高亮HTML转义，仅加em标签，超长正文的高亮分析截断到100万字符但不截断索引全文。历史P0曾对semantic/hybrid返回503，当前V2已实现三模式，状态见/api/capabilities。standard暂用于英文Mock，中文分析策略待真实语料评估。

## 导入与质量

全量内存校验适用于本课程约1000篇：兼容BOM、缺字段和数据组可选source_file/parse_status/errors；拒绝重复ID、错误类型、非法日期、年份冲突和未知字段。partial可导入，error隔离；未提供状态记unknown。正文含U+FFFD或带unreadable_characters_in_fulltext则暂缓正文，其他元数据仍可用。报告记录输入SHA-256、数量、状态、非空率和隔离原因，原JSONL不修改。

每次创建全新generation，bulk全部成功且数量校验通过才原子切换alias。失败不切换当前alias，保留staging排查；旧generation不自动删除，供回退。操作系统写入故障须结合实际alias状态核实。不向同一alias并发导入。

## 测试

```powershell
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m ruff format --check backend
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml -q
```

预期74项通过。默认要求真实本机ES8.19.23；缺依赖明确失败，不替换假搜索引擎。测试生成唯一scholarlens-test-*别名、明确Mock样本，退出仅清理本次测试资源。覆盖六字段、BM25、分页/高亮/排序/筛选、schema、导入回退，以及第二阶段的详情、PDF缺失、路径约束、错误响应、OpenAPI和PR#2兼容性。离线可运行 `-m 'not integration'`，不代表完成集成验收。现有Starlette/httpx测试客户端有一条弃用提示，详见验证记录。

## 切换正式论文

先完成解析修复和数据交付验收，核实来源清单、ID、日期、乱码、去重、人工修订及PDF映射。导入器检查结构，不认证论文事实。以下JSONL路径是示例，替换为实际交付位置：

```powershell
$env:ELASTICSEARCH_INDEX = 'scholarlens-papers-real'
$report = 'backend/.runtime/import-real-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
backend/.venv/Scripts/python.exe -m backend.import_jsonl --input 'F:/scholarlens-data/papers_final.jsonl' --data-status real --index scholarlens-papers-real --report $report
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
```

正式模式拒绝mock-前缀ID；Mock和real别名隔离。搜索代码不更改，只切换环境变量并重启API。变量在启动API的PowerShell设置，名字见infra/.env.example，程序不自动加载.env。详情和PDF路由已实现，文件访问默认关闭；PDF交付后配置SCHOLARLENS_PDF_ROOT，必要时设置SCHOLARLENS_PDF_PATH_BASE解析相对路径。搜索无需PDF已部署；真实PDF成功读取待交付验收。

## 回退与停止

第二次及之后成功导入报告包含前代，可回退alias且不删数据：

```powershell
backend/.venv/Scripts/python.exe -m backend.rollback_index --report $report
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-elasticsearch.ps1
```

首批没有前代，回退会停止并说明原因。启动脚本再次运行会使用保留的数据。内存紧张时可停止闲置进程或关闭其他应用；脚本不改系统内存设置。
