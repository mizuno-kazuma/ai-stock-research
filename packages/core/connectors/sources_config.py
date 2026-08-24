"""データソース設定の読み込み。

**権威ある定義は `packages/core/config/sources.yaml`**（別担当が作成）である。
本モジュールはそれを読むローダーであり、ファイルが未作成の間は
docs/02-data-ingestion.md §1.2 の実値をそのまま写した既定値で動作する。
既定値をここに置くのは「設定ファイルが無いと import すらできない」状態を
避けるためで、値の一次情報源にする意図はない。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
SOURCES_YAML = CONFIG_DIR / "sources.yaml"

# docs/02-data-ingestion.md §1.2 / §9 の実値。`[要検証]` の注記もそのまま持つ。
DEFAULT_SOURCES: dict[str, dict[str, Any]] = {
    "jquants": {
        "base_url": "https://api.jquants.com",
        "rate_limit_per_min": 5,  # free plan。light は 60 [要検証]
        "plan": "${JQUANTS_PLAN}",
        "delay_weeks": 12,  # free plan の遅延。light は 0
        "history_years": 2,
        "auth": {"kind": "header", "header_name": "x-api-key", "env_var": "JQUANTS_API_KEY"},
        "retry": {"max_attempts": 5, "backoff_base_sec": 4.0},
        "timeout_sec": 30,
        "read_timeout_sec": 120,
        "enabled": True,
        "last_verified": "2026-08-23",
    },
    "edinet": {
        "base_url": "https://api.edinet-fsa.go.jp/api/v2",
        "rate_limit_per_min": 60,  # 公式に明示なし。安全側 [要検証]
        "auth": {
            "kind": "header",
            "header_name": "Subscription-Key",
            "env_var": "EDINET_SUBSCRIPTION_KEY",
        },
        "retry": {"max_attempts": 5, "backoff_base_sec": 4.0},
        "timeout_sec": 30,
        "read_timeout_sec": 120,
        "enabled": True,
        "last_verified": "2026-08-23",
    },
    "tdnet": {
        "base_url": "https://www.release.tdnet.info",
        "rate_limit_per_min": 6,  # 礼儀としての自主制限。APIではないため保守的に
        "min_poll_interval_min": 10,
        "concurrency": 1,
        "auth": {"kind": "none"},
        "retry": {"max_attempts": 2, "backoff_base_sec": 8.0},
        "timeout_sec": 30,
        # 規約がグレーであるため既定は無効。利用者が明示的に有効化する。
        "enabled": False,
        "last_verified": "2026-08-23",
    },
    "edgar": {
        "base_url": "https://data.sec.gov",
        "archives_base_url": "https://www.sec.gov",
        "rate_limit_per_sec": 5,  # SEC の明示上限は 10。安全側に 5
        "auth": {"kind": "header", "header_name": "User-Agent", "env_var": "EDGAR_USER_AGENT"},
        "retry": {"max_attempts": 5, "backoff_base_sec": 4.0},
        "timeout_sec": 30,
        "read_timeout_sec": 120,
        "enabled": True,
        "last_verified": "2026-08-23",
    },
    "yfinance": {
        "rate_limit_per_min": 60,  # 非公式。ブロックされたら下げる
        "batch_size": 50,
        "batch_sleep_sec": 1.0,
        "threads": False,  # threads=True は 429 を誘発しやすい
        "auth": {"kind": "none"},
        "enabled": True,
        "last_verified": "2026-08-23",
    },
    "fred": {
        "base_url": "https://api.stlouisfed.org/fred",
        "rate_limit_per_min": 120,  # [要検証]
        "auth": {"kind": "query", "param_name": "api_key", "env_var": "FRED_API_KEY"},
        "retry": {"max_attempts": 5, "backoff_base_sec": 4.0},
        "timeout_sec": 30,
        "enabled": True,
        "last_verified": "2026-08-23",
    },
    "alpha_vantage": {
        "base_url": "https://www.alphavantage.co",
        "rate_limit_per_min": 5,  # 無料枠。日次上限もある [要検証]
        "daily_cap": 25,
        "auth": {"kind": "query", "param_name": "apikey", "env_var": "ALPHA_VANTAGE_API_KEY"},
        "enabled": False,
        "last_verified": "2026-08-23",
    },
    "finnhub": {
        "base_url": "https://finnhub.io/api/v1",
        "rate_limit_per_min": 60,  # 無料枠 [要検証]
        "auth": {"kind": "query", "param_name": "token", "env_var": "FINNHUB_API_KEY"},
        "enabled": False,
        "last_verified": "2026-08-23",
    },
}

# docs/02-data-ingestion.md §9。第1優先から順に並べる。
DEFAULT_PRECEDENCE: dict[str, list[str]] = {
    "prices_daily_jp": ["jquants"],
    "prices_live_jp": ["yfinance", "jquants"],
    "prices_daily_us": ["yfinance", "finnhub", "alpha_vantage"],
    "financials_jp": ["jquants", "edinet"],
    "financials_us": ["edgar", "finnhub"],
    "usdjpy": ["fred", "yfinance"],
    "documents_jp": ["edinet", "tdnet"],
}

# 価格の乖離がこれを超えたら `data_conflicts` に記録して通知する。
CONFLICT_THRESHOLD_PCT = 1.0


@dataclass(slots=True)
class SourceConfig:
    """1ソース分の設定。"""

    name: str
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def enabled(self) -> bool:
        return bool(self.raw.get("enabled", True))

    @property
    def base_url(self) -> str:
        return str(self.raw.get("base_url", ""))

    @property
    def timeout(self) -> tuple[float, float]:
        """(接続タイムアウト, 読み取りタイムアウト)。docs §1.3 の 30s / 120s。"""
        return (
            float(self.raw.get("timeout_sec", 30)),
            float(self.raw.get("read_timeout_sec", 120)),
        )

    def auth_env_var(self) -> str | None:
        auth = self.raw.get("auth") or {}
        return auth.get("env_var")

    def secret(self, env: dict[str, str] | None = None) -> str | None:
        """認証情報を環境変数から取得する。値そのものはログに出さない。"""
        var = self.auth_env_var()
        if not var:
            return None
        source = env if env is not None else os.environ
        value = source.get(var)
        return value or None


@dataclass(slots=True)
class SourcesConfig:
    sources: dict[str, dict[str, Any]]
    precedence: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_PRECEDENCE))
    conflict_threshold_pct: float = CONFLICT_THRESHOLD_PCT

    def __getitem__(self, name: str) -> SourceConfig:
        return self.for_source(name)

    def for_source(self, name: str) -> SourceConfig:
        if name not in self.sources:
            raise KeyError(f"未知のデータソース: {name}")
        return SourceConfig(name=name, raw=dict(self.sources[name]))

    def names(self) -> list[str]:
        return sorted(self.sources)


def load_sources_config(path: Path | None = None) -> SourcesConfig:
    """`sources.yaml` を読む。存在しない場合は既定値を返す。

    存在する場合は既定値に対する上書きマージとし、
    yaml 側に無いキー（安全側の既定）が消えないようにする。
    """
    target = path or SOURCES_YAML
    merged = {name: dict(cfg) for name, cfg in DEFAULT_SOURCES.items()}
    precedence = dict(DEFAULT_PRECEDENCE)
    threshold = CONFLICT_THRESHOLD_PCT

    if target.exists():
        import yaml

        with target.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for name, cfg in (data.get("sources") or {}).items():
            merged.setdefault(name, {})
            merged[name].update(cfg or {})
        if data.get("precedence"):
            precedence = data["precedence"]
        if data.get("conflict_threshold_pct") is not None:
            threshold = float(data["conflict_threshold_pct"])

    return SourcesConfig(sources=merged, precedence=precedence, conflict_threshold_pct=threshold)


@lru_cache(maxsize=1)
def default_sources_config() -> SourcesConfig:
    return load_sources_config()


def jquants_plan_params(plan: str) -> dict[str, Any]:
    """プラン名から派生する値。docs/02-data-ingestion.md §2.1。

    Light への移行を `.env` の1行変更で完了させるため、
    プラン依存の値をここ1箇所から導出する。
    """
    normalized = (plan or "free").strip().lower()
    if normalized not in ("free", "light"):
        raise ValueError(f"未知の JQUANTS_PLAN: {plan!r}（free | light）")
    if normalized == "light":
        return {
            "plan": "light",
            "rate_limit_per_min": 60,
            "delay_weeks": 0,
            "history_years": 5,
            "yfinance_gap_fill": False,
            "cv_n_splits": 12,
        }
    return {
        "plan": "free",
        "rate_limit_per_min": 5,
        "delay_weeks": 12,
        "history_years": 2,
        "yfinance_gap_fill": True,
        "cv_n_splits": 6,
    }
