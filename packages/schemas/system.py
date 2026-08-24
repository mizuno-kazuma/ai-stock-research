"""ウォッチリスト・設定・アラート・システム（docs/09-api-spec.md §2.10）。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field, RootModel

from packages.schemas.common import DataFreshness, SchemaModel
from packages.schemas.enums import ComponentStatus, Market, Severity, SystemStatus


class WatchlistItem(SchemaModel):
    ticker: str
    market: Market
    list_name: str = "default"
    name_local: str | None = None
    note_ja: str | None = None
    ref_price: float | None = None
    change_pct: float | None = None
    total_score: float | None = None
    days_to_earnings: int | None = None
    filings_today: int | None = None
    added_at: dt.datetime | None = None


class WatchlistCreate(SchemaModel):
    ticker: str
    market: Market
    list_name: str = "default"
    note_ja: str | None = None


class WatchlistResponse(SchemaModel):
    list_name: str
    items: list[WatchlistItem] = Field(default_factory=list)
    total: int = 0


class SettingsResponse(SchemaModel):
    """`settings` テーブルの全キー（docs/03-data-model.md §3.6）。

    キーはドット区切りで、値は JSON。UI の設定画面が扱う形に合わせて
    フラットな dict のまま返す。
    """

    values: dict[str, Any]
    updated_at: dt.datetime | None = None


class SettingsPatch(RootModel[dict[str, Any]]):
    """部分更新。

    ボディは `{"ui.direction_colors": "jp", "llm.daily_cap_usd": 1.5}` のような
    フラットな dict（docs/09-api-spec.md §2.10）。既知のキーかどうかは
    ルータ側で検証し、未知のキーは 422 にする。
    """

    root: dict[str, Any]


class AlertItem(SchemaModel):
    alert_id: str
    severity: Severity
    category: str
    title_ja: str
    body_ja: str | None = None
    entity: str | None = None
    is_read: bool = False
    created_at: dt.datetime
    link: str | None = None


class AlertItemList(SchemaModel):
    items: list[AlertItem]
    total: int
    unread_count: int = 0


class HealthComponent(SchemaModel):
    name: str
    status: ComponentStatus
    last_success: dt.datetime | None = None
    next_run: dt.datetime | None = None
    message_ja: str | None = None
    spent_today_usd: float | None = None


class DiskUsage(SchemaModel):
    data_dir_gb: float | None = None
    free_gb: float | None = None


class SystemHealth(SchemaModel):
    status: SystemStatus
    app_version: str | None = None
    python_version: str | None = None
    components: list[HealthComponent] = Field(default_factory=list)
    disk: DiskUsage | None = None
    uptime_sec: float | None = None
    data_dir: str | None = None
    data_dir_on_windows_mount: bool = False
    python_utf8_mode: bool | None = None
    is_seed_data: bool = False


class FreshnessResponse(SchemaModel):
    sources: list[DataFreshness] = Field(default_factory=list)


class LivenessResponse(SchemaModel):
    """`GET /health`。Envelope で包まない軽量な生存確認。"""

    status: str = "ok"
    app_version: str
    checked_at: dt.datetime


__all__ = [
    "AlertItem",
    "AlertItemList",
    "DiskUsage",
    "FreshnessResponse",
    "HealthComponent",
    "LivenessResponse",
    "SettingsPatch",
    "SettingsResponse",
    "SystemHealth",
    "WatchlistCreate",
    "WatchlistItem",
    "WatchlistResponse",
]
