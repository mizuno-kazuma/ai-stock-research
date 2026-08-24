"""FRED API（為替・マクロ）。

docs/02-data-ingestion.md §8。

改訂（revision）の扱いが要点である。CPI・失業率・GDP は後から改訂されるため、
`realtime_start` / `realtime_end`（ALFRED 機能）で「ある時点で公表されていた値」
を取得し、`macro_series.vintage_date` に持たせる。**バックテストで改訂後の値を
使うとリークになる。**

FRED は API キーをクエリパラメータで渡すため、URL をログに出すと漏洩する。
`http.mask_url` を通すことで防いでいる（T-SEC-02）。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pandas as pd

from packages.core.connectors.base import (
    Checkpoint,
    FetchWindow,
    HttpConnector,
    RawBatch,
    now_utc,
    tag_table,
)
from packages.core.connectors.errors import ConfigurationError, SchemaDriftError

EP_OBSERVATIONS = "series_observations"

# docs/02-data-ingestion.md §8.2。`[要検証]` の series_id は実装時に FRED で確認する。
SERIES: dict[str, dict[str, str]] = {
    "DEXJPUS": {"frequency": "D", "revises": "no", "label_ja": "USD/JPY"},
    "DFF": {"frequency": "D", "revises": "no", "label_ja": "米国実効FFレート"},
    "DGS2": {"frequency": "D", "revises": "no", "label_ja": "米国2年国債利回り"},
    "DGS10": {"frequency": "D", "revises": "no", "label_ja": "米国10年国債利回り"},
    "IRLTLT01JPM156N": {"frequency": "M", "revises": "yes", "label_ja": "日本長期金利"},
    "CPIAUCSL": {"frequency": "M", "revises": "yes", "label_ja": "米国CPI（総合）"},
    "CPALTT01JPM659N": {"frequency": "M", "revises": "yes", "label_ja": "日本CPI"},
    "UNRATE": {"frequency": "M", "revises": "yes", "label_ja": "米国失業率"},
    "T10Y2Y": {"frequency": "D", "revises": "no", "label_ja": "米10年-2年スプレッド"},
    "VIXCLS": {"frequency": "D", "revises": "no", "label_ja": "VIX"},
    "NIKKEI225": {"frequency": "D", "revises": "no", "label_ja": "日経225"},
    "SP500": {"frequency": "D", "revises": "no", "label_ja": "S&P500"},
}

#: 日次の為替・金利は改訂されないため vintage_date = observation_date としてよい。
NON_REVISED = frozenset(sid for sid, meta in SERIES.items() if meta["revises"] == "no")


class FredConnector(HttpConnector):
    source = "fred"

    required_payload_keys = {EP_OBSERVATIONS: ("observations",)}

    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        self._api_key = api_key
        super().__init__(**kwargs)

    def auth_params(self) -> dict[str, str]:
        key = self._api_key or self.config.secret(self.env)
        return {"api_key": key} if key else {}

    def require_credentials(self) -> None:
        if not self.auth_params():
            raise ConfigurationError("FRED_API_KEY が設定されていません")

    def observations_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/series/observations"

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        series_ids: list[str] | None = None,
        vintage: date | None = None,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        """系列単位で取得する。チェックポイントの粒度は series_id。

        `vintage` を指定すると、その日に公表されていた値を取得する
        （バックテスト再現用）。
        """
        self.require_credentials()
        for series_id in series_ids or list(SERIES):
            unit = f"{EP_OBSERVATIONS}:{series_id}"
            if self._checkpoint.is_done(unit):
                continue
            params: dict[str, Any] = {
                "series_id": series_id,
                "file_type": "json",
                "observation_start": window.start.isoformat(),
                "observation_end": window.end.isoformat(),
                **self.auth_params(),
            }
            if vintage is not None:
                params["realtime_start"] = vintage.isoformat()
                params["realtime_end"] = vintage.isoformat()
            payload = self.http.get_json(
                self.observations_url(), params=params, endpoint=EP_OBSERVATIONS
            )
            self._checkpoint.bump("api_calls")
            # request にキーを含めない（Raw層に残さない）。
            masked = {k: v for k, v in params.items() if k != "api_key"}
            masked["api_key"] = "***"
            yield self.make_batch(
                endpoint=EP_OBSERVATIONS,
                as_of=window.end,
                payload=payload,
                request=masked,
                persist=persist,
            )
            self._checkpoint.mark_done(unit)

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        self.assert_payload_shape(batch)
        observations = batch.payload.get("observations") or []
        series_id = str(batch.request.get("series_id") or "")
        if not series_id:
            raise SchemaDriftError(
                "fred: request に series_id がありません",
                source=self.source,
                endpoint=batch.endpoint,
            )
        if not observations:
            return tag_table(pd.DataFrame(), "macro_series")

        raw = pd.DataFrame(observations)
        meta = SERIES.get(series_id, {"frequency": "D", "revises": "no"})
        observation_date = pd.to_datetime(raw["date"], errors="coerce").dt.date
        # FRED は欠損を '.' で返す。
        value = pd.to_numeric(raw["value"].replace(".", None), errors="coerce")

        if series_id in NON_REVISED:
            vintage = observation_date
        else:
            # realtime_start はその値が公表された日。改訂系列では必須。
            vintage_raw = raw.get("realtime_start")
            if vintage_raw is None:
                # realtime_* が返らない場合、公表日を保守的に「取得日」とする。
                # 改訂前の値を過去に遡って使わないための安全側の扱い。
                vintage = pd.Series([batch.as_of] * len(raw))
            else:
                vintage = pd.to_datetime(vintage_raw, errors="coerce").dt.date

        df = pd.DataFrame(
            {
                "series_id": series_id,
                "observation_date": observation_date,
                "vintage_date": vintage,
                "value": value,
                "unit": batch.payload.get("units"),
                "frequency": meta.get("frequency", "D"),
                "source": self.source,
                "ingested_at": now_utc(),
            }
        )
        df = df[df["observation_date"].notna()]
        return tag_table(df.reset_index(drop=True), "macro_series")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint
