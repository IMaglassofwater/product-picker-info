from dashboard_data import page_records


def test_page_records_defaults_to_fifty():
    products = list(range(652))
    assert page_records(products) == list(range(50))
    assert page_records(products, 14) == [650, 651]
