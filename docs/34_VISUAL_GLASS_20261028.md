# 34 外观玻璃化与透明控制（2026-10-28）

本轮把界面环境从"冰川夜 + 深色侧栏"改成"日间冰川 + 纯白玻璃"，并把玻璃透明度做成用户可切换的三档预设。**只改视觉层，未改变任何路由、接口、数据流、交互逻辑。**

## 1. 来源与授权

| 项 | 内容 |
|---|---|
| 用户要求（2026-10-28 第一轮） | 只做外观美化；可以改，但要有记录方便回滚；不要破坏其他功能 |
| 用户要求（2026-10-28 第二轮） | 不喜欢深沉色调；喜欢玻璃质感、大海冰川；要玻璃色、纯白透明页面框；透明度可以调节；移动端不用管 |
| 影响面 | `frontend/src` 下 5 个文件；不涉及后端、接口、数据、路由、AI 配置 |

## 2. 两个阶段

| 阶段 | 目录 | 状态 |
|---|---|---|
| 阶段一：冰川夜玻璃 | `output/visual-upgrade-20261028/` | 已实现，被阶段二取代 |
| 阶段二：日间白玻璃 + 透明度三档 | `output/glass-daylight/` | 当前生效 |

阶段一的方向（深色冰川夜 + 深蓝侧栏）在阶段二被判定为"深沉"，已整体替换。阶段一的产物保留作为对照，回滚时按下面的顺序处理。

## 3. 阶段二改动清单

### 3.1 `frontend/src/design-core.css`

**(a) 玻璃透明度变量（新增，唯一调节入口）**

```css
.workspace-shell{--glass-sidebar:.36;--glass-stage:.54;--glass-home:.46;--glass-header:.5;--glass-shell:.18}
.workspace-shell[data-glass=clear]{--glass-sidebar:.22;--glass-stage:.34;--glass-home:.28;--glass-header:.34;--glass-shell:.1}
.workspace-shell[data-glass=solid]{--glass-sidebar:.60;--glass-stage:.76;--glass-home:.68;--glass-header:.72;--glass-shell:.40}
```

所有玻璃表面只引用这五个变量，不另写孤立透明度。切换 `data-glass` 即可整体换档。

| 变量 | 控制对象 |
|---|---|
| `--glass-sidebar` | 左侧导航栏玻璃 |
| `--glass-stage` | 内容区玻璃 |
| `--glass-home` | 首页内容区玻璃（略透一档） |
| `--glass-header` | 顶栏玻璃 |
| `--glass-shell` | 最外层圆角画框玻璃 |

**(b) 冰川背景提亮**

| 规则 | 改前 | 改后 | 目的 |
|---|---|---|---|
| `.observatory-backdrop` | `#071726` 深夜蓝 | `#cfe4f0` 日间冰蓝 | 背景不再是黑蓝 |
| `img` filter | `brightness(.96) saturate(1.14) contrast(1.05)` | `brightness(1.02) saturate(1.16) contrast(1.06)` | 冰川纹理更清楚 |
| `:before` | 深色压光三层 | 顶部白色柔光 + 底部极淡冷调 | 照亮画面顶部 |
| `:after` | `#0b2b3fd9` 深色暗角 | `#b9d5e48f` 淡蓝雾化 | 去掉底部发黑 |

**(c) 侧栏从深蓝改纯白玻璃**

| 项 | 改前 | 改后 |
|---|---|---|
| 背景 | `linear-gradient(180deg,#04182a9e,#03111d94)` | `rgba(255,255,255,var(--glass-sidebar))` |
| 模糊 | `blur(22px) saturate(1.3)` | `blur(20px) saturate(1.4)` |
| 右边界 | `#bcecf03d` | `1px solid #ffffffd1` + 内外高光 |
| 主文字 | `#e4f3f7` 浅白 | `#193348` 深墨 |
| 次级文字 | `#a9c3cc` | `#5b768a` |
| hover 底 | `#d4f4f51b` | `#ffffffa8` |
| 选中底 | `#d9f7fa28` | `#ffffffe6` + 投影 |
| 选中图标 | `#8adbd8` 青绿 | `#0969a9` 品牌蓝 |
| 底部账户章 | `#d8f5f52a` | `#ffffffd1` / 文字 `#2b5266` |

**(d) 内容区与顶栏改白玻璃**

| 规则 | 改前 | 改后 |
|---|---|---|
| `.app-stage:before` | 蓝灰渐变 `#eef8fcb8→#d6e8f2b3`，`blur(26px)` | `rgba(255,255,255,var(--glass-stage))`，`blur(16px) saturate(1.3)` + 左侧内阴影 |
| `.app-stage[data-space=home]:before` | 另一组蓝灰渐变 | `rgba(255,255,255,var(--glass-home))` |
| `.site-header` | 蓝灰渐变 | `rgba(255,255,255,var(--glass-header))`，`blur(20px) saturate(1.3)` |
| `.workspace-shell:before` | 白 15% 淡渐变 | `rgba(255,255,255,var(--glass-shell))`，`blur(6px)` |

**(e) 页面标题字距**

`.page-heading h1`：`letter-spacing:-.04em; line-height:1.2` → `-.025em; line-height:1.24`。
原因：中文四字标题在 `-.04em` 下字挤在一起，与首页标题（`-.02em`）不一致。

**(f) 玻璃档位按钮样式**

`.site-motion-toggle` 选择器扩展为 `.site-motion-toggle,.site-glass-toggle`，共享尺寸、hover、文字色，避免新增一套按钮样式。

### 3.2 `frontend/src/design-pages.css`

| 规则 | 改前 | 改后 | 目的 |
|---|---|---|---|
| `.apple-home .hero h1` | `line-height:1.22; letter-spacing:-.022em` | `1.26; -.02em` | 中文两行标题呼吸感 |
| `.hero h1>span` 渐变 | `#1b5878,#2b8ba6 56%,#35a7b2` | `#24556f,#2f7189 54%,#3d869d` | 收敛荧光青，与第一行统一 |
| `.research-prism` 位置 | `inset:-24px -16px 0 -64px` | `inset:8px -16px 0 -60px` | 顶部尖角不再刺入天空 |
| `.research-prism` 存在感 | 无 opacity | `opacity:.55` | 背景变亮后棱镜不再抢戏 |
| 棱镜各面填充 | `#f6ffffcc` / `#93d4eea8` / `#dbf6ff7d` / `#6fa9d09e` / `#cdf4fa9e` / `#f7ffff80` | `#eefafdd4` / `#8fcfea94` / `#d3f2fb6b` / `#6fa9d094` / `#c8f1f894` / `#e4f7fc63` | 与白玻璃区分开 |
| `.prism-edges` | `#f4ffffcc` / `.9` 宽 | `#e9fcff9c` / `.52` | 硬白描边减淡 |
| `.motion-toggle` | `#fff` 实底 + `#eeeef2` 边 | `#ffffff52` 半透明 + `#ffffffa8` 边 + 深墨字 `#3d5b70` | 从"白标签"降为轻量控制 |
| `.search-form` 背景 | `rgba(255,255,255,.52)` | `rgba(255,255,255,.8)` + 双层投影 | 输入控件在浅底上必须浮起来 |
| 移动端 `.search-options` | 右对齐孤悬 | `margin:12px 0 0;width:100%`，`summary` 左对齐 | 与下方"试试搜索"同一条左对齐线 |

### 3.3 `frontend/src/App.tsx`

新增纯界面状态，与既有 `presentation` / `motionPaused` 同一套模式（`readLocal` + `useEffect` 持久化）：

```ts
export type GlassLevel = "clear" | "soft" | "solid";
export const GLASS_PRESETS = [
  { value: "clear", label: "通透", hint: "玻璃最薄，冰川最清楚" },
  { value: "soft",  label: "标准", hint: "文字与背景的默认平衡" },
  { value: "solid", label: "厚雾", hint: "玻璃最实，正文对比最强" },
];
export const normalizeGlass = (value: unknown): GlassLevel => ...;
```

- 存储键：`scholarlens-v1:glass`（沿用既有存储前缀）
- 上下文新增：`glass`、`setGlass`
- 默认值 `soft`；非法值回落 `soft`

### 3.4 `frontend/src/components/Layout.tsx`

- 根节点加 `data-glass={glass}`
- 侧栏底部新增按钮：

```tsx
<button className="site-glass-toggle" type="button" onClick={cycleGlass} title="调整页面玻璃的通透度：通透 / 标准 / 厚雾">
  <Layers size={18}/><span>玻璃通透度 · {glassLabel}</span>
</button>
```

- `cycleGlass()` 在 `通透 → 标准 → 厚雾` 之间循环，切换后通过既有 `notify()` 给出提示。**不新增 toast 机制。**

### 3.5 `frontend/src/pages/HomePage.tsx`

只有 2 个数字（阶段一遗留）：鼠标视差幅度 `×8/×10` → `×14/×18`。角度上限仍是 `14°/18°`，不产生眩晕。

## 4. 新增的本地验证脚本

三个脚本都在 `frontend/scripts/`，只读页面、不改项目状态，用于替代"凭截图猜"的验收方式：

| 脚本 | 用途 | 命令 |
|---|---|---|
| `capture-screens.mjs` | CDP 精确视口截图（8 个页面 × 桌面/移动）；`--glass` 可预置透明度档位 | `node scripts/capture-screens.mjs --out DIR --prefix p [--only home] [--glass clear]` |
| `measure-overflow.mjs` | 逐元素检测横向溢出，输出超出视口的元素清单 | `node scripts/measure-overflow.mjs`（`WIDTH=390` 等环境变量可选） |
| `probe-dom.mjs` | 在真实页面上取计算样式与包围盒，用于核对"以为改了其实没生效" | `node scripts/probe-dom.mjs --url /search --selector ".page-heading h1" --styles font-size,letter-spacing` |

为什么不用 `chrome --headless --screenshot --window-size`：那条路径栅格化的是窗口而不是 CSS 视口，右边缘会假性截断，曾导致把"没有溢出的移动端"误判成横向滚动。`--virtual-time-budget` 也无法与 `Emulation.setDeviceMetricsOverride` 等价。

`.env.visual`（`VITE_DATA_SOURCE=demo`）只用于评审构建，让 18 篇标注为虚构的样本把各页面填满；已被 `.gitignore` 的 `.env.*` 规则排除，不进仓库，不用于生产。

## 5. 验证记录

| 检查 | 命令 | 结果 |
|---|---|---|
| 类型检查 + 生产构建 | `npm run build:production` | 见 `output/glass-daylight/verify-build.txt` |
| 单元测试 | `npm run test` | 35 passed / 0 failed |
| 结构校验 | `npm run verify:structure` | 44 files, 24 modules, 8 routes + 404, 18 synthetic papers |
| 浏览器冒烟 | `npm run test:browser` | 16 项全 PASS，含"sidebar exposes all secondary workflows" |
| 横向溢出 | `node scripts/measure-overflow.mjs` | 390px 与 1440px 均为 0px |
| 视觉对拍 | `output/glass-daylight/*.png` | 首页/搜索/文献/探索/阅读 + 390 移动端 |

## 6. 回滚

### A. 只回滚本轮（阶段二 → 阶段一）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File output/glass-daylight/rollback.ps1
```

### B. 回到仓库 HEAD（取消两轮外观改动）

```powershell
cd dev\scholarlens-ir\zjl
git checkout -- frontend/src/App.tsx frontend/src/components/Layout.tsx `
  frontend/src/design-core.css frontend/src/design-pages.css frontend/src/pages/HomePage.tsx
```

### C. 手工覆盖

`output/glass-daylight/before/` 保存本轮改前的原始字节，直接复制回同名路径即可。

## 7. 未改动清单（确认没碰）

- 全部路由与 URL、`services/*`、`lib/*`、`data/*`
- 搜索、收藏、笔记、备份导入导出、本地 PDF、检索评测、审核、AI 占位逻辑
- 后端与索引；`index.html`、`vite.config.ts`、`package.json`
- 未新增覆盖样式表：所有规则就地改在 `design-core.css` / `design-pages.css` 的 canonical 位置
- 移动端布局结构未动（仅"关键词检索"一行对齐方式调整）
