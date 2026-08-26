# OpenAI Setup

1. 在 [OpenAI API 平台](https://platform.openai.com/)创建 API Key。
2. 不要把 API Key 发到聊天、邮件或提交到 Git。
3. 打开项目根目录的 `.env`，加入或替换：

   ```text
   OPENAI_API_KEY=你的真实key
   AI_MODE=openai
   OPENAI_TRIAGE_MODEL=gpt-5.4-nano
   ```

4. 第一次真实验证只运行：

   ```text
   python main.py --ai-triage-openai-test
   ```

   该入口最多分析 5 条候选；已有结果默认跳过。

5. 如需在不调用 API 的情况下检查配置和请求准备，运行：

   ```text
   python main.py --ai-triage-openai-dry-run
   ```

6. 要切回无费用的本地 Mock 模式，将 `.env` 中的配置改为：

   ```text
   AI_MODE=mock
   ```

不要提交真实 `.env` 或任何 API Key。
