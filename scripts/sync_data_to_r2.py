#!/usr/bin/env python3
"""ローカル DATA_DIR の Parquet / blob を Cloudflare R2 へ同期する。

必要環境変数:
  S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
  WAREHOUSE_URI=s3://bucket/prefix
  BLOB_URI=s3://bucket/prefix（任意）
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

from packages.core.config import get_settings


def _client(settings):
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("boto3 が必要です: uv sync --extra cloud") from exc
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
    )


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"s3:// URI が必要です: {uri}")
    rest = uri[5:]
    bucket, _, prefix = rest.partition("/")
    return bucket, prefix.rstrip("/")


def _upload_tree(client, root: Path, uri: str, *, dry_run: bool) -> int:
    if not root.exists():
        print(f"skip missing {root}")
        return 0
    bucket, prefix = _parse_s3_uri(uri)
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        key = f"{prefix}/{rel}" if prefix else rel
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        print(f"{'DRY ' if dry_run else ''}PUT s3://{bucket}/{key} ({path.stat().st_size} bytes)")
        if not dry_run:
            client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": ctype})
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.uses_object_storage:
        print("S3_ENDPOINT_URL と WAREHOUSE_URI を設定してください", file=sys.stderr)
        return 2
    assert settings.warehouse_uri
    client = _client(settings)
    total = 0
    total += _upload_tree(client, settings.parquet_dir, settings.warehouse_uri, dry_run=args.dry_run)
    if settings.blob_uri:
        total += _upload_tree(client, settings.blob_dir, settings.blob_uri, dry_run=args.dry_run)
    print(f"done files={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
