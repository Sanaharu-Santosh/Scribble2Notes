from __future__ import annotations

from tests.conftest import upload


def test_scan_returns_typed_blocks(client, page_image):
    response = client.post("/api/scan", files=upload(page_image))
    assert response.status_code == 200

    body = response.json()
    types = {block["type"] for block in body["blocks"]}
    assert {"heading", "paragraph", "table", "figure"} <= types


def test_scan_table_is_a_real_grid(client, page_image):
    """A table has to come back as addressable cells, not a picture of a table —
    that is the whole difference between Mode 2 and a screenshot."""
    body = client.post("/api/scan", files=upload(page_image)).json()
    table_block = next(block for block in body["blocks"] if block["type"] == "table")
    table = table_block["table"]

    assert table["rows"] == 4
    assert table["cols"] == 3
    assert len(table["cells"]) == 12
    assert {(cell["row"], cell["col"]) for cell in table["cells"]} == {
        (row, col) for row in range(4) for col in range(3)
    }


def test_scan_carries_annotations(client, page_image):
    body = client.post("/api/scan", files=upload(page_image)).json()
    kinds = {
        annotation["kind"]
        for block in body["blocks"]
        for annotation in block["annotations"]
    }
    assert {"underline", "highlight"} <= kinds


def test_scan_reading_order_is_a_clean_sequence(client, page_image):
    body = client.post("/api/scan", files=upload(page_image)).json()
    orders = sorted(block["reading_order"] for block in body["blocks"])
    assert orders == list(range(len(orders)))
