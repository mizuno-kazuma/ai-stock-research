"""OpenAPI から `apps/web/lib/api-types.generated.ts` を生成する（T-API-01）。

    uv run python scripts/gen_api_types.py
    uv run python scripts/gen_api_types.py --check

生成物は UTF-8（BOM なし）・改行 LF。CI は `--check` でコミット済みファイルとの差分を見る。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "apps" / "web" / "lib" / "api-types.generated.ts"
CLI_JS = ROOT / "apps" / "web" / "node_modules" / "openapi-typescript" / "bin" / "cli.js"


def _node_bin() -> str:
    found = shutil.which("node")
    extra = [
        Path("/mnt/c/Program Files/Volta/node.exe"),
        Path(r"C:\Program Files\Volta\node.exe"),
        Path("/mnt/c/Program Files/nodejs/node.exe"),
        Path(r"C:\Program Files\nodejs\node.exe"),
    ]
    # WSL 上の Linux node を優先。Windows の node.exe はパス変換が必要。
    if found and not found.lower().endswith(".exe"):
        return found
    for cand in extra:
        if cand.is_file():
            return str(cand)
    if found:
        return found
    raise SystemExit(
        "node が見つかりません。openapi-typescript を実行できません。"
        " Node.js を入れたうえで `pnpm --filter web install` を実行してください。"
    )


def _is_windows_exe(path: str) -> bool:
    return path.lower().endswith(".exe")


def _node_arg(path: Path, windows_node: bool) -> str:
    """Windows の node.exe に渡すパス。WSL の /mnt/c/... を C:\\... に変換する。"""
    text = str(path.resolve())
    if windows_node and text.startswith("/mnt/") and len(text) > 6 and text[6] == "/":
        return f"{text[5].upper()}:{text[6:].replace('/', '\\')}"
    return text


def export_openapi_text() -> str:
    sys.path.insert(0, str(ROOT))
    try:
        from packages.schemas.export import build_openapi
    except ImportError:
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        proc = subprocess.run(
            [uv, "run", "python", "-m", "services.api.export_openapi"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        return proc.stdout
    spec = build_openapi()
    import json

    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _normalize_ts(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    return text


def generate(dest: Path) -> None:
    if not CLI_JS.is_file():
        raise SystemExit(
            f"{CLI_JS} がありません。`pnpm --filter web add -D openapi-typescript` を実行してください。"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = export_openapi_text()
    # Windows node.exe は WSL の /tmp を読めないので、成果物と同じ NTFS 上に中間ファイルを置く。
    spec_path = dest.parent / ".openapi.tmp.json"
    out_tmp = dest.parent / ".api-types.tmp.ts"
    node = _node_bin()
    windows_node = _is_windows_exe(node)
    try:
        spec_path.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run(
            [
                node,
                _node_arg(CLI_JS, windows_node),
                _node_arg(spec_path, windows_node),
                "-o",
                _node_arg(out_tmp, windows_node),
            ],
            cwd=ROOT / "apps" / "web",
            check=True,
        )
        generated = out_tmp.read_text(encoding="utf-8")
    finally:
        spec_path.unlink(missing_ok=True)
        out_tmp.unlink(missing_ok=True)
    dest.write_text(_normalize_ts(generated), encoding="utf-8", newline="\n")


def check() -> int:
    fresh = GENERATED.parent / ".api-types.check.ts"
    try:
        generate(fresh)
        expected = _normalize_ts(fresh.read_text(encoding="utf-8"))
    finally:
        fresh.unlink(missing_ok=True)
    if not GENERATED.is_file():
        print(
            "apps/web/lib/api-types.generated.ts がありません。"
            "`uv run python scripts/gen_api_types.py` を実行してください。"
        )
        return 1
    actual = _normalize_ts(GENERATED.read_text(encoding="utf-8"))
    if actual != expected:
        print(
            "API 型が古くなっています。`uv run python scripts/gen_api_types.py` を実行してください。",
            file=sys.stderr,
        )
        return 1
    print("T-API-01: apps/web/lib/api-types.generated.ts は OpenAPI と一致しています。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAPI から TS 型を生成する")
    parser.add_argument("--check", action="store_true", help="生成し直してコミット済みファイルと差分比較する")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    generate(GENERATED)
    print(f"wrote {GENERATED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
