#!/usr/bin/env python3
"""クラウド向け DB 初期化。

Neon / Supabase の DATABASE_URL を向けた状態で:

    DATABASE_URL=postgresql+psycopg://... uv run python scripts/cloud_init_db.py
"""

from __future__ import annotations

import json
import sys

from packages.core.config import get_settings, reset_settings_cache
from packages.core.storage import init_all


def main() -> int:
    reset_settings_cache()
    settings = get_settings()
    settings.ensure_directories()
    result = init_all(settings)
    target = settings.sync_database_url.split("@")[-1]
    payload = {"ok": True, "database": target, **{k: str(v) for k, v in result.items()}}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
