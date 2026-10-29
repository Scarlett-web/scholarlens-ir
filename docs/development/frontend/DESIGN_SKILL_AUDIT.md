# ScholarLens — design skill audit

> 阅读口径：本文件保留原阶段的协议、命令与验收条件。当前实现、部署和外部服务状态见[项目总报告](../../PROJECT_REPORT.md)与[当前状态](../../operations/STATUS.md)。旧阶段的“待接通/待交付”不覆盖后续已完成内容。

Sources:
- https://github.com/elayadesign/ai-design-skills (landing-page-design)
- https://github.com/elayadesign/redesign-skill (redesign-existing-projects)

Installed as plain Markdown project skills under .agents/skills. The showcase/video skill was excluded because this is a functioning research product.

## Before edits

1. Typography too small: many 10/11px labels and 12.7px abstracts reduce readability, especially in classroom projection.
2. Inconsistent values: successive CSS patches contain radii 9/10/11/13/15/17/18/19/22px and arbitrary gaps. Components feel subtly misaligned.
3. Repeated generic home cards: two equal promotional cards under a centered hero hide the actual research workflow.
4. Distracting secondary labels: dense tags, muted explanations and repeated banners compete with paper titles.
5. Weak recovery: unknown routes silently redirect home, with no explanation or a meaningful next step.
6. Future design work lacked project-specific guidance and repeatedly reintroduced generic patterns.

## Planned changes

- Keep React/Vite architecture and working behavior.
- Normalize tokens in existing design-core, design-pages and design-workspaces stylesheets; no extra cascade layer.
- Recompose home lower section as an editorial sequence of real routes.
- Enlarge paper, filter, button and metadata type; reduce decorative tags and shadows.
- Give empty library and unknown routes a clear next action.
- Use full-circle borders for panels, coherent nested radii, custom easing and visible focus.
- Preserve synthetic-demo labels, empty AI endpoint and separation from FastAPI.

## Verification

Production build and actual Chrome click/resize tests should be repeated after edits. Backend integration and AI configuration remain future work; no fictional effectiveness claims.
