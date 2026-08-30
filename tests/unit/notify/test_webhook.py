"""Webhook 通知。URL 未設定なら送らない。"""

from __future__ import annotations

from packages.core.notify.webhook import notify_event, send_webhook


def test_send_skips_empty_url() -> None:
    called = []
    assert send_webhook("", title_ja="x", post_fn=lambda *a, **k: called.append(1)) is False
    assert called == []


def test_send_posts_payload() -> None:
    seen: list[dict] = []

    def post(url: str, json: dict, timeout: float) -> None:
        seen.append({"url": url, "json": json, "timeout": timeout})

    assert send_webhook(
        "https://example.test/hook",
        title_ja="完了",
        body_ja="推奨 3 件",
        severity="info",
        post_fn=post,
    )
    assert seen[0]["url"] == "https://example.test/hook"
    assert "[info] 完了" in seen[0]["json"]["text"]
    assert "推奨 3 件" in seen[0]["json"]["text"]


def test_notify_event_reads_setting() -> None:
    class State:
        def get_setting(self, key: str, default: str = "") -> str:
            return "https://hooks.test/x" if key == "notify.webhook_url" else default

    seen: list[str] = []

    def post(url: str, json: dict, timeout: float) -> None:
        seen.append(url)

    notify_event(title_ja="失敗", severity="error", state=State(), post_fn=post)
    assert seen == ["https://hooks.test/x"]
