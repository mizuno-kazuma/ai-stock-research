"""機能縮退・レート制限・Critic 機械検証。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from packages.core.connectors.rate_limit import InMemoryRateLimitStore, TokenBucket
from packages.core.interfaces.storage import RateLimitState
from packages.core.llm.cost_guard import CostGuard
from packages.core.llm.errors import InvariantViolationError
from packages.core.llm.schemas import Citation
from services.agent.jobs.critic import mechanical_checks
from services.agent.jobs.strategist import build_recommendation
from services.agent.pipeline import run_pipeline
from tests.fakes import FakeStateRepo, FakeWarehouse


def test_token_bucket_waits_when_empty() -> None:
    slept = []
    now = datetime(2026, 8, 24, 0, 0, 0)

    def fake_now():
        return now

    bucket = TokenBucket(
        "jquants",
        rate_per_min=5,
        burst=1,
        store=InMemoryRateLimitStore(),
        sleep=lambda s: slept.append(s),
        now=fake_now,
    )
    waited1 = bucket.acquire()
    waited2 = bucket.acquire()
    assert waited1 == 0.0
    assert waited2 > 0.0
    assert slept


def test_token_bucket_persists_across_instances() -> None:
    store = InMemoryRateLimitStore()
    t0 = datetime(2026, 8, 24, 12, 0, 0)
    b1 = TokenBucket("x", rate_per_min=1, burst=1, store=store, sleep=lambda s: None, now=lambda: t0)
    b1.acquire()
    b2 = TokenBucket("x", rate_per_min=1, burst=1, store=store, sleep=lambda s: None, now=lambda: t0)
    # 同じ瞬間に再生成してもトークンは空のまま。
    assert b2.tokens_available() < 1.0


def _ok_prices_step(market: str, as_of: date) -> dict:
    return {"rows": 10}


def _fail(*a, **k):
    raise RuntimeError("source down")


def test_pipeline_degrades_when_optional_source_fails() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    warehouse.scores = _score_frame(as_of)
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    warehouse.documents["quant:scores_daily"] = {
        "doc_id": "quant:scores_daily",
        "filed_at": datetime(2026, 8, 20),
        "ticker": "7203",
    }
    steps = {
        "prices": _ok_prices_step,
        "tdnet": _fail,
        "documents": _fail,
        "macro": _fail,
        "financials": _fail,
        "prices_live": _fail,
    }
    result = run_pipeline(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        collector_steps=steps,
        scores=warehouse.scores,
    )
    assert result.status == "partial"
    assert result.jobs["collector"].status == "partial"
    assert len(warehouse.recs) > 0


def test_pipeline_fails_when_prices_unavailable() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    result = run_pipeline(
        "JP",
        date(2026, 8, 21),
        state=state,
        warehouse=warehouse,
        collector_steps={"prices": _fail},
    )
    assert result.status == "failed"
    assert result.jobs["collector"].status == "failed"


def test_pipeline_continues_when_llm_capped() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    warehouse.scores = _score_frame(as_of)
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    warehouse.documents["quant:scores_daily"] = {
        "doc_id": "quant:scores_daily",
        "filed_at": datetime(2026, 8, 20),
        "ticker": "7203",
    }
    guard = CostGuard(daily_cap=1.0, monthly_cap=10.0, call_log=state, budget=state, alerts=state)
    guard.force_cap_exceeded()
    from packages.core.llm.router import LLMRouter

    router = LLMRouter(cost_guard=guard, completion_fn=lambda **k: {"content": "{}"})
    result = run_pipeline(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        router=router,
        collector_steps={"prices": _ok_prices_step},
        scores=warehouse.scores,
    )
    assert result.status == "partial"
    recs = warehouse.get_recommendations(as_of=as_of)
    assert len(recs) > 0
    assert all(r.get("qual_score") is None or pd.isna(r.get("qual_score")) for r in recs)
    assert result.metrics.get("llm_capped") or any(
        j.metrics.get("llm_capped") for j in result.jobs.values()
    )


def test_recommendation_rejects_empty_bear_case() -> None:
    warehouse = FakeWarehouse()
    with pytest.raises(InvariantViolationError, match="bear_case"):
        warehouse.insert_recommendation(
            {
                "rec_id": "r1",
                "bear_case_ja": "",
                "expected_ret_lo": 0.0,
                "expected_ret_hi": 0.1,
                "citations": [{"doc_id": "d", "quote": "十分な長さの引用ですよ"}],
            }
        )


def test_recommendation_requires_confidence_interval() -> None:
    warehouse = FakeWarehouse()
    with pytest.raises(InvariantViolationError, match="confidence_interval"):
        warehouse.insert_recommendation(
            {
                "rec_id": "r1",
                "bear_case_ja": "具体的な弱気論拠を20文字以上で書く必要があります",
                "expected_ret_lo": None,
                "expected_ret_hi": 0.1,
                "citations": [{"doc_id": "d", "quote": "十分な長さの引用ですよ"}],
            }
        )


def test_conviction_forced_to_low_when_few_samples() -> None:
    row = pd.Series(
        {
            "ticker": "7203",
            "quant_score": 80,
            "total_score": 80,
            "ml_pred_h20": 0.04,
            "ml_pred_h20_lo": -0.01,
            "ml_pred_h20_hi": 0.08,
            "qual_score": None,
        }
    )
    rec = build_recommendation(
        row,
        as_of=date(2026, 8, 21),
        market="JP",
        n_prior_samples=8,
        hit_rate_prior=None,
        thesis=None,
        memory_ids=[],
        source_doc_ids=["quant:scores_daily"],
        data_freshness=[],
    )
    assert rec["conviction"] == "low"


def test_critic_rejects_boilerplate_bear_case() -> None:
    rec = {
        "bear_case_ja": "市場環境の悪化や予想外の事態により、株価が下落する可能性があります。",
        "expected_ret_lo": -0.05,
        "expected_ret_hi": 0.08,
        "citations": [],
        "conviction": "low",
        "n_prior_samples": 30,
        "thesis_ja": "定量的に割安",
        "as_of": date(2026, 8, 21),
        "source_doc_ids": [],
    }
    issues = mechanical_checks(rec)
    assert any(i.code == "boilerplate_bear_case" for i in issues)


def test_jobs_depend_on_job_runs() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    warehouse.scores = _score_frame(as_of)
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    run_pipeline(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        collector_steps={"prices": _ok_prices_step},
        scores=warehouse.scores,
    )
    names = {r.job_name for r in state._runs.values()}
    assert {"collector", "analyst", "researcher", "strategist", "critic", "evaluator"} <= names
    coll = state.latest_job_run(job_name="collector", market="JP")
    assert coll is not None
    assert coll.status in {"success", "partial"}


def _score_frame(as_of: date) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "as_of": as_of,
                "quant_score": 80.0,
                "quant_percentile": 0.9,
                "total_score": 80.0,
                "ml_pred_h20": 0.04,
                "ml_pred_h20_lo": -0.01,
                "ml_pred_h20_hi": 0.09,
                "qual_score": None,
                "qual_confidence": None,
                "value_z": 1.2,
                "momentum_z": 0.4,
                "sector_code": "S01",
                "n_missing": 0,
                "adv_20d": 5e8,
                "market_cap": 5e12,
            }
        ]
    )
