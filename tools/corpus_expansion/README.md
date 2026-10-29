# 01 论文扩容只读校验

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
