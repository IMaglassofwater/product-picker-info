"""Network-free regression tests for PostgreSQL batch persistence."""

from contextlib import contextmanager
from types import SimpleNamespace

import db
import main
from candidate_pool import MicroInnovationCandidate
from models import Product
from postgres_backend import PRODUCT_BATCH_COLUMNS, persist_product_batch
from tests.test_pipeline import _MockScraper, _product


class _Cursor:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _BatchConnection:
    def __init__(self, *, fail_on_snapshots=False):
        self.products = {
            "https://example.com/existing": {"id": 1, "title": "Old"},
        }
        self.snapshots = {1: {"rank": 10}}
        self.next_id = 2
        self.queries = []
        self.fail_on_snapshots = fail_on_snapshots

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if normalized.startswith("SELECT id, url FROM products"):
            urls = params[0]
            return _Cursor(
                ({"id": self.products[url]["id"], "url": url}
                 for url in urls if url in self.products)
            )
        if normalized.startswith("INSERT INTO products"):
            returned = []
            width = len(PRODUCT_BATCH_COLUMNS)
            for offset in range(0, len(params), width):
                values = params[offset:offset + width]
                item = dict(zip(PRODUCT_BATCH_COLUMNS, values))
                url = item["url"]
                if url not in self.products:
                    self.products[url] = {"id": self.next_id}
                    self.next_id += 1
                self.products[url].update(item)
                returned.append({"id": self.products[url]["id"], "url": url})
            return _Cursor(returned, len(returned))
        if normalized.startswith("SELECT DISTINCT ON (product_id)"):
            return _Cursor(
                ({"product_id": product_id, "metric_data": self.snapshots[product_id]}
                 for product_id in params[0] if product_id in self.snapshots)
            )
        if normalized.startswith("INSERT INTO product_metric_snapshots"):
            if self.fail_on_snapshots:
                raise RuntimeError("synthetic snapshot failure")
            for offset in range(0, len(params), 4):
                product_id, _source, _captured, metric_json = params[offset:offset + 4]
                import json
                self.snapshots[product_id] = json.loads(metric_json)
            return _Cursor(rowcount=len(params) // 4)
        raise AssertionError(f"Unexpected SQL: {normalized}")


def _row(url, title, metrics):
    values = [""] * len(PRODUCT_BATCH_COLUMNS)
    mapped = dict(zip(PRODUCT_BATCH_COLUMNS, values))
    mapped.update({
        "project_id": title, "source_platform": "amazon", "url": url,
        "title": title, "description": title, "category": "home",
        "image_url": "", "raw_data": "{}", "first_seen_at": "2026-01-01",
        "last_seen_at": "2026-01-01", "updated_at": "2026-01-01",
    })
    return {
        "url": url,
        "values": tuple(mapped[column] for column in PRODUCT_BATCH_COLUMNS),
        "source_platform": "amazon",
        "captured_at": "2026-01-01",
        "metrics": metrics,
    }


def test_product_upsert_ids_duplicates_and_snapshots_are_batched():
    connection = _BatchConnection()
    rows = [
        _row("https://example.com/existing", "Updated", {"rank": 8}),
        _row("https://example.com/new", "New first", {"rank": 5}),
        _row("https://example.com/new", "New final", {"rank": 4}),
    ]

    saved, duplicates, snapshots, _duration = persist_product_batch(connection, rows)

    assert (saved, duplicates, snapshots) == (1, 2, 2)
    assert connection.products["https://example.com/existing"]["title"] == "Updated"
    assert connection.products["https://example.com/new"]["title"] == "New final"
    assert connection.snapshots == {1: {"rank": 8}, 2: {"rank": 4}}
    assert len(connection.queries) == 4

    connection.queries.clear()
    saved, duplicates, snapshots, _duration = persist_product_batch(connection, rows)
    assert (saved, duplicates, snapshots) == (0, 3, 0)
    assert len(connection.queries) == 3


def test_non_metric_source_needs_only_lookup_and_upsert_queries():
    connection = _BatchConnection()
    result = persist_product_batch(
        connection, [_row("https://example.com/new", "New", {})],
    )
    assert result[:3] == (1, 0, 0)
    assert len(connection.queries) == 2


def test_failed_postgres_source_rolls_back_and_is_contained(monkeypatch):
    connection = _BatchConnection(fail_on_snapshots=True)
    original_products = dict(connection.products)
    rolled_back = False

    @contextmanager
    def transactional_connection():
        nonlocal rolled_back
        products_before = {key: dict(value) for key, value in connection.products.items()}
        snapshots_before = dict(connection.snapshots)
        try:
            yield connection
        except Exception:
            rolled_back = True
            connection.products = products_before
            connection.snapshots = snapshots_before
            raise

    monkeypatch.setattr(
        db, "DATABASE_SETTINGS",
        SimpleNamespace(backend="postgresql", database_url="postgresql://test"),
    )
    monkeypatch.setattr(db, "_connect", transactional_connection)
    product = Product(
        project_id="new", source_platform="amazon",
        url="https://example.com/new", title="New", description="New",
        category="home", image_url="https://example.com/new.jpg",
        raw_data={"rank": 1},
    )

    assert db.save_products([product], initialize=False) == (0, 0)
    assert rolled_back
    assert connection.products == original_products


def test_postgres_schema_initializes_once_per_database_url(monkeypatch):
    calls = []
    settings = SimpleNamespace(
        backend="postgresql", database_url="postgresql://schema-once",
    )
    monkeypatch.setattr(db, "DATABASE_SETTINGS", settings)
    db._INITIALIZED_POSTGRES_DATABASES.discard(settings.database_url)
    monkeypatch.setattr(
        "postgres_backend.initialize_postgres_schema", calls.append,
    )

    assert db.init_db() and db.init_db()
    assert calls == [settings.database_url]


def test_postgres_candidates_use_one_insert_and_preserve_payload(monkeypatch):
    statements = []

    class CandidateConnection:
        def execute(self, sql, params=()):
            statements.append((" ".join(sql.split()), params))
            return _Cursor(rowcount=2)

    @contextmanager
    def connection_context():
        yield CandidateConnection()

    monkeypatch.setattr(db, "_connect", connection_context)
    candidates = [
        MicroInnovationCandidate(
            candidate_id=f"c{index}", candidate_type="consumer_trend",
            source_platform="amazon", source_url=f"https://example.com/c{index}",
            title=f"Candidate {index}", summary="Summary", candidate_score=80,
            feasibility_score=75, demand_score=0, market_validation_score=70,
            micro_innovation_score=60, reason="Reason", signals=["signal"],
            raw_reference_id=f"p{index}",
        )
        for index in range(2)
    ]

    assert db._save_candidates_postgres_batch(candidates) == (2, 0)
    assert len(statements) == 1
    assert "ON CONFLICT DO NOTHING" in statements[0][0]
    assert '["signal"]' in statements[0][1]


def test_synthetic_source_batch_meets_query_budget():
    connection = _BatchConnection()
    rows = [
        _row(f"https://example.com/item-{index}", f"Item {index}", {"rank": index})
        for index in range(100)
    ]
    assert persist_product_batch(connection, rows)[:3] == (100, 0, 100)
    assert len(connection.queries) == 4


def test_synthetic_full_run_projection_is_below_500_queries():
    source_batches = {
        "product_hunt": (50, False), "kickstarter": (100, True),
        "reddit": (100, False), "amazon": (50, True),
        "yanko_design": (10, False), "indiegogo": (100, True),
    }
    batch_query_count = 0
    for source, (size, has_metrics) in source_batches.items():
        connection = _BatchConnection()
        metrics = {"rank": 1} if has_metrics else {}
        rows = [
            _row(f"https://example.com/{source}/{index}", f"{source}-{index}", metrics)
            for index in range(size)
        ]
        persist_product_batch(connection, rows)
        batch_query_count += len(connection.queries)

    # Baseline source persistence used 1,819 of 2,193 measured queries. Keep
    # every other baseline query in this conservative projection; schema and
    # candidate batching reduce the real count further.
    projected_full_run_queries = 2193 - 1819 + batch_query_count
    assert batch_query_count == 18
    assert projected_full_run_queries == 392
    assert projected_full_run_queries < 500


def test_pipeline_continues_after_one_source_persistence_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "source-isolation.db")
    original_save = db.save_products

    def source_aware_save(products, *args, **kwargs):
        if products and products[0].source_platform == "amazon":
            return 0, 0
        return original_save(products, *args, **kwargs)

    monkeypatch.setattr(db, "save_products", source_aware_save)
    messages = []
    assert main.run_pipeline(
        scrapers=[
            _MockScraper("amazon", [_product("amazon", 1)]),
            _MockScraper("kickstarter", [_product("kickstarter", 2)]),
        ],
        output=messages.append,
    )
    assert "Database persistence failed" in messages
    stored = db.get_all_products()
    assert [product.source_platform for product in stored] == ["kickstarter"]
