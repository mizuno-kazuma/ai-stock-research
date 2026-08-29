"""`ui.default_market=auto` を日本時間15時で JP / US に解決する。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.api.util import resolve_market

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")


def test_passthrough_and_fallback() -> None:
    assert resolve_market("JP") == "JP"
    assert resolve_market("US") == "US"
    assert resolve_market(None) == "JP"
    assert resolve_market("xyz") == "JP"
    assert resolve_market("") == "JP"


def test_auto_before_15_jst_is_jp() -> None:
    now = datetime(2026, 8, 30, 14, 59, tzinfo=JST)
    assert resolve_market("auto", now=now) == "JP"


def test_auto_at_15_jst_is_us() -> None:
    now = datetime(2026, 8, 30, 15, 0, tzinfo=JST)
    assert resolve_market("auto", now=now) == "US"


def test_auto_converts_utc_to_jst() -> None:
    # 14:00 JST = 05:00 UTC
    assert resolve_market("auto", now=datetime(2026, 8, 30, 5, 0, tzinfo=UTC)) == "JP"
    # 15:00 JST = 06:00 UTC
    assert resolve_market("auto", now=datetime(2026, 8, 30, 6, 0, tzinfo=UTC)) == "US"


def test_naive_datetime_is_treated_as_jst() -> None:
    assert resolve_market("auto", now=datetime(2026, 8, 30, 10, 0)) == "JP"
    assert resolve_market("auto", now=datetime(2026, 8, 30, 16, 0)) == "US"
