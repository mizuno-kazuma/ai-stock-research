"""DuckDB / SQLite のスキーマを作成する。

    uv run python -m packages.core.storage.init_db

冪等なので何度実行してもよい。
"""

from __future__ import annotations

import json
import logging
import sys

from packages.core.config import get_settings

from . import init_all


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    result = init_all(settings)
    if (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
