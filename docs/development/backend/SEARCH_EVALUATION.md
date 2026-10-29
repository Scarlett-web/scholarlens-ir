# 三种检索模式评价

> 阅读口径：本文件保留原阶段的协议、命令与验收条件。当前实现、部署和外部服务状态见[项目总报告](../../PROJECT_REPORT.md)与[当前状态](../../operations/STATUS.md)。旧阶段的“待接通/待交付”不覆盖后续已完成内容。

日期2026-10-27。keyword是真实ES BM25；semantic是真实MiniLM CPU嵌入、ES精确cosine扫描、按paper_id聚合；hybrid执行真实两路召回及RRF(k=60)。评分尺度不同，不能跨模式直接比较。

> 本页耗时表是 2026-10-27 Windows 历史基准，不是当前华为云或公网 SLA。最新源站顺序测量和未标注边界见[总报告](../../archive/releases-20261028-29/PROJECT_REPORT_20261028.md)与[当前观察](../../archive/releases-20261028-29/33_PASSIVE_CHECKS_AND_RESIDUALS.md)。V2.1 已实现上传独立向量，是否就绪取决于实际 generation 对齐；当前生产没有批准上传，不能因能力已实现就声称生产有上传向量数据。

## 方法与复现

固定8条查询见backend/evaluate_search.py，覆盖脑成像、信息检索、DNA修复、分布式系统、土壤、图像学习和物理。每模式预热1次，再执行8查询×3轮，共24次；记录每次HTTP墙钟耗时、候选数和Top5 ID/标题。耗时包含嵌入、ES和序列化；不包含首次模型加载。p95使用nearest-rank。

```powershell
backend/.venv/Scripts/python.exe -m backend.evaluate_search --api http://127.0.0.1:8000 --repeats 3 --output backend/.runtime/search-evaluation.json
Invoke-RestMethod 'http://127.0.0.1:8000/api/evaluation' | ConvertTo-Json -Depth 8
```

环境：Windows11、Python3.11.9、ES8.19.23单分片0副本512MB堆；MiniLM CPU2线程、384维。API0.2.0，859篇/49420片段。全量构建已结束；field=all、page_size=5。初轮结果另存search-evaluation-initial.json，以下为最终轮次，不混合统计。

## 实际测量

| 模式 | 请求数 | 平均ms | p50 ms | p95 ms |
|---|---:|---:|---:|---:|
| keyword | 24 | 39.172 | 36.092 | 79.001 |
| semantic | 24 | 509.002 | 505.846 | 557.710 |
| hybrid | 24 | 584.131 | 544.096 | 794.262 |

逐查询记录位于backend/.runtime/search-evaluation.json，GET /api/evaluation返回同一记录。24次/模式是课程单机预热基准，不是生产SLA或并发压测；后台用户请求和CPU负载会影响耗时。

## 结果解释与限制

语义/混合total为去重候选论文数，窗口1000，不是人工相关论文总数。向量使用最高分片段代表论文；RRF只融合排名，不相加原始分数。年份先过滤两路，缺年份排序置后。

真实问题“How can MRI measure human brain function?”中，semantic将目标脑成像论文排第一，hybrid将其排第二，MRF图像配准论文排第一。两路融合会提高词项候选名次，不保证每条问题都优于单路语义。原magnetic/title关键词查询仍total1、score21.500313。

没有人工qrels，Precision@5、nDCG@10保持null；不从标题重叠、单条查询或模型相似度猜标注，不虚构效果提升。后续由数据组/组长对固定结果独立标注0/1/2，再在固定语料版本计算相关性指标，时间待会议确认。

[all-MiniLM-L6-v2模型卡](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)说明该模型是英文通用语义模型；本项目固定revision并使用CPU ONNX，不宣称医学专门训练或中文效果。原论文抽取遗漏、重音断词和4条正文隔离仍会影响召回，见[真实数据历史验收](../../archive/backend/20261026-27/REAL_DATA_VERIFICATION.md)。上传语义/混合能力的后续实现与验收见[V2.1增补](FRONTEND_API_GUIDE_V21.md)和[隔离上传链](../../specs/31_ISOLATED_UPLOAD_AND_OWNERSHIP.md)，不能沿用本页早期阶段的“尚未向量化”限制描述当前代码。
