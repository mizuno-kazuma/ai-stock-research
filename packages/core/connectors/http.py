"""リトライ付き HTTP クライアント。

docs/02-data-ingestion.md §1.3 のリトライ方針をそのまま実装する。

| 状況 | 動作 |
| --- | --- |
| 429 | `Retry-After` があれば従う。なければ 4 → 8 → 16 → 32 → 64 秒 |
| 5xx / タイムアウト | 指数バックオフ（最大5回） |
| 401 / 403 | **即座に中断**しリトライしない |
| 404 | リトライせずスキップ |
| JSON パース失敗 | リトライせず `SchemaDriftError` |
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from packages.core.connectors.errors import (
    AuthError,
    NotFoundError,
    RateLimitError,
    SchemaDriftError,
    TransientError,
)
from packages.core.connectors.rate_limit import TokenBucket

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# FRED のようにクエリパラメータでキーを渡すAPIがあるため、
# ログに出す前に必ずマスクする（T-SEC-02）。
SECRET_QUERY_KEYS = frozenset(
    {"api_key", "apikey", "token", "key", "access_token", "subscription-key"}
)
SECRET_HEADER_KEYS = frozenset(
    {"x-api-key", "authorization", "subscription-key", "cookie", "set-cookie"}
)
MASK = "***"


def mask_url(url: str) -> str:
    """クエリ中のシークレットを `***` に置換する。"""
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    masked = [(k, MASK if k.lower() in SECRET_QUERY_KEYS else v) for k, v in pairs]
    return urlunsplit(parts._replace(query=urlencode(masked)))


def mask_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: (MASK if k.lower() in SECRET_HEADER_KEYS else v) for k, v in headers.items()}


def mask_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    return {k: (MASK if k.lower() in SECRET_QUERY_KEYS else v) for k, v in params.items()}


_SECRET_VALUE_RE = re.compile(r"(sk-ant-[\w-]{8,}|AIza[\w-]{8,})")


def scrub(text: str) -> str:
    """既知のキー形式を含む文字列をマスクする（例外メッセージ用）。"""
    return _SECRET_VALUE_RE.sub(MASK, text)


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 5
    backoff_base_sec: float = 4.0
    max_backoff_sec: float = 64.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)

    def backoff(self, attempt: int) -> float:
        """1回目の失敗後は 4s、以降 8, 16, 32, 64 と倍にする。"""
        return min(self.backoff_base_sec * (2 ** max(0, attempt - 1)), self.max_backoff_sec)


@dataclass(slots=True)
class HttpResult:
    status_code: int
    url: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    attempts: int = 1

    def json(self, *, source: str = "", endpoint: str = "") -> Any:
        import json as _json

        try:
            return _json.loads(self.text)
        except ValueError as exc:  # JSONDecodeError も含む
            raise SchemaDriftError(
                f"JSON のパースに失敗しました（仕様変更の可能性）: {exc}",
                source=source,
                endpoint=endpoint,
            ) from exc


class HttpClient:
    """`httpx.Client` の薄いラッパ。

    レート制限（`TokenBucket`）とリトライをここに集約し、各コネクタは
    「どのURLを叩くか」だけを書く。`transport` を差し替えられるので
    テストではネットワークに出ない。
    """

    def __init__(
        self,
        *,
        source: str,
        bucket: TokenBucket | None = None,
        retry: RetryPolicy | None = None,
        timeout: tuple[float, float] = (30.0, 120.0),
        default_headers: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source = source
        self.bucket = bucket
        self.retry = retry or RetryPolicy()
        self._sleep = sleep
        self._default_headers = dict(default_headers or {})
        self._owns_client = client is None
        connect, read = timeout
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=connect, read=read, write=read, pool=connect),
            headers={"Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        endpoint: str = "",
        expect_json: bool = True,
    ) -> HttpResult:
        merged_headers = {**self._default_headers, **(headers or {})}
        last_error: Exception | None = None

        for attempt in range(1, self.retry.max_attempts + 1):
            if self.bucket is not None:
                self.bucket.acquire()
            logger.debug(
                "%s %s params=%s headers=%s (attempt %d)",
                method,
                mask_url(url),
                mask_params(params),
                mask_headers(merged_headers),
                attempt,
            )
            try:
                response = self._client.request(
                    method, url, params=dict(params or {}), headers=merged_headers
                )
            except FileNotFoundError as exc:
                path = exc.filename or str(exc)
                raise TransientError(
                    f"{self.source}: 必要なファイルが見つかりません（{path}）。"
                    "仮想環境を作り直したあとは API を再起動してください。"
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = TransientError(f"{self.source}: 通信エラー: {scrub(str(exc))}")
                self._backoff(attempt, last_error)
                continue

            status = response.status_code
            if status in (401, 403):
                raise AuthError(
                    f"{self.source}: 認証に失敗しました（HTTP {status}）。"
                    "リトライせず中断します。APIキーと権限を確認してください。"
                )
            if status == 404:
                raise NotFoundError(f"{self.source}: 対象が見つかりません（HTTP 404）")
            if status == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                last_error = RateLimitError(
                    f"{self.source}: レート制限（HTTP 429）", retry_after=retry_after
                )
                self._backoff(attempt, last_error, override=retry_after)
                continue
            if status in self.retry.retry_on_status or 500 <= status < 600:
                last_error = TransientError(f"{self.source}: 一時障害（HTTP {status}）")
                self._backoff(attempt, last_error)
                continue
            if status >= 400:
                raise TransientError(f"{self.source}: 想定外のHTTPステータス {status}")

            result = HttpResult(
                status_code=status,
                url=mask_url(str(response.url)),
                text=response.text if expect_json else "",
                headers=dict(response.headers),
                content=response.content,
                attempts=attempt,
            )
            return result

        assert last_error is not None
        raise last_error

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        return self.request("GET", url, **kwargs)

    def get_json(self, url: str, *, endpoint: str = "", **kwargs: Any) -> Any:
        result = self.request("GET", url, endpoint=endpoint, **kwargs)
        return result.json(source=self.source, endpoint=endpoint)

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self.request("GET", url, expect_json=False, **kwargs).content

    # ------------------------------------------------------------------
    def _backoff(self, attempt: int, error: Exception, *, override: float | None = None) -> None:
        if attempt >= self.retry.max_attempts:
            return
        wait = override if override is not None else self.retry.backoff(attempt)
        logger.warning(
            "%s: %s。%.1f 秒待って再試行します（%d/%d）",
            self.source,
            error,
            wait,
            attempt,
            self.retry.max_attempts,
        )
        self._sleep(wait)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        # HTTP-date 形式は本プロジェクトでは扱わない（秒指定のみを想定）。
        return None
