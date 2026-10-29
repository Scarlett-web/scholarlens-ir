# 冰川观测站与玻璃研究桌（2026-10-27）

## 范围与结果

用户已授权先实施桌面版看效果。本轮把冰岛实景、玻璃导航与纸面阅读应用到首页、检索、探索、我的文献、论文详情、检索评测、PDF 工作区、审核、AI 空配置界面和 404。保留现有功能与 URL，不配置 AI、不写真实索引、不改变用户本地数据，不增加新的 CSS 覆盖层或依赖。

首页透明度较高；工具页增加纸面分组；正文更不透明。搜索聚焦、列表入场、点击反馈、最近五篇 3D 翻页保留，新增事件驱动的局部玻璃高光。动画可全局暂停并遵循减少动态设置；不支持背景模糊时回退为较实的背景色。修复收藏分类数量与重命名/删除按钮间距。

## 图片

- 摄影师：X1ntao ZHOU。
- 来源：https://www.pexels.com/photo/stunning-icebergs-in-jokulsarlon-glacier-lagoon-32014201/
- 许可：https://www.pexels.com/license/
- 本地资源：public/images/iceland-jokulsarlon.webp，3200×1801，716,302 字节。
- 原图 6000×3376，等比缩小、转 WebP quality 88；页面从本地加载。来源详见 public/images/SOURCES.md，页脚保留摄影署名。

## 变更位置

- src/components/Layout.tsx：背景、工作区透明层级、摄影来源。
- src/components/MotionEffects.tsx：鼠标局部高光与暂停清理。
- src/pages/HomePage.tsx：首页场景说明。
- src/design-core.css、src/design-pages.css、src/design-workspaces.css：直接维护已有样式。
- README.md、docs/DESIGN_SYSTEM.md、docs/QA_CHECKLIST.md：当前说明与验收。

## 验证

npm run build 通过；npm run test 的 6 项指标测试通过；npm run verify:structure 通过。最终 CSS 后 npm run test:browser 再次通过，覆盖搜索/分页/筛选/详情、收藏笔记及备份、评测、本地 PDF 保存去重与审核预览、AI 禁用、工具导航、404、最近五篇与移动搜索导航。

独立 Playwright Chrome 检查：1440px 各主要页面截图；1024px 九个主要页面无水平溢出；1280px、1920px 首页无水平溢出。实际鼠标翻页及标题导航通过。高光变量随鼠标更新，暂停及减少动态后清除。390×844 首页截图无溢出，移动仅作原有功能回归。图片加载成功，naturalWidth=3200；浏览器页面错误列表为空。

截图位于 output/playwright/glacier-*。主要交付图 glacier-home-desktop.png；其中最近五篇来自隔离测试上下文实际浏览演示论文，不是预置到用户浏览器的历史记录。

## 回滚

修改前副本：C:/Users/lenovo/Desktop/zjl-backups/20261027-204651-glacier-observatory。

需要撤销时，先保存当前项目副本，然后按备份中的相对路径，仅恢复上述三个 CSS、Layout.tsx、MotionEffects.tsx、HomePage.tsx 以及已备份的 README 和两份设计/验收文档，再运行 npm run build 更新 4173 预览。不覆盖备份以外文件，不清除 localStorage 或 IndexedDB。新增的图片及本说明可先保留，不影响旧页面；仅在另行确认后移除。备份中的 tests/browser-smoke.mjs 本轮没有必要恢复，因为本轮未改测试脚本。

## 边界

默认仍为 18 篇明确标记的虚构演示论文。真实 FastAPI/Elasticsearch、语义/混合检索、真实 AI 服务、教室投影、用户已有浏览器状态及真机性能不由本轮检查证明。本轮未发布、提交、推送或停止已有服务。
