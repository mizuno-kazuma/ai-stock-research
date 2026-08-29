"""LiteLLM を薄いプロキシとして挟むルータ（docs/07-llm-rag.md §2.3）。

呼び出し側はモデル名を知らない。`tier` だけを渡し、実モデルは
`packages/core/config/models.yaml` から解決する。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from packages.core.config.models import ModelsConfig, get_models_config
from packages.core.interfaces.storage import LlmCall, LlmCallLog
from packages.core.llm.cache import LLMCache, input_hash, prompt_hash, sha256_text
from packages.core.llm.cost_guard import CostGuard, estimate_cost_usd
from packages.core.llm.errors import SchemaRetryExhausted
from packages.core.llm.redact import assert_no_sensitive_data

logger = logging.getLogger(__name__)

Tier = Literal["bulk", "default", "deep"]
TOKEN_CAPS = {"bulk": 500_000, "default": 200_000, "deep": 800_000}

CompletionFn = Callable[..., Any]


@dataclass
class LLMResponse:
    content: str
    parsed: BaseModel | None
    model_id: str
    tier: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    was_cache_hit: bool
    latency_ms: int
    call_id: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMRouter:
    def __init__(
        self,
        config: ModelsConfig | None = None,
        cost_guard: CostGuard | None = None,
        call_log: LlmCallLog | None = None,
        cache: LLMCache | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        self.config = config or get_models_config()
        self.cost_guard = cost_guard
        self.call_log = call_log
        self.cache = cache or LLMCache()
        self._completion = completion_fn

    def complete(
        self,
        *,
        tier: Tier,
        purpose: str,
        messages: list[dict[str, Any]],
        files: list[Path] | None = None,
        response_schema: type[BaseModel] | None = None,
        entity: str | None = None,
        job_run_id: int | None = None,
        prompt_name: str | None = None,
        prompt_body: str | None = None,
    ) -> LLMResponse:
        """tier から実モデルを解決して呼ぶ。呼び出し側はモデル名を知らない。"""
        assert_no_sensitive_data({"messages": messages})
        chain = self.config.resolve_chain(tier)
        estimated = self.estimate_cost(tier, messages, files)
        if self.cost_guard is not None:
            self.cost_guard.raise_if_blocked(estimated)

        input_tokens_est = _estimate_tokens(messages, files)
        cap = TOKEN_CAPS[tier]
        if input_tokens_est > cap:
            messages = _truncate_messages(messages, cap)

        p_hash = prompt_hash(prompt_name or purpose, prompt_body or "")
        i_hash = input_hash({"messages": messages, "purpose": purpose, "entity": entity})
        primary = chain[0]
        cached = self.cache.get(
            prompt_hash=p_hash, input_hash=i_hash, model_id=primary.litellm_model
        )
        if cached is not None:
            parsed = None
            content = cached.value if isinstance(cached.value, str) else json.dumps(
                cached.value, ensure_ascii=False
            )
            if response_schema is not None:
                payload = cached.value if isinstance(cached.value, dict) else json.loads(content)
                parsed = response_schema.model_validate(payload)
                content = parsed.model_dump_json()
            return LLMResponse(
                content=content,
                parsed=parsed,
                model_id=primary.litellm_model,
                tier=tier,
                purpose=purpose,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                was_cache_hit=True,
                latency_ms=0,
                call_id=f"cache-{p_hash[:12]}",
            )

        last_error: Exception | None = None
        for spec in chain:
            try:
                response = self._call_model(
                    spec.litellm_model,
                    messages,
                    files=files,
                    max_tokens=self.config.tiers[tier].max_output_tokens,
                    temperature=self.config.tiers[tier].temperature,
                    response_schema=response_schema,
                )
                parsed = None
                content = response["content"]
                if response_schema is not None:
                    parsed = self._parse_with_retry(
                        response_schema, content, spec.litellm_model, messages
                    )
                    content = parsed.model_dump_json()
                in_tok = int(response.get("input_tokens") or input_tokens_est)
                out_tok = int(response.get("output_tokens") or max(len(content) // 4, 1))
                cost = estimate_cost_usd(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    input_usd_per_mtok=spec.input_usd_per_mtok,
                    output_usd_per_mtok=spec.output_usd_per_mtok,
                )
                call_id = str(uuid.uuid4())
                call = LlmCall(
                    call_id=call_id,
                    tier=tier,
                    model_id=spec.litellm_model,
                    purpose=purpose,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    status="success",
                    called_at=datetime.now(timezone.utc),
                    job_run_id=job_run_id,
                    entity=entity,
                    latency_ms=int(response.get("latency_ms") or 0),
                    was_cache_hit=False,
                )
                if self.cost_guard is not None:
                    self.cost_guard.record(call)
                elif self.call_log is not None:
                    self.call_log.insert_llm_call(call)
                store_value: Any = parsed.model_dump() if parsed is not None else content
                self.cache.put(
                    prompt_hash=p_hash,
                    input_hash=i_hash,
                    model_id=spec.litellm_model,
                    value=store_value,
                )
                return LLMResponse(
                    content=content,
                    parsed=parsed,
                    model_id=spec.litellm_model,
                    tier=tier,
                    purpose=purpose,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    was_cache_hit=False,
                    latency_ms=int(response.get("latency_ms") or 0),
                    call_id=call_id,
                    raw=response,
                )
            except SchemaRetryExhausted:
                if self.call_log is not None:
                    self.call_log.insert_llm_call(
                        LlmCall(
                            call_id=str(uuid.uuid4()),
                            tier=tier,
                            model_id=spec.litellm_model,
                            purpose=purpose,
                            input_tokens=input_tokens_est,
                            output_tokens=0,
                            cost_usd=0.0,
                            status="schema_error",
                            called_at=datetime.now(timezone.utc),
                            job_run_id=job_run_id,
                            entity=entity,
                        )
                    )
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("LLM %s が失敗: %s。fallback を試します", spec.litellm_model, exc)
                continue
        raise RuntimeError(f"全モデルが失敗しました: {last_error}")

    def estimate_cost(
        self,
        tier: Tier,
        messages: list[dict[str, Any]],
        files: list[Path] | None = None,
    ) -> float:
        spec = self.config.resolve(tier)
        tokens = _estimate_tokens(messages, files)
        out = self.config.tiers[tier].max_output_tokens
        return estimate_cost_usd(
            input_tokens=tokens,
            output_tokens=min(out, 1024),
            input_usd_per_mtok=spec.input_usd_per_mtok,
            output_usd_per_mtok=spec.output_usd_per_mtok,
        )

    def _call_model(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        files: list[Path] | None,
        max_tokens: int,
        temperature: float,
        response_schema: type[BaseModel] | None,
    ) -> dict[str, Any]:
        fn = self._completion or _default_completion()
        t0 = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Claude 5 は temperature=1 以外を拒否する。未対応パラメータは落とす。
            "drop_params": True,
        }
        if response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        result = fn(**kwargs)
        latency = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, dict) and "content" in result:
            result.setdefault("latency_ms", latency)
            return result
        # LiteLLM ModelResponse
        content = _extract_content(result)
        usage = getattr(result, "usage", None)
        return {
            "content": content,
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "latency_ms": latency,
            "raw": result,
        }

    def _parse_with_retry(
        self,
        schema: type[BaseModel],
        content: str,
        model: str,
        messages: list[dict[str, Any]],
    ) -> BaseModel:
        try:
            return _validate_schema(schema, content)
        except ValidationError as exc:
            retry_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": f"スキーマ違反です。修正して JSON のみ返してください: {exc}",
                },
            ]
            second = self._call_model(
                model,
                retry_messages,
                files=None,
                max_tokens=2048,
                temperature=0.0,
                response_schema=schema,
            )
            try:
                return _validate_schema(schema, second["content"])
            except ValidationError as exc2:
                raise SchemaRetryExhausted(str(exc2)) from exc2


def _validate_schema(schema: type[BaseModel], content: str) -> BaseModel:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    payload = json.loads(text)
    return schema.model_validate(payload)


def _estimate_tokens(messages: list[dict[str, Any]], files: list[Path] | None) -> int:
    chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    extra = 0
    if files:
        for p in files:
            try:
                extra += p.stat().st_size
            except OSError:
                extra += 0
    return max((chars + extra) // 4, 1)


def _truncate_messages(
    messages: list[dict[str, Any]], cap_tokens: int
) -> list[dict[str, Any]]:
    # 末尾（最新）を残し、中間を切る。
    kept: list[dict[str, Any]] = []
    budget = cap_tokens * 4
    used = 0
    for msg in reversed(messages):
        size = len(json.dumps(msg, ensure_ascii=False))
        if used + size > budget and kept:
            break
        kept.append(msg)
        used += size
    kept.reverse()
    return kept


def _extract_content(result: Any) -> str:
    choices = getattr(result, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            return str(getattr(message, "content", "") or "")
    if isinstance(result, dict):
        return str(result.get("content") or result.get("text") or "")
    return str(result)


def _default_completion() -> CompletionFn:
    try:
        import litellm

        litellm.drop_params = True
        return litellm.completion
    except ImportError as exc:
        def _missing(**kwargs: Any) -> Any:
            raise RuntimeError(
                "litellm がインストールされていません。"
                "テストでは completion_fn を注入してください。"
            ) from exc

        return _missing
