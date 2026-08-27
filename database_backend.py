"""Database backend selection for local and future cloud runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping, MutableMapping
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "product_picker.db"


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    database_url: str = field(repr=False)
    sqlite_path: Path | None = None


def get_database_settings(database_url: str | None = None) -> DatabaseSettings:
    """Resolve DATABASE_URL without logging credentials or changing databases."""
    raw = (database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
    if not raw:
        return DatabaseSettings("sqlite", "", DEFAULT_SQLITE_PATH)
    parsed = urlparse(raw)
    if parsed.scheme in {"postgres", "postgresql"}:
        return DatabaseSettings("postgresql", raw, None)
    if parsed.scheme == "sqlite":
        path_text = unquote(parsed.path)
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{path_text}"
        if os.name == "nt" and path_text.startswith("/") and len(path_text) > 2 and path_text[2] == ":":
            path_text = path_text[1:]
        path = Path(path_text)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return DatabaseSettings("sqlite", raw, path.resolve())
    raise ValueError("DATABASE_URL must use sqlite://, postgres://, or postgresql://")


def configure_database_environment(
    secrets: Mapping[str, object] | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> DatabaseSettings:
    """Resolve env first, then a Streamlit-compatible secrets mapping.

    This must run before importing ``db`` because that module intentionally
    selects one backend for the process lifetime.
    """
    environment = environ if environ is not None else os.environ
    raw = str(environment.get("DATABASE_URL", "") or "").strip()
    if not raw and secrets is not None:
        try:
            secret_value = secrets.get("DATABASE_URL", "")
        except (FileNotFoundError, KeyError, AttributeError):
            secret_value = ""
        raw = str(secret_value or "").strip()
        if raw:
            environment["DATABASE_URL"] = raw
    return get_database_settings(raw)


def require_postgres_url(value: str | None = None) -> str:
    """Return a PostgreSQL URL for an explicitly authorized future migration."""
    raw = (value if value is not None else os.getenv("POSTGRES_DATABASE_URL", "")).strip()
    if urlparse(raw).scheme not in {"postgres", "postgresql"}:
        raise ValueError("POSTGRES_DATABASE_URL is not configured")
    return raw
