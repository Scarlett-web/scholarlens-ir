# 4000篇扩容发布与恢复

日期：2026-10-30。负责人：组长。用户已授权先推送origin/zjl，再更新既有华为云ScholarLens；不合并、不强推、不修改其他服务。

## 输入与本地验收

- 合并4000条JSONL及来源CSV来自output/corpus-expansion/prepare-02，原件保留；这些文件不进入源码Git。
- 独立关键词别名scholarlens-papers-expansion-real；向量别名scholarlens-vectors-expansion-real，236947个384维片段。
- 本地新增3141份PDF文件层全量哈希通过；API25项检查、前端38项测试和10组真实浏览器检查已通过。旧859份PDF在服务器，本地没有原件。
- API入口已改为backend.app1:app，服务文件及调用引用同步；旧文件不是同时保留的兼容入口。

## 发布前检查

只提交源码、测试、配置示例和公共文档；不提交.env、PDF/XML、JSONL、来源数据CSV、数据库、ES目录、模型、dist或运行报告。
先fetch并核对分支差异，保持zjl；远端有不兼容进展时停止，不强推或擅自合并。
依赖继续使用既有锁文件。本地扩容工具的模块改名导入及格式检查须通过。

## 服务器步骤

1. 先只读检查目标主机身份、磁盘/内存、服务current、环境文件路径、ES版本/别名和旧PDF目录；不得把其他平台SSH配置当作华为云部署凭据。
2. 保存上一release、环境配置和systemd单元；以SQLite backup API生成一致性用户库备份，记录SHA-256。不从本机复制测试用户库覆盖生产库。
3. 新源码与dist进入独立release。新增PDF进入独立目录，按清单逐份核验；旧859份原件保留，不覆盖。
4. 以现有ES scroll导出/导入到独立新generation，或从合并JSONL重建关键词及配套向量；不直接复制运行中的Windows ES数据目录到Linux。核对全部ID、来源、指纹与向量。
5. 配置SCHOLARLENS_PDF_MANIFEST为服务器合并来源清单；SCHOLARLENS_PDF_ROOTS_FILE为私有JSON，其old/new分别指向服务器旧、新PDF根目录。不要使用本机绝对路径。
6. 确认新release采用backend.app1:app，配套索引与用户运行目录正确；核验成功才原子切换current与环境，仅重启scholarlens-api。隧道、域名和其他应用保持原样。
7. 公网核对4000篇、三种模式、新旧检索与PDF、分页、详情、注册登录既有流程，以及正式构建信息。保存脱敏验收结果。

## 失败恢复

原子恢复上一current、环境和服务单元，仅重启本应用；旧索引和原件始终保留。数据库无必要不回退；确需恢复时先保存发布后数据，避免丢失用户写入。
本说明不是线上完成报告。以实际推送回执和服务器、公网验收为准；未取得有效SSH连接信息时不得宣称部署成功。
