"""`models.yaml` の読み込みと型付け（docs/07-llm-rag.md §2.2）。

LLM のモデル識別子は `models.yaml` にしか存在しない。
このモジュールは YAML を読んで検証するだけで、モデル名を持たない。
"""

from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

MODELS_YAML_PATH = Path(__file__).with_name("models.yaml")

Tier = Literal["bulk", "default", "deep"]

# last_verified がこれより古い場合、読み込み時に警告を返す。
STALE_VERIFICATION_DAYS = 90


class LLMModelSpec(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    litellm_model: str
    provider: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    context_window: int
    supports_pdf_input: bool = False
    supports_json_mode: bool = False
    supports_prompt_cache: bool = False


class TierSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str
    fallbacks: list[str] = Field(default_factory=list)
    max_output_tokens: int
    temperature: float


class EmbeddingModelSpec(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    litellm_model: str
    dimensions: int
    usd_per_mtok: float


class EmbeddingsSpec(BaseModel):
    primary: str
    models: dict[str, EmbeddingModelSpec]


class ModelsConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    version: int
    last_verified: dt.date
    tiers: dict[str, TierSpec]
    models: dict[str, LLMModelSpec]
    embeddings: EmbeddingsSpec

    def resolve(self, tier: Tier) -> LLMModelSpec:
        """tier から実モデルの仕様を得る。呼び出し側はモデル名を知らない。"""
        spec = self.tiers[tier]
        return self.models[spec.primary]

    def resolve_chain(self, tier: Tier) -> list[LLMModelSpec]:
        """primary → fallbacks の順に並べた仕様の列。"""
        spec = self.tiers[tier]
        names = [spec.primary, *spec.fallbacks]
        return [self.models[n] for n in names]

    def embedding_dimensions(self) -> int:
        return self.embeddings.models[self.embeddings.primary].dimensions

    def verification_is_stale(self, *, today: dt.date | None = None) -> bool:
        today = today or dt.date.today()
        return (today - self.last_verified).days > STALE_VERIFICATION_DAYS


def load_models_config(path: Path | None = None) -> ModelsConfig:
    p = path or MODELS_YAML_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg = ModelsConfig.model_validate(raw)
    for tier, spec in cfg.tiers.items():
        for name in (spec.primary, *spec.fallbacks):
            if name not in cfg.models:
                raise ValueError(
                    f"models.yaml: tiers.{tier} が未定義のモデル '{name}' を参照しています"
                )
    if cfg.embeddings.primary not in cfg.embeddings.models:
        raise ValueError(
            f"models.yaml: embeddings.primary '{cfg.embeddings.primary}' が未定義です"
        )
    return cfg


@functools.lru_cache(maxsize=1)
def get_models_config() -> ModelsConfig:
    return load_models_config()
