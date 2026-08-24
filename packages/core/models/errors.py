"""予測モデルの例外。

GARCH が収束しない・定常でない場合は例外にし、発散した予測値を静かに
使わない（docs/04-analysis-engine.md §1.3.1）。
"""

from __future__ import annotations


class ModelError(Exception):
    """モデル層の基底例外。"""


class GarchConvergenceError(ModelError):
    """GARCH の最適化が収束しなかった。"""


class GarchNonStationaryError(ModelError):
    """alpha + beta >= 1（IGARCH 状態）。予測が発散する。"""


class InsufficientHistoryError(ModelError):
    """推定に必要な履歴長が足りない。"""


class ModelUnavailableError(ModelError):
    """依存ライブラリが無い、または学習済みモデルファイルが無い。"""
