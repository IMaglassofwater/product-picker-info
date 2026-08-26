# Deploy Streamlit Community Cloud

1. Create a private GitHub repository and push the reviewed project manually.
2. Sign in to Streamlit Community Cloud and authorize access to that private repository.
3. Select **Create app / New App** and choose the repository and branch.
4. Set **Main file path** to `app.py` and Python to 3.12.
5. In Advanced settings / Secrets, add only:

   ```toml
   DATABASE_URL = "your Neon pooled connection string"
   ```

6. Deploy, open the URL, and verify Today, All Products, one feedback action, and Last Daily Run.

Do not place `GEMINI_API_KEY` in Streamlit secrets: the Web process does not call Gemini. Opening the app never scrapes, migrates, or starts `run_daily.py`.

References: [deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [private repository access](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account), and [secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
