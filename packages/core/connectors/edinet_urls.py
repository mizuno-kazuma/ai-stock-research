"""EDINET 閲覧サイト（人間がブラウザで開く URL）。

docs/06-filings-access.md §3.2。

`api.edinet-fsa.go.jp` は Subscription-Key が必要な API であり、ブラウザ向けではない。
2024 年以降の閲覧 UI は `disclosure2.edinet-fsa.go.jp` で、書類管理番号を
クエリ文字列そのもの（`WZEK0040.aspx?S100XXXX`）として渡す。

`WZEK0040.aspx?S100=S100XXXX`（パラメータ名 S100）は 301 で `wzek0130.aspx`
（規定外操作）へ送られる。WZEK0130 をクエリ無しで開いても同じエラー画面になる。
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

from packages.core.connectors.paths import document_native_id

EDINET_VIEWER_PAGE = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx"
EDINET_SEARCH_TOP = "https://disclosure2.edinet-fsa.go.jp/"

# 例: S100TMMG, S100YZYL。長さは公式に固定されていない。
_EDINET_DOC_ID = re.compile(r"^S[0-9A-Z]{6,}$", re.IGNORECASE)


def is_edinet_native_id(doc_id: str) -> bool:
    native = document_native_id(doc_id).strip()
    return bool(native and _EDINET_DOC_ID.fullmatch(native))


def edinet_viewer_url(doc_id: str) -> str:
    """ブラウザで直接開ける閲覧画面 URL。

    `[要検証]` 公式のディープリンク仕様は公開されていない。2026-09-01 に
    `WZEK0040.aspx?S100TMMG` が HTTP 200「提出書類内容照会画面（提出本文書）」
    になること、`WZEK0040.aspx?S100=S100TMMG` が `wzek0130.aspx` へ 301
    されることを確認した。
    """
    native = document_native_id(doc_id).strip()
    if not is_edinet_native_id(native):
        return EDINET_SEARCH_TOP
    return f"{EDINET_VIEWER_PAGE}?{native}"


def is_usable_edinet_viewer_url(url: str | None, doc_id: str) -> bool:
    """保存済み source_url を人間に出してよいか。

    既知の壊れた形（WZEK0130、`?S100=`、API ホスト、example.invalid）は棄却し、
    呼び出し側で `edinet_viewer_url` から作り直す。
    """
    text = str(url or "").strip()
    if not text:
        return False
    lower = text.lower()
    if "example.invalid" in lower:
        return False
    if "wzek0130" in lower:
        return False
    if "api.edinet-fsa.go.jp" in lower:
        return False

    native = document_native_id(doc_id).strip().upper()
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "wzek0130" in path:
        return False
    if not is_edinet_native_id(native):
        return bool(parsed.scheme and parsed.netloc)

    if "edinet-fsa.go.jp" not in host:
        return False
    if "disclosure" not in host:
        return False

    query = (parsed.query or "").strip()
    if query.upper() == native:
        return True
    pairs = parse_qsl(query, keep_blank_values=True)
    if len(pairs) == 1 and pairs[0][0].upper() == native:
        return True
    return False


def resolve_edinet_source_url(doc_id: str, stored: str | None = None) -> str:
    """一覧・原文リダイレクト用。壊れた保存 URL は doc_id から作り直す。"""
    if is_usable_edinet_viewer_url(stored, doc_id):
        return str(stored).strip()
    if is_edinet_native_id(doc_id):
        return edinet_viewer_url(doc_id)
    text = str(stored or "").strip()
    return text or EDINET_SEARCH_TOP
