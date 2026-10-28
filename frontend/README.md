# ScholarLens 前端

React 18 + Vite 6 + TypeScript + React Router 7。桌面优先的冰岛照片、玻璃导航、研究书架和清晰纸面阅读，主流程为搜索 → 阅读 → 保存与标注。

当前页面已连接真实 API，涵盖账户、三模式检索、收藏笔记、最近阅读、上传审核、证据助手与评测。[项目总报告](../docs/PROJECT_REPORT_20261028.md)包含完整现状和汇报材料，旧设计过程在 `docs/archive/20261027-28/`。

## 开发与正式构建

进入本目录：

```powershell
npm ci
npm run dev
```

正式发布：

```powershell
npm run typecheck
npm run test
npm run verify:structure
npm run build:production
```

默认 demo 使用 18 篇明确标记的虚构样本，不能称为 BM25 或真实检索。普通 `npm run build` 不应直接上传生产；`build:production` 固定 `VITE_DATA_SOURCE=api`、`VITE_API_BASE_URL=/api`，输出 `build-info.json` 记录 JS/CSS hash。生产仍须验证页面显示真实论文，不只检查构建退出码。

API、ES、SQLite 分别运行；Vite 代理只连接后端，浏览器不直接访问 ES 或数据库。现有预览进程和端口可能属于其他工作，先核对再操作。

## 页面与交互

- 首页首屏搜索、玻璃研究棱镜、最多五篇真实最近阅读。自动翻页可暂停，支持前后/页码/键盘。
- 搜索字段/年份/排序/分页/建议/分享链接；关键词、语义、混合遵守服务端能力限制。
- 详情、正文窗口、专注模式、位置恢复、选文摘录、PDF 与文本 DOCX、来源证据。
- 发现列表与按真实字段连接的关系图；关系不表示引用次数或语义距离。
- 书架分类、笔记、导入导出；加载/同步失败保留已知数据和恢复入口。
- 账户、安全、通知、个人 API 配置；上传和审核按角色隔离。
- 评测使用 0/1/2 人工标注，满足当前前缀要求后才展示 Precision/nDCG。
- 动效暂停与系统减少动态效果始终生效；390px 只做回归。

## 数据保存

游客空间和阅读位置使用浏览器本地存储；登录工作区同步服务器，失败保留本机恢复草稿。阅读位置不是跨设备同步进度。

每用户 API URL/模型偏好存 `localStorage`；API key 仅存标签页 `sessionStorage`，退出/会话失效清除，按请求传给同源后端，不进 Vite 变量或服务器数据库。默认不配置共享供应商；无模型时真实 API 证据检索可用，demo 模式该入口禁用并说明原因。

本机 PDF 使用 IndexedDB，与服务器上传队列不同；本机审核通过不表示正式进入 ES。原始论文 PDF 由后端受控读取，不由 JSONL 合成。

## 维护入口

- [当前 QA 清单](docs/QA_CHECKLIST.md)
- [设计规范](docs/DESIGN_SYSTEM.md)、[功能范围](docs/FEATURE_SPEC.md)
- [前后端契约](docs/FULL_STACK_CONTRACT.md)、[后端集成](docs/BACKEND_INTEGRATION.md)、[个人 API](docs/AI_API_INTEGRATION.md)
- [设计参考审计](docs/DESIGN_SKILL_AUDIT.md)和[图片来源](public/images/SOURCES.md)
- [历史设计与验收](docs/archive/20261027-28/README.md)

样式直接维护现有 canonical CSS；不追加覆盖表。图片本地提供，不在运行中请求摄影网站。第三方设计 Skill 是参考，服从实际产品和用户要求。
