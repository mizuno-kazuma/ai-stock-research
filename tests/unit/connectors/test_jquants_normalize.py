"""J-Quants v2 短縮フィールド名の正規化。"""

from __future__ import annotations

from datetime import date

from packages.core.connectors.base import RawBatch
from packages.core.connectors.jquants import JQuantsConnector
from packages.core.connectors.sources_config import jquants_plan_params


def _connector(tmp_path, plan: str = "light") -> JQuantsConnector:
    return JQuantsConnector(
        data_dir=tmp_path,
        plan=plan,
        env={"JQUANTS_PLAN": plan, "JQUANTS_API_KEY": "test-key"},
        require_enabled=True,
    )


def test_light_plan_has_no_delay_and_higher_rate(tmp_path) -> None:
    params = jquants_plan_params("light")
    assert params["delay_weeks"] == 0
    assert params["rate_limit_per_min"] == 60
    connector = _connector(tmp_path, plan="light")
    assert connector.delay_weeks == 0
    assert connector.http.bucket.rate_per_min == 60
    connector.close()


def test_normalize_master_reads_v2_short_names(tmp_path) -> None:
    connector = _connector(tmp_path)
    batch = RawBatch(
        source="jquants",
        endpoint="equities_master",
        as_of=date(2026, 8, 26),
        payload={
            "data": [
                {
                    "Date": "2026-08-26",
                    "Code": "44770",
                    "CoName": "BASE",
                    "CoNameEn": "BASE, Inc.",
                    "S17": "10",
                    "S17Nm": "情報通信・サービスその他",
                    "S33": "5250",
                    "S33Nm": "情報・通信業",
                    "Mkt": "0113",
                    "MktNm": "グロース",
                    "ProdCat": "011",
                }
            ]
        },
    )
    frame = connector.normalize(batch)
    connector.close()
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["ticker"] == "44770"
    assert row["name_local"] == "BASE"
    assert row["name_en"] == "BASE, Inc."
    assert row["exchange"] == "グロース"
    assert row["sector_name"] == "情報・通信業"
    assert row["product_category"] == "011"
    assert str(row["yf_symbol"]).endswith(".T")


def test_normalize_master_reads_product_category_for_etf(tmp_path) -> None:
    """ETF・REIT等を個別株フィルタで除外するための商品区分が保存される。"""
    connector = _connector(tmp_path)
    batch = RawBatch(
        source="jquants",
        endpoint="equities_master",
        as_of=date(2026, 8, 26),
        payload={
            "data": [
                {
                    "Date": "2026-08-26",
                    "Code": "15600",
                    "CoName": "野村アセットマネジメント株式会社 NEXT FUNDS",
                    "S33": "9999",
                    "S33Nm": "その他",
                    "Mkt": "0109",
                    "MktNm": "その他",
                    "ProdCat": "014",
                }
            ]
        },
    )
    frame = connector.normalize(batch)
    connector.close()
    assert len(frame) == 1
    assert frame.iloc[0]["product_category"] == "014"


def test_normalize_financials_reads_v2_short_names(tmp_path) -> None:
    connector = _connector(tmp_path)
    batch = RawBatch(
        source="jquants",
        endpoint="fins_summary",
        as_of=date(2026, 8, 26),
        payload={
            "data": [
                {
                    "DiscDate": "2026-08-01",
                    "Code": "86970",
                    "DiscNo": "20260801123456",
                    "DocType": "FYFinancialStatements_Consolidated_IFRS",
                    "CurPerType": "FY",
                    "CurPerEn": "2026-03-31",
                    "CurFYEn": "2026-03-31",
                    "Sales": "1000",
                    "OP": "200",
                    "NP": "100",
                    "EPS": "10.5",
                    "TA": "5000",
                    "Eq": "3000",
                    "FSales": "1100",
                    "FOP": "220",
                    "FNP": "110",
                    "FEPS": "11.0",
                }
            ]
        },
    )
    frame = connector.normalize(batch)
    connector.close()
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["ticker"] == "86970"
    assert str(row["filed_at"]) == "2026-08-01"
    assert str(row["period_end"]) == "2026-03-31"
    assert int(row["fiscal_year"]) == 2026
    assert float(row["revenue"]) == 1000
    assert float(row["operating_income"]) == 200
    assert float(row["forecast_eps"]) == 11.0
