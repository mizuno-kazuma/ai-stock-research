"""OpenAPI JSON を標準出力に書き出す。

    uv run python -m packages.schemas.export > openapi.json
    npx openapi-typescript openapi.json -o apps/web/lib/api-types.ts

CI ではこの出力と `apps/web/lib/api-types.ts` の再生成結果を突き合わせ、
差分があれば失敗させる（docs/12-testing-validation.md T-API-01）。

`services.api` を import するのは main() の中だけにしてある。
スキーマだけを使いたい利用側に FastAPI 依存を強制しないため。
"""

from __future__ import annotations

import json
import sys
from typing import Any


def build_openapi() -> dict[str, Any]:
    from services.api.main import create_app

    app = create_app()
    return app.openapi()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    spec = build_openapi()
    # ensure_ascii=False で日本語の description をそのまま出す。
    # sort_keys=True にするのは CI の差分比較を安定させるため。
    text = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True)

    if argv and argv[0] not in {"-", "--stdout"}:
        from pathlib import Path

        out = Path(argv[0])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8", newline="\n")
        return 0

    # 標準出力のエンコーディングを UTF-8 に固定する
    # （日本語ロケール Windows では cp932 になり得る。docs/15-windows-runtime.md §4.6）
    if (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
