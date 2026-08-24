"""プロンプト / 要約キャッシュ（docs/07-llm-rag.md §5.6、docs/06-filings-access.md）。

ハッシュがキャッシュキーになるため、プロンプトの些細な変更でも再計算が走る。
過去分の一括再計算は自動で行わない。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from packages.core.interfaces.storage import LlmCall, LlmCallLog


def sha256_text(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def prompt_hash(name: str, body: str) -> str:
    return sha256_text("prompt", name, body)


def input_hash(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256_text("input", blob)


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime
    prompt_hash: str
    input_hash: str
    model_id: str


class LLMCache:
    """メモリ + 任意の warehouse.find_summary。テストではメモリのみ。"""

    def __init__(self, warehouse: Any | None = None) -> None:
        self._mem: dict[str, CacheEntry] = {}
        self._warehouse = warehouse
        self.hits = 0
        self.misses = 0

    def make_key(self, *, prompt_hash: str, input_hash: str, model_id: str) -> str:
        return sha256_text(prompt_hash, input_hash, model_id)

    def get(
        self, *, prompt_hash: str, input_hash: str, model_id: str
    ) -> CacheEntry | None:
        key = self.make_key(
            prompt_hash=prompt_hash, input_hash=input_hash, model_id=model_id
        )
        hit = self._mem.get(key)
        if hit is not None:
            self.hits += 1
            return hit
        if self._warehouse is not None:
            row = self._warehouse.find_summary(
                doc_id=input_hash, prompt_hash=prompt_hash, input_hash=input_hash
            )
            if row is not None:
                entry = CacheEntry(
                    key=key,
                    value=row,
                    created_at=datetime.now(),
                    prompt_hash=prompt_hash,
                    input_hash=input_hash,
                    model_id=model_id,
                )
                self._mem[key] = entry
                self.hits += 1
                return entry
        self.misses += 1
        return None

    def put(
        self,
        *,
        prompt_hash: str,
        input_hash: str,
        model_id: str,
        value: Any,
    ) -> CacheEntry:
        key = self.make_key(
            prompt_hash=prompt_hash, input_hash=input_hash, model_id=model_id
        )
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=datetime.now(),
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            model_id=model_id,
        )
        self._mem[key] = entry
        return entry

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def log_cache_hit(call_log: LlmCallLog | None, call: LlmCall) -> None:
    if call_log is None:
        return
    call.was_cache_hit = True
    call_log.insert_llm_call(call)
