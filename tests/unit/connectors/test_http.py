"""HTTP クライアントのエラー変換。"""

from __future__ import annotations

import pytest

from packages.core.connectors.errors import TransientError
from packages.core.connectors.http import HttpClient, RetryPolicy


class _MissingFileClient:
    def request(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise FileNotFoundError(2, "No such file or directory")

    def close(self) -> None:
        return None


def test_missing_file_becomes_transient_with_restart_hint() -> None:
    client = HttpClient(
        source="jquants",
        client=_MissingFileClient(),  # type: ignore[arg-type]
        retry=RetryPolicy(max_attempts=1),
    )
    with pytest.raises(TransientError, match="再起動"):
        client.get("https://example.invalid")
    client.close()
