"""LLM 層の例外。"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 層の基底例外。"""


class KillSwitchActive(LLMError):
    """キルスイッチが立っている。定量スコアのみで続行すること。"""


class CostCapExceeded(LLMError):
    def __init__(self, *, estimated: float, remaining: float) -> None:
        self.estimated = estimated
        self.remaining = remaining
        super().__init__(
            f"LLM コスト上限を超えます（見積 ${estimated:.4f}、残り ${remaining:.4f}）"
        )


class SensitiveDataInPromptError(LLMError):
    """保有株数・取得単価・総資産などをプロンプトに含めようとした。"""


class SchemaRetryExhausted(LLMError):
    """構造化出力のスキーマ検証が 2 回失敗した。"""


class InvariantViolationError(ValueError):
    """推奨の不変条件違反（bear case / 信頼区間 / 引用）。"""
