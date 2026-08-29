"""API 契約で使う値域の定義（docs/03-data-model.md / docs/05-scoring-screening.md）。

値域を固定するものは `StrEnum` にし、追加され得るものは `str` のまま扱う。
どちらにするかの基準は「未知の値が来たときにエラーにしてよいか」である。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

# ---------------------------------------------------------------------------
# 固定値域（未知の値はエラーにしてよい）
# ---------------------------------------------------------------------------

Market = Literal["JP", "US"]
Horizon = Literal["H5", "H20"]
Action = Literal["watch", "accumulate", "reduce", "avoid"]
Conviction = Literal["low", "medium", "high"]
CriticVerdict = Literal["approved", "revised", "rejected"]
Severity = Literal["info", "warning", "error"]
GuidanceTone = Literal["positive", "neutral", "cautious", "negative"]
CitationVerification = Literal["verified", "verified_fuzzy", "quote_not_found", "unverified"]
PriceSeries = Literal["research", "live"]
Side = Literal["buy", "sell"]
EmotionTag = Literal["confident", "fomo", "fearful", "neutral"]
FeedbackVerdict = Literal["agree", "disagree", "acted_on", "ignored"]
JobStatus = Literal["running", "success", "partial", "failed", "skipped", "interrupted", "cancelled"]
JobTrigger = Literal["schedule", "manual", "retry", "resume", "auto_resume", "startup"]
RebalanceFreq = Literal["weekly", "monthly", "quarterly"]
ModelKind = Literal["ranker", "garch", "arimax", "vecm"]
MemoryCategory = Literal["lesson", "bias", "pattern", "caveat"]
MemoryScope = Literal["global", "market", "sector", "ticker"]
LLMTier = Literal["bulk", "default", "deep", "embedding"]
LLMPurpose = Literal["doc_summary", "thesis", "critic", "evaluator", "embedding"]
ComponentStatus = Literal["ok", "degraded", "failed", "capped", "disabled", "unknown"]
SystemStatus = Literal["ok", "degraded", "failed"]
SortDir = Literal["asc", "desc"]

# docs/09-api-spec.md §2.3
FilterOp = Literal[
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between", "is_null", "is_not_null"
]

# docs/03-data-model.md §2.5。追加時は同ドキュメントを更新すること。
DocType = Literal[
    "annual_report",
    "quarterly_report",
    "semiannual_report",
    "earnings_flash",
    "earnings_presentation",
    "guidance_revision",
    "dividend_revision",
    "buyback",
    "stock_split",
    "management_change",
    "current_report",
    "large_holding",
    "insider_transaction",
    "proxy",
    "other_disclosure",
]

DocSource = Literal["edinet", "tdnet", "edgar"]


# ---------------------------------------------------------------------------
# 拡張され得る値域（型は str のまま。ここは既知の一覧としてのカタログ）
# ---------------------------------------------------------------------------


class ReasonCode(StrEnum):
    """推奨の理由コード（docs/05-scoring-screening.md §7.4）。

    `RecommendationCard.reason_codes` の型は `list[str]` にしてある。
    Strategist が新しいコードを追加したときに読み取り API が 500 に
    なるのを避けるためで、このカタログは UI のラベル対応と検証に使う。
    """

    VAL_CHEAP_VS_SECTOR = "VAL_CHEAP_VS_SECTOR"
    VAL_CHEAP_VS_HISTORY = "VAL_CHEAP_VS_HISTORY"
    MOM_STRONG_12M = "MOM_STRONG_12M"
    MOM_NEAR_52W_HIGH = "MOM_NEAR_52W_HIGH"
    MOM_ABOVE_MA200 = "MOM_ABOVE_MA200"
    MOM_BELOW_MA200 = "MOM_BELOW_MA200"
    QLT_HIGH_ROIC = "QLT_HIGH_ROIC"
    QLT_LOW_LEVERAGE = "QLT_LOW_LEVERAGE"
    QLT_CLEAN_ACCRUALS = "QLT_CLEAN_ACCRUALS"
    GRW_ACCELERATING = "GRW_ACCELERATING"
    REV_UP_GUIDANCE = "REV_UP_GUIDANCE"
    REV_DOWN_GUIDANCE = "REV_DOWN_GUIDANCE"
    VOL_LOW_REGIME = "VOL_LOW_REGIME"
    VOL_HIGH_REGIME = "VOL_HIGH_REGIME"
    FX_TAILWIND = "FX_TAILWIND"
    FX_HEADWIND = "FX_HEADWIND"
    LLM_POSITIVE_GUIDANCE = "LLM_POSITIVE_GUIDANCE"
    LLM_NEW_RISK_DISCLOSED = "LLM_NEW_RISK_DISCLOSED"
    EVENT_EARNINGS_SOON = "EVENT_EARNINGS_SOON"
    DATA_STALE = "DATA_STALE"
    MODEL_LOW_CONFIDENCE = "MODEL_LOW_CONFIDENCE"


KNOWN_REASON_CODES: frozenset[str] = frozenset(c.value for c in ReasonCode)


class WarningCode(StrEnum):
    """`warnings[]` の code（docs/09-api-spec.md §1.2）。"""

    STALE_DATA = "STALE_DATA"
    SECTION_UNAVAILABLE = "SECTION_UNAVAILABLE"
    NO_DATA_FOR_DATE = "NO_DATA_FOR_DATE"
    PARTIAL_JOB = "PARTIAL_JOB"
    SEED_DATA = "SEED_DATA"
    TRUNCATED = "TRUNCATED"
    LLM_CAPPED = "LLM_CAPPED"
    SOURCE_DISABLED = "SOURCE_DISABLED"


class ProblemType(StrEnum):
    """RFC 7807 の `type`（docs/09-api-spec.md §1.1）。"""

    VALIDATION_ERROR = "validation-error"
    NOT_FOUND = "not-found"
    DATA_NOT_READY = "data-not-ready"
    COST_CAP_EXCEEDED = "cost-cap-exceeded"
    UPSTREAM_UNAVAILABLE = "upstream-unavailable"
    INTERNAL_ERROR = "internal-error"


class FactorGroup(StrEnum):
    """ファクターグループ（docs/05-scoring-screening.md §3）。"""

    VALUE = "value"
    MOMENTUM = "momentum"
    QUALITY = "quality"
    GROWTH = "growth"
    LOWVOL = "lowvol"
    LIQUIDITY = "liquidity"
    REVISION = "revision"


__all__ = [
    "Action",
    "CitationVerification",
    "ComponentStatus",
    "Conviction",
    "CriticVerdict",
    "DocSource",
    "DocType",
    "EmotionTag",
    "FactorGroup",
    "FeedbackVerdict",
    "FilterOp",
    "GuidanceTone",
    "Horizon",
    "JobStatus",
    "JobTrigger",
    "KNOWN_REASON_CODES",
    "LLMPurpose",
    "LLMTier",
    "Market",
    "MemoryCategory",
    "MemoryScope",
    "ModelKind",
    "PriceSeries",
    "ProblemType",
    "ReasonCode",
    "RebalanceFreq",
    "Severity",
    "Side",
    "SortDir",
    "SystemStatus",
    "WarningCode",
]
