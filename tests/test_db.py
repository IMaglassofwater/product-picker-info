"""Tests for the SQLite persistence layer."""

import sqlite3

import db
from models import Product


def _product() -> Product:
    return Product(
        project_id="project-1",
        source_platform="Example",
        url="https://example.com/products/1",
        title="Example product",
        description="A test product",
        category="Test",
        image_url="https://example.com/images/1.jpg",
        raw_data={"source_id": 1},
    )


def test_init_db_creates_database_and_tables(tmp_path, monkeypatch):
    database_path = tmp_path / "data" / "product_picker.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)

    assert db.init_db() is True
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"products", "processed_projects"}.issubset(tables)


def test_create_product(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product()

    assert db.create_product(product) is True
    assert db.get_product_by_url(product.url) == product


def test_duplicate_url_is_not_inserted_twice(tmp_path, monkeypatch):
    database_path = tmp_path / "product_picker.db"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    product = _product()

    assert db.create_product(product) is True
    assert db.create_product(product) is False

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM products WHERE url = ?", (product.url,)
        ).fetchone()[0]
    assert count == 1


def test_mark_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    url = "https://example.com/products/processed"

    assert db.is_processed(url) is False
    assert db.mark_processed(url) is True
    assert db.is_processed(url) is True
