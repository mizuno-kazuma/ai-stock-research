"""起動時キャッチアップとセッション日付。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.agent.main import session_as_of
from services.api.routers.dashboard import _filings_range

JST = ZoneInfo("Asia/Tokyo")
NY = ZoneInfo("America/New_York")


def test_jp_session_before_batch_uses_previous_business_day() -> None:
    now = datetime(2026, 8, 28, 0, 27, tzinfo=JST)
    assert session_as_of("JP", now=now).isoformat() == "2026-08-27"


def test_jp_session_after_batch_uses_today() -> None:
    now = datetime(2026, 8, 28, 18, 30, tzinfo=JST)
    assert session_as_of("JP", now=now).isoformat() == "2026-08-28"


def test_jp_session_weekend_uses_friday() -> None:
    now = datetime(2026, 8, 29, 10, 0, tzinfo=JST)
    assert session_as_of("JP", now=now).isoformat() == "2026-08-28"


def test_us_session_before_close_uses_previous_business_day() -> None:
    now = datetime(2026, 8, 27, 11, 27, tzinfo=NY)
    assert session_as_of("US", now=now).isoformat() == "2026-08-26"


def test_filings_range_is_calendar_week_monday_through_as_of() -> None:
    start, end = _filings_range(date(2026, 8, 28))
    assert end.isoformat() == "2026-08-28"
    assert start.isoformat() == "2026-08-24"


def test_filings_range_on_monday_is_that_day_only() -> None:
    start, end = _filings_range(date(2026, 8, 24))
    assert start.isoformat() == "2026-08-24"
    assert end.isoformat() == "2026-08-24"
