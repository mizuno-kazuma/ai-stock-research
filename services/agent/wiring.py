"""スケジュール実行と手動実行で共有する LLM / ranker の配線。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packages.core.llm.router import LLMRouter
from packages.core.models.ranker import FittedRanker, load_fitted_ranker, ranker_artifact_path

logger = logging.getLogger(__name__)


def llm_keys_configured(settings: Any) -> bool:
    keys = (
        getattr(settings, "gemini_api_key", None),
        getattr(settings, "openai_api_key", None),
        getattr(settings, "anthropic_api_key", None),
    )
    for key in keys:
        if key is None:
            continue
        getter = getattr(key, "get_secret_value", None)
        value = getter() if callable(getter) else str(key)
        if value:
            return True
    return False


def build_llm_router(
    state: Any,
    warehouse: Any,
    settings: Any | None = None,
) -> LLMRouter | None:
    """API キーと CostGuard が揃っていれば Router を返す。無ければ None。"""
    from packages.core.config import get_settings
    from packages.core.llm.cache import LLMCache
    from packages.core.llm.cost_guard import CostGuard

    cfg = settings or get_settings()
    if not llm_keys_configured(cfg):
        return None
    getter = getattr(state, "get_setting", None)
    daily = float(cfg.llm_daily_cap_usd)
    monthly = float(cfg.llm_monthly_cap_usd)
    kill = bool(cfg.llm_kill_switch)
    if callable(getter):
        daily = float(getter("llm.daily_cap_usd", daily) or daily)
        monthly = float(getter("llm.monthly_cap_usd", monthly) or monthly)
        kill = bool(getter("llm.kill_switch", kill) or kill)
    guard = CostGuard(
        daily_cap=daily,
        monthly_cap=monthly,
        call_log=state,
        budget=state,
        kill_switch=kill,
    )
    return LLMRouter(
        cost_guard=guard,
        call_log=state,
        cache=LLMCache(warehouse=warehouse),
    )


def try_load_ranker(
    settings: Any | None = None, *, market: str = "JP"
) -> FittedRanker | None:
    """`data/models/ranker_{market}_h20.pkl` があれば読み込む。"""
    from packages.core.config import get_settings

    cfg = settings or get_settings()
    data_dir = Path(getattr(cfg, "data_dir", Path.home() / "ai-stock" / "data"))
    path = ranker_artifact_path(data_dir, market)
    loaded = load_fitted_ranker(path)
    if loaded is None:
        logger.info("学習済み ranker がありません: %s", path)
        return None
    logger.info("ranker を読み込みました: %s backend=%s", path, loaded.backend)
    return loaded


def pipeline_dependencies(
    state: Any,
    warehouse: Any,
    *,
    market: str,
    settings: Any | None = None,
) -> dict[str, Any]:
    """`run_pipeline` に渡す router / ranker / memory / プラン。"""
    from packages.core.config import get_settings

    cfg = settings or get_settings()
    return {
        "router": build_llm_router(state, warehouse, cfg),
        "ranker": try_load_ranker(cfg, market=market),
        "memory": state,
        "jquants_plan": str(getattr(cfg, "jquants_plan", "free") or "free"),
    }
