# ScholarLens — 冰川观测站与玻璃研究桌

当前版本已连接账户、三模式检索、收藏笔记、最近阅读、上传审核和研究助手。登录用户可独立填写个人 API，密钥仅在标签页会话内保存。当前集成状态见 docs/BACKEND_INTEGRATION.md 与 docs/AI_API_INTEGRATION.md，下方纯前端内容为设计历史。

当前桌面版使用冰岛杰古沙龙冰河湖实景、连贯的玻璃框架与导航、开放首页与清晰纸面阅读区。保留系统字体、蓝色主动作和检索 → 阅读 → 收藏整理的完整流程；最近五篇仍来自实际阅读记录。鼠标局部高光与已有动效支持暂停及减少动态设置。设计规范见 docs/DESIGN_SYSTEM.md；图片来源见 docs/UI_GLACIER_OBSERVATORY_20261027.md；最新的通透材质与容器精简见 docs/UI_CLEAR_GLASS_20261027.md。

## 启动与校验

在 Windows PowerShell 中：

    cd frontend
    npm install
    npm run dev

打开 Vite 控制台给出的本地网址。检查项目：

    npm run test
    npm run verify:structure
    npm run build

## 最近阅读与动效

首页 3D 卡片展示自己最近打开过的最多 5 篇不同论文，最近看过的排在前面；不足 5 篇按实际数量显示，没有记录时显示空状态。支持纸张翻页、7 秒自动切换、前后按钮、页码跳转与键盘方向键。悬停、键盘焦点、离屏或页面隐藏时暂停自动翻页。阅读记录继续使用原浏览器本地存储，刷新保留；同一浏览器的新标签页阅读后，首页会同步更新。

动效扩展到知识连线、侧栏导航、搜索聚焦、按钮点击波纹、收藏反馈、列表滚动入场和探索卡片。侧栏可以暂停/开启网站动效，设置会记住；系统减少动态效果时自动停用运动，手动翻页仍可操作。没有增加动画依赖、WebGL 或远程媒体。本轮按用户要求以电脑端为设计和验收重点，详见 docs/UI_READING_DECK_20261027.md。

## 如何找到功能

- 桌面左侧常驻：**首页 / 论文检索 / 探索论文 / 我的文献**。
- 左侧“研究工具”分组：**检索评测 / PDF 工作区 / 审核工作台 / AI 助手**；手机端使用收起式全功能导航；三个工具页面之间保留页内切换。
- 首页只有一个主搜索框，右上方可翻阅最近五篇阅读记录，下方集中放置主题入口和个人阅读空间。
- 搜索页左侧筛选、右侧连续文献列表；探索页使用首篇突出、其余双列的浏览布局。手机端筛选与收藏分类默认收起，展开后可正常使用。
- AI 默认为空 API，未接入时禁用发送按钮。

## 已经可以独立使用的前端功能

1. 检索：全部字段及标题、作者、日期、机构、地址、全文六字段；查询历史、搜索建议、URL 分享、年份筛选、分页、排序和关键词高亮。
2. 论文详情：摘要与全文、文中查词、全文展开、引用整理与导出、收藏、主题相关论文、PDF 可用时内嵌阅读。
3. 文献探索：按领域、关键词、年份和随机顺序浏览，卡片直达详情。
4. 我的空间：收藏分类创建/重命名/删除、笔记、本地历史、JSON 导出与恢复。
5. 本地 PDF 工作区：校验 PDF 文件头、15MB 限制、SHA-256 去重、IndexedDB 存文件、原文阅读与删除。
6. 本地审核：按状态与文件名筛选、看 PDF、写备注、通过/拒绝/恢复待审、删除文件。
7. 检索评测：运行当前搜索，对返回论文人工标注 0/1/2，满足标注要求后才计算 Precision@k 和 nDCG@k，支持 JSON 导出。
8. AI：聊天界面已准备发送、停止、错误处理和来源回链；**模型和 API 完全空白，未配置时不会发请求或伪造答案**。具体说明见 docs/AI_API_INTEGRATION.md。

## 数据真实性与隔离

- 默认模式只有 18 篇虚构演示论文。模拟字符串检索不是 Elasticsearch BM25。
- 接入 FastAPI 使用 VITE_DATA_SOURCE=api，但请求字段和响应结构仍须与原项目契约核对。
- Semantic / Hybrid 模式没有后端前不开放操作，不冒充已完成。
- 本地 PDF 的上传与审核只影响当前浏览器。审核通过也不会进入 ES 正式索引。
- AI 模型和供应商由你自己决定，个人密钥仅保存在标签页 sessionStorage，请求时交给同源后端转发，不应写进 Vite 变量。
- 真实检索和真实评测必须使用正式论文和人工标注集，不能用演示数据代替。

## 关键文件

- src/pages/：完整页面。
- src/components/：组件与本地 PDF 阅读器。
- src/services/papers.ts：FastAPI 论文适配层。
- src/services/ai.ts：AI 空配置适配层。
- src/lib/pdfStore.ts：PDF 本地存储与内容校验。
- src/lib/evaluation.ts：标注指标计算。
- src/design-core.css、src/design-pages.css、src/design-workspaces.css：V6 设计规范，直接维护已有 CSS，不再新增叠加的补丁层。
- docs/：功能、设计、API 对接和验收资料。
- tests/：纯函数测试及结构检查。

可选浏览器交互回归：先运行 npm run build，再启动 npm run preview -- --port 4173；在另一终端运行 npm run test:browser（本机 Chrome）。

已在项目下安装 .agents/skills/landing-page-design 与 .agents/skills/redesign-existing-projects；AGENTS.md 告诉后续 Codex 如何组合使用。两套技能按 MIT 许可提供，来源是公开的 GitHub 仓库；其设计约束服从 ScholarLens 的真实产品要求。本轮桌面与真实 390px 手机模拟截图见 output/playwright/，最新改版说明见 docs/UI_REFRESH_V6_20261027.md。根目录 qa-skill-*.png 为旧版验收图（浏览器测试会更新其中的手机图）。正式课堂演示前仍应按 docs/QA_CHECKLIST.md 检查投影效果与真实后端。
