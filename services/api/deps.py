"""依存性注入（docs/09-api-spec.md §5, docs/11-security-ops.md §2）。

Phase A では認証なし（`AUTH_MODE=none`）。すべてのエンドポイントは
`Depends(get_current_user)` を差し込める形にしてあり、Phase B で
Bearer / パスキーを追加するだけで済む。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from packages.core.config import Settings, get_settings
from packages.core.storage import DuckDBRepo, SQLiteRepo, is_serving_seed
from packages.schemas.common import DataFreshness, Warning_
from packages.schemas.enums import ProblemType
from services.api.errors import ApiError
from services.api.events import EventBus
from services.api.util import as_date, as_utc, utc_now

AuthMode = Literal["none", "token", "passkey"]


@dataclass(slots=True)
class User:
    id: str
    name: str


@dataclass
class AppState:
    settings: Settings
    duck: DuckDBRepo
    sqlite: SQLiteRepo
    bus: EventBus
    started_at: dt.datetime
    payload: dict[str, Any] = field(default_factory=dict)
    duck_owned: bool = False
    sqlite_owned: bool = False

    @property
    def is_seed_data(self) -> bool:
        """sample JSON を出しているときだけ True。live 投入後は payload があっても False。"""
        return is_serving_seed(self.sqlite)

    @property
    def as_of(self) -> dt.date:
        meta = self.payload.get("_meta") or {}
        parsed = as_date(meta.get("as_of"))
        if parsed:
            return parsed
        latest = self.duck.latest_recommendation_date()
        if latest:
            return as_date(latest) or dt.date.today()
        return dt.date.today()

    def freshness(self) -> list[DataFreshness]:
        items: list[DataFreshness] = []
        seed_rows = self.payload.get("data_freshness") or []
        if self.is_seed_data and seed_rows:
            for row in seed_rows:
                items.append(
                    DataFreshness(
                        source=row.get("source"),
                        latest_as_of=as_utc(row.get("latest_as_of")) or as_date(row.get("latest_as_of")),
                        label_ja=row.get("label_ja"),
                        expected_as_of=as_utc(row.get("expected_as_of"))
                        or as_date(row.get("expected_as_of")),
                        status=row.get("status"),
                        note_ja=row.get("note_ja"),
                    )
                )
            return items
        try:
            raw = self.duck.data_freshness()
        except Exception:
            raw = {}
        for source, latest in raw.items():
            items.append(DataFreshness(source=source, latest_as_of=as_date(latest)))
        return items

    def base_warnings(self) -> list[Warning_]:
        warnings: list[Warning_] = []
        if self.is_seed_data:
            warnings.append(
                Warning_(
                    code="SEED_DATA",
                    message_ja="表示中のデータは docs/ui/sample-data.json 由来のシードです。",
                    severity="info",
                )
            )
        dashboard = self.payload.get("dashboard") or {}
        for row in dashboard.get("warnings") or []:
            code = row.get("code") or "SECTION_UNAVAILABLE"
            if code == "TDNET_DISABLED":
                code = "SOURCE_DISABLED"
            warnings.append(
                Warning_(
                    code=code,
                    message_ja=row.get("message_ja") or "",
                    severity=row.get("severity") or "info",
                    source=row.get("source"),
                    section=row.get("section"),
                )
            )
        tdnet_disabled = bool(self.sqlite.get_setting("data.tdnet_enabled", False) is False)
        if tdnet_disabled and not any(w.code == "SECTION_UNAVAILABLE" for w in warnings):
            warnings.append(
                Warning_(
                    code="SECTION_UNAVAILABLE",
                    message_ja="適時開示（TDnet）の取得は設定で無効になっているため、このセクションはありません。",
                    severity="info",
                    source="tdnet",
                    section="tdnet",
                )
            )
        return warnings


_bearer = HTTPBearer(auto_error=False)


def get_app_state(request: Request) -> AppState:
    state: AppState = request.app.state.api
    # live 投入後はメモリ上の sample JSON を捨て、ルーターの payload フォールバックを止める
    if state.payload and not is_serving_seed(state.sqlite):
        state.payload = {}
    return state


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> User:
    """Phase A は常に固定ユーザー。Phase B でトークン検証に差し替える。"""
    mode: AuthMode = settings.auth_mode
    if mode == "none":
        return User(id="local", name="local")
    if mode == "token":
        expected = settings.api_token.get_secret_value()
        if not expected:
            raise ApiError(
                problem_type=ProblemType.INTERNAL_ERROR,
                title="認証設定が不正です",
                status=500,
                detail="AUTH_MODE=token ですが API_TOKEN が空です。",
            )
        if creds is None or creds.credentials != expected:
            raise ApiError(
                problem_type=ProblemType.VALIDATION_ERROR,
                title="認証に失敗しました",
                status=401,
                detail="Bearer トークンが必要です。",
                instance=str(request.url.path),
            )
        return User(id="token", name="api")
    # passkey は Phase B。未実装のうちは固定ユーザー。
    return User(id="local", name="local")


def require_user(_user: User = Depends(get_current_user)) -> User:
    return _user


def spent_today_usd(state: AppState) -> float:
    day_key = utc_now().date().isoformat()
    month_key = utc_now().strftime("%Y-%m")
    summary = state.sqlite.llm_cost_summary(day_key=day_key, month_key=month_key)
    spent = float(summary.get("spent_today_usd") or 0.0)
    if spent == 0.0:
        cost = (state.payload.get("llm_cost") or {}).get("today_usd")
        if cost is not None:
            return float(cost)
    return spent
