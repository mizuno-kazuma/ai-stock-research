"""S3 互換オブジェクトストレージ（Cloudflare R2）向けの DuckDB 設定。

小規模クラウドではまず Fly Volume に DATA_DIR を載せる。
データ量が増えたら Parquet / blob を R2 へ移し、DuckDB の httpfs で読む。
"""

from __future__ import annotations

import logging
from typing import Any

from packages.core.config.settings import Settings

logger = logging.getLogger(__name__)


def configure_duckdb_s3(connection: Any, settings: Settings) -> bool:
    """DuckDB 接続に R2/S3 認証を載せる。設定が無ければ何もしない。

    Returns:
        httpfs を有効化したら True。
    """
    if not settings.uses_object_storage:
        return False
    endpoint = (settings.s3_endpoint_url or "").removeprefix("https://").removeprefix("http://")
    key = settings.s3_access_key_id.get_secret_value()
    secret = settings.s3_secret_access_key.get_secret_value()
    if not key or not secret:
        raise RuntimeError("S3_ENDPOINT_URL 利用時は S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY が必要です。")
    connection.execute("INSTALL httpfs; LOAD httpfs;")
    connection.execute(f"SET s3_endpoint='{endpoint}';")
    connection.execute(f"SET s3_access_key_id='{key}';")
    connection.execute(f"SET s3_secret_access_key='{secret}';")
    connection.execute(f"SET s3_region='{settings.s3_region}';")
    connection.execute("SET s3_url_style='path';")
    connection.execute("SET s3_use_ssl=true;")
    logger.info("DuckDB httpfs configured for endpoint=%s", endpoint)
    return True
