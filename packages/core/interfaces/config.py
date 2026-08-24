"""設定層（`packages/core/config/`）に対する契約。

`settings.py`（pydantic-settings）と `*.yaml` は別担当が実装する。
本モジュールは「こちらが読む属性」だけを Protocol として宣言する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SettingsLike(Protocol):
    """`packages.core.config.settings.Settings` に期待する属性。

    シークレットは `.env` 由来。未設定でも import と単体テストが通ること
    （値が None のまま生成できること）を要件とする。
    """

    data_dir: Path
    jquants_plan: str  # 'free' | 'light'
    jquants_api_key: str | None
    edinet_subscription_key: str | None
    fred_api_key: str | None
    edgar_user_agent: str | None
    tdnet_enabled: bool
    anthropic_api_key: str | None
    gemini_api_key: str | None


@runtime_checkable
class SourceConfigLike(Protocol):
    """`packages/core/config/sources.yaml` の1ソース分。"""

    def get(self, key: str, default: Any = None) -> Any: ...


@runtime_checkable
class FactorConfigLike(Protocol):
    """`packages/core/config/factors.yaml` に期待する構造。"""

    factor_groups: dict[str, Any]
    group_weights: dict[str, Any]
    universe_filter: dict[str, Any]
    winsorize: dict[str, float]
