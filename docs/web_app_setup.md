# Product Picker Web App Setup

## Install

From Windows Command Prompt:

```bat
cd /d "D:\系统默认\桌面\Product picker"
python -m pip install -r requirements.txt
```

## Run

```bat
cd /d "D:\系统默认\桌面\Product picker"
streamlit run app.py
```

The browser normally opens at [http://localhost:8501](http://localhost:8501).

The app uses the existing local SQLite database. Starting the app does not run scrapers or call Gemini/OpenAI.
