# ScholarLens 前端

React 18 + Vite 6 + TypeScript + React Router 7。当前为冰川白玻璃、桌面顶部 Dock、3D 最近阅读与大对话区；本轮只更新文档，保留 `d7cfc56` 外观。

## 开发与正式构建

在本目录运行 `npm ci`、`npm run dev`。正式应用发布运行：

```powershell
npm run typecheck
npm run test
npm run verify:structure
npm run build:production
```

已有隔离预览环境才运行相应 browser 检查，先核对端口和数据归属。普通 build 可能生成 18 篇明确标记的 demo，不能当成生产真实检索；production 固定 API 模式和同源 `/api` 并生成 `dist/build-info.json`。

## 文档入口

- [项目总报告](../docs/PROJECT_REPORT.md)和[PPT 底稿](../docs/PPT_OUTLINE.md)。
- [当前设计](../docs/development/frontend/DESIGN_SYSTEM.md)、[功能范围](../docs/development/frontend/FEATURE_SPEC.md)、[QA](../docs/development/frontend/QA_CHECKLIST.md)。
- [全栈契约](../docs/development/frontend/FULL_STACK_CONTRACT.md)、[后端集成](../docs/development/frontend/BACKEND_INTEGRATION.md)、[个人 API](../docs/development/frontend/AI_API_INTEGRATION.md)。
- [历史设计](../docs/archive/frontend/20261027-28/README.md)、[图片来源](public/images/SOURCES.md)。

`frontend/docs/` 仅保留结构检查要求的短跳转文件；正文统一在根 `docs/`，不要再复制一份。游客工作区与阅读位置在浏览器，登录工作区同步后端；个人 key 只存标签页，禁止写入构建变量。本地 PDF 与服务器入库分开，页面下载使用原 PDF。样式继续维护现有 canonical 层，本次不改。
