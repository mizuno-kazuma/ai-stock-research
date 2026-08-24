"""Envelope 組み立て（docs/09-api-spec.md §1.2 / §3）。"""

from __future__ import annotations

import datetime as dt
from typing import Any, TypeVar

from packages.schemas.common import Envelope, Meta, Warning_
from services.api.deps import AppState
from services.api.util import utc_now

T = TypeVar("T")


def wrap(
    state: AppState,
    data: T,
    *,
    as_of: dt.date | None = None,
    extra_warnings: list[Warning_] | None = None,
) -> Envelope[T]:
    warnings = list(state.base_warnings())
    if extra_warnings:
        warnings.extend(extra_warnings)
    return Envelope(
        data=data,
        warnings=warnings,
        meta=Meta(
            as_of=as_of or state.as_of,
            computed_at=utc_now(),
            data_freshness=state.freshness(),
            is_seed_data=state.is_seed_data,
        ),
    )


def model_or_dict(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="python")
    return value
