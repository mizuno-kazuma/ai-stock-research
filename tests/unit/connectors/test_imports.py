"""全コネクタが API キーなしの環境で import・初期化できること。

キーが無いだけで import が壊れると、CI と開発環境でテストが回らなくなる。
"""

from __future__ import annotations

import pytest

from packages.core.connectors import get_connector
from packages.core.connectors.edgar import edgar_urls, validate_user_agent
from packages.core.connectors.errors import ConfigurationError, SourceDisabledError

CONNECTORS = ["jquants", "yfinance", "edinet", "edgar", "fred"]


@pytest.mark.parametrize("name", [*CONNECTORS, "tdnet"])
def test_connector_class_resolves(name: str) -> None:
    cls = get_connector(name)
    assert cls.source == name


@pytest.mark.parametrize("name", CONNECTORS)
def test_connector_instantiates_without_api_key(name: str, tmp_path, monkeypatch) -> None:
    for var in (
        "JQUANTS_API_KEY",
        "EDINET_SUBSCRIPTION_KEY",
        "FRED_API_KEY",
        "EDGAR_USER_AGENT",
    ):
        monkeypatch.delenv(var, raising=False)
    connector = get_connector(name)(data_dir=tmp_path)
    assert connector.source == name
    connector.close()


def test_tdnet_is_disabled_by_default(tmp_path) -> None:
    """規約がグレーであるため既定は無効。明示的な有効化を要求する。"""
    with pytest.raises(SourceDisabledError):
        get_connector("tdnet")(data_dir=tmp_path, contact="me@example.com")


def test_edgar_requires_contact_in_user_agent() -> None:
    with pytest.raises(ConfigurationError):
        validate_user_agent("")
    with pytest.raises(ConfigurationError):
        validate_user_agent("bot")
    assert validate_user_agent("AI Stock Research (me@example.com)")


def test_edgar_cik_zero_padding_differs_by_url_kind() -> None:
    """submissions は10桁ゼロ埋め、Archives は整数。取り違えると404になる。"""
    urls = edgar_urls("320193", "0000320193-26-000012", "aapl-20260331.htm")
    assert urls.submissions_json.endswith("CIK0000320193.json")
    assert "edgar/data/320193/000032019326000012" in urls.primary_doc
    assert urls.filing_index.endswith("0000320193-26-000012-index.htm")
