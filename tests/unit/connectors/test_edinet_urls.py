"""EDINET 閲覧 URL は WZEK0130（規定外操作）を踏まない。"""

from __future__ import annotations

from packages.core.connectors.edinet import EdinetConnector
from packages.core.connectors.edinet_urls import (
    edinet_viewer_url,
    is_usable_edinet_viewer_url,
    resolve_edinet_source_url,
)


def test_viewer_url_uses_doc_id_as_query_string() -> None:
    url = edinet_viewer_url("edinet:S100YZYL")
    assert url == "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100YZYL"
    assert "wzek0130" not in url.lower()
    assert "S100=" not in url
    assert EdinetConnector.viewer_url("S100TMMG") == (
        "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100TMMG"
    )


def test_stale_s100_named_param_and_wzek0130_are_rewritten() -> None:
    native = "edinet:S100YZYL"
    good = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100YZYL"
    assert is_usable_edinet_viewer_url(good, native)
    assert not is_usable_edinet_viewer_url(
        "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100=S100YZYL", native
    )
    assert not is_usable_edinet_viewer_url(
        "https://disclosure2.edinet-fsa.go.jp/wzek0130.aspx", native
    )
    assert not is_usable_edinet_viewer_url("", native)
    assert not is_usable_edinet_viewer_url("https://example.invalid/S100YZYL", native)
    assert not is_usable_edinet_viewer_url(
        "https://api.edinet-fsa.go.jp/api/v2/documents/S100YZYL", native
    )
    assert resolve_edinet_source_url(
        native, "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100=S100YZYL"
    ) == good
    assert resolve_edinet_source_url(
        native, "https://disclosure2.edinet-fsa.go.jp/wzek0130.aspx"
    ) == good
