# AI 服务配置

> 阅读口径：本文件保留原阶段的协议、命令与验收条件。当前实现、部署和外部服务状态见[项目总报告](../../PROJECT_REPORT.md)与[当前状态](../../operations/STATUS.md)。旧阶段的“待接通/待交付”不覆盖后续已完成内容。

V2.1已加入会话上下文/持久化、单篇总结、多文献方法与结论比较、完整校验后SSE，详见FRONTEND_API_GUIDE_V21.md。下方“尚无多轮上下文”属于旧V2状态；当前会话需登录，取最近12条消息，每条至多1000字符，paper_ids按每次请求传入，不自动继承上次论文选择。旧回答仅是语境，引用必须来自当前真实证据。全局 Key 保持空，个人 Key 不在文档保存。指定模型真实生成已经单独验收，见[助手验收](../../archive/releases-20261028-29/38_ASSISTANT_CHAT_AND_API.md)；模型替身结果仍不代表真实云端生成。

2026-10-28：网站优先使用登录用户自行配置的个人 API，全局配置保持为空。支持 Chat Completions 和 Responses，可读取模型列表并进行一次真实小请求测试。新契约及最新验证边界见 [个人 AI 配置](../../operations/10_RELEASE_AND_PERSONAL_AI.md)。下方旧 V2 验收说明仅代表当时状态。

在项目私有.env中自行设置（不要提交、截图或粘贴真实Key）：

```dotenv
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
AI_TIMEOUT_SECONDS=30
AI_MAX_OUTPUT_TOKENS=800
AI_TOKEN_PARAMETER=max_completion_tokens
AI_PROTOCOL=chat_completions
```

AI_BASE_URL 是兼容 API 的根地址，通常以 /v1 结束；程序按 AI_PROTOCOL 追加 /chat/completions 或 /responses。个人配置通过按请求生效的专用头传入，需登录，不修改服务器环境。模型须选供应商当前可用项，不自动替换已下线模型。

默认使用 Chat Completions messages 和 max_completion_tokens；旧服务可选 max_tokens。Responses 使用 input、max_output_tokens、store:false，仅接受 completed 的 assistant output_text。规划与回答使用同一协议，不强制 temperature 或 JSON mode；引用仍在服务端校验。

参考[官方Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。此项目选择兼容端点方便更换供应商，不宣称所有兼容服务都已实测。更换后用短问题验证响应形状和引用。

下列命令仅用于管理员主动修改全局环境后的本机启动；个人 API 页面保存无需重启。命令从仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens1.ps1 -RestartApi
Invoke-RestMethod 'http://127.0.0.1:8000/api/capabilities' | ConvertTo-Json -Depth 8
$body = @{question='How is magnetic resonance used for brain imaging?'; mode='hybrid'; top_k=4} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/ask' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 12
```

不要使用Write-Output $env:AI_API_KEY检查。启动脚本只读取白名单变量、不执行.env内容、不打印密钥。直接start-backend1.ps1继承当前Shell环境，不加载.env；一键脚本会加载私有.env。

AI未配置为503 ai_not_configured。配置后但尚未成功调用，能力仍显示dependency_unavailable并说明待验证；成功生成及引用校验后5分钟内ready。问答不被这个“待验证”状态阻止。提供商401/403→502 ai_authentication_failed；429→503 ai_rate_limited；超时→504 ai_timeout；上游异常→502 ai_upstream_error；格式/引用不可信→502 ai_invalid_response或ai_invalid_citations。不给前端上游响应原文或认证头。

全局默认超时30秒（限制1..120），个人读取至少60秒且受Agent总预算120秒约束；一次超时或5xx最多重试一次；400/401/403/429不自动重试。输出限制64..4096 tokens；证据最多10片，每片900字符；响应正文上限1MB。不在应用中记录完整问题、Key、模型请求或用户密码。

POST /api/evidence使用同一AskInput但不调用生成服务，可在Key缺失时先验证证据。keyword使用真实基库词项召回和透明的内容词覆盖启发式；semantic使用真实向量和cosine≥0.30的证据候选；hybrid对片段排名RRF。阈值是保守启发式，尚无人工标注校准，不能当答案置信概率。

每条引用先核对索引原文字段字符区间，模型输出再核对 chunk_id、原文 quote 子串与行内引用。无法证明所有生成语句事实正确，前端保留原文入口供用户核对；引用检测失败不展示未经验证的论文答案。论文文本作为不可信数据进入提示词。严格 `/ask` 保留证据不足语义；`/agent/run` 在缺少论文证据时可以自然回答，并明确标注通用回答，不伪造本库引用。

当前支持账户隔离的多轮对话；临时对话传 null，不自动保存。模型商与额度由各用户自行选择。读取模型列表不代表生成成功；连接测试只发送短问题，论文问答则按用户选择发送必要证据。供应商验收须注明日期、模型和真实调用范围，不以替身测试或 HTTP 200 代替。
