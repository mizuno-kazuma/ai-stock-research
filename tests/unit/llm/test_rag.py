"""T-LLM-09: ハイブリッド RAG（チャンク分割・埋め込み・RRF・PIT）。"""

from __future__ import annotations

from datetime import date, datetime

from packages.core.llm.rag import (
    chunk_document_text,
    detect_section,
    index_document,
    retrieve,
)
from packages.core.llm.router import LLMRouter, _extract_embedding
from packages.core.storage.vector_store import InMemoryVectorStore
from services.agent.jobs.researcher import researcher
from tests.fakes import FakeStateRepo, FakeVectorStore, FakeWarehouse


def _hash_embed(text: str) -> list[float]:
    """決定論的な偽ベクトル。同じ語が近い方向を向く。"""
    vocab = ["リスク", "為替", "のれん", "減損", "売上", "guidance"]
    vec = [0.0] * len(vocab)
    for i, word in enumerate(vocab):
        vec[i] = float(text.count(word))
    if sum(vec) == 0:
        vec[0] = 0.01
    return vec


def test_chunk_document_keeps_table_together() -> None:
    text = (
        "## 事業等のリスク\n\n"
        "為替変動により海外売上高が影響を受ける。\n\n"
        "| 項目 | 金額 |\n| --- | --- |\n| 売上 | 100 |\n| 利益 | 10 |\n\n"
        "これは表の後の段落です。" + ("あ" * 80)
    )
    chunks = chunk_document_text(text, max_tokens=40, overlap_tokens=5)
    assert chunks
    table_chunks = [c for _, c in chunks if "|" in c]
    assert table_chunks
    assert all("売上" in c and "利益" in c for c in table_chunks)


def test_detect_section_normalizes_risk_heading() -> None:
    assert detect_section("事業等のリスク\n為替の影響") == "risk_factors"
    assert detect_section("Item 1A. Risk Factors") == "risk_factors"
    assert detect_section("普通の本文だけ") == "other"


def test_index_and_hybrid_retrieve_prefers_vector_match() -> None:
    store = InMemoryVectorStore()
    warehouse = FakeWarehouse()
    warehouse.documents["d1"] = {
        "doc_id": "d1",
        "ticker": "7203",
        "market": "JP",
        "title": "有価証券報告書",
        "doc_type": "annual_report",
        "filed_at": datetime(2026, 6, 30),
    }
    warehouse.doc_text["d1"] = (
        "事業等のリスク。のれん減損の兆候は認められない。"
        "為替変動により海外売上高が影響を受ける可能性がある。"
    )
    n = index_document(
        doc_id="d1",
        text=warehouse.doc_text["d1"],
        market="JP",
        ticker="7203",
        doc_type="annual_report",
        filed_at=datetime(2026, 6, 30),
        embed=_hash_embed,
        vector_store=store,
        embedding_model="test",
    )
    assert n >= 1
    hits = retrieve(
        "のれん減損 リスク",
        ticker="7203",
        market="JP",
        k=4,
        as_of=date(2026, 8, 21),
        embed=_hash_embed,
        vector_store=store,
        keyword_search=warehouse,
    )
    assert hits
    assert any("のれん" in h.text or "リスク" in h.text for h in hits)


def test_retrieve_pit_excludes_future_filings() -> None:
    store = InMemoryVectorStore()
    index_document(
        doc_id="future",
        text="事業等のリスク。のれん減損を認識した。",
        market="JP",
        ticker="7203",
        filed_at=datetime(2026, 9, 1),
        embed=_hash_embed,
        vector_store=store,
    )
    hits = retrieve(
        "のれん減損",
        ticker="7203",
        market="JP",
        k=4,
        as_of=date(2026, 8, 21),
        embed=_hash_embed,
        vector_store=store,
    )
    assert hits == []


def test_retrieve_falls_back_when_embed_fails() -> None:
    warehouse = FakeWarehouse()
    warehouse.documents["d1"] = {
        "doc_id": "d1",
        "ticker": "7203",
        "market": "JP",
        "title": "有価証券報告書 リスク情報",
        "filed_at": datetime(2026, 6, 30),
    }
    warehouse.doc_text["d1"] = "為替変動により海外売上高が影響を受ける可能性がある。" * 2

    def boom(_text: str) -> list[float]:
        raise RuntimeError("embed down")

    hits = retrieve(
        "為替 リスク",
        ticker="7203",
        market="JP",
        k=4,
        as_of=date(2026, 8, 21),
        embed=boom,
        vector_store=InMemoryVectorStore(),
        keyword_search=warehouse,
    )
    assert hits
    assert "為替" in hits[0].text


def test_router_embed_uses_injected_fn_not_model_name() -> None:
    def fake_embed(*, model: str, input: str, **_kwargs: object) -> dict:
        assert model.startswith("gemini/") or "embedding" in model
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    router = LLMRouter(embedding_fn=fake_embed)
    vec = router.embed("テスト")
    assert vec == [0.1, 0.2, 0.3]


def test_researcher_indexes_document_text() -> None:
    warehouse = FakeWarehouse()
    warehouse.documents["edinet:1"] = {
        "doc_id": "edinet:1",
        "ticker": "7203",
        "market": "JP",
        "title": "有価証券報告書 リスク情報",
        "doc_type": "annual_report",
        "filed_at": datetime(2026, 8, 10),
    }
    warehouse.doc_text["edinet:1"] = "事業等のリスク。為替変動により海外売上高が影響を受ける。" * 3
    store = FakeVectorStore()
    result = researcher(
        "JP",
        date(2026, 8, 21),
        state=FakeStateRepo(),
        warehouse=warehouse,
        tickers=["7203"],
        vector_store=store,
        embed=_hash_embed,
    )
    assert result.metrics["n_chunks"] >= 1
    assert store.chunks


def test_extract_embedding_handles_gemini_shape() -> None:
    assert _extract_embedding({"embedding": {"values": [1.0, 2.0]}}) == [1.0, 2.0]
    assert _extract_embedding({"data": [{"embedding": [3.0]}]}) == [3.0]
