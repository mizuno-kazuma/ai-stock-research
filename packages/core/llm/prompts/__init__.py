"""Jinja プロンプトの読み込みと描画。

jinja2 を優先し、未インストール時のみ `{{ }}` / `{% if %}` / `{% for %}` の
サブセットで描画する。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent

_VAR = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_IF = re.compile(
    r"\{%\s*if\s+(.+?)\s*%\}(.*?)\{%\s*endif\s*%\}",
    re.DOTALL,
)
_FOR = re.compile(
    r"\{%\s*for\s+(\w+)\s+in\s+(.+?)\s*%\}(.*?)\{%\s*endfor\s*%\}",
    re.DOTALL,
)
_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        path = PROMPTS_DIR / f"{name}.jinja"
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=32)
def prompt_body(name: str) -> str:
    return load_prompt(name)


def render_prompt(name: str, **context: Any) -> str:
    body = prompt_body(name if name.endswith(".jinja") else f"{name}.jinja")
    try:
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader(), autoescape=False)
        env.filters["join"] = lambda v, sep=", ": sep.join(str(x) for x in (v or []))
        return env.from_string(body).render(**context)
    except ImportError:
        return _render_subset(body, context)


def extract_version(body: str) -> str | None:
    m = re.search(r"\{#\s*version:\s*([^\s#]+)\s*#\}", body)
    return m.group(1) if m else None


def _render_subset(template: str, context: dict[str, Any]) -> str:
    text = _COMMENT.sub("", template)

    def replace_if(match: re.Match[str]) -> str:
        cond = match.group(1).strip()
        inner = match.group(2)
        return inner if _truthy(_eval_expr(cond, context)) else ""

    text = _IF.sub(replace_if, text)

    def replace_for(match: re.Match[str]) -> str:
        var = match.group(1)
        seq_expr = match.group(2).strip()
        inner = match.group(3)
        seq = _eval_expr(seq_expr, context) or []
        chunks = []
        for item in seq:
            local = dict(context)
            local[var] = item
            chunks.append(_render_subset(inner, local))
        return "".join(chunks)

    text = _FOR.sub(replace_for, text)

    def replace_var(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        value = _eval_expr(expr, context)
        if value is None:
            return ""
        return str(value)

    return _VAR.sub(replace_var, text)


def _eval_expr(expr: str, context: dict[str, Any]) -> Any:
    if "| join" in expr:
        left, _, rest = expr.partition("|")
        value = _eval_expr(left.strip(), context)
        sep = ", "
        m = re.search(r'join\((["\'])(.*)\1\)', rest)
        if m:
            sep = m.group(2)
        if value is None:
            return ""
        return sep.join(str(x) for x in value)
    if expr == "schema_json":
        raw = context.get("schema_json")
        if raw is None:
            return "{}"
        if isinstance(raw, (dict, list)):
            return json.dumps(raw, ensure_ascii=False)
        return str(raw)
    current: Any = context
    for part in expr.split("."):
        part = part.strip()
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _truthy(value: Any) -> bool:
    return bool(value)
