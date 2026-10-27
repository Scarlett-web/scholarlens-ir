# AI 服务配置

2026-10-27。当前真实Key保持空，不存在真实模型生成验收。后端已实现真实论文证据召回、兼容适配器、引用验证和错误处理；受控生成替身仅用于测试。

在项目私有.env中自行设置（不要提交、截图或粘贴真实Key）：

```dotenv
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
AI_TIMEOUT_SECONDS=30
AI_MAX_OUTPUT_TOKENS=800
AI_TOKEN_PARAMETER=max_completion_tokens
```

AI_BASE_URL是服务商OpenAI-compatible API的根地址，通常以/v1结束；程序追加/chat/completions，不重复填完整终点。模型名按服务商文档填写，不猜测你账号可用模型。只有服务器配置地址，客户端不允许指定URL、Key或模型。

默认使用Chat Completions messages和max_completion_tokens，无需安装大型LLM。旧兼容服务若只支持max_tokens，可将AI_TOKEN_PARAMETER改为max_tokens；其他值拒绝启动调用。不强制temperature/JSON mode等供应商可能不支持的参数；通过提示词请求JSON并在服务端校验。

参考[官方Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。此项目选择兼容端点方便更换供应商，不宣称所有兼容服务都已实测。更换后用短问题验证响应形状和引用。

配置后重启API：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infra/start-scholarlens.ps1 -RestartApi
Invoke-RestMethod 'http://127.0.0.1:8000/api/capabilities' | ConvertTo-Json -Depth 8
$body = @{question='How is magnetic resonance used for brain imaging?'; mode='hybrid'; top_k=4} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/ask' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 12
```

不要使用Write-Output $env:AI_API_KEY检查。启动脚本只读取白名单变量、不执行.env内容、不打印密钥。直接start-backend.ps1继承当前Shell环境，不加载.env；一键脚本会加载私有.env。

AI未配置为503 ai_not_configured。配置后但尚未成功调用，能力仍显示dependency_unavailable并说明待验证；成功生成及引用校验后5分钟内ready。问答不被这个“待验证”状态阻止。提供商401/403→502 ai_authentication_failed；429→503 ai_rate_limited；超时→504 ai_timeout；上游异常→502 ai_upstream_error；格式/引用不可信→502 ai_invalid_response或ai_invalid_citations。不给前端上游响应原文或认证头。

默认超时30秒（限制1..120），一次超时或5xx最多重试一次；400/401/403/429不自动重试。输出限制64..4096 tokens；证据最多10片，每片900字符；响应正文上限1MB。不在应用中记录完整问题、Key、模型请求或用户密码。

POST /api/evidence使用同一AskInput但不调用生成服务，可在Key缺失时先验证证据。keyword使用真实基库词项召回和透明的内容词覆盖启发式；semantic使用真实向量和cosine≥0.30的证据候选；hybrid对片段排名RRF。阈值是保守启发式，尚无人工标注校准，不能当答案置信概率。

每条引用先核对索引原文字段字符区间，模型输出再核对chunk_id、原文quote子串与行内引用。无法证明所有生成语句事实正确，前端应保留原文引用入口并提示用户核对；检测失败不展示未经验证的答案。论文文本作为不可信数据进入提示词，不能覆盖系统指令。没有证据时返回insufficient_evidence，不调用生成或空答案弃答。

当前不保存多轮聊天上下文，conversation_id传null。模型商、资费、数据出境和联网额度由组长配置时确认；本轮未发送真实论文到外部生成服务。
