from pathlib import Path

import pytest

from phase11d_reset import (
    DISCOVERY_TABLES,
    Phase11DSafetyError,
    RESET_CONFIRMATION,
    _favorite_ids,
    require_confirmation,
    require_database_url,
    write_json,
)


def test_reset_requires_exact_explicit_confirmation():
    require_confirmation(RESET_CONFIRMATION)
    for value in ("", "reset_non_favorites", "RESET", " RESET_NON_FAVORITES"):
        with pytest.raises(Phase11DSafetyError):
            require_confirmation(value)


def test_database_url_is_required_but_never_in_error():
    with pytest.raises(Phase11DSafetyError) as error:
        require_database_url({})
    assert "DATABASE_URL" in str(error.value)
    assert "password" not in str(error.value).casefold()
    database_url = "postgresql://example.invalid/database"
    assert require_database_url({"DATABASE_URL": database_url}) == database_url


def test_favorite_id_set_is_strict_and_stable():
    rows = [{"entity_id": "12"}, {"entity_id": "3"}]
    assert _favorite_ids(rows) == [3, 12]
    with pytest.raises(Phase11DSafetyError):
        _favorite_ids([{"entity_id": "not-a-product-id"}])
    with pytest.raises(Phase11DSafetyError):
        _favorite_ids([{"entity_id": "3"}, {"entity_id": "3"}])


def test_report_writer_serializes_without_environment_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    target = tmp_path / "report.json"
    write_json(target, {"products": 12, "status": "safe"})
    content = target.read_text(encoding="utf-8")
    assert '"products": 12' in content
    assert "example.invalid" not in content
    assert "DATABASE_URL" not in content


def test_phase11d_workflow_is_manual_only_and_safely_bounded():
    workflow = Path(".github/workflows/phase11d-production-reset.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "RESET_NON_FAVORITES" in workflow
    assert "DATABASE_URL: ${{ secrets.DATABASE_URL }}" in workflow
    assert "GEMINI_API_KEY: \"\"" in workflow
    assert "WXPUSHER_APP_TOKEN: \"\"" in workflow
    assert "retention-days: 30" in workflow


def test_reset_module_never_drops_tables_or_schema():
    source = Path("phase11d_reset.py").read_text(encoding="utf-8").upper()
    assert "DROP TABLE" not in source
    assert "DROP SCHEMA" not in source
    assert "CREATE SCHEMA" in source
    assert "products" in DISCOVERY_TABLES
