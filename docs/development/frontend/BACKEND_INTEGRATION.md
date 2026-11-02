# 前后端集成

## 本地4000篇接入（2026-10-30）

负责人：组长。输入为本地8000端口真实API；frontend/.env.local启用api及同源/api代理，不改后端。
首页和搜索页显示stats返回的文库数量，不硬编码4000；探索页区分候选数量与全库数量，并提供全库检索入口。
验收：真实API构建、自动测试、桌面和390px检查，新旧论文、三种模式、分页、高亮、年份筛选及详情/PDF。
本地旧859份原件使用已有不可用提示，不回退演示数据。报告放output/corpus-expansion/frontend-06/；不push、不部署。

> 阅读口径：本文件保留原阶段的协议、命令与验收条件。当前实现、部署和外部服务状态见[项目总报告](../../PROJECT_REPORT.md)与[当前状态](../../operations/STATUS.md)。旧阶段的“待接通/待交付”不覆盖后续已完成内容。

仓库 frontend/ 为 React + Vite + TypeScript 源码，backend/ 为 FastAPI。源码默认 demo（18 篇明确标记的虚构样本）；真实部署构建时设置 VITE_DATA_SOURCE=api，VITE_API_BASE_URL=/api。不在 VITE_ 变量中放密钥。

## 已连接流程

- 六字段关键词检索、语义/混合检索、分页、年份排序和筛选、建议/发现、论文详情与原文片段。能力接口决定语义模式是否开放，失败不回退为模拟数据。
- 真实注册、登录、退出、资料编辑；登录后的收藏、分类、笔记和最近阅读同步 SQLite，游客本地记录不会自动上传。
- 登录上传 PDF，管理员审核与解析索引；本地 PDF 工作区可独立使用，明确不影响服务器审核或正式索引。无 GROBID 时已有 pypdf fallback，解析来源如实标记。
- 原文证据检索、单篇总结、多篇比较及按账号隔离的研究对话；个人 API 设置见 AI_API_INTEGRATION.md。
- 原始文库 PDF/XML 未交付，正文可读不代表 PDF 可下载，接口明确返回 pdf_not_available。以后提供原件及清单即可接入。

## 运行

开发：在 frontend/ 执行 npm ci、npm run dev，Vite 将 /api 代理到 loopback 8000，可用 SCHOLARLENS_API_TARGET 更改服务端代理目标。

生产：构建 frontend/dist，把其绝对路径写入后端 FRONTEND_DIST，FastAPI 同源提供网页与 /api。HTTPS 域名通过独立 Cloudflare Tunnel 转发 loopback 后端，不公开 Elasticsearch 或 Vite preview。详见仓库 docs/11_SERVER_DEPLOYMENT.md。

检索评测仍需真实查询集及人工标注，不能将演示数字作为论文结论。GitHub 不包含数据库、模型、原论文和运行索引，部署需另外交付这些资源。
