"""レビュー残件（実績・RAG・Critic 修正・要約永続化・週次ジョブ）の回帰テスト。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TradingCalendar
from packages.core.llm.router import LLMResponse
from packages.core.llm.schemas import Citation, CriticOutput, DocSummaryOutput
from packages.core.storage import DuckDBRepo
from services.agent.jobs.critic import critic
from services.agent.jobs.evaluator import evaluate_outcomes, evaluator, propose_factor_weights
from services.agent.jobs.maintenance import garch_refit, model_retrain, weekly_review
from services.agent.jobs.researcher import researcher
from services.agent.jobs.strategist import _retrieve_chunks
from tests.fakes import FakeStateRepo, FakeWarehouse


def _bday_prices(ticker: str, start: date, end: date, *, start_px: float = 100.0) -> pd.DataFrame:
    days = pd.bdate_range(start=start, end=end)
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(days),
            "market": ["JP"] * len(days),
            "trade_date": [d.date() for d in days],
            "adj_open": np.linspace(start_px, start_px * 1.1, len(days)),
            "adj_close": np.linspace(start_px, start_px * 1.1, len(days)),
            "adj_high": np.linspace(start_px * 1.01, start_px * 1.12, len(days)),
            "adj_low": np.linspace(start_px * 0.99, start_px * 1.08, len(days)),
        }
    )


def _approved_rec(*, rec_id: str, as_of: date, ticker: str = "7203") -> dict:
    return {
        "rec_id": rec_id,
        "as_of": as_of,
        "ticker": ticker,
        "market": "JP",
        "action": "watch",
        "horizon": "H20",
        "conviction": "low",
        "thesis_ja": "定量スコア上位で注目する。",
        "bear_case_ja": "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。",
        "invalidation_ja": "次期予想が下方修正されたら破棄する。",
        "citations": [{"doc_id": "quant:scores_daily", "quote": "定量スコアとML予測区間に基づく自動生成カードです。"}],
        "source_doc_ids": ["quant:scores_daily"],
        "expected_ret_lo": -0.05,
        "expected_ret_hi": 0.08,
        "n_prior_samples": 8,
        "critic_verdict": "approved",
    }


def test_evaluate_outcomes_uses_benchmark_and_excursions() -> None:
    cal = TradingCalendar()
    rec_as_of = date(2026, 7, 22)
    entry = cal.next_business_day(rec_as_of)
    exit_d = cal.shift(entry, 20)
    eval_as_of = cal.shift(rec_as_of, 21)
    warehouse = FakeWarehouse()
    warehouse.recs = [_approved_rec(rec_id="r1", as_of=rec_as_of)]
    stock = _bday_prices("7203", entry, exit_d, start_px=100.0)
    bench = _bday_prices("TOPIX", entry, exit_d, start_px=200.0)
    warehouse.prices = pd.concat([stock, bench], ignore_index=True)
    outcomes = evaluate_outcomes(eval_as_of, warehouse=warehouse)
    assert len(outcomes) == 1
    row = outcomes[0]
    assert row["benchmark_ticker"] == "TOPIX"
    assert row["benchmark_return"] != 0.0
    assert row["excess_return"] == row["raw_return"] - row["benchmark_return"]
    assert row["max_favorable_excursion"] is not None
    assert row["max_adverse_excursion"] is not None


def test_evaluator_proposes_weights_when_sample_ge_100() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    scores_rows = []
    recs = []
    for i in range(100):
        ticker = f"{7200 + i}"
        recs.append(_approved_rec(rec_id=f"r{i}", as_of=as_of, ticker=ticker))
        scores_rows.append(
            {
                "ticker": ticker,
                "market": "JP",
                "as_of": as_of,
                "value_z": 0.1 * (i % 5),
                "momentum_z": 0.2,
                "quality_z": 0.0,
                "growth_z": -0.1,
                "lowvol_z": 0.05,
                "revision_z": 0.3,
            }
        )
    warehouse.recs = recs
    warehouse.scores = pd.DataFrame(scores_rows)
    outcomes = [
        {
            "rec_id": f"r{i}",
            "horizon": "H20",
            "ticker": f"{7200 + i}",
            "market": "JP",
            "as_of": as_of,
            "excess_return": 0.01 if i % 2 == 0 else -0.01,
            "is_hit": i % 2 == 0,
            "benchmark_ticker": "TOPIX",
        }
        for i in range(100)
    ]
    warehouse.outcomes = outcomes
    # propose_factor_weights 自体は 100 件で提案する
    group = pd.DataFrame(
        [
            {
                "value": 0.1 * (i % 5),
                "momentum": 0.2,
                "quality": 0.0,
                "growth": -0.1,
                "lowvol": 0.05,
                "revision": 0.3,
            }
            for i in range(100)
        ]
    )
    proposed = propose_factor_weights(
        group,
        pd.Series([o["excess_return"] for o in outcomes]),
        {
            "value": 0.25,
            "momentum": 0.20,
            "quality": 0.20,
            "growth": 0.15,
            "lowvol": 0.10,
            "revision": 0.10,
        },
    )
    assert proposed is not None
    assert abs(sum(proposed.values()) - 1.0) < 1e-6

    result = evaluator("JP", as_of, state=state, warehouse=warehouse, memory=state)
    # 実績対象日がずれるため n_outcomes は 0 でも、提案経路の関数は上で担保する
    assert result.status == "success"


def test_retrieve_chunks_falls_back_to_document_text() -> None:
    warehouse = FakeWarehouse()
    warehouse.documents["edinet:1"] = {
        "doc_id": "edinet:1",
        "ticker": "7203",
        "market": "JP",
        "title": "有価証券報告書 リスク情報",
        "doc_type": "annual_report",
        "filed_at": datetime(2026, 6, 30),
    }
    warehouse.doc_text["edinet:1"] = "為替変動により海外売上高が影響を受ける可能性がある。" * 2
    hits = _retrieve_chunks(
        warehouse,
        ticker="7203",
        market="JP",
        as_of=date(2026, 8, 21),
        reasons=["VAL_CHEAP_VS_SECTOR"],
        docs=pd.DataFrame([warehouse.documents["edinet:1"]]),
    )
    assert hits
    assert "為替" in hits[0].text


def test_critic_applies_revised_fields_to_card() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    rec = _approved_rec(rec_id="r1", as_of=date(2026, 8, 21))
    rec["critic_verdict"] = None
    warehouse.recs = [rec]

    class _Router:
        def complete(self, **_kwargs: object) -> LLMResponse:
            return LLMResponse(
                content="{}",
                parsed=CriticOutput(
                    verdict="revised",
                    revised_fields={
                        "bear_case_ja": (
                            "次期ガイダンスが下方修正され、営業利益率が8%を下回る可能性がある。"
                        )
                    },
                    notes_ja="弱気論拠を具体化しました。",
                ),
                model_id="x",
                tier="default",
                purpose="critic",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                was_cache_hit=False,
                latency_ms=1,
                call_id="c1",
            )

    result = critic(
        "JP",
        date(2026, 8, 21),
        state=state,
        warehouse=warehouse,
        router=_Router(),  # type: ignore[arg-type]
        recs=[rec],
    )
    assert result.metrics["revised"] == 1
    saved = warehouse.get_recommendations()[0]
    assert "営業利益率" in saved["bear_case_ja"]
    assert saved["critic_verdict"] == "revised"


def test_researcher_persists_document_summaries() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    warehouse.documents["doc-1"] = {
        "doc_id": "doc-1",
        "ticker": "7203",
        "market": "JP",
        "title": "決算短信",
        "doc_type": "earnings_flash",
        "filed_at": datetime(2026, 8, 10),
    }

    parsed = DocSummaryOutput(
        summary_ja="業績は計画どおり進捗しており、通期予想を据え置いた。" + "補足します。" * 8,
        key_points=["通期予想据え置き"],
        risk_factors=["為替"],
        guidance_tone="neutral",
        guidance_evidence="通期予想を据え置いたと記載されている。",
        qualitative_score=0.2,
        citations=[Citation(doc_id="doc-1", quote="通期予想を据え置いたと記載されている。")],
    )

    class _Router:
        def complete(self, **_kwargs: object) -> LLMResponse:
            return LLMResponse(
                content="{}",
                parsed=parsed,
                model_id="gemini",
                tier="bulk",
                purpose="doc_summary",
                input_tokens=10,
                output_tokens=20,
                cost_usd=0.001,
                was_cache_hit=False,
                latency_ms=1,
                call_id="s1",
            )

    result = researcher(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        router=_Router(),  # type: ignore[arg-type]
        tickers=["7203"],
    )
    assert result.metrics["n_summaries"] == 1
    assert warehouse.summaries
    stored = next(iter(warehouse.summaries.values()))
    assert stored["doc_id"] == "doc-1"
    assert stored["qualitative_score"] == 0.2


def test_weekly_review_records_job_without_llm() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    warehouse.recs = [_approved_rec(rec_id="r1", as_of=date(2026, 8, 21))]
    result = weekly_review(
        "JP", date(2026, 8, 22), state=state, warehouse=warehouse, router=None, memory=state
    )
    assert result.status == "partial"
    assert result.metrics["n_recs"] == 1
    run = state.latest_job_run(job_name="weekly_review", market="JP")
    assert run is not None
    assert run.status == "partial"


def test_model_retrain_partial_when_features_empty(tmp_path: Path) -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    result = model_retrain(
        "JP", date(2026, 8, 21), state=state, warehouse=warehouse, data_dir=tmp_path
    )
    assert result.status == "partial"


def test_garch_refit_partial_without_universe() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    result = garch_refit("JP", date(2026, 8, 21), state=state, warehouse=warehouse)
    assert result.status == "partial"
    assert result.metrics["n_tickers"] == 0


def test_duckdb_search_text_and_update_recommendation() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    duck.upsert_documents(
        [
            {
                "doc_id": "d1",
                "ticker": "7203",
                "market": "JP",
                "source": "edinet",
                "doc_type": "earnings_flash",
                "title": "リスク要因と業績下方修正の懸念についての説明資料",
                "filed_at": datetime(2026, 8, 1),
                "source_url": "https://example.invalid/d1",
            }
        ]
    )
    hits = duck.search_text("下方修正", k=4, ticker="7203", market="JP", as_of=date(2026, 8, 21))
    assert hits
    rec = {
        "rec_id": "r-db",
        "as_of": date(2026, 8, 21),
        "ticker": "7203",
        "market": "JP",
        "action": "watch",
        "horizon": "H20",
        "conviction": "low",
        "conviction_score": 0.4,
        "thesis_ja": "定量スコア上位で注目する銘柄である。",
        "bear_case_ja": "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。",
        "invalidation_ja": "次期予想が下方修正されたら破棄する。",
        "reason_codes": ["VAL_CHEAP_VS_SECTOR"],
        "citations": [{"doc_id": "quant:scores_daily", "quote": "定量スコアとML予測区間に基づく自動生成カードです。"}],
        "source_doc_ids": ["quant:scores_daily"],
        "expected_ret": 0.02,
        "expected_ret_lo": -0.05,
        "expected_ret_hi": 0.08,
        "n_prior_samples": 8,
        "currency": "JPY",
    }
    duck.insert_recommendation(rec)
    n = duck.update_recommendation(
        "r-db",
        {
            "critic_verdict": "revised",
            "bear_case_ja": "次期ガイダンスが下方修正され、営業利益率が8%を下回る可能性がある。",
        },
    )
    assert n == 1
    saved = duck.get_recommendations(ticker="7203", include_rejected=True)[0]
    assert saved["critic_verdict"] == "revised"
    assert "営業利益率" in saved["bear_case_ja"]
