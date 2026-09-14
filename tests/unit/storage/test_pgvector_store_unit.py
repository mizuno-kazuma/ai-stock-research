from __future__ import annotations

from packages.core.config.settings import Settings, reset_settings_cache
from packages.core.storage.vector_store import DocChunk, InMemoryVectorStore, get_vector_store


def test_get_vector_store_memory_backend(tmp_path) -> None:
    reset_settings_cache()
    settings = Settings(data_dir=tmp_path, vector_store_backend="memory")
    store = get_vector_store(settings)
    assert isinstance(store, InMemoryVectorStore)
    chunk = DocChunk(
        chunk_id="c1",
        doc_id="d1",
        text="hello",
        embedding=[0.1, 0.2, 0.3],
        market="JP",
    )
    assert store.upsert([chunk]) == 1
    assert store.count() == 1
    hits = store.search([0.1, 0.2, 0.3], k=1)
    assert hits and hits[0].chunk_id == "c1"
