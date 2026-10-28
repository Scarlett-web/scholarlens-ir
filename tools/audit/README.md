# ScholarLens 项目内审计工具链

这里是本项目专用的审计工具目录。依赖安装在 `tools/audit/node_modules`，不会修改全局 npm 配置，也不会上传扫描结果。

## 已纳入的工具

| 工具 | 用途 | 默认状态 |
| --- | --- | --- |
| Squirrelscan | 页面、SEO、无障碍和响应头初筛 | 本地安装，需显式指定目标后运行 |
| Playwright CLI | 独立浏览器流程和截图 | 本地安装，优先使用测试账号 |
| Lighthouse | 性能、SEO、可访问性基线 | 本地安装，默认只扫本机预览 |
| Semgrep | 前后端静态安全模式 | 仅探测本机已有命令，不上传云端 |
| Gitleaks | 当前仓库和历史凭据线索 | 仅探测本机已有命令 |
| OWASP ZAP | 动态安全 | 不随项目启动；只在隔离测试环境被动运行 |

## 运行

在仓库根目录执行：

```powershell
pwsh -File tools/audit/run-audit.ps1 -TargetUrl http://127.0.0.1:4173
```

线上只读检查必须显式加 `-AllowLive`，脚本不会登录、提交表单、上传文件、删除数据或启动主动攻击扫描：

```powershell
pwsh -File tools/audit/run-audit.ps1 -TargetUrl https://scholarlens.lingion.cc.cd/ -AllowLive
```

报告输出到 `tools/audit/reports/<timestamp>/`，默认被 Git 忽略。缺少 Semgrep 或 Gitleaks 时会标记 `not_installed`，不会伪造通过。
