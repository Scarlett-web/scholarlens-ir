# 原始论文存档与在线预览交付

## 范围与约定

负责人：组长。2026-10-28 用户明确要求将提供的原始压缩包存到 GitHub，并继续完成华为云部署。本次原件发布授权仅覆盖这批论文材料；不包含用户数据库、会话、API 密钥、模型和运行索引，不改数据组的正式 JSONL、ID、来源路径或检索索引。

输入：用户提供的 `oriPDFs.rar`，以及 `feat/pdf-parser` 的正式 `papers_final.jsonl`、`paper_source_manifest.csv`。JSONL 是原 PDF 解析结果，不是可以恢复原排版的替代文件。XML 未交付，也不是原件预览的必需依赖。

输出：GitHub Release 保存可恢复的原包分卷、正式元数据和 SHA-256 清单；华为云保存正式库对应的 859 份原 PDF，现有同源 PDF 接口提供原件阅读。

验收条件：859 份原件的来源哈希全部匹配；服务端恢复后再次逐份核验；公网接口返回原始字节和正确 Range 响应；浏览器实际显示原 PDF，并验证翻页与缩放。仅 HTTP 200 或正文可读不能作为原件交付通过的证据。

## 已核验的源材料

- 原始 RAR：2,730,175,210 字节，包含 999 份 PDF。
- 原包 SHA-256：`36ffd4aa883bbc12445d1fd1de74a177b996454d88990d8019e3e2d6380fe025`。
- 正式库 859 个来源文件全部存在，无缺失；859 个 PDF 的 SHA-256 全部与来源 CSV 匹配。
- 正式库原件共 2,743,301,045 字节、22,686 页；所有页面经 PyMuPDF 低分辨率渲染，无异常退出。另人工查看 6 份原件的 12 个页面，覆盖照片、图表、结构图和双栏文字，以及存在正文提取替换字符的 4 篇。
- 页面渲染通过不意味着逐字人工校对，也不会提升原始扫描件的清晰度。网站交付保持源文件字节不变。
- 包中另有 140 份未被正式清单收录的 PDF，仅保存在完整原包内；本次不新增或重建索引。

## GitHub 存储与恢复

Release：[papers-originals-2026-10-28](https://github.com/Scarlett-web/scholarlens-ir/releases/tag/papers-originals-2026-10-28)。原包拆为 6 个二进制分卷：前 5 个各 512 MiB，最后一个 45,820,650 字节。分卷不单独解压，须按编号合并后校验原包 SHA-256。

附件 `delivery-manifest.json` 记录每个分卷、原包和元数据的大小及哈希；`README-originals.md` 提供使用固定 4 MiB 缓冲区的恢复脚本。正式元数据按 Git blob 原始字节导出，避免 Windows 换行转换。

大文件不写入源码 Git 历史。GitHub 负责存档，华为云运行网站和检索服务；将文件放在 GitHub 不等于让 GitHub 运行 Elasticsearch，也不会自动释放本机磁盘或内存。

## 服务端接入方式

不改正式 `pdf_path`。使用既有的平铺迁移模式：

```dotenv
SCHOLARLENS_PDF_ROOT=/var/lib/scholarlens/original-pdfs
SCHOLARLENS_PDF_MANIFEST=/var/lib/scholarlens/original-delivery-20261028/paper_source_manifest.csv
```

现有解析器按 `paper_id`、`source_file` 和 `pdf_sha256` 三项校验。文件不在允许根目录、路径不安全、文件缺失、签名不符或哈希不匹配时，仍返回不可用，禁止静默回退到同名文件或远程 URL。

在完整源文件校验通过后，备份并原子更新 `/etc/scholarlens/app.env` 的两个 PDF 配置字段，仅重启 ScholarLens API。无需修改或重建 Elasticsearch 索引，不改 WorkBuddy、既有隧道或其他服务。回退时恢复该次环境备份并重启 ScholarLens API，原件和索引均保留。

## 交付状态

2026-10-28 已交付：

- 网站：[ScholarLens](https://scholarlens.lingion.cc.cd/)，运行于华为云，不依赖个人电脑开机；正式库 859 份原件可在线阅读和下载。
- GitHub Release 已公开，10 个附件共 2,769,631,025 字节，全部附件大小及 SHA-256 匹配。`delivery-manifest.json` 的固定 SHA-256 为 `699d3096e38f128d9e43f2192fc3e1b4a6c87eaaaf02f49bd36b9380a07199c9`。
- 服务端原包恢复与逐份哈希核验通过；859/859 源站及公网浏览器 Range 检查通过。公网分段证据为全量批次控制台计数；原脚本后续全文步骤超时，未保存逐篇公网结果数组，另以独立浏览器作业验证 3 份全文哈希、后缀与越界 Range。
- 原生 PDF 阅读器实际显示 18 页样例；第 4 页彩色地质图、翻页、缩放与原件下载已验证，下载哈希与来源 CSV 一致。详见 [验收记录](12_RELEASE_ACCEPTANCE.md)。
- 环境回滚副本：`/etc/scholarlens/backups/app.env.before-pdf-20261027T175627Z`（root:root、0600）。仅重启本应用 API，其他业务及隧道保持运行；既有检索索引与用户库未改。
- 默认 Python-urllib 公网预检曾收到 Cloudflare 403；真实浏览器通过。初次失败记录单独保留，最终完成报告记录独立验收，没有调整 Cloudflare 安全策略。
- 本机用户提供的原始压缩包保留；仅清理本轮生成且已在服务器和 GitHub 核验的临时提取/传输副本。正式 PDF、来源 CSV、验收证据和备份保留。
- XML、邮件、真实 AI 供应商调用及首次管理员指定仍待后续。原件预览不需要 XML；GitHub 存档不能代替运行中的华为云网站。
