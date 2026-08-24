"""データソース Connector 群。

docs/02-data-ingestion.md に対応する。設計上の制約（`fetch` は保存のみ /
`normalize` はネットワークに触らない / `upsert` は冪等）は
`packages.core.connectors.base` の docstring を参照。
"""

from packages.core.connectors.base import (
    Checkpoint,
    Connector,
    FetchWindow,
    HttpConnector,
    RawBatch,
    tag_table,
)
from packages.core.connectors.errors import (
    AuthError,
    ConfigurationError,
    ConnectorError,
    NotFoundError,
    RateLimitError,
    SchemaDriftError,
    SourceDisabledError,
    TransientError,
)
from packages.core.connectors.http import HttpClient, RetryPolicy, mask_url
from packages.core.connectors.paths import (
    blob_path,
    is_valid_path_component,
    raw_path,
    safe_component,
)
from packages.core.connectors.quality import (
    QualityResult,
    validate_price_frame,
    validate_price_row,
)
from packages.core.connectors.rate_limit import InMemoryRateLimitStore, TokenBucket
from packages.core.connectors.raw_store import RawStore
from packages.core.connectors.sources_config import (
    SourcesConfig,
    jquants_plan_params,
    load_sources_config,
)

__all__ = [
    "AuthError",
    "Checkpoint",
    "ConfigurationError",
    "Connector",
    "ConnectorError",
    "FetchWindow",
    "HttpClient",
    "HttpConnector",
    "InMemoryRateLimitStore",
    "NotFoundError",
    "QualityResult",
    "RateLimitError",
    "RawBatch",
    "RawStore",
    "RetryPolicy",
    "SchemaDriftError",
    "SourceDisabledError",
    "SourcesConfig",
    "TokenBucket",
    "TransientError",
    "blob_path",
    "is_valid_path_component",
    "jquants_plan_params",
    "load_sources_config",
    "mask_url",
    "raw_path",
    "safe_component",
    "tag_table",
    "validate_price_frame",
    "validate_price_row",
]


def get_connector(name: str) -> type[Connector]:
    """名前から Connector クラスを解決する。

    各コネクタは重い依存（yfinance など）を持つため遅延 import する。
    """
    if name == "jquants":
        from packages.core.connectors.jquants import JQuantsConnector

        return JQuantsConnector
    if name == "yfinance":
        from packages.core.connectors.yfinance import YFinanceConnector

        return YFinanceConnector
    if name == "edinet":
        from packages.core.connectors.edinet import EdinetConnector

        return EdinetConnector
    if name == "tdnet":
        from packages.core.connectors.tdnet import TdnetConnector

        return TdnetConnector
    if name == "edgar":
        from packages.core.connectors.edgar import EdgarConnector

        return EdgarConnector
    if name == "fred":
        from packages.core.connectors.fred import FredConnector

        return FredConnector
    raise KeyError(f"未知のコネクタ: {name}")
