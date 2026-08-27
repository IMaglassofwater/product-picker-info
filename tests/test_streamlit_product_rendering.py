from pathlib import Path

import db
from models import Product
from streamlit.testing.v1 import AppTest


APP = Path(__file__).parents[1] / "app.py"


def _product(index: int) -> Product:
    return Product(
        project_id=f"render-{index}",
        source_platform="product_hunt" if index == 24 else "amazon",
        url=f"https://example.test/render/{index}",
        title=f"Rendered Product {index}",
        description="A real product description for Streamlit rendering.",
        category="software" if index == 24 else "home",
        image_url=f"https://example.test/render/{index}.jpg",
        raw_data={},
    )


def test_streamlit_renders_only_active_paginated_product_page(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "render.db")
    assert db.init_db()
    assert db.save_products([_product(index) for index in range(25)]) == (25, 0)
    with db._connect() as connection:
        connection.execute(
            """UPDATE products SET record_role='software', opportunity_type='software'
               WHERE project_id='render-24'"""
        )
        connection.execute(
            "UPDATE products SET filter_status='rejected' WHERE project_id='render-23'"
        )

    app = AppTest.from_file(str(APP), default_timeout=20).run(timeout=20)
    assert not app.exception
    assert next(metric.value for metric in app.metric if metric.label == "Page Records") == "20"
    assert "Rendered Products: 20" in [caption.value for caption in app.caption]
    rendered_titles = [heading.value for heading in app.subheader]
    assert {"Rendered Product 24", "Rendered Product 23", "Rendered Product 22"}.issubset(rendered_titles)

    app.radio[0].set_value("💻 软件机会 / Software").run(timeout=20)
    assert not app.exception
    assert "Rendered Product 24" in [heading.value for heading in app.subheader]
    assert "Rendered Products: 1" in [caption.value for caption in app.caption]

    app.radio[0].set_value("🗑 淘汰库 / Rejected").run(timeout=20)
    assert not app.exception
    assert "Rendered Product 23" in [heading.value for heading in app.subheader]
    assert "Rendered Products: 1" in [caption.value for caption in app.caption]
