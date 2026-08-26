# Gemini Setup

1. 在 [Google AI Studio](https://aistudio.google.com/)创建 Gemini API Key。
2. 不要把 API Key 发到聊天、邮件或提交到 Git。
3. 打开项目根目录的 `.env`，加入或替换：

   ```text
   GEMINI_API_KEY=你的真实key
   AI_MODE=gemini
   GEMINI_TRIAGE_MODEL=gemini-3.5-flash-lite
   ```

4. 第一次真实验证只运行：

   ```text
   python main.py --ai-triage-gemini-test
   ```

   该入口最多分析 5 条候选，已有结果默认跳过。

5. 在不调用 API 的情况下检查请求准备：

   ```text
   python main.py --ai-triage-gemini-dry-run
   ```

6. 切回本地无费用 Mock：

   ```text
   AI_MODE=mock
   ```

7. 切换到 OpenAI 备用 Provider：

   ```text
   AI_MODE=openai
   OPENAI_TRIAGE_MODEL=gpt-5.4-nano
   ```

不要提交真实 `.env` 或任何 API Key。
