"""Connector 層の例外。

docs/02-data-ingestion.md §1.3 のリトライ方針と1対1に対応させる。
「どの例外がリトライ対象か」を型で表現し、呼び出し側に判定ロジックを
書かせないための分割である。
"""

from __future__ import annotations


class ConnectorError(Exception):
    """Connector 層の基底例外。"""


class TransientError(ConnectorError):
    """一時障害（5xx / タイムアウト / 接続エラー）。指数バックオフで再試行する。"""


class RateLimitError(TransientError):
    """HTTP 429。`retry_after` があればそれに従う。"""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class AuthError(ConnectorError):
    """HTTP 401 / 403。**リトライしない。** 認証情報の誤りは待っても直らない。"""


class NotFoundError(ConnectorError):
    """HTTP 404。対象なしとしてスキップし `data_gaps` に記録する。"""


class SchemaDriftError(ConnectorError):
    """レスポンス構造が想定と違う。

    無料APIは予告なく構造を変える。静かに壊れるのが最悪なので、
    リトライせず Raw層に生レスポンスを残して例外にする。
    """

    def __init__(self, message: str, *, source: str = "", endpoint: str = "") -> None:
        super().__init__(message)
        self.source = source
        self.endpoint = endpoint


class ConfigurationError(ConnectorError):
    """必須設定（APIキー、User-Agent など）が欠けている。"""


class SourceDisabledError(ConnectorError):
    """`enabled: false` のソースを呼び出した。"""
