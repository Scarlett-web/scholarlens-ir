# 单域名服务器部署

输入：本仓库源码、已验收的论文索引/向量和 MiniLM 模型；输出：同源 HTTPS 网页、API 与隔离持久化目录。负责人为项目维护者。不要把本机 QA 用户或运行库直接复制为正式用户库。

## 构建与运行

1. frontend/ 中执行 npm ci；设置 VITE_DATA_SOURCE=api 和 VITE_API_BASE_URL=/api 后执行 npm run build。不要设置真实 AI 密钥。
2. Python 3.11+ 创建 /opt/scholarlens/venv 并安装 backend/requirements.txt。源码放 /opt/scholarlens/current；frontend/dist 同步进这个目录。
3. 独立 Elasticsearch 8.19.23 容器只绑定 127.0.0.1:19200，持久化独立卷，单节点、课程数据；参考 infra/elasticsearch.compose.yml（固定镜像 digest），根据主机资源限制堆和容器内存。不要修改其他应用或公开 ES。生产数据如需加密/认证按部署环境补充，不能把 loopback 无认证端口暴露公网。
4. 建立独立 scholarlens 用户和 /var/lib/scholarlens，模型放该目录 minilm/，SQLite/上传/评价放 runtime/。不要使用 root 运行 API。
5. /etc/scholarlens/app.env 仅管理员可读，参考 infra/.env.example，配置 ELASTICSEARCH_URL=http://127.0.0.1:19200、实际索引别名、SCHOLARLENS_RUNTIME_DIR=/var/lib/scholarlens/runtime、EMBEDDING_MODEL_DIR=/var/lib/scholarlens/minilm、FRONTEND_DIST=/opt/scholarlens/current/frontend/dist。邮件和服务器 AI 值默认留空。
6. 使用 infra/scholarlens-api.service，systemctl daemon-reload 后启动并启用。API 仅监听 127.0.0.1:18090，验证 /api/stats、/api/capabilities、网页与 /assistant 深层路由。
7. 新建独立 Cloudflare Tunnel 及空闲子域名，参考 cloudflared-scholarlens.example.yml 与 cloudflared-scholarlens.service，最后必须有 http_status:404。凭据只放 /etc/scholarlens，不进入 Git；显式指定配置文件、Tunnel UUID 和 DNS zone，不依赖旧应用默认配置。独立 systemd 隧道服务，不覆盖已有 cloudflared 配置。

## 数据与验收

论文、向量可通过 ES scroll 只读导出，在服务器独立索引导入并逐篇/逐片段核对 ID 与哈希，再建立别名；禁止替换已有正式索引。代码仓库不包含私有交付包、数据库、模型或原论文。每次更新先备份 SQLite 和应用环境，保留上一源码 release，通过 current 符号链接切换；不删除旧数据。数据库 schema 有变动时先验证迁移。

外网验收包括 HTTPS、主页及深层路由、BM25/语义/混合检索与分页、注册登录退出、账号隔离、未配置 AI/邮件和缺失原 PDF 的真实状态。浏览器本地收藏和文件仍按域名隔离，不自动迁入服务器。

## 回滚

停止本应用的 scholarlens-api 与 cloudflared-scholarlens 服务；current 指回上一 release 后重启 API。只删除本次新建的 DNS 记录/隧道需要额外确认，保留其他服务。新部署若无上一版本，停止本应用即可，数据卷保留。不要运行全局 docker prune 或关闭其他 tunnel。

2GB 主机仅适合课程规模的低并发演示；完整检索依赖 ES 和模型，资源不足必须如实报告并升级资源，不能将语义功能静默替换成模拟结果。
