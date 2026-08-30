"""外部 Webhook 通知（docs/10-mobile-pwa.md §5）。

未設定なら何もしない。送信失敗でジョブを落としてはいけない。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_webhook_url(settings: Any | None = None, state: Any | None = None) -> str:
    if state is not None:
        getter = getattr(state, "get_setting", None)
        if callable(getter):
            try:
                value = getter("notify.webhook_url", "")
            except TypeError:
                value = getter("notify.webhook_url")
            if value:
                return str(value)
    if settings is not None:
        url = getattr(settings, "notify_webhook_url", "") or ""
        if url:
            return str(url)
    return ""


def send_webhook(
    url: str,
    *,
    title_ja: str,
    body_ja: str = "",
    severity: str = "info",
    post_fn: Any | None = None,
    timeout: float = 10.0,
) -> bool:
    if not url:
        return False
    payload = {"text": f"[{severity}] {title_ja}\n{body_ja}".rstrip()}
    try:
        if post_fn is not None:
            post_fn(url, json=payload, timeout=timeout)
        else:
            import httpx

            httpx.post(url, json=payload, timeout=timeout)
    except Exception:
        logger.warning("Webhook 送信に失敗しました", exc_info=True)
        return False
    return True


def notify_event(
    *,
    title_ja: str,
    body_ja: str = "",
    severity: str = "info",
    settings: Any | None = None,
    state: Any | None = None,
    post_fn: Any | None = None,
) -> bool:
    return send_webhook(
        resolve_webhook_url(settings, state),
        title_ja=title_ja,
        body_ja=body_ja,
        severity=severity,
        post_fn=post_fn,
    )
