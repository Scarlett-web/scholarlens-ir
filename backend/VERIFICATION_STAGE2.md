# 后端 P0 第二阶段实际验证

日期：2026-10-26（Asia/Shanghai）。在现有环境上增量开发，分支保持 zjl。本轮未安装 ES 或新依赖，未执行 commit/push/merge，未导入真实论文或重建论文 ID。

## 开发前与开发后

开发前已有 search/stats，原有32项测试。业务 alias 为 scholarlens-papers-mock，指向 scholarlens-papers-mock-6baa7d070b4f，文档数2。开发前相关文件和 SHA-256 保存在被 Git 忽略的 backend/.runtime/p0-stage2-before.zip/json。

新增详情和受控 PDF 接口；搜索既定字段不改名，增加公开响应模型和 OpenAPI 类型。默认不启用 PDF 目录访问。原始 PDF 和正式 JSONL 未交付，没有生成任何假 PDF，也没有宣称真实 PDF 成功传输。

## 实际命令与结果

| 命令 | 退出状态 | 实际结果 |
|---|---:|---|
| backend/.venv/Scripts/python.exe -m ruff check backend | 0 | All checks passed! |
| backend/.venv/Scripts/python.exe -m ruff format --check backend | 0 | 格式检查通过 |
| backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml -q | 0 | 74 passed, 1 warning in 4.11s |
| powershell -NoProfile -ExecutionPolicy Bypass -File infra/stop-backend.ps1 | 0 | 停止记录的 API 进程 |
| powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-backend.ps1 | 0 | API 重新启动 |
| Python urllib HTTP 采集 | 0 | 下表请求全部得到预期状态和响应 |
| git -c core.safecrlf=false diff --check | 0 | 没有空白错误 |

唯一测试警告来自已安装 Starlette/httpx 测试客户端的弃用提示，没有测试失败。此前73项增量测试也全部通过；新增OpenAPI检查后为74项。本轮仅重启API，ES持续运行，不重建已有索引。

## 真实 HTTP 结果

API 重启后，通过 urllib 访问 http://127.0.0.1:8000，原始 JSON 和状态码保存在 backend/.runtime/stage2-http-results.json。

| GET 请求 | HTTP | 实际结果 |
|---|---:|---|
| /api/search?q=computer&field=title&mode=keyword&page=1&page_size=2&sort=relevance | 200 | total=1，mock-0002，score=2.0794415，title高亮Computer |
| /api/search?q=notpresentanywhere | 200 | total=0，results=[] |
| /api/stats | 200 | papers=2，indexed=2，status=mock，unknown=2 |
| /api/papers/mock-0001 | 200 | 完整公开字段，pdf_available=false |
| /api/papers/mock-0002 | 200 | 完整公开字段，pdf_available=false |
| /api/papers/mock-never-existed | 404 | paper_not_found |
| /api/papers/mock-0001/pdf | 404 | pdf_not_available |
| /api/papers/mock-never-existed/pdf | 404 | paper_not_found |
| /api/search?q=x&page_size=101 | 400 | invalid_parameter |

搜索和详情成功响应含 X-ScholarLens-Data-Status: mock。完整请求和响应样例见 FRONTEND_HANDOFF.md，耗时随请求变化。实际错误 body：

```json
{"error":{"code":"paper_not_found","message":"论文不存在","details":{}}}
{"error":{"code":"pdf_not_available","message":"原始 PDF 尚未交付或暂不可访问","details":{}}}
{"error":{"code":"invalid_parameter","message":"请求参数不符合契约","details":{"fields":["query.page_size"]}}}
```

## 测试范围与兼容性

保留原32项；新增详情与原Mock字段比对、PDF缺失、论文缺失、空字段、含冒号ID、非法ID、路由404/方法405、缺索引503、搜索query和结果结构、OpenAPI响应形状、PDF路径限制、PR#2字段/null兼容性。集成测试使用真实ES中的唯一scholarlens-test-*索引，结束只清理本次测试资源，不覆盖业务alias。

PR#2的parse_status、errors、source_file、pdf_path和pages对象可接收；year/pages及页数子字段可为null，数组为空可接收。字符串/数组字段传null不符合协议，仍拒绝，应使用空字符串/空数组。没有修改索引器代码，仅补兼容测试。正式数据尚未交付，不能据此称为真实论文导入成功。

PDF真实成功传输、Range请求及浏览器渲染待实际文件交付后验收。本轮只验证缺失和受控路径拒绝逻辑。Vite配置依据官方文档，React/Vite没有安装或运行，页面联调待前端组员执行。

## 索引与 Git 安全

业务alias和generation保持不变、文档数仍为2；API重启后继续查询原索引。Mock源文件SHA-256保持40036eb9c579b87c9b62ab9b75382f657b231929ecda2c43cb5563ad8d9ae8f7。scripts/、data/、frontend/未修改。

非忽略文件扫描未发现常见私钥/OpenAI/AWS密钥格式、超过5MB文件、.env、依赖/日志/索引目录。check-ignore确认backend/.venv、infra/.runtime、backend/.runtime和.env被忽略；暂存区为空。扫描不是对所有密钥格式的保证，PR仍需人工review。

本轮源文件差异与哈希为backend/.runtime/stage2-changes.patch、stage2-change-hashes.json；原文件为p0-stage2-before.zip；回退工具为rollback-stage2.py。回退前全量检查当前哈希，在独立临时目录执行恢复并核对原始哈希，当前运行代码不回退。审核产物均被Git忽略。第一阶段历史记录保留在VERIFICATION.md。

当前可整理为PR，但尚未提交或推送。合并前仍需至少另一名成员审阅；PDF成功分支与真实数据质量属于明确待验收项。
