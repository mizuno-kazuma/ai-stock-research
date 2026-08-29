"""LLM スキーマ・引用・コストキャップ・redact・プロンプト。"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from packages.core.config.models import get_models_config
from packages.core.interfaces.storage import LlmCall
from packages.core.llm.cache import LLMCache
from packages.core.llm.citations import CitationVerdict, verify_citation
from packages.core.llm.cost_guard import CostGuard
from packages.core.llm.errors import (
    CostCapExceeded,
    KillSwitchActive,
    SensitiveDataInPromptError,
)
from packages.core.llm.prompts import render_prompt
from packages.core.llm.redact import assert_no_sensitive_data, redact_portfolio
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import Citation, DocSummaryOutput
from tests.fakes import FakeStateRepo, FakeWarehouse


def test_doc_summary_rejects_empty_citations() -> None:
    with pytest.raises(ValidationError):
        DocSummaryOutput(
            summary_ja="あ" * 60,
            key_points=["a"],
            risk_factors=[],
            guidance_tone="neutral",
            guidance_evidence="根拠となる原文の引用です",
            qualitative_score=0.0,
            citations=[],
        )


def test_citation_verification_detects_fabricated_quote() -> None:
    docs = {"d1": {"doc_id": "d1"}}
    texts = {"d1": "当社の営業利益は前年同期比12.4%増加しました。"}

    def get_doc(doc_id: str):
        return docs.get(doc_id)

    def get_text(doc_id: str, *, page=None):
        return texts.get(doc_id)

    ok = verify_citation(
        Citation(doc_id="d1", page=1, quote="営業利益は前年同期比12.4%増加"),
        get_document=get_doc,
        get_document_text=get_text,
    )
    assert ok == CitationVerdict.VERIFIED
    ng = verify_citation(
        Citation(doc_id="d1", page=1, quote="来期は営業利益が倍増する見込みです"),
        get_document=get_doc,
        get_document_text=get_text,
    )
    assert ng == CitationVerdict.QUOTE_NOT_FOUND


def test_citation_verification_tolerates_normalization() -> None:
    docs = {"d1": {"doc_id": "d1"}}
    texts = {"d1": "営業利益は１２．４％増加"}

    ok = verify_citation(
        Citation(doc_id="d1", page=1, quote="営業利益は12.4%増加"),
        get_document=lambda i: docs.get(i),
        get_document_text=lambda i, page=None: texts.get(i),
    )
    assert ok in (CitationVerdict.VERIFIED, CitationVerdict.VERIFIED_FUZZY)


def test_router_reads_models_yaml_not_hardcoded() -> None:
    cfg = get_models_config()
    router = LLMRouter(config=cfg, completion_fn=lambda **k: {"content": "{}", "input_tokens": 1, "output_tokens": 1})
    chain = cfg.resolve_chain("default")
    assert chain[0].litellm_model.startswith(("anthropic/", "gemini/", "openai/"))
    # アプリコードにモデル名を書かせない: router は yaml の識別子を使う。
    from pathlib import Path

    text = Path("packages/core/llm/router.py").read_text(encoding="utf-8")
    assert "claude-sonnet-5" not in text
    assert "gemini-3.7-flash" not in text


def test_router_asks_litellm_to_drop_unsupported_params() -> None:
    seen: dict[str, object] = {}

    def fn(**kwargs):
        seen.update(kwargs)
        return {"content": "{}", "input_tokens": 1, "output_tokens": 1}

    router = LLMRouter(completion_fn=fn)
    router.complete(tier="default", purpose="x", messages=[{"role": "user", "content": "hi"}])
    assert seen.get("drop_params") is True


def test_cost_guard_raises_and_records_kill() -> None:
    state = FakeStateRepo()
    guard = CostGuard(
        daily_cap=0.01,
        monthly_cap=1.0,
        call_log=state,
        budget=state,
        alerts=state,
    )
    with pytest.raises(CostCapExceeded):
        guard.raise_if_blocked(1.0)
    guard.record(
        LlmCall(
            call_id="c1",
            tier="bulk",
            model_id="x",
            purpose="t",
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.05,
            status="success",
            called_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
    )
    assert guard.is_killed()
    assert any(a["category"] == "cost" for a in state.alerts)


def test_kill_switch_blocks_complete() -> None:
    guard = CostGuard(daily_cap=1.0, monthly_cap=10.0, kill_switch=True)
    router = LLMRouter(
        cost_guard=guard,
        completion_fn=lambda **k: (_ for _ in ()).throw(RuntimeError("should not call")),
    )
    with pytest.raises(KillSwitchActive):
        router.complete(tier="bulk", purpose="x", messages=[{"role": "user", "content": "hi"}])


def test_cache_hit_skips_completion() -> None:
    calls = {"n": 0}

    def fn(**kwargs):
        calls["n"] += 1
        return {"content": '{"ok": true}', "input_tokens": 3, "output_tokens": 2}

    cache = LLMCache()
    router = LLMRouter(cache=cache, completion_fn=fn)
    router.complete(
        tier="bulk",
        purpose="x",
        messages=[{"role": "user", "content": "hello"}],
        prompt_name="t",
        prompt_body="hello",
    )
    router.complete(
        tier="bulk",
        purpose="x",
        messages=[{"role": "user", "content": "hello"}],
        prompt_name="t",
        prompt_body="hello",
    )
    assert calls["n"] == 1
    assert cache.hits >= 1


@pytest.mark.parametrize(
    "payload",
    [
        {"positions": [{"ticker": "7203", "quantity": 100}]},
        {"portfolio": {"total_assets": 5000000}},
        {"trade": {"avg_cost": 3125.0}},
        {"nested": {"deep": {"market_value": 312500}}},
    ],
)
def test_sensitive_data_blocked_from_prompt(payload: dict) -> None:
    with pytest.raises(SensitiveDataInPromptError):
        assert_no_sensitive_data(payload)


def test_redacted_portfolio_has_only_ratios() -> None:
    out = redact_portfolio(
        [{"ticker": "7203", "market_value": 100, "unrealized_pnl_pct": 3.2, "quantity": 10}]
    )
    for item in out:
        assert set(item.keys()) <= {"ticker", "weight_pct", "unrealized_pnl_pct"}


def test_thesis_prompt_contains_required_instructions() -> None:
    rendered = render_prompt(
        "thesis.jinja",
        ticker="7203",
        company_name="トヨタ",
        market="JP",
        sector_name="輸送用機器",
        quant_score=72,
        sector_rank=3,
        sector_count=40,
        value_z=1.1,
        momentum_z=0.4,
        quality_z=0.8,
        growth_z=0.2,
        lowvol_z=0.1,
        revision_z=1.0,
        horizon="H20",
        ml_pred=0.03,
        ml_pred_lo=-0.02,
        ml_pred_hi=0.07,
        per=12,
        pbr=1.1,
        roic=0.15,
        realized_vol=0.22,
        reason_codes=["VAL_CHEAP_VS_SECTOR", "REV_UP_GUIDANCE"],
        retrieved_chunks=[],
        hit_rate_prior=0.55,
        n_prior_samples=40,
        avg_excess_return=0.01,
        agent_memory=[],
    )
    assert "却下すべき理由を3つ挙げる" in rendered
    assert "「買い」「売り」という語を使わない" in rendered
