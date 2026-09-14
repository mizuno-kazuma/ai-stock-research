#!/usr/bin/env python3
"""SQLite の状態 DB を Postgres へコピーする（小規模向け）。

    DATABASE_URL=postgresql+psycopg://... \\
      SOURCE_SQLITE_URL=sqlite+pysqlite:////path/to/state.sqlite \\
      uv run python scripts/migrate_sqlite_to_postgres.py
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from packages.core.config import get_settings
from packages.core.storage.sqlite_repo import Base


def main() -> int:
    settings = get_settings()
    dest = settings.sync_database_url
    if not dest.startswith("postgresql"):
        print("DATABASE_URL に Postgres を指定してください", file=sys.stderr)
        return 2
    source = os.environ.get("SOURCE_SQLITE_URL") or f"sqlite+pysqlite:///{settings.state_db_path.as_posix()}"
    src_engine = create_engine(source, future=True)
    dst_engine = create_engine(dest, future=True)
    Base.metadata.create_all(dst_engine)
    with Session(src_engine) as src, Session(dst_engine) as dst:
        for table in Base.metadata.sorted_tables:
            rows = [dict(row) for row in src.execute(table.select()).mappings()]
            if not rows:
                print(f"{table.name}: 0 rows")
                continue
            dst.execute(table.delete())
            dst.execute(table.insert(), rows)
            print(f"{table.name}: {len(rows)} rows")
        dst.commit()
    with dst_engine.begin() as conn:
        conn.execute(text("SELECT 1"))
    print("migration complete ->", dest.split("@")[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
