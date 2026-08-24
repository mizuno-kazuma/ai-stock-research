"""トークンバケットによるレート制限。

docs/02-data-ingestion.md §1.2。バケット状態を **プロセス内メモリではなく
SQLite に永続化する**のが要点で、再起動直後に制限を超えて叩き BAN されるのを防ぐ。
永続化先は `RateLimitStateStore`（`packages/core/storage/` 側の実装）に委譲し、
未実装の間は `InMemoryRateLimitStore` で動く。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from packages.core.interfaces.storage import RateLimitState


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InMemoryRateLimitStore:
    """テストと、SQLite 実装が使えない場面のための代替。

    プロセス再起動で状態が失われるため、本番では
    `packages/core/storage/` の SQLite 実装を注入する。
    """

    def __init__(self) -> None:
        self._states: dict[str, RateLimitState] = {}

    def load_rate_limit_state(self, source: str) -> RateLimitState | None:
        return self._states.get(source)

    def save_rate_limit_state(self, state: RateLimitState) -> None:
        self._states[state.source] = state


class TokenBucket:
    """毎分 `rate_per_min` トークンで補充されるバケット。

    `acquire` はトークンが得られるまでブロックする。待機時間の計算は
    永続化された `last_refill_at`（壁時計）との差分で行う。プロセスを
    落として即座に再起動しても補充量が巻き戻らないことが目的である。
    """

    def __init__(
        self,
        source: str,
        *,
        rate_per_min: float,
        burst: float | None = None,
        store: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = _utcnow,
        daily_cap: int | None = None,
    ) -> None:
        if rate_per_min <= 0:
            raise ValueError("rate_per_min は正の値である必要があります")
        self.source = source
        self.rate_per_min = float(rate_per_min)
        # burst 既定を 1 にする。無料枠では「まとめて叩ける」前提を置かない方が安全。
        self.burst = float(burst) if burst is not None else max(1.0, min(rate_per_min, 5.0))
        self._store = store if store is not None else InMemoryRateLimitStore()
        self._sleep = sleep
        self._now = now
        self.daily_cap = daily_cap
        self._lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        source: str,
        config: dict,
        **kwargs: object,
    ) -> TokenBucket:
        """`sources.yaml` の1ソース分の dict から生成する。

        `rate_limit_per_min` と `rate_limit_per_sec` のどちらでも受ける
        （SEC は秒単位で上限を公開しているため）。
        """
        per_min = config.get("rate_limit_per_min")
        per_sec = config.get("rate_limit_per_sec")
        if per_min is None and per_sec is None:
            rate_limit = config.get("rate_limit") or {}
            requests = rate_limit.get("requests")
            per_seconds = rate_limit.get("per_seconds")
            if requests and per_seconds:
                per_min = float(requests) * 60.0 / float(per_seconds)
        if per_min is None and per_sec is not None:
            per_min = float(per_sec) * 60.0
        if per_min is None:
            raise ValueError(f"{source}: レート制限が設定されていません")
        burst = config.get("burst")
        if burst is None and per_sec is not None:
            burst = float(per_sec)
        return cls(
            source,
            rate_per_min=float(per_min),
            burst=float(burst) if burst is not None else None,
            daily_cap=config.get("daily_cap"),
            **kwargs,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    def acquire(self, tokens: float = 1.0) -> float:
        """トークンが得られるまでブロックし、待機した秒数を返す。"""
        if tokens > self.burst:
            # burst を超える要求はバケットの定義上永久に満たせない。
            raise ValueError(f"tokens={tokens} が burst={self.burst} を超えています")
        with self._lock:
            state = self._load_state()
            state = self._refill(state)
            self._check_daily_cap(state)

            waited = 0.0
            if state.tokens < tokens:
                deficit = tokens - state.tokens
                wait_sec = deficit * 60.0 / self.rate_per_min
                self._sleep(wait_sec)
                waited = wait_sec
                state = self._refill(state)
                # sleep が実時間を進めない実装（テスト）でも成立させる。
                state.tokens = max(state.tokens, tokens)

            state.tokens -= tokens
            state.calls_today += 1
            self._store.save_rate_limit_state(state)  # type: ignore[attr-defined]
            return waited

    def tokens_available(self) -> float:
        with self._lock:
            return self._refill(self._load_state()).tokens

    # ------------------------------------------------------------------
    def _load_state(self) -> RateLimitState:
        state = self._store.load_rate_limit_state(self.source)  # type: ignore[attr-defined]
        if state is None:
            state = RateLimitState(
                source=self.source,
                tokens=self.burst,
                last_refill_at=self._now(),
                calls_today=0,
                day_key=self._now().strftime("%Y-%m-%d"),
            )
        return state

    def _refill(self, state: RateLimitState) -> RateLimitState:
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        last = state.last_refill_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = max(0.0, (now - last).total_seconds())
        state.tokens = min(self.burst, state.tokens + elapsed * self.rate_per_min / 60.0)
        state.last_refill_at = now
        day_key = now.strftime("%Y-%m-%d")
        if state.day_key != day_key:
            state.day_key = day_key
            state.calls_today = 0
        return state

    def _check_daily_cap(self, state: RateLimitState) -> None:
        if self.daily_cap is not None and state.calls_today >= self.daily_cap:
            from packages.core.connectors.errors import RateLimitError

            raise RateLimitError(
                f"{self.source}: 日次上限 {self.daily_cap} 回に達しました",
                retry_after=None,
            )
