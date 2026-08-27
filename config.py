"""Application configuration loaded from environment variables or local .env."""

from __future__ import annotations

import os
from pathlib import Path


ENV_PATH = Path(__file__).resolve().parent / ".env"
ETSY_PLACEHOLDERS = {
    "",
    "PASTE_YOUR_ETSY_API_KEY_HERE",
    "PASTE_YOUR_ETSY_SHARED_SECRET_HERE",
}

REDDIT_SUBREDDITS = [
    {"name": "EDC", "weight": "low"},
    {"name": "ShutUpAndTakeMyMoney", "weight": "medium"},
    {"name": "onebag", "weight": "high"},
    {"name": "BuyItForLife", "weight": "high"},
    {"name": "CampingGear", "weight": "medium_high"},
    {"name": "organization", "weight": "high"},
]
REDDIT_LIMIT_PER_SUBREDDIT = 30
REDDIT_LOOKBACK_DAYS = 90
REDDIT_INTENTS = (
    "looking for", "recommend", "recommendation", "suggestions", "need",
    "wish", "can't find", "cannot find", "too expensive", "cheaper",
    "alternative", "replacement", "problem", "annoying", "better way",
    "what do you use", "what should I get", "how do you carry",
    "how do you store", "how do you organize",
)
REDDIT_SUBREDDIT_INTENTS = {
    "onebag": ("lightweight", "bulky", "pack", "carry", "organize", "space"),
    "buyitforlife": ("durable", "last", "replacement", "broke", "quality", "recommend"),
    "organization": ("storage", "organize", "clutter", "drawer", "shelf", "space"),
    "campinggear": ("lightweight", "pack", "setup", "recommend", "carry", "storage"),
    "edc": ("looking for", "recommend", "organizer", "carry", "keys", "wallet"),
    "shutupandtakemymoney": ("want", "where can I buy", "need", "take my money"),
}
REDDIT_INTENT_QUERY_BATCHES = {
    "edc": ("recommend", "organizer"),
    "shutupandtakemymoney": ("want", "need"),
    "onebag": ("lightweight", "bulky"),
    "buyitforlife": ("durable", "replacement"),
    "campinggear": ("recommend", "lightweight"),
    "organization": ("organize", "storage"),
}


def _read_env_file() -> dict[str, str]:
    """Read simple KEY=VALUE entries without exposing values."""
    values: dict[str, str] = {}
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _config_value(name: str) -> str:
    return os.getenv(name, _read_env_file().get(name, "")).strip()


def is_etsy_configured() -> bool:
    """Return True only when both required Etsy credentials are configured."""
    api_key = _config_value("ETSY_API_KEY")
    shared_secret = _config_value("ETSY_SHARED_SECRET")
    return api_key not in ETSY_PLACEHOLDERS and shared_secret not in ETSY_PLACEHOLDERS


AI_MODE = (_config_value("AI_MODE") or "mock").casefold()
OPENAI_API_KEY = _config_value("OPENAI_API_KEY")
OPENAI_TRIAGE_MODEL = _config_value("OPENAI_TRIAGE_MODEL") or "gpt-5.4-nano"
OPENAI_KEY_PLACEHOLDERS = {"", "PASTE_YOUR_OPENAI_API_KEY_HERE", "YOUR_OPENAI_API_KEY"}


def is_openai_configured() -> bool:
    """Return whether a non-placeholder OpenAI API key is configured."""
    return OPENAI_API_KEY not in OPENAI_KEY_PLACEHOLDERS


GEMINI_API_KEY = _config_value("GEMINI_API_KEY")
DEFAULT_GEMINI_TRIAGE_MODEL = "gemini-3.5-flash-lite"
GEMINI_TRIAGE_MODEL = _config_value("GEMINI_TRIAGE_MODEL") or DEFAULT_GEMINI_TRIAGE_MODEL
GEMINI_KEY_PLACEHOLDERS = {"", "PASTE_YOUR_GEMINI_API_KEY_HERE", "YOUR_GEMINI_API_KEY"}


def is_gemini_configured() -> bool:
    """Return whether a non-placeholder Gemini API key is configured."""
    return GEMINI_API_KEY not in GEMINI_KEY_PLACEHOLDERS


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(_config_value(name) or default))
    except ValueError:
        return default


MAX_DAILY_TRIAGE_CALLS = _positive_int("MAX_DAILY_TRIAGE_CALLS", 30)
