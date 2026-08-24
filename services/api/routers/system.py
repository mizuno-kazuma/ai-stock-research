"""ウォッチリスト・設定・アラート・ヘルス（docs/09-api-spec.md §2.10）。"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from packages.core.storage import DEFAULT_SETTINGS, SETTING_TYPES
from packages.schemas.common import Envelope, OkResponse
from packages.schemas.system import (
    AlertItemList,
    DiskUsage,
    FreshnessResponse,
    HealthComponent,
    LivenessResponse,
    SettingsPatch,
    SettingsResponse,
    SystemHealth,
    WatchlistCreate,
    WatchlistResponse,
)
from services.api.deps import AppState, User, get_app_state, require_user, spent_today_usd
from services.api.envelope import wrap
from services.api.errors import not_found, validation_error
from services.api.mapping import alert_from_row, watchlist_from_row
from services.api.util import utc_now

router = APIRouter(tags=["system"])


@router.get("/watchlist", response_model=Envelope[WatchlistResponse])
def get_watchlist(
    list_name: str = Query(default="default"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[WatchlistResponse]:
    rows = state.sqlite.get_watchlist(list_name)
    seed_by = {(w.get("market"), w.get("ticker")): w for w in state.payload.get("watchlist") or []}
    items = [watchlist_from_row(r, extra=seed_by.get((r.market, r.ticker))) for r in rows]
    if not items:
        items = [
            watchlist_from_row({**w, "list_name": list_name, "added_at": utc_now().isoformat()})
            for w in state.payload.get("watchlist") or []
        ]
    return wrap(state, WatchlistResponse(list_name=list_name, items=items, total=len(items)))


@router.post("/watchlist", response_model=Envelope[WatchlistResponse])
def add_watchlist(
    body: WatchlistCreate,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[WatchlistResponse]:
    state.sqlite.add_to_watchlist(
        body.ticker, body.market, list_name=body.list_name, note_ja=body.note_ja
    )
    return get_watchlist(list_name=body.list_name, _user=_user, state=state)


@router.delete("/watchlist/{market}/{ticker}", response_model=Envelope[OkResponse])
def delete_watchlist(
    market: str,
    ticker: str,
    list_name: str = Query(default="default"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    if not state.sqlite.remove_from_watchlist(ticker, market, list_name=list_name):
        raise not_found(f"{market}:{ticker} はウォッチリストにありません。")
    return wrap(state, OkResponse(ok=True, id=f"{market}:{ticker}"))


@router.get("/settings", response_model=Envelope[SettingsResponse])
def get_settings_endpoint(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[SettingsResponse]:
    values = state.sqlite.get_settings_dict()
    return wrap(state, SettingsResponse(values=values, updated_at=utc_now()))


@router.patch("/settings", response_model=Envelope[SettingsResponse])
def patch_settings(
    body: SettingsPatch,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[SettingsResponse]:
    updates = dict(body.root)
    unknown = [k for k in updates if k not in SETTING_TYPES and k not in DEFAULT_SETTINGS]
    # シード由来の拡張キーは許可（ui.number_format など）
    allowed_extra = {k for k in (state.payload.get("settings") or {})}
    unknown = [k for k in unknown if k not in allowed_extra and not k.startswith("seed.")]
    if unknown:
        raise validation_error(f"未知の設定キーです: {', '.join(unknown)}")
    for key, value in updates.items():
        expected = SETTING_TYPES.get(key)
        if expected is bool and not isinstance(value, bool):
            raise validation_error(f"{key} は bool である必要があります。")
        if expected is float and not isinstance(value, (int, float)):
            raise validation_error(f"{key} は数値である必要があります。")
        if expected is int and not isinstance(value, int):
            raise validation_error(f"{key} は整数である必要があります。")
    values = state.sqlite.set_settings(updates)
    return wrap(state, SettingsResponse(values=values, updated_at=utc_now()))


@router.get("/alerts", response_model=Envelope[AlertItemList])
def list_alerts(
    is_read: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[AlertItemList]:
    unread_only = is_read is False
    rows = state.sqlite.get_alerts(unread_only=unread_only, limit=limit)
    items = [alert_from_row(r) for r in rows]
    if not items:
        items = [
            alert_from_row(a)
            for a in state.payload.get("alerts") or []
            if is_read is None or bool(a.get("is_read")) == is_read
        ][:limit]
    unread = state.sqlite.count_alerts(unread_only=True)
    if unread == 0:
        unread = sum(1 for a in state.payload.get("alerts") or [] if not a.get("is_read"))
    return wrap(state, AlertItemList(items=items, total=len(items), unread_count=unread))


@router.post("/alerts/{alert_id}/read", response_model=Envelope[OkResponse])
def read_alert(
    alert_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    if not state.sqlite.mark_alert_read(alert_id):
        raise not_found(f"アラート {alert_id} は存在しません。")
    return wrap(state, OkResponse(ok=True, id=alert_id))


@router.post("/alerts/read-all", response_model=Envelope[OkResponse])
def read_all_alerts(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    n = state.sqlite.mark_all_alerts_read()
    return wrap(state, OkResponse(ok=True, message_ja=f"{n} 件を既読にしました。"))


@router.get("/system/health", response_model=Envelope[SystemHealth])
def system_health(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[SystemHealth]:
    duck_ok = True
    sqlite_ok = True
    try:
        state.duck.scalar("SELECT 1")
    except Exception:
        duck_ok = False
    try:
        state.sqlite.get_setting("ui.theme")
    except Exception:
        sqlite_ok = False
    usage = shutil.disk_usage(state.settings.data_dir if state.settings.data_dir.exists() else Path.cwd())
    spent = spent_today_usd(state)
    cap = float(state.sqlite.get_setting("llm.daily_cap_usd", 1.0))
    llm_status = "capped" if spent >= cap else "ok"
    tdnet_on = bool(state.sqlite.get_setting("data.tdnet_enabled", False))
    components = [
        HealthComponent(name="duckdb", status="ok" if duck_ok else "failed"),
        HealthComponent(name="sqlite", status="ok" if sqlite_ok else "failed"),
        HealthComponent(name="lancedb", status="ok"),
        HealthComponent(name="scheduler", status="ok"),
        HealthComponent(name="jquants", status="ok"),
        HealthComponent(
            name="tdnet",
            status="disabled" if not tdnet_on else "failed",
            message_ja=None if tdnet_on else "設定で無効になっています",
        ),
        HealthComponent(name="llm", status=llm_status, spent_today_usd=spent),
    ]
    overall = "ok"
    if any(c.status == "failed" for c in components):
        overall = "degraded"
    if not duck_ok or not sqlite_ok:
        overall = "failed"
    if llm_status == "capped" and overall == "ok":
        overall = "degraded"
    data_dir = str(state.settings.data_dir)
    return wrap(
        state,
        SystemHealth(
            status=overall,  # type: ignore[arg-type]
            app_version=state.settings.app_version,
            python_version=sys.version.split()[0],
            components=components,
            disk=DiskUsage(
                data_dir_gb=round(usage.used / (1024**3), 2),
                free_gb=round(usage.free / (1024**3), 2),
            ),
            uptime_sec=max(0.0, time.time() - state.started_at.timestamp()),
            data_dir=data_dir,
            data_dir_on_windows_mount=data_dir.startswith("/mnt/"),
            python_utf8_mode=bool(os.environ.get("PYTHONUTF8") == "1" or sys.flags.utf8_mode),
            is_seed_data=state.is_seed_data,
        ),
    )


@router.get("/system/freshness", response_model=Envelope[FreshnessResponse])
def system_freshness(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FreshnessResponse]:
    return wrap(state, FreshnessResponse(sources=state.freshness()))
