from __future__ import annotations

from contextlib import contextmanager

import db
import postgres_backend
from dashboard_data import load_dashboard_snapshot


def test_pool_configures_health_check_and_bounded_idle(monkeypatch):
    import psycopg_pool

    captured = {}

    class Pool:
        check_connection = object()

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", Pool)
    postgres_backend._create_pool("postgresql://example.invalid/db")

    assert captured["check"] is Pool.check_connection
    assert captured["max_idle"] == postgres_backend.POOL_MAX_IDLE_SECONDS
    assert captured["reconnect_timeout"] == postgres_backend.POOL_RECONNECT_TIMEOUT_SECONDS


def test_closed_pool_is_replaced(monkeypatch):
    database_url = "postgresql://example.invalid/closed"
    closed_pool = type("ClosedPool", (), {"closed": True})()
    replacement = type("OpenPool", (), {"closed": False})()
    postgres_backend._POOLS[database_url] = closed_pool
    monkeypatch.setattr(postgres_backend, "_create_pool", lambda _url: replacement)

    assert postgres_backend._pool(database_url) is replacement
    assert postgres_backend._POOLS[database_url] is replacement


class _ConnectionContext:
    def __init__(self, connection, exits):
        self.connection = connection
        self.exits = exits

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, _exc, _tb):
        self.exits.append(exc_type)
        return False


class _Pool:
    closed = False

    def __init__(self):
        self.borrowed = []
        self.exits = []

    def connection(self):
        connection = type("RawConnection", (), {})()
        self.borrowed.append(connection)
        return _ConnectionContext(connection, self.exits)


def test_sequential_requests_borrow_and_release_connections(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(postgres_backend, "_pool", lambda _url: pool)

    with postgres_backend.postgres_connection("postgresql://example.invalid/db") as first:
        assert first.connection is pool.borrowed[0]
    with postgres_backend.postgres_connection("postgresql://example.invalid/db") as second:
        assert second.connection is pool.borrowed[1]

    assert first.connection is not second.connection
    assert pool.exits == [None, None]


def test_exception_cleanup_does_not_poison_next_request(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(postgres_backend, "_pool", lambda _url: pool)

    try:
        with postgres_backend.postgres_connection("postgresql://example.invalid/db"):
            raise RuntimeError("simulated query failure")
    except RuntimeError:
        pass

    with postgres_backend.postgres_connection("postgresql://example.invalid/db") as recovered:
        assert recovered.connection is pool.borrowed[1]

    assert pool.exits == [RuntimeError, None]


def test_statement_timeout_is_transaction_local_and_bounded(monkeypatch):
    calls = []

    class RawConnection:
        def execute(self, sql, params=()):
            calls.append((sql, params))

    pool = type(
        "Pool", (),
        {"connection": lambda self: _ConnectionContext(RawConnection(), [])},
    )()
    monkeypatch.setattr(postgres_backend, "_pool", lambda _url: pool)

    with postgres_backend.postgres_connection(
        "postgresql://example.invalid/db", statement_timeout_ms=30_000,
    ):
        pass

    assert calls == [
        ("SELECT set_config('statement_timeout', %s, true)", ("30000",)),
    ]


def test_repeated_dashboard_snapshot_reads_do_not_mutate_sqlite():
    with db._connect() as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in (
                "products", "product_families", "product_directions",
                "daily_picks_items", "user_voice_items",
            )
        }

    first = load_dashboard_snapshot()
    second = load_dashboard_snapshot()

    with db._connect() as connection:
        after = {
            table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in before
        }

    assert len(first.products) == len(second.products)
    assert after == before
