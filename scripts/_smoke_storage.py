"""ストレージ層の疎通確認（開発用の一時スクリプト）。"""

from __future__ import annotations

import datetime as dt

from packages.core.storage import DuckDBRepo, InvariantViolation, SQLiteRepo

duck = DuckDBRepo.in_memory()
print("migrations:", duck.schema_version())
print("tables:", len(duck.row_counts()))

duck.upsert_securities(
    [
        {
            "ticker": "7203",
            "market": "JP",
            "name_local": "トヨタ自動車",
            "currency": "JPY",
            "valid_from": dt.date(2020, 1, 1),
            "sector_name": "輸送用機器",
        }
    ]
)
print("securities:", duck.get_securities(market="JP"))

duck.upsert_prices_daily(
    [
        {
            "ticker": "7203",
            "market": "JP",
            "trade_date": dt.date(2026, 8, 21),
            "close": 3000.0,
            "adj_close": 3000.0,
            "currency": "JPY",
            "source": "jquants",
        }
    ]
)
print("prices:", duck.get_prices_daily("7203", "JP"))

duck.upsert_financials(
    [
        {
            "ticker": "7203",
            "market": "JP",
            "period_end": dt.date(2026, 3, 31),
            "fiscal_year": 2026,
            "fiscal_period": "FY",
            "period_type": "consolidated",
            "filed_at": dt.date(2026, 5, 10),
            "revenue": 1.0,
            "currency": "JPY",
            "source": "edinet",
        },
        {
            "ticker": "7203",
            "market": "JP",
            "period_end": dt.date(2026, 3, 31),
            "fiscal_year": 2026,
            "fiscal_period": "FY",
            "period_type": "consolidated",
            "filed_at": dt.date(2026, 7, 1),
            "revenue": 2.0,
            "currency": "JPY",
            "source": "edinet",
        },
    ]
)
print(
    "pit 2026-06-30:",
    [r["revenue"] for r in duck.get_financials_as_of("7203", "JP", dt.date(2026, 6, 30))],
)
print(
    "pit 2026-08-01:",
    [r["revenue"] for r in duck.get_financials_as_of("7203", "JP", dt.date(2026, 8, 1))],
)

try:
    duck.insert_recommendations([{"rec_id": "x", "bear_case_ja": "短い"}])
except InvariantViolation as exc:
    print("invariant ok:", str(exc)[:40])

print("freshness:", duck.data_freshness())

state = SQLiteRepo.in_memory()
print("settings:", state.get_settings_dict()["ui.direction_colors"])
state.set_settings({"ui.theme": "light"})
print("after set:", state.get_settings_dict()["ui.theme"])
run_id = state.start_job_run("collector_jp", trigger="manual")
state.update_job_run(run_id, status="success", finished=True, metrics={"n": 1})
print("job:", state.get_job_run(run_id).status)
print("OK")
