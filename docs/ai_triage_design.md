# AI Cheap Triage Design

AI Cheap Triage 只分析免费规则层已经生成的 Candidate Pool，避免把原始抓取数据、网页或完整 `raw_data` 发送给付费模型。它只回答候选是否值得投入更多成本继续研究，不承担完整市场、供应链或营销分析。

## Input

每条输入仅包含候选类型、来源、标题、最多 500 字符的纯文本描述、分类、主题、候选分，以及存在时的可执行性、需求、Commodity、众筹和公开榜单信号。HTML 会移除，完整原始数据不会进入输入。

## Output

输出为严格 `AITriageResult`：PASS / REVIEW / REJECT、1–10 分、置信度、短原因、机会类型、短机会说明、最多三项风险、是否需要深度分析，以及 provider、model 和分析时间。

评分关注个人可执行性、需求证据、微创新空间、通货竞争风险和监管/技术风险。众筹金额、Amazon rank 或 Reddit signal 不会单独决定高分。

## Cost Protection

- 每批最多 20 条。
- 按 candidate type 轮转选择，避免单一类型占满批次。
- `candidate_id` 在 `ai_triage_results` 中唯一；已有结果默认跳过。
- 只有 `force_reanalyze=True` 才允许覆盖分析。
- Amazon `consumer_trend` 仅允许 Commodity 状态为 PROMISING 的候选进入。

## Mock Mode

Phase 8.1 默认且仅实现 deterministic `MockAIProvider`。相同输入产生相同输出，不访问网络，也不产生 API 费用。Provider 接口为未来 OpenAI 或 Anthropic 实现预留，但本阶段没有实现任何真实 Provider。

## OpenAI Provider Readiness

`OpenAIProvider` 使用 Responses API 的 Structured Outputs JSON Schema，并复用同一套 System Prompt、输入构造器和结果验证。默认模型由 `OPENAI_TRIAGE_MODEL` 统一配置为 `gpt-5.4-nano`。请求不启用工具、检索、网页、图片或文件能力。

Provider 设定 30 秒超时，总共最多尝试两次；鉴权错误不重试。单条失败由 batch 隔离。Provider 选择由 `AI_MODE` 控制，默认仍为 mock。

OpenAI Dry Run 会构造最终请求、验证模型、Schema、候选选择和字符长度，但不初始化网络客户端或发送 HTTP。未来首次真实验证由显式 `--ai-triage-openai-test` 入口触发，并硬限制为最多 5 条、多 candidate type 取样。已有结果仍默认跳过。

官方参考：[GPT-5.4 nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano)、[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)。

## Gemini Provider Readiness

`GeminiProvider` 使用官方 `google-genai` SDK，Cheap Triage 默认模型为 `gemini-3.5-flash-lite`。Structured Output 通过 `application/json` 与同一份 `TRIAGE_JSON_SCHEMA` 约束；Gemini、OpenAI 与 Mock 共用 `SYSTEM_PROMPT`、Candidate Input Builder 和结果验证，不维护分叉的业务规则。

Provider factory 支持 `mock`、`openai` 和 `gemini`。Gemini 同样使用 30 秒超时、最多一次轻量重试，鉴权错误不重试，单条错误由 batch 隔离。Dry Run 不需要 Key、不创建网络请求；未来显式 Gemini 真实验证最多选择 5 条，并复用相同的 candidate type diversity 策略与已有结果跳过保护。

官方参考：[Gemini models](https://ai.google.dev/gemini-api/docs/models)、[Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output)。
