"""銘柄詳細の開示一覧は JP の 4 桁と J-Quants 5 桁を同一銘柄として返す。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_stock_documents_accepts_jquants_padded_ticker(client: TestClient) -> None:
    four = client.get("/api/v1/stocks/JP/7203/documents")
    five = client.get("/api/v1/stocks/JP/72030/documents")
    assert four.status_code == 200
    assert five.status_code == 200
    ids4 = {row["doc_id"] for row in four.json()["data"]["items"]}
    ids5 = {row["doc_id"] for row in five.json()["data"]["items"]}
    assert ids4
    assert ids4 == ids5
