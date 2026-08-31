"""発行体キーの畳み込み。"""

from packages.core.storage import (
    canonical_jp_ticker,
    issuer_key,
    jp_ticker_aliases,
    unique_by_issuer,
)


def test_canonical_jp_ticker_strips_jquants_padding() -> None:
    assert canonical_jp_ticker("13010") == "1301"
    assert canonical_jp_ticker("7203") == "7203"
    assert canonical_jp_ticker("130A") == "130A"
    assert canonical_jp_ticker("AAPL") == "AAPL"


def test_jp_ticker_aliases_include_four_and_five_digit() -> None:
    assert jp_ticker_aliases("7203") == ("7203", "72030")
    assert jp_ticker_aliases("72030") == ("72030", "7203")
    assert jp_ticker_aliases("130A") == ("130A",)
    assert jp_ticker_aliases("AAPL") == ("AAPL",)
    assert jp_ticker_aliases("") == ()


def test_issuer_key_treats_4_and_5_digit_as_same() -> None:
    assert issuer_key("JP", "13010") == issuer_key("JP", "1301")
    assert issuer_key("US", "AAPL") == ("US", "AAPL")


def test_unique_by_issuer_keeps_named_row() -> None:
    rows = [
        {"market": "JP", "ticker": "15600", "name_local": "15600"},
        {
            "market": "JP",
            "ticker": "15600",
            "name_local": "野村アセットマネジメント株式会社 NEXT FUNDS",
        },
        {"market": "JP", "ticker": "15600", "name_local": "野村アセットマネジメント株式会社 NEXT FUNDS"},
    ]
    unique = unique_by_issuer(rows)
    assert len(unique) == 1
    assert unique[0]["name_local"].startswith("野村")


def test_unique_by_issuer_extra_key_keeps_horizons_apart() -> None:
    rows = [
        {"market": "JP", "ticker": "13010", "horizon": "H20", "name_local": "極洋"},
        {"market": "JP", "ticker": "13010", "horizon": "H5", "name_local": "極洋"},
        {"market": "JP", "ticker": "13010", "horizon": "H20", "name_local": "極洋"},
    ]
    unique = unique_by_issuer(rows, extra_key="horizon")
    assert {(r["ticker"], r["horizon"]) for r in unique} == {("13010", "H20"), ("13010", "H5")}
