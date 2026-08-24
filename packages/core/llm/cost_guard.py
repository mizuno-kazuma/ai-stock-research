"""日次・月次の LLM コストキャップとキルスイッチ（docs/07-llm-rag.md §3）。

キャップ到達時にシステム全体を止めてはならない。呼び出し側は例外を捕捉し、
定量スコアのみで続行する（T-LLM-03）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from packages.core.interfaces.storage import AlertSink, CostBudgetRepo, LlmCall, LlmCallLog
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive

JST = ZoneInfo("Asia/Tokyo")


def _today_jst(now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(JST).date()


@dataclass
class CostGuard:
    daily_cap: float
    monthly_cap: float
    call_log: LlmCallLog | None = None
    budget: CostBudgetRepo | None = None
    alerts: AlertSink | None = None
    kill_switch: bool = False
    _forced_cap: bool = False

    def force_cap_exceeded(self) -> None:
        """テスト用。本番では使わない。"""
        self._forced_cap = True

    def spent_today(self, *, today: date | None = None) -> float:
        day = today or _today_jst()
        if self.call_log is None:
            return 0.0
        return float(self.call_log.sum_llm_cost(period="day", period_key=day.isoformat()))

    def spent_this_month(self, *, today: date | None = None) -> float:
        day = today or _today_jst()
        key = f"{day.year:04d}-{day.month:02d}"
        if self.call_log is None:
            return 0.0
        return float(self.call_log.sum_llm_cost(period="month", period_key=key))

    def remaining_today(self) -> float:
        return max(0.0, self.daily_cap - self.spent_today())

    def is_killed(self) -> bool:
        if self.kill_switch or self._forced_cap:
            return True
        if self.budget is None:
            return False
        today = _today_jst()
        daily = self.budget.get_budget(period="day", period_key=today.isoformat()) or {}
        monthly = self.budget.get_budget(
            period="month", period_key=f"{today.year:04d}-{today.month:02d}"
        ) or {}
        if daily.get("kill_switch_on"):
            return True
        if monthly.get("kill_switch_on"):
            return True
        return False

    def would_exceed_cap(self, estimated_usd: float) -> bool:
        if self._forced_cap:
            return True
        daily = self.spent_today() + estimated_usd
        monthly = self.spent_this_month() + estimated_usd
        return daily > self.daily_cap or monthly > self.monthly_cap

    def raise_if_blocked(self, estimated_usd: float) -> None:
        if self.is_killed():
            raise KillSwitchActive("LLM キルスイッチが有効です")
        if self.would_exceed_cap(estimated_usd):
            raise CostCapExceeded(estimated=estimated_usd, remaining=self.remaining_today())

    def record(self, call: LlmCall) -> None:
        if self.call_log is not None:
            self.call_log.insert_llm_call(call)
        today = _today_jst()
        month_key = f"{today.year:04d}-{today.month:02d}"
        spent = call.cost_usd
        if self.budget is not None:
            daily_spent = self.budget.add_spend(
                period="day", period_key=today.isoformat(), amount_usd=spent
            )
            self.budget.add_spend(period="month", period_key=month_key, amount_usd=spent)
        else:
            daily_spent = self.spent_today()
        if daily_spent > self.daily_cap or self.spent_today() > self.daily_cap:
            self.kill_switch = True
            if self.budget is not None:
                self.budget.set_kill_switch(
                    period="day", period_key=today.isoformat(), on=True
                )
            if self.alerts is not None:
                self.alerts.create_alert(
                    severity="warning",
                    category="cost",
                    title_ja="LLMの日次予算に達しました",
                    body_ja=f"本日の使用額 ${daily_spent:.4f}。定性分析を停止しました。",
                )


def estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
    cached_tokens: int = 0,
    cache_discount: float = 0.5,
) -> float:
    billable_in = max(input_tokens - cached_tokens, 0)
    cached = min(cached_tokens, input_tokens)
    return (
        billable_in / 1_000_000 * input_usd_per_mtok
        + cached / 1_000_000 * input_usd_per_mtok * cache_discount
        + output_tokens / 1_000_000 * output_usd_per_mtok
    )
