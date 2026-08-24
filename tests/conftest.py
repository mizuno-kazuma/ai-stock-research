from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """テスト中に本物の LLM API を呼ばない（T-LLM-08）。"""

    def fail(*a, **kw):
        raise RuntimeError("テスト中に実際のLLM APIを呼び出そうとしました")

    monkeypatch.setattr("packages.core.llm.router._default_completion", lambda: fail)
    try:
        import litellm

        if hasattr(litellm, "completion"):
            monkeypatch.setattr(litellm, "completion", fail)
        if hasattr(litellm, "acompletion"):
            monkeypatch.setattr(litellm, "acompletion", fail)
    except ImportError:
        pass


# API 層のフィクスチャは API 担当の実装が揃っているときだけ有効にする。
try:
    from fastapi.testclient import TestClient

    from packages.core.storage import DuckDBRepo, SQLiteRepo
    from services.api.main import create_app
    from services.api.seed import load_sample, seed_all

    @pytest.fixture()
    def seeded_repos():
        duck = DuckDBRepo.in_memory()
        state = SQLiteRepo.in_memory()
        payload = load_sample()
        seed_all(duck, state, payload)
        yield duck, state, payload
        duck.close()
        state.close()

    @pytest.fixture()
    def client(seeded_repos):
        duck, state, payload = seeded_repos
        application = create_app(duck=duck, sqlite=state, payload=payload)
        with TestClient(application) as test_client:
            yield test_client

except ImportError:
    pass
