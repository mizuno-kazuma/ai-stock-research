"""LLM の構造化出力スキーマ（docs/07-llm-rag.md §6）。

Pydantic の制約で「引用 1 件以上」を強制する。引用のない出力は保存しない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    doc_id: str
    page: int | None = None
    quote: str
    chunk_id: str | None = None

    @field_validator("quote")
    @classmethod
    def quote_not_blank(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("引用が短すぎます")
        return v


class DocSummaryOutput(BaseModel):
    summary_ja: str = Field(min_length=50, max_length=600)
    key_points: list[str] = Field(min_length=1, max_length=8)
    risk_factors: list[str] = Field(max_length=10)
    guidance_tone: Literal["positive", "neutral", "cautious", "negative"]
    guidance_evidence: str = Field(min_length=10)
    qualitative_score: float = Field(ge=-1.0, le=1.0)
    citations: list[Citation] = Field(min_length=1)

    @field_validator("citations")
    @classmethod
    def quotes_not_empty(cls, v: list[Citation]) -> list[Citation]:
        for c in v:
            if len(c.quote.strip()) < 10:
                raise ValueError("引用が短すぎます")
        return v


class ThesisOutput(BaseModel):
    thesis_ja: str = Field(min_length=20)
    bear_case_ja: str = Field(min_length=20)
    invalidation_ja: str = Field(min_length=10)
    conviction: Literal["low", "medium", "high"]
    citations: list[Citation] = Field(min_length=1)


class CriticIssue(BaseModel):
    severity: Literal["critical", "major", "minor"]
    code: str
    detail: str = ""


class CriticOutput(BaseModel):
    verdict: Literal["approved", "revised", "rejected"]
    issues: list[CriticIssue] = Field(default_factory=list)
    revised_fields: dict[str, str] = Field(default_factory=dict)
    notes_ja: str = ""


class Lesson(BaseModel):
    scope: Literal["global", "market", "sector", "ticker"]
    category: Literal["lesson", "bias", "pattern", "caveat"]
    lesson_ja: str = Field(min_length=10, max_length=150)
    evidence_ja: str = Field(min_length=10)
    n_observations: int = Field(ge=10)
    confidence: float = Field(ge=0.0, le=1.0)
    scope_value: str | None = None


class EvaluatorOutput(BaseModel):
    lessons: list[Lesson] = Field(default_factory=list)
    calibration_note_ja: str = ""
    contradicted_memory_ids: list[str] = Field(default_factory=list)
