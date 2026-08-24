"""引用の正規化と検証（docs/07-llm-rag.md §4.5）。

DOC_NOT_FOUND または QUOTE_NOT_FOUND が 1 つでもある推奨は Critic が rejected にする。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher
from enum import StrEnum

from packages.core.llm.schemas import Citation

GetDocument = Callable[[str], dict | None]
GetDocumentText = Callable[..., str | None]


class CitationVerdict(StrEnum):
    VERIFIED = "VERIFIED"
    VERIFIED_FUZZY = "VERIFIED_FUZZY"
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    QUOTE_NOT_FOUND = "QUOTE_NOT_FOUND"


_SPACE_RE = re.compile(r"[\s\u3000]+")


def normalize_ja(text: str) -> str:
    """全角英数の半角化、空白除去、記号の正規化（NFKC）。"""
    nfkc = unicodedata.normalize("NFKC", text)
    return _SPACE_RE.sub("", nfkc)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def verify_citation(
    c: Citation,
    *,
    get_document: GetDocument,
    get_document_text: GetDocumentText,
) -> CitationVerdict:
    doc = get_document(c.doc_id)
    if doc is None:
        return CitationVerdict.DOC_NOT_FOUND
    text = get_document_text(c.doc_id, page=c.page)
    if text is None:
        return CitationVerdict.PAGE_NOT_FOUND
    n_quote = normalize_ja(c.quote)
    n_text = normalize_ja(text)
    if n_quote in n_text:
        return CitationVerdict.VERIFIED
    # ページ全文との類似度。短い引用が長い本文に埋もれる場合は窓で最大を取る。
    window = max(len(n_quote), 8)
    best = 0.0
    if len(n_text) >= window:
        step = max(1, window // 4)
        for i in range(0, len(n_text) - window + 1, step):
            best = max(best, similarity(n_quote, n_text[i : i + window]))
            if best >= 0.9:
                break
    else:
        best = similarity(n_quote, n_text)
    if best >= 0.9:
        return CitationVerdict.VERIFIED_FUZZY
    return CitationVerdict.QUOTE_NOT_FOUND
