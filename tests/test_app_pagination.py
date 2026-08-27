from dashboard_data import page_records


def test_page_records_defaults_to_twenty():
    products = list(range(652))
    assert page_records(products) == list(range(20))
    assert page_records(products, 33) == list(range(640, 652))
