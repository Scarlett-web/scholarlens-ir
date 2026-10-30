# 01 论文扩容只读校验

## 05 本地API与PDF接通（2026-10-30）

负责人：组长。修改原启动、app、PDF解析、真实数据检查文件并改名加1；同步代码引用。
输入：prepare-02合并数据/清单、index-04配套索引报告、新批PDF根目录。旧批根目录本机留空，明确待服务器验证。
输出：api-05下local-api.env、pdf-roots.json、pdf-mapping-checks.csv、startup-report.json、api-verification.json、summary.md。
原件、ID和索引不修改；保留单目录PDF兼容，同时增加按source_batch选择受信根目录，校验文件名、签名、SHA-256并拒绝越界。
验收：API4000篇，新旧检索和详情、三种模式、分页/筛选/高亮；新增3141份PDF全量校验；HTTP样例验证原PDF及Range，旧批859份标记未配置。
不push、不部署。配置和报告只在忽略目录中。无需运行旧859篇历史全套业务测试。

## 04 扩容索引构建协议（2026-10-29）

负责人：组长。新增 backend/import_jsonl1.py、backend/vector_index1.py，调用原模块的导入和构建函数，不修改原脚本。
输入：02阶段合并JSONL及summary.json、Elasticsearch 8.19.23、本地固定版本MiniLM模型。
默认独立别名 scholarlens-papers-expansion-real、scholarlens-vectors-expansion-real，拒绝覆盖原859篇的正式别名。
关键词阶段核对02输出哈希、4000条有效输入后才写新代；向量阶段核对关键词报告的generation、数量和输入哈希，再使用独立检查点。
输出位于 output/corpus-expansion/index-04/：keyword-report.json、vector-state.json、vector-report.json；只在配套向量完成且校验后生成 local-index.env，供下一步本地API配置使用。
--dry-run只做输入及依赖检查，不写索引，独立写关键词/向量preflight报告；依赖缺失必须返回非零，不以预检代替导入。
验收：关键词4000条、bulk失败0；向量ready、completed等于chunks、base_generation对应关键词新代；旧正式别名不动。脚本不自动重启服务或更新根目录.env，不触及线上。

```powershell
backend/.venv/Scripts/python.exe -m backend.import_jsonl1
backend/.venv/Scripts/python.exe -m backend.vector_index1 --batch-size 32 --workers 2
```

两个脚本均支持 --dry-run；预检依赖缺失时退出2，正式构建参数及路径可通过 --help 查看。
向量成功构建后额外调用现有 verify_vectors.verify，全量核对片段、来源定位及384维归一化向量，写 vector-report-verification.json。
--state可在中断后复用同一检查点，但模型、关键词generation或输入变化时必须使用新检查点。

本机本轮进度：隔离 backend/.venv 已安装既有 requirements-lock.txt；使用Python3.12（满足项目3.11+要求）。
两个扩容工具的2项保护测试及Ruff检查通过；原import_jsonl.load_jsonl离线解析接受4000条、跳过0条、隔离正文27条。
输入核验结果位于 keyword-input-validation.json，依赖预检位于 keyword-preflight-after-install.json、vector-preflight-after-install.json。
预检时ES未启动、模型未就绪，因此未宣称实际关键词/向量索引完成，未切换本地或线上配置。

## 02 合并准备协议（2026-10-29）

负责人：组长。工具：02_prepare_expansion.py。输入为两批原始 JSONL/来源 CSV 和01阶段校验目录。
旧批可从固定 Git ref 只读取得。合并前重新检查输入哈希与01报告一致、结构、ID唯一性、清单一一对应及跨批PDF哈希冲突；不接受过期或有阻断问题的报告。
输出独立 merged_papers.jsonl、merged_source_manifest.csv、preparation_ledger.csv、summary.json、summary.md。
顺序为旧批在前、新批在后。保留全部原字段、稳定ID与原pdf_path，不猜标题、不替换论文、不自动删除同标题记录。
27条正文警告只登记，沿用现有导入器隔离规则；这一步不清空正文、不导入索引、不复制PDF。
来源清单增补 source_batch，方便后续映射两批PDF根目录；它本身不代表PDF访问配置已完成。
验收：4000条记录、4000个唯一ID、4000条来源清单及逐条账本；所有输入字节不变；输出目录必须不存在。
运行产物仅写入被Git忽略的 output/corpus-expansion/prepare-02/，不进入源码提交。

```powershell
python -m tools.corpus_expansion.02_prepare_expansion --new-jsonl data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl --new-manifest data/kaggle_arxiv_papers_jsonl/arxiv_paper_source_manifest.csv --old-git-ref 6e40caab5dd2ad689e3dcfaf592df2694d1fbd06 --audit-dir output/corpus-expansion/audit-01 --output output/corpus-expansion/prepare-02
```

本阶段已实际生成并独立逐条验证4000条记录，字段值与原始两批JSON对象完全一致，所有输出哈希及CSV行对应关系通过。
解析状态：success 2551、partial 1449；未替换、删除或修改字段值。
测试命令：`python -m unittest tools.corpus_expansion.test_prepare_expansion`，预期1项通过；覆盖字段保留、警告登记、已有输出拒绝覆盖、过期校验和跨批PDF冲突阻断。

负责人：组长。日期：2026-10-29。

输入：新增 JSONL、来源 CSV、PDF 根目录，以及旧库原始 JSONL/CSV（支持固定 Git ref）。
输出：独立目录中的 summary.json、summary.md、duplicates.csv、issues.csv、pdf_checks.csv。
不改原件、不生成 ID、不连接或修改 Elasticsearch、不自动合并数据。

验收：逐条复用 backend.schema.Paper 校验；分别报告跨批和批内 ID、PDF SHA-256、标准化标题、标准化正文匹配。
标题/正文相同仅为疑似重复，不能直接删除。PDF 哈希匹配才表示字节相同；清单声明与实物核验分开统计。
逐份核对新批 PDF 存在性、签名和哈希，记录 CSV 对应、解析失败、乱码及字段问题。
退出码 0 表示完成且无阻断问题，2 表示报告完成但存在阻断问题；重复不自动删除。

在仓库根目录运行（Python 3.11+，安装后端的 Pydantic 2 依赖）：

```powershell
python -m tools.corpus_expansion.audit_expansion --help
python -m tools.corpus_expansion.audit_expansion --new-jsonl data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl --new-manifest data/kaggle_arxiv_papers_jsonl/arxiv_paper_source_manifest.csv --pdf-root data/ScholarLensData/extracted/kaggle_papers_PDF --old-git-ref 6e40caab5dd2ad689e3dcfaf592df2694d1fbd06 --output output/corpus-expansion/audit-01
```

旧库默认 Git 路径为 data/paper_jsonl/papers_final.jsonl 和同目录 paper_source_manifest.csv。
也可以用 --old-jsonl 和 --old-manifest 指定本地旧库文件。输出目录必须不存在，避免覆盖既有报告。
默认 --expected-old 859、--expected-new 3141；数量不符会记录阻断问题。
脚本保存输入 SHA-256、旧来源 ref，支持追溯。未校验旧 PDF 实物，不把旧清单声明当作本次实物验收。

## 2026-10-29 首次执行摘要

- 旧库859、新库3141条全部通过结构校验；对应来源清单均为同等条数。
- 跨批 ID、来源 PDF SHA-256、标准化标题、标准化正文匹配均为0。
- 新批3141份 PDF 存在、签名及 SHA-256 全部通过；目录共有3500份 PDF。
- 新批内部 ID/PDF哈希/正文匹配为0，同标题额外匹配24条（按每组首条对照计数），需人工复核，不自动删除。
- 正文隔离警告：旧库4条、新库23条；现有导入器会保留元数据并隔离这些正文，不修改原文件。
- 阻断问题0。无合并、导入或服务重启。本地详细报告位于忽略目录 output/corpus-expansion/audit-01/。

可重复测试：`python -m unittest tools.corpus_expansion.test_audit_expansion`，预期1项通过。
覆盖跨批不同ID同PDF、同ID匹配、标题标准化、空正文不误判、PDF哈希失败、解析失败及输出防覆盖。
