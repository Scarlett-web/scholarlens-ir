# 后端 V2 验收记录

日期：2026-10-27（Asia/Shanghai）。负责人：组长。原859篇真实论文、正式ID、JSONL/XML/PDF及所有旧索引保留，分支zjl。没有修改frontend/scripts/data，没有自动Commit、Push或Merge。

## 结论与实际服务

正常API为http://127.0.0.1:8000，版本0.2.0；/api/stats返回papers=859、indexed=859、status=real，success215、partial644。原/api/search?q=magnetic&field=title仍HTTP200、total1、BM25 score21.500313及em高亮正常，没有重导或重建859篇基础索引。

keyword/semantic/hybrid、用户、收藏、历史和上传均有实际服务端实现及测试。AI Key、原论文PDF和GROBID未配置，能力如实标记not_configured；生成、PDF和解析的受控测试不冒充真实资源验收。前端未交付不阻塞本轮，没有寻找或创建React项目。

## 验收清单

- [x] 源码前态ZIP、逐文件SHA及原13个索引清单保留。
- [x] 真实建议/发现、六字段、跨字段、BM25、短语/模糊、筛选/排序/分页和错误分支通过。
- [x] 859篇、49420片段完整发布，逐条原文、locator、ID、维度及单位范数审计通过。
- [x] 实际语义、双路RRF、参数生效、同论文聚合和缺依赖策略通过。
- [x] 真实RAG证据、可配置适配器、无Key、受控生成、引用及异常验证通过。
- [x] 受控PDF、Range206/400/416、来源清单SHA迁移、按需正文/片段通过；原论文缺PDF如实404。
- [x] SQLite账号、会话、收藏、历史、用户隔离、退出及实际进程重启持久化通过。
- [x] 上传权限、类型/大小、审核、失败重试、独立增量索引及管理员CLI通过。
- [x] 固定三模式各24次延迟测量；无人工标注时相关性指标null。
- [x] 完整131项测试通过，无skip；ruff check/format和git diff --check退出0。
- [x] 27个OpenAPI路径、类型化接口、CORS及前端文档核对。
- [x] 42文件补丁反向检查及隔离源码回退逐哈希验证通过，当前服务未回退。

## 模型、向量与真实结果

固定sentence-transformers/all-MiniLM-L6-v2 revision为1110a243fdf4706b3f48f1d95db1a4f5529b4d41；ONNX文件90405214字节，SHA256为6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452。CPU2线程、mean pooling、L2归一化、384维、最大256 tokens，不安装PyTorch/CUDA。

向量别名scholarlens-vectors-real，generation scholarlens-vectors-real-a4f213be7ec5；基础代始终scholarlens-papers-real-090928bb1545。完整扫描25.094秒：title859块、abstract1571块、fulltext46990块，总49420；全部与当前原文和字符位置一致，全部向量有限、384维，范数范围0.9999999404..1.0。4条严重乱码正文零片段，其元数据保留。证据v2-vector-verification.json。

正常8000实际HTTP中，magnetic/all的keyword有61候选；问题“How can MRI measure human brain function?”在semantic有859候选，目标论文第一、score1.7077552；hybrid同问目标第二，MRF图像配准第一。不能声称RRF总比单路更相关。完整前5条和排名解释在v2-main-three-modes.json。

同一目标论文的实际hybrid证据返回3片段，每个quote逐字匹配字段区间，GET /api/chunks返回同一原文。真实AI请求503 ai_not_configured。最终能力keyword_search/semantic_search/hybrid_search/authentication/favorites/history/uploads=ready，ai_qa/pdf_preview/upload_parsing=not_configured；v2-main-final-http.json包含实际响应。

## 测试与重启证据

原字节源码从v2-before.zip提取至被忽略的独立目录，原74项测试为“74 passed in 20.53s”，退出0；不是用新代码结果代替基线。中间组合115 passed、2 deselected保留为历史；最终全套为：

```powershell
$data = (Select-String -LiteralPath .env -Pattern '^SCHOLARLENS_REAL_DATA_DIR=').Line.Split('=',2)[1]
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --tb=short --real-data-dir $data --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8000
```

字面摘要“131 passed in 69.17s (0:01:09)”，退出0，无skip。精确命令、字面stdout和退出码分别在v2-original-baseline-pytest.json、v2-full-pytest.json及对应log中。覆盖正式交付和全部_source、六字段、跨字段、真实向量/RRF/年份/分页、真实证据、AI受控错误与引用、PDF Range/路径、SQLite隔离/重启、上传审核/失败恢复/增量和Windows检查点。

真实构建曾在32680检查点发生WinError5：Windows短暂占用文件使Path.replace失败，确认进程退出后增加短暂重试，从同一state/generation续建；实际Windows读句柄占用测试通过。后续环境中的ES/API/构建停止，39936片段保留；恢复后cluster_uuid仍65T3rUJHRdKST9Am6J9Oqw，859篇与39936片段从磁盘恢复，再续建到49420。证据v2-build-recovery.json、v2-es-recovery.json；没有重建全库或丢弃已确认批次。

独立8004实际停止/启动后，原会话、收藏和历史仍在，退出后401，真实关键词搜索仍有效；v2-http-restart.json。管理员本地CLI也在独立数据库实际执行：普通账号先403，--promote后同一会话为admin并返回200，主数据库未改；v2-admin-cli-verification.json。临时数据库与凭证不进Git。

## 性能与质量限制

最终固定8查询×3轮、每模式预热1次，HTTP墙钟：

| 模式 | 请求数 | 平均ms | p50 ms | p95 ms |
|---|---:|---:|---:|---:|
| keyword | 24 | 39.172 | 36.092 | 79.001 |
| semantic | 24 | 509.002 | 505.846 | 557.710 |
| hybrid | 24 | 584.131 | 544.096 | 794.262 |

原始逐查询结果见search-evaluation.json，API为/api/evaluation。没有人工qrels，Precision@5/nDCG@10为null，不虚构效果提升。详见SEARCH_EVALUATION.md；当前不是并发压测或生产SLA。

原数据的4条正文隔离、34组标题重复候选、41条正文边界候选和旧声明哈希差异沿用REAL_DATA_VERIFICATION.md，未擅自修订元数据或重新执行组员转换器。GROBID未配置且未发现8070监听，不代表调查过所有磁盘安装；真实上传自动解析需要外部服务。AI真实生成和原论文PDF预览尚无资源验收。

## 按阶段的主要文件

| 阶段 | 新增/修改 |
|---|---|
| 0 审计保护 | AGENTS.md、docs/01_REQUIREMENTS.md、02_ARCHITECTURE.md、03_DATA_SCHEMA.md、04_API_CONTRACT.md、08_MEETING_DECISIONS.md、BACKEND_V2_GOAL.md |
| 1 建议发现 | discovery.py、app.py、tests/test_search_integration.py |
| 2 真实向量 | embeddings.py、chunks.py、vector_index.py、verify_vectors.py、requirements.txt/requirements-lock.txt、infra/start-vector-build.ps1 |
| 3 语义RRF | retrieval.py、config.py、app.py、tests/test_v2_vectors.py |
| 4 RAG | rag.py、capabilities.py、AI_CONFIGURATION.md、tests/test_v2.py |
| 5 PDF/正文 | pdf_access.py、pdf_response.py、api_models.py、app.py |
| 6 用户个人数据 | accounts.py、api_models.py、accept_v2_http.py、tests/test_v2.py |
| 7 审核上传 | uploads.py、request_limits.py、config.py、tests/test_v2.py |
| 8 评价交接 | evaluate_search.py、SEARCH_EVALUATION.md、FRONTEND_API_GUIDE.md、BACKEND_STARTUP.md、BACKEND_V2_VERIFICATION.md、README/FRONTEND_HANDOFF链接、infra/start-scholarlens.ps1/start-elasticsearch.ps1/.env.example、rollback_v2.py |

## Git、四类交付与恢复

75个Git源码候选未发现常见密钥格式、超过5MB文件或私有运行目录；扫描不代替人工review。分支zjl、暂存为空，frontend/scripts/data与前态哈希一致。所有原13个索引UUID/文档数不变，Mock、样本和旧代均保留。原始JSONL、清洗输入和来源清单SHA保持不变，正式ID未重建。

修改后的工作区源码为第一类交付。对V2前快照的增量为42文件；补丁backend/.runtime/v2-changes.patch、前后SHA清单v2-source-manifest.json、原态v2-before.zip为可核验包装。快照包含本轮前已有P0修改，不把工作区重置到Git main。

验证记录包括本报告、v2-full-pytest.json、v2-vector-verification.json、v2-main-final-http.json、search-evaluation.json、v2-es-recovery.json、v2-http-restart.json、v2-git-index-safety.json；聚合审计v2-completion-audit.json。均位于被忽略runtime，不提交数据、数据库、模型、上传或日志。

回退工具backend/rollback_v2.py先核对全部当前哈希，出现后续他人修改则停止；只恢复源码，不动ES、原数据、SQLite、上传、模型、私有.env或已安装依赖。本轮--apply只在隔离目录执行，42文件恢复为原哈希；当前工作区保持V2。补丁仅执行git apply --check --reverse，无实际应用。证据v2-rollback-verification.json。

```powershell
# 仅读检查，不改变当前源码
backend/.venv/Scripts/python.exe -m backend.rollback_v2 --check
# 仅当组长选择回退时执行以下操作；本轮未对工作区执行--apply
powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1
backend/.venv/Scripts/python.exe -m backend.rollback_v2 --apply
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1
```

## 下一步资源与使用

日常执行infra/start-scholarlens.ps1，无需重导859篇；前端阅读FRONTEND_API_GUIDE.md和/docs即可接入。需要组长自行配置AI Key/地址/模型、提供原论文PDF和正确清单、提供运行中的GROBID，以及安排人工qrels标注。未提供前如实报告外部状态。

审核上传已支持关键词检索和详情，但尚未加入基础语义索引；metrics标记not_vectorized，向量覆盖范围为本轮859篇基础语料。此限制已公开，不宣称新增上传自动获得语义召回。当前可以交给组员review，至少一名成员审阅后由组长决定提交/PR；没有自动提交推送。
