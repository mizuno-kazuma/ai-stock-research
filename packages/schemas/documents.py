"""決算資料（docs/09-api-spec.md §2.5, docs/06-filings-access.md）。"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import DocSource, DocType, GuidanceTone, Market
from packages.schemas.recommendations import Citation


class Document(SchemaModel):
    doc_id: str
    ticker: str | None = None
    market: Market
    name_local: str | None = None
    source: DocSource
    doc_type: DocType
    form_code: str | None = None
    title: str
    title_en: str | None = None
    fiscal_period: str | None = None
    period_end: dt.date | None = None
    filed_at: dt.datetime
    disclosed_at: dt.datetime | None = None
    source_url: str
    pdf_url: str | None = None
    xbrl_url: str | None = None
    # ローカル保存の有無。false の場合 UI は source_url へのリンクに切り替える。
    has_local_copy: bool = False
    local_copy_error_ja: str | None = None
    page_count: int | None = None
    byte_size: int | None = None
    language: str | None = None
    is_amendment: bool = False
    amends_doc_id: str | None = None
    has_summary: bool = False
    tone: GuidanceTone | None = None
    estimated_summary_cost_usd: float | None = None
    info_value_rank: int | None = None


class DocumentList(SchemaModel):
    items: list[Document]
    total: int
    limit: int | None = None
    offset: int | None = None


class GuidanceChange(SchemaModel):
    metric_ja: str
    from_value: float | None = Field(default=None, alias="from")
    to_value: float | None = Field(default=None, alias="to")
    change_pct: float | None = None
    fiscal_period: str | None = None


class DocumentSummary(SchemaModel):
    """`document_summaries`（docs/03-data-model.md §2.6）。

    `citations` が空の要約は保存も返却もしない。
    """

    doc_id: str
    summary_version: int
    model_id: str
    prompt_hash: str | None = None
    input_hash: str | None = None
    headline_ja: str | None = None
    summary_ja: str
    key_points_ja: list[str] = Field(default_factory=list)
    risk_factors_ja: list[str] = Field(default_factory=list)
    guidance_tone: GuidanceTone | None = None
    guidance_evidence: str | None = None
    guidance_change: GuidanceChange | None = None
    tone_rationale_ja: str | None = None
    qualitative_score: float | None = None
    citations: list[Citation] = Field(min_length=1)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cache_hit: bool = False
    computed_at: dt.datetime


class DocumentSummaryRequest(SchemaModel):
    """オンデマンド要約生成。コストキャップ超過時は 429。"""

    force_regenerate: bool = False


class DocumentChunk(SchemaModel):
    chunk_id: str
    doc_id: str
    section: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    text: str
    token_count: int | None = None


class DocumentChunkList(SchemaModel):
    doc_id: str
    items: list[DocumentChunk] = Field(default_factory=list)
    total: int = 0


__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentChunkList",
    "DocumentList",
    "DocumentSummary",
    "DocumentSummaryRequest",
    "GuidanceChange",
]
