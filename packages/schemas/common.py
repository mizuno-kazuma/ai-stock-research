"""全レスポンス共通の型（docs/09-api-spec.md §1.2, §3）。

すべてのレスポンスを `Envelope` で包む。フロント側は `warnings` を
一律で表示する共通コンポーネントを持てばよい。
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from packages.schemas.enums import Severity

T = TypeVar("T")


class SchemaModel(BaseModel):
    """本プロジェクトのモデル基底。

    - `extra="forbid"`: リクエストのタイポを 422 で弾く
    - フィールド名は仕様書のまま（snake_case）。TS 型は OpenAPI から生成するので変換しない
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DataFreshness(SchemaModel):
    """データソースごとの鮮度。UI ヘッダの鮮度表示に使う。

    `latest_as_of` は日次ソースでは日付、参考現在値のように分単位で
    更新されるソースでは日時になる（docs/ui/sample-data.json の
    `data_freshness` に両方が現れる）。
    """

    source: str
    latest_as_of: dt.date | dt.datetime | None = None
    label_ja: str | None = None
    expected_as_of: dt.date | dt.datetime | None = None
    status: str | None = None
    note_ja: str | None = None


class Warning_(SchemaModel):  # noqa: N801 - docs/09-api-spec.md §3 の名前をそのまま使う
    """部分失敗をエラーにせず伝えるための警告。

    `code` は `packages.schemas.enums.WarningCode` のカタログに従うが、
    型は str のままにしてある（新しい警告種別の追加で 500 にしない）。
    """

    code: str
    message_ja: str
    severity: Severity = "info"
    source: str | None = None
    section: str | None = None


class Meta(SchemaModel):
    as_of: dt.date | None = None
    computed_at: dt.datetime
    data_freshness: list[DataFreshness] = Field(default_factory=list)
    # シードデータで動いていることを UI から判別できるようにする。
    # 実データ投入後は False になる。
    is_seed_data: bool = False


class Envelope(SchemaModel, Generic[T]):
    data: T
    warnings: list[Warning_] = Field(default_factory=list)
    meta: Meta


class Page(SchemaModel, Generic[T]):
    """`limit` / `offset` + `total` のページネーション（docs/09-api-spec.md §1）。"""

    items: list[T]
    total: int
    limit: int | None = None
    offset: int | None = None
    truncated: bool = False


class ProblemDetails(SchemaModel):
    """RFC 7807 (Problem Details)。

    エラー型ごとの追加フィールド（`latest_available_as_of` など）を
    持たせるため `extra="allow"` にしている。
    """

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    # data-not-ready
    latest_available_as_of: dt.date | None = None
    # cost-cap-exceeded
    spent_today_usd: float | None = None
    daily_cap_usd: float | None = None
    resets_at: dt.datetime | None = None
    # validation-error
    errors: list[dict[str, Any]] | None = None


class OkResponse(SchemaModel):
    """書き込み系で返す最小の確認レスポンス。"""

    ok: bool = True
    id: str | int | None = None
    message_ja: str | None = None


__all__ = [
    "DataFreshness",
    "Envelope",
    "Meta",
    "OkResponse",
    "Page",
    "ProblemDetails",
    "SchemaModel",
    "Warning_",
]
