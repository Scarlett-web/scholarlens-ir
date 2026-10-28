# 首页与专注阅读发布记录

2026-10-28，华为云既有 ScholarLens 服务。用户持续授权验收后及时推送、及时更新线上；本次不新增基础设施或变更域名。

## 发布内容

- `d67a7b2`：首页装饰冰晶、真实最近阅读保留、专注阅读、浏览器内位置恢复、追加原文摘录、背景衍生图与预加载、robots。
- `a3b468e613e7a63a9cc8e1934118cad7a6daaacd`：头像依赖升级至 Pillow 13.0.0，隔离头像测试与局部审计工具。本轮源码已推送 `origin/zjl`。
- 应用 release：`20261028T035053Z-a3b468e`；旧版 `20261028T030645Z-0d3be7b` 保留。发布包 218 个文件，SHA-256 `d8ea2572620821defc8e1a1525882d75454e9729c63fe9dda4d79ccbf18104c8`。

## 部署与恢复

切换前校验全部文件和新旧官方 wheel 的 SHA-256；严格确认两个 requirements 文件仅有 Pillow 这一项变化。先在服务器临时目录验证 Pillow 13 导入及 PNG/JPEG 重编码，再短暂停止本应用、离线升级专用虚拟环境、切换 release 并启动；未触及全局 Python。

备份目录 `/opt/scholarlens/backups/20261028T035053Z-a3b468e` 保存 SQLite 一致性备份（完整性检查通过）、环境副本、新旧 wheel 和部署报告。目录仅 root 可读；没有把敏感副本带入 Git。`rollback.sh` 语法已核对，包含恢复旧 Pillow 与旧 release 的步骤；自动失败恢复路径已实现，本次正常发布未触发回滚。

切换前后论文均为 859 篇，用户均为 25 个。Cloudflare Tunnel PID 与 Elasticsearch 容器身份和启动时间一致，环境文件哈希一致。未注册生产测试账户、写测试笔记、重建索引或重启其他服务。

## 公网验收

地址：<https://scholarlens.lingion.cc.cd/>。独立 Chrome 游客会话实际打开首页与真实论文页，首页搜索框可见、冰晶存在、采用 1600px 背景衍生图且无横向溢出；进入专注模式后侧栏隐藏、正文为实色纸面，退出后侧栏恢复。保存并查看了桌面截图。

只读 HTTP 验收通过：

- 公网 JS `index-D2V3sqCw.js`：SHA-256 `9088e5edbb08cbd1eacd06c2e5feaaf53601301957ed6926bd6df3a118243ae7`；CSS `index-McMwGCcl.css`：SHA-256 `e55e2c9c3fa924bfd1f5e4f10296f25422ce34548000b3f7b1ad7bdd6eaf4e55`。两者与本次构建及发布 manifest 一致。
- `/api/stats` 为 859 篇，`magnetic` 关键词检索为 61 条命中。
- 证据工作流返回 5 条真实证据，工具步骤为 `search_papers`、`verify_sources`，Agent 版本 `0.2.0`，模型状态 `not_called`。
- 原 PDF `Range: bytes=0-63` 返回 206，64 字节以 `%PDF-` 开始，Content-Range 为 `bytes 0-63/3215996`。
- robots 返回真实 `text/plain` 规则；1600px、2560px 背景图大小和哈希均匹配本次发布。

机器证据与截图保存在本机忽略目录 `output/deploy-prism-reader-20261028/`（外层开发工作区）。Node 直连检查曾遇到连接重置，改用系统 curl 网络路径完成上述公网验收；浏览器也独立打开成功。

本次只证明已发布内容及上述路径通过。本机测试、桌面 Lighthouse 和其他审计覆盖限制见文档 19、20；不将只读证据调用写成个人模型成功生成，不将本轮发布写成其余逐页优化或全局审计完成。此后的发布记录文档提交不改变应用构建，无需再次重启服务。
