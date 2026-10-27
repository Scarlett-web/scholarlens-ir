# 真实论文索引持续执行记录

日期：2026-10-27。最终目标：保持组员正式paper_id，将全部有效真实论文经过完整校验、安全清洗后导入独立Elasticsearch别名，FastAPI实际查询真实数据；Mock与旧索引保留，生成完整验收报告。范围不含补足1000篇、PDF补抽取、语义/RAG或前端。

## 分阶段计划

- [x] 1. 检查源代码/服务/索引，保护工作区和配置，运行已有74项回归。
- [x] 2. fetch origin，按固定提交字节保真取得JSONL和来源清单，核验SHA-256。
- [x] 3. 全部记录结构/类型/ID/日期/完整率/长度/乱码/来源对账。
- [x] 4. 生成独立索引输入、质量报告、修改账本；原件不变。
- [x] 5. 代表性20篇独立真实索引，六字段、BM25、详情、空值、PDF缺失验证。
- [x] 6. 使用现有导入器建立全量真实新generation/alias，保留所有旧索引。
- [x] 7. 8001真实HTTP验收后调整正常启动配置；重启/回退测试，确认8000指向real。
- [x] 8. 既有与真实数据回归、Git安全检查、更新运行文档和REAL_DATA_VERIFICATION.md。

## 已完成与证据

- 已读取完整附件目标；分支zjl；保留上两阶段未提交改动。只在backend/、infra/和必要公共文档工作。
- 快照：backend/.runtime/real-goal-before.zip，文件SHA-256与服务初态：real-goal-before.json。两者不入Git。
- 本地起始数据目录仅有pdfXML；已开始fetch origin与服务基线回归。
- 已取得提交6e40caab5dd2ad689e3dcfaf592df2694d1fbd06的正式文件（39226615字节），实际SHA-256=a73e65c552264ae7dee265d1ad854ea700c9377c0e2f54bb97a49c78b1d1441c；旧声明哈希不同，常见LF/CRLF/BOM变体也不匹配。来源Git blob核验，保留真实差异说明，不宣称旧快照字节相同。
- 全部859条类型/唯一ID/来源映射与公式通过；215success、644partial；0严重错误、0实物PDF、859份XML来源存在。报告和逐字段账本在本地数据目录real_data_quality_report.json、real_data_changes.json；独立输入papers_index_ready.jsonl保留859条，只隔离4条乱码fulltext，其他字段不变。重复标题仅列候选；41条正文边界待核查不猜改。
- 初始ES/API未运行，第一次pytest=35passed/39errors（依赖连接拒绝）；随后启动已有ES恢复同一cluster_uuid，基线74项重跑通过。
- 恢复后基线74passed/1warning，Mock8000正常。20篇样本包括4条正文隔离、完整字段、缺日期、仅年份、多作者/机构、缺地址/机构/作者/摘要、长短正文；样本和选择原因位于本地数据目录papers_real_sample20.jsonl、real_sample20_selection.json。
- 独立alias scholarlens-sample20-real→scholarlens-sample20-real-ae12ba4bafff，20/20导入，bulk_failed=0。8001实际HTTP完成7组字段查询和20篇详情全字段比对；分页/高亮/BM25/年份/空结果/错误/PDF缺失通过，报告backend/.runtime/real-sample20-acceptance.json。ES空字符串的exists语义不代表有词项，隔离验证已改为termvectors零词项。
- 全量初代scholarlens-papers-real-90c44deda57e已导入859/859，0skip/0bulk失败；8001完成全部859个_source逐字段比对与真实HTTP验收（real-full-acceptance-initial.json）。随后修正导入报告对“输入已为空但已有乱码标记”的隔离计数，再构建新的可回退generation，保留初代。数据内容不变。

## 未解决与下一步

当前全量alias指向scholarlens-papers-real-090928bb1545，报告real-full-import-audited.json包含4条正文隔离，初代90c44deda57e保留。8001通过859篇_source全字段和7组HTTP查询验收。新增Windows API重启测试发现后台子进程/继承管道问题，停止脚本已验证项目进程树并等待端口释放，测试启动改日志文件后，完整90passed/1warning。最终日志real-complete-pytest.log；早期重启失败日志real-final-pytest.log保留。ES实际重启后green，真实859篇和旧Mock保留；8000、8001目前均real。

全部目标阶段已完成。最终90passed/1warning（44.89s），ruff/格式/diff检查通过；859条原件与索引输入的哈希、ID、字段逐项对账，8000/8001均real；ES与API重启/Mock回退已实测。Git候选50文件未发现常见密钥/大文件/运行产物，暂存区为空，保护目录无修改。

待数据组解释旧哈希并交付PDF，复核重复标题和正文边界；这些是明确保留的外部质量限制，不代表论文事实已人工认证。未执行commit/push/merge。

## 恢复/验证命令

```powershell
git branch --show-current
git status --short
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml -q
backend/.venv/Scripts/python.exe -m pytest backend/tests -c backend/pyproject.toml -q --real-data-dir $env:SCHOLARLENS_REAL_DATA_DIR --real-alias scholarlens-papers-real --real-api http://127.0.0.1:8001
Invoke-RestMethod http://127.0.0.1:9200/_alias
Invoke-RestMethod http://127.0.0.1:8000/api/stats
```

服务未运行时使用infra/已有启动脚本；默认API查询real，Mock需显式-Index scholarlens-papers-mock。完整运行/清洗/回退命令见REAL_DATA_VERIFICATION.md。本轮源代码变更补丁、哈希和经隔离恢复验证的rollback-real-goal.py保存在backend/.runtime，恢复只涉及源码，不删除数据和索引。
