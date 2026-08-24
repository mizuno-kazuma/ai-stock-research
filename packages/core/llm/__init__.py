"""LLM ルーティング・RAG・プロンプト。モデル識別子は models.yaml のみ。"""

from packages.core.llm.cache import LLMCache, input_hash, prompt_hash
from packages.core.llm.citations import CitationVerdict, normalize_ja, verify_citation
from packages.core.llm.cost_guard import CostGuard, estimate_cost_usd
from packages.core.llm.errors import (
    CostCapExceeded,
    InvariantViolationError,
    KillSwitchActive,
    SchemaRetryExhausted,
    SensitiveDataInPromptError,
)
from packages.core.llm.prompts import extract_version, load_prompt, render_prompt
from packages.core.llm.rag import reciprocal_rank_fusion, retrieve
from packages.core.llm.redact import assert_no_sensitive_data, redact_portfolio
from packages.core.llm.router import LLMResponse, LLMRouter
from packages.core.llm.schemas import (
    Citation,
    CriticOutput,
    DocSummaryOutput,
    EvaluatorOutput,
    Lesson,
    ThesisOutput,
)

__all__ = [
    "Citation",
    "CitationVerdict",
    "CostCapExceeded",
    "CostGuard",
    "CriticOutput",
    "DocSummaryOutput",
    "EvaluatorOutput",
    "InvariantViolationError",
    "KillSwitchActive",
    "LLMCache",
    "LLMResponse",
    "LLMRouter",
    "Lesson",
    "SchemaRetryExhausted",
    "SensitiveDataInPromptError",
    "ThesisOutput",
    "assert_no_sensitive_data",
    "estimate_cost_usd",
    "extract_version",
    "input_hash",
    "load_prompt",
    "normalize_ja",
    "prompt_hash",
    "reciprocal_rank_fusion",
    "redact_portfolio",
    "render_prompt",
    "retrieve",
    "verify_citation",
]
