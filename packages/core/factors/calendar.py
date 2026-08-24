"""営業日カレンダー。

**既知の制約**: 祝日カレンダーを持たない（土日のみを非営業日とする）。
日本の祝日データを無料で PIT 整合に取得する経路が仕様書に定義されていないため、
`prices_daily` に実在する日付を「市場カレンダー」として使う経路
（`TradingCalendar.from_prices`）を用意し、価格データがある場面ではそちらを使う。
価格データがない場面（開示の15時ルールなど）は土日判定にフォールバックする。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

JST = ZoneInfo("Asia/Tokyo")
NY = ZoneInfo("America/New_York")

MARKET_TZ = {"JP": JST, "US": NY}
#: 大引け。これ以降の開示は翌営業日扱いとする（docs/04-analysis-engine.md §1.1）。
MARKET_CUTOFF = {"JP": time(15, 0), "US": time(16, 0)}
TRADING_DAYS_PER_YEAR = 252


class TradingCalendar:
    """営業日集合。

    `sessions` を与えた場合はそれを唯一の真実として扱う。与えない場合は
    土日を除く平日を営業日とする。
    """

    def __init__(self, sessions: list[date] | None = None) -> None:
        self._sessions = sorted(set(sessions)) if sessions else None

    @classmethod
    def from_prices(cls, prices: pd.DataFrame, *, date_col: str = "trade_date") -> TradingCalendar:
        """`prices_daily` に実在する日付を市場カレンダーとして使う。"""
        if prices.empty or date_col not in prices.columns:
            return cls()
        values = pd.to_datetime(prices[date_col]).dt.date.unique().tolist()
        return cls(values)

    @property
    def has_sessions(self) -> bool:
        return self._sessions is not None and len(self._sessions) > 0

    def is_business_day(self, d: date) -> bool:
        if self.has_sessions:
            assert self._sessions is not None
            index = bisect_left(self._sessions, d)
            return index < len(self._sessions) and self._sessions[index] == d
        return d.weekday() < 5

    def next_business_day(self, d: date) -> date:
        """`d` より後の最初の営業日。`d` 自身は含まない。"""
        if self.has_sessions:
            assert self._sessions is not None
            index = bisect_right(self._sessions, d)
            if index < len(self._sessions):
                return self._sessions[index]
            # カレンダーの外は土日判定にフォールバックする。
        return _next_weekday(d)

    def prev_business_day(self, d: date) -> date:
        if self.has_sessions:
            assert self._sessions is not None
            index = bisect_left(self._sessions, d)
            if index > 0:
                return self._sessions[index - 1]
        return _prev_weekday(d)

    def shift(self, d: date, n: int) -> date:
        """`n` 営業日ずらす（正で未来、負で過去）。"""
        if n == 0:
            return d if self.is_business_day(d) else self.next_business_day(d)
        step = self.next_business_day if n > 0 else self.prev_business_day
        current = d
        for _ in range(abs(n)):
            current = step(current)
        return current

    def business_day_count(self, start: date, end: date) -> int:
        """`[start, end)` の営業日数。"""
        if self.has_sessions:
            assert self._sessions is not None
            return bisect_left(self._sessions, end) - bisect_left(self._sessions, start)
        return int(np.busday_count(start, end))

    def sessions_between(self, start: date, end: date) -> list[date]:
        if self.has_sessions:
            assert self._sessions is not None
            lo = bisect_left(self._sessions, start)
            hi = bisect_right(self._sessions, end)
            return self._sessions[lo:hi]
        return [d.date() for d in pd.bdate_range(start, end)]


DEFAULT_CALENDAR = TradingCalendar()


def _next_weekday(d: date) -> date:
    nxt = d
    while True:
        nxt = nxt.fromordinal(nxt.toordinal() + 1)
        if nxt.weekday() < 5:
            return nxt


def _prev_weekday(d: date) -> date:
    prev = d
    while True:
        prev = prev.fromordinal(prev.toordinal() - 1)
        if prev.weekday() < 5:
            return prev


def next_business_day(d: date, market: str = "JP", calendar: TradingCalendar | None = None) -> date:
    return (calendar or DEFAULT_CALENDAR).next_business_day(d)


def shift_business_days(
    d: date, n: int, market: str = "JP", calendar: TradingCalendar | None = None
) -> date:
    return (calendar or DEFAULT_CALENDAR).shift(d, n)


def effective_date(
    disclosed_at: datetime, market: str = "JP", calendar: TradingCalendar | None = None
) -> date:
    """開示時刻から、その情報を織り込める最初の営業日を返す。

    この処理を省くと「決算発表当日の終値で決算内容を知っていた」というリークが
    入る。日本株のバックテストで実際によくある誤りである。
    """
    tz = MARKET_TZ.get(market, JST)
    cutoff = MARKET_CUTOFF.get(market, time(15, 0))
    if disclosed_at.tzinfo is None:
        # タイムゾーンなしは市場現地時刻として解釈する。
        local = disclosed_at.replace(tzinfo=tz)
    else:
        local = disclosed_at.astimezone(tz)
    cal = calendar or DEFAULT_CALENDAR
    day = local.date()
    if local.time() >= cutoff:
        return cal.next_business_day(day)
    if not cal.is_business_day(day):
        return cal.next_business_day(day)
    return day


def effective_dates(
    disclosed_at: pd.Series, market: str = "JP", calendar: TradingCalendar | None = None
) -> pd.Series:
    """`effective_date` のベクトル版。"""
    values = pd.to_datetime(disclosed_at, errors="coerce", utc=False)
    return values.map(
        lambda ts: None
        if pd.isna(ts)
        else effective_date(ts.to_pydatetime(), market=market, calendar=calendar)
    )
