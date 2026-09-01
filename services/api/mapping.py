"""ストレージ行 / シード JSON を API スキーマへ写す。"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any

from packages.core.storage import issuer_key, jp_ticker_aliases, to_dict
from packages.schemas.agent import AgentMemory, JobCheckpoint, JobPhase, JobRun
from packages.schemas.common import DataFreshness
from packages.schemas.documents import Document, DocumentSummary
from packages.schemas.portfolio import Position, Trade
from packages.schemas.recommendations import Citation, FactorScores, RecommendationCard
from packages.schemas.screener import ScoreRow
from packages.schemas.stocks import Security
from packages.schemas.system import AlertItem, WatchlistItem
from services.api.util import as_date, as_dict, as_iso, as_list, as_utc

DOC_TYPE_MAP = {
    "10-Q": "quarterly_report",
    "10-K": "annual_report",
    "8-K": "current_report",
    "other": "other_disclosure",
}

DOC_SOURCE_MAP = {
    "sec_edgar": "edgar",
}

JOB_LABEL_JA = {
    "collector": "データ収集",
    "collector_jp": "データ収集（日本）",
    "collector_us": "データ収集（米国）",
    "analyst": "分析",
    "researcher": "資料読解",
    "strategist": "推奨生成",
    "critic": "レビュー",
    "evaluator": "実績評価",
    "weekly_review": "週次の深掘り",
    "model_retrain": "ranker 再学習",
    "garch_refit": "GARCH 再推定",
    "pipeline": "パイプライン",
    "backtest": "バックテスト",
}


def map_doc_type(value: str | None) -> str:
    if not value:
        return "other_disclosure"
    return DOC_TYPE_MAP.get(value, value)


def map_doc_source(value: str | None) -> str:
    if not value:
        return "edinet"
    return DOC_SOURCE_MAP.get(value, value)


def _factor_scores(raw: Any) -> FactorScores | None:
    data = as_dict(raw)
    if not data:
        return None
    if "lowvol" not in data and "volatility" in data:
        data["lowvol"] = data.get("volatility")
    return FactorScores.model_validate(data)


def recommendation_from_row(
    row: dict[str, Any], *, security: dict[str, Any] | None = None
) -> RecommendationCard:
    sec = security or {}
    citations_raw = as_list(row.get("citations"))
    citations = []
    for item in citations_raw:
        if isinstance(item, dict):
            citations.append(
                Citation(
                    doc_id=str(item.get("doc_id") or ""),
                    page=item.get("page"),
                    quote=str(item.get("quote") or ""),
                    doc_type=map_doc_type(item.get("doc_type")) if item.get("doc_type") else None,
                    title=item.get("title"),
                    filed_at=as_date(item.get("filed_at")) or as_utc(item.get("filed_at")),
                    verification=item.get("verification"),
                )
            )
    freshness = []
    for item in as_list(row.get("data_freshness")):
        if isinstance(item, dict):
            freshness.append(
                DataFreshness(
                    source=str(item.get("source") or ""),
                    latest_as_of=as_utc(item.get("latest_as_of"))
                    or as_date(item.get("latest_as_of")),
                )
            )
    generated = as_utc(row.get("generated_at")) or dt.datetime.now(dt.UTC)
    return RecommendationCard(
        rec_id=str(row["rec_id"]),
        as_of=as_date(row["as_of"]) or dt.date.today(),
        ticker=str(row["ticker"]),
        market=row.get("market") or "JP",
        name_local=str(row.get("name_local") or sec.get("name_local") or row["ticker"]),
        name_en=row.get("name_en") or sec.get("name_en"),
        sector_code=row.get("sector_code") or sec.get("sector_code"),
        sector_name=row.get("sector_name") or sec.get("sector_name"),
        action=row["action"],
        horizon=row["horizon"],
        conviction=row["conviction"],
        conviction_score=float(row["conviction_score"]),
        thesis_ja=str(row["thesis_ja"]),
        bear_case_ja=str(row["bear_case_ja"]),
        invalidation_ja=str(row["invalidation_ja"]),
        reason_codes=[str(x) for x in as_list(row.get("reason_codes"))],
        expected_ret=row.get("expected_ret"),
        expected_ret_lo=float(row["expected_ret_lo"]),
        expected_ret_hi=float(row["expected_ret_hi"]),
        hit_rate_prior=row.get("hit_rate_prior"),
        n_prior_samples=row.get("n_prior_samples"),
        quant_score=row.get("quant_score"),
        quant_rank=row.get("quant_rank"),
        quant_percentile=row.get("quant_percentile"),
        qual_score=row.get("qual_score"),
        qual_confidence=row.get("qual_confidence"),
        qual_doc_count=row.get("qual_doc_count"),
        total_score=row.get("total_score"),
        ml_pred=row.get("ml_pred"),
        factor_scores=_factor_scores(row.get("factor_scores")),
        entry_ref_price=row.get("entry_ref_price"),
        entry_ref_source=row.get("entry_ref_source"),
        entry_ref_note_ja=row.get("entry_ref_note_ja"),
        stop_ref_price=row.get("stop_ref_price"),
        target_ref_price=row.get("target_ref_price"),
        suggested_size_pct=row.get("suggested_size_pct"),
        currency=row.get("currency"),
        source_doc_ids=[str(x) for x in as_list(row.get("source_doc_ids"))],
        citations=citations,
        data_freshness=freshness,
        critic_verdict=row.get("critic_verdict"),
        critic_notes_ja=row.get("critic_notes_ja"),
        memory_ids_used=as_list(row.get("memory_ids_used")),
        flags=[str(x) for x in as_list(row.get("flags"))],
        generated_at=generated,
    )


def recommendation_from_seed(row: dict[str, Any]) -> RecommendationCard:
    payload = dict(row)
    if not payload.get("source_doc_ids"):
        payload["source_doc_ids"] = [
            str(c.get("doc_id")) for c in as_list(row.get("citations")) if c.get("doc_id")
        ]
    if payload.get("suggested_size_pct") is None:
        payload["suggested_size_pct"] = None
    return recommendation_from_row(payload)


def security_from_row(row: dict[str, Any]) -> Security:
    return Security(
        ticker=row["ticker"],
        market=row["market"],
        exchange=row.get("exchange"),
        name_local=row["name_local"],
        name_en=row.get("name_en"),
        sector_code=row.get("sector_code"),
        sector_name=row.get("sector_name"),
        industry_name=row.get("industry_name"),
        currency=row.get("currency") or ("JPY" if row.get("market") == "JP" else "USD"),
        cik=row.get("cik"),
        edinet_code=row.get("edinet_code"),
        isin=row.get("isin"),
        shares_outstanding=row.get("shares_outstanding"),
        trading_unit=row.get("trading_unit"),
        listing_date=as_date(row.get("listing_date")),
        delisting_date=as_date(row.get("delisting_date")),
        is_active=bool(row.get("is_active", True)),
    )


def score_from_row(row: dict[str, Any], *, name_local: str | None = None) -> ScoreRow:
    return ScoreRow(
        ticker=row["ticker"],
        market=row.get("market") or "JP",
        as_of=as_date(row.get("as_of")) or dt.date.today(),
        name_local=name_local or row.get("name_local"),
        sector_code=row.get("sector_code"),
        sector_name=row.get("sector_name"),
        value_z=row.get("value_z"),
        momentum_z=row.get("momentum_z"),
        quality_z=row.get("quality_z"),
        growth_z=row.get("growth_z"),
        lowvol_z=row.get("lowvol_z"),
        liquidity_z=row.get("liquidity_z"),
        revision_z=row.get("revision_z"),
        quant_score=row.get("quant_score"),
        quant_rank=row.get("quant_rank"),
        quant_percentile=row.get("quant_percentile"),
        sector_rank=row.get("sector_rank"),
        qual_score=row.get("qual_score"),
        qual_confidence=row.get("qual_confidence"),
        qual_doc_count=row.get("qual_doc_count"),
        total_score=row.get("total_score"),
        ml_pred_h5=row.get("ml_pred_h5"),
        ml_pred_h20=row.get("ml_pred_h20"),
        ml_pred_h5_lo=row.get("ml_pred_h5_lo"),
        ml_pred_h5_hi=row.get("ml_pred_h5_hi"),
        ml_pred_h20_lo=row.get("ml_pred_h20_lo"),
        ml_pred_h20_hi=row.get("ml_pred_h20_hi"),
        weight_set_id=row.get("weight_set_id"),
        feature_version=row.get("feature_version"),
        model_run_id=row.get("model_run_id"),
        computed_at=as_utc(row.get("computed_at")),
    )


def display_company_name(
    *candidates: Any, ticker: str | None = None, market: str | None = None
) -> str | None:
    """ティッカーそのものではない会社名を返す。コードだけの行は一覧に出さない。"""
    aliases = {str(ticker or "").strip()}
    if market == "JP" and ticker:
        aliases.update(jp_ticker_aliases(ticker))
    aliases.discard("")
    for raw in candidates:
        name = str(raw or "").strip()
        if name and name not in aliases:
            return name
    return None


def securities_by_issuer(
    duck: Any, rows: Iterable[Mapping[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    """開示行のティッカー（4桁/5桁）から証券マスタをまとめて引く。"""
    by_market: dict[str, set[str]] = {}
    for row in rows:
        market = str(row.get("market") or "JP")
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        aliases = jp_ticker_aliases(ticker) if market == "JP" else (ticker,)
        by_market.setdefault(market, set()).update(code for code in aliases if code)
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for market, tickers in by_market.items():
        if not tickers:
            continue
        for sec in duck.get_securities(market=market, tickers=list(tickers), active_only=False):
            key = issuer_key(market, str(sec.get("ticker") or ""))
            name = display_company_name(sec.get("name_local"), ticker=str(sec.get("ticker") or ""), market=market)
            prev = index.get(key)
            if prev is None:
                index[key] = sec
                continue
            prev_name = display_company_name(
                prev.get("name_local"), ticker=str(prev.get("ticker") or ""), market=market
            )
            if name and not prev_name:
                index[key] = sec
                continue
            if (
                bool(name) == bool(prev_name)
                and len(str(sec.get("ticker") or "")) < len(str(prev.get("ticker") or ""))
            ):
                index[key] = sec
    return index


def documents_from_storage(
    duck: Any,
    rows: Iterable[Mapping[str, Any]],
    *,
    has_summary: bool | None = None,
) -> list[Document]:
    materialized = [dict(row) for row in rows]
    names = securities_by_issuer(duck, materialized)
    items: list[Document] = []
    for row in materialized:
        key = issuer_key(row.get("market"), row.get("ticker"))
        flag = bool(has_summary) if has_summary is not None else bool(row.get("has_summary"))
        items.append(
            document_from_row(
                row,
                has_summary=flag,
                security=names.get(key),
            )
        )
    return items


def document_from_row(
    row: dict[str, Any],
    *,
    has_summary: bool = False,
    security: Mapping[str, Any] | None = None,
) -> Document:
    source = map_doc_source(row.get("source"))
    if source not in {"edinet", "tdnet", "edgar"}:
        source = "edinet"
    sec = security or {}
    market = row.get("market") or "JP"
    ticker = row.get("ticker")
    name = display_company_name(
        sec.get("name_local"),
        row.get("name_local"),
        ticker=str(ticker or ""),
        market=str(market),
    )
    return Document(
        doc_id=row["doc_id"],
        ticker=ticker,
        market=market,
        name_local=name,
        source=source,  # type: ignore[arg-type]
        doc_type=map_doc_type(row.get("doc_type")),  # type: ignore[arg-type]
        form_code=row.get("form_code"),
        title=row.get("title") or row["doc_id"],
        title_en=row.get("title_en"),
        fiscal_period=row.get("fiscal_period"),
        period_end=as_date(row.get("period_end")),
        filed_at=as_utc(row.get("filed_at")) or dt.datetime.now(dt.UTC),
        disclosed_at=as_utc(row.get("disclosed_at")),
        source_url=row.get("source_url") or row.get("pdf_url") or f"https://example.invalid/{row['doc_id']}",
        pdf_url=row.get("pdf_url"),
        xbrl_url=row.get("xbrl_url"),
        has_local_copy=bool(row.get("blob_path") or row.get("local_copy") or row.get("has_local_copy")),
        local_copy_error_ja=row.get("local_copy_error_ja"),
        page_count=row.get("page_count") or row.get("pages"),
        byte_size=row.get("byte_size") or row.get("bytes"),
        language=row.get("language"),
        is_amendment=bool(row.get("is_amendment")),
        amends_doc_id=row.get("amends_doc_id"),
        has_summary=has_summary or bool(row.get("has_summary")),
        tone=row.get("tone") or row.get("guidance_tone"),
        estimated_summary_cost_usd=row.get("estimated_summary_cost_usd"),
        info_value_rank=row.get("info_value_rank"),
    )


def document_summary_from_row(row: dict[str, Any]) -> DocumentSummary:
    citations = []
    for item in as_list(row.get("citations")):
        if isinstance(item, dict):
            citations.append(
                Citation(
                    doc_id=str(row.get("doc_id") or item.get("doc_id") or ""),
                    page=item.get("page"),
                    quote=str(item.get("quote") or ""),
                    verification=item.get("verification"),
                )
            )
    return DocumentSummary(
        doc_id=row["doc_id"],
        summary_version=int(row.get("summary_version") or 1),
        model_id=str(row.get("model_id") or row.get("model") or "unknown"),
        prompt_hash=row.get("prompt_hash"),
        input_hash=row.get("input_hash"),
        headline_ja=row.get("headline_ja"),
        summary_ja=str(row.get("summary_ja") or row.get("headline_ja") or ""),
        key_points_ja=as_list(row.get("key_points_ja") or row.get("key_points")),
        risk_factors_ja=as_list(row.get("risk_factors_ja") or row.get("risk_factors")),
        guidance_tone=row.get("guidance_tone") or row.get("tone"),
        guidance_evidence=row.get("guidance_evidence"),
        tone_rationale_ja=row.get("tone_rationale_ja"),
        qualitative_score=row.get("qualitative_score"),
        citations=citations,
        input_tokens=row.get("input_tokens"),
        output_tokens=row.get("output_tokens"),
        cost_usd=row.get("cost_usd"),
        cache_hit=bool(row.get("cache_hit")),
        computed_at=as_utc(row.get("computed_at") or row.get("generated_at"))
        or dt.datetime.now(dt.UTC),
    )


def job_from_row(row: Any, *, seed: dict[str, Any] | None = None) -> JobRun:
    data = to_dict(row, json_fields=("checkpoint", "metrics")) if not isinstance(row, dict) else dict(row)
    extra = seed or {}
    checkpoint_raw = data.get("checkpoint") or extra.get("checkpoint")
    checkpoint = None
    if isinstance(checkpoint_raw, dict):
        units = checkpoint_raw.get("completed_units")
        completed = checkpoint_raw.get("completed")
        total = checkpoint_raw.get("total")
        if completed is None and isinstance(units, list):
            completed = len(units)
        cursor = checkpoint_raw.get("cursor") or checkpoint_raw.get("next_unit")
        checkpoint = JobCheckpoint(
            phase=checkpoint_raw.get("phase"),
            cursor=str(cursor) if cursor is not None else None,
            completed=completed,
            total=total,
        )
    phases = []
    for item in extra.get("phases") or []:
        phases.append(
            JobPhase(
                name=item.get("name"),
                label_ja=item.get("label_ja"),
                status=item.get("status"),
                duration_sec=item.get("duration_sec"),
                detail_ja=item.get("detail_ja"),
            )
        )
    run_id = data.get("id") or data.get("job_run_id")
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else extra.get("metrics")
    failed_steps = list(extra.get("failed_steps") or [])
    if not failed_steps and isinstance(metrics, dict):
        failed_steps = [str(s) for s in (metrics.get("failed_steps") or [])]
    error_message = data.get("error_message")
    if not error_message and isinstance(metrics, dict):
        reason = metrics.get("reason")
        if reason == "no_scores":
            error_message = "スコアがありません。先に分析ジョブを成功させてください。"
        elif isinstance(metrics.get("step_errors"), dict) and metrics["step_errors"]:
            error_message = " / ".join(
                f"{name}: {msg}" for name, msg in metrics["step_errors"].items()
            )
        elif reason:
            error_message = str(reason)
    output_summary = extra.get("output_summary_ja")
    if not output_summary and error_message:
        output_summary = error_message
    elif not output_summary and isinstance(metrics, dict):
        output_summary = metrics.get("output_summary_ja")
    job_name = str(data.get("job_name"))
    return JobRun(
        job_run_id=int(run_id),
        job_name=job_name,
        label_ja=extra.get("label_ja") or JOB_LABEL_JA.get(job_name),
        market=data.get("market"),
        trigger=data.get("trigger") or "schedule",
        status=data.get("status") or "success",
        attempt=int(extra.get("attempt") or (data.get("retry_count") or 0) + 1),
        started_at=as_utc(data.get("started_at")) or dt.datetime.now(dt.UTC),
        finished_at=as_utc(data.get("finished_at")),
        duration_sec=data.get("duration_sec") or extra.get("duration_sec"),
        output_summary_ja=output_summary,
        failed_steps=failed_steps,
        phases=phases,
        checkpoint=checkpoint,
        metrics=metrics if isinstance(metrics, dict) else extra.get("metrics"),
        error_type=data.get("error_type"),
        error_message=error_message,
        retry_count=int(data.get("retry_count") or 0),
        parent_run_id=data.get("parent_run_id"),
        git_commit=data.get("git_commit"),
    )


def _harmful_memory(before: Any, after: Any, use_count: Any) -> bool:
    try:
        if before is None or after is None:
            return False
        return float(after) < float(before) - 0.05 and int(use_count or 0) >= 20
    except (TypeError, ValueError):
        return False


def memory_from_row(row: Any, *, seed: dict[str, Any] | None = None) -> AgentMemory:
    data = to_dict(row, json_fields=("derived_from",)) if not isinstance(row, dict) else dict(row)
    extra = seed or {}
    return AgentMemory(
        memory_id=str(data.get("memory_id")),
        category=data.get("category") or extra.get("category") or "lesson",
        label_ja=extra.get("label_ja"),
        scope=data.get("scope") or extra.get("scope") or "global",
        scope_value=data.get("scope_value") or extra.get("scope_value"),
        lesson_ja=str(data.get("lesson_ja") or extra.get("lesson_ja") or ""),
        evidence_ja=str(data.get("evidence_ja") or extra.get("evidence_ja") or ""),
        derived_from=as_list(data.get("derived_from")),
        n_observations=int(data.get("n_observations") or extra.get("n_evidence") or 0),
        confidence=float(data.get("confidence") or 0.7),
        hit_rate_before=data.get("hit_rate_before"),
        hit_rate_after=data.get("hit_rate_after"),
        times_injected_30d=extra.get("times_injected_30d") or data.get("use_count"),
        effect_hit_rate_used=extra.get("effect_hit_rate_used", data.get("hit_rate_after")),
        effect_n_used=extra.get("effect_n_used"),
        effect_hit_rate_unused=extra.get("effect_hit_rate_unused", data.get("hit_rate_before")),
        effect_n_unused=extra.get("effect_n_unused"),
        is_active=bool(data.get("is_active", True)),
        harmful_flag=bool(
            extra.get("harmful_flag")
            or _harmful_memory(data.get("hit_rate_before"), data.get("hit_rate_after"), data.get("use_count"))
        ),
        harmful_note_ja=extra.get("harmful_note_ja"),
        superseded_by=data.get("superseded_by"),
        created_at=as_utc(data.get("created_at")) or as_date(data.get("created_at")),
        last_used_at=as_utc(data.get("last_used_at")),
        use_count=int(data.get("use_count") or 0),
        review_due_at=as_utc(data.get("review_due_at")) or as_date(data.get("review_due_at")),
    )


def trade_from_row(row: Any, *, name_local: str | None = None) -> Trade:
    data = to_dict(row) if not isinstance(row, dict) else dict(row)
    return Trade(
        trade_id=str(data["trade_id"]),
        ticker=data["ticker"],
        market=data["market"],
        name_local=name_local or data.get("name_local"),
        side=data["side"],
        quantity=float(data["quantity"]),
        price=float(data["price"]),
        fee=float(data.get("fee") or 0.0),
        currency=data["currency"],
        executed_at=as_utc(data["executed_at"]) or dt.datetime.now(dt.UTC),
        broker=data.get("broker"),
        account_type=data.get("account_type"),
        linked_rec_id=data.get("linked_rec_id"),
        thesis_ja=data.get("thesis_ja"),
        emotion_tag=data.get("emotion_tag"),
        exit_plan_ja=data.get("exit_plan_ja"),
        review_ja=data.get("review_ja"),
        created_at=as_utc(data.get("created_at")),
        updated_at=as_utc(data.get("updated_at")),
    )


def position_from_row(row: Any, *, extra: dict[str, Any] | None = None) -> Position:
    data = to_dict(row) if not isinstance(row, dict) else dict(row)
    overlay = extra or {}
    return Position(
        ticker=data["ticker"],
        market=data["market"],
        name_local=overlay.get("name_local") or data.get("name_local"),
        sector_name=overlay.get("sector_name"),
        account_type=data.get("account_type"),
        quantity=float(data["quantity"]),
        avg_cost=float(data["avg_cost"]),
        currency=data.get("currency") or "JPY",
        book_value_jpy=overlay.get("book_value_jpy"),
        ref_price=overlay.get("ref_price"),
        market_value_jpy=overlay.get("market_value_jpy"),
        unrealized_pl_jpy=overlay.get("unrealized_pl_jpy"),
        unrealized_pl_pct=overlay.get("unrealized_pl_pct"),
        weight=overlay.get("weight"),
        total_score=overlay.get("total_score"),
        current_view=overlay.get("current_view"),
        current_view_label_ja=overlay.get("current_view_label_ja"),
        holding_days=overlay.get("holding_days"),
        next_earnings_date=as_date(overlay.get("next_earnings_date")),
        opened_at=as_utc(data.get("opened_at")) or as_date(data.get("opened_at")),
        is_open=bool(data.get("is_open", True)),
    )


def alert_from_row(row: Any) -> AlertItem:
    data = to_dict(row) if not isinstance(row, dict) else dict(row)
    severity = data.get("severity") or "info"
    if severity == "danger":
        severity = "error"
    return AlertItem(
        alert_id=str(data.get("alert_id")),
        severity=severity,
        category=str(data.get("category") or "data"),
        title_ja=str(data.get("title_ja") or ""),
        body_ja=data.get("body_ja"),
        entity=data.get("entity"),
        is_read=bool(data.get("is_read")),
        created_at=as_utc(data.get("created_at")) or dt.datetime.now(dt.UTC),
        link=data.get("link"),
    )


def watchlist_from_row(row: Any, *, extra: dict[str, Any] | None = None) -> WatchlistItem:
    data = to_dict(row) if not isinstance(row, dict) else dict(row)
    overlay = extra or {}
    return WatchlistItem(
        ticker=data["ticker"],
        market=data["market"],
        list_name=data.get("list_name") or "default",
        name_local=overlay.get("name_local") or data.get("name_local"),
        note_ja=data.get("note_ja"),
        ref_price=overlay.get("ref_price"),
        change_pct=overlay.get("change_pct"),
        total_score=overlay.get("total_score"),
        days_to_earnings=overlay.get("days_to_earnings"),
        filings_today=overlay.get("filings_today"),
        added_at=as_utc(data.get("added_at")),
    )


def iso_or_now(value: Any) -> str:
    return as_iso(value) or dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
