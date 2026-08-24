"""他ワーカーが実装する層（storage / config）に対する契約の宣言。

`packages/core/storage/` と `packages/core/config/` は別担当が実装する。
本パッケージはそれらに依存する側（connectors / factors / models / backtest /
llm / services.agent）が前提としているシグネチャを Protocol として明示し、
実装が未完成の間でもテストを fake で回せるようにするためのものである。

実装が揃った後は、ここの Protocol と実クラスの型が一致することを
mypy が検証する（構造的部分型なので継承は不要）。
"""

from packages.core.interfaces.config import (
    FactorConfigLike,
    SettingsLike,
    SourceConfigLike,
)
from packages.core.interfaces.storage import (
    AlertSink,
    CostBudgetRepo,
    JobRunRepo,
    LlmCallLog,
    MemoryRepo,
    RateLimitStateStore,
    SearchHit,
    StateRepo,
    VectorStore,
    WarehouseRepo,
)

__all__ = [
    "AlertSink",
    "CostBudgetRepo",
    "FactorConfigLike",
    "JobRunRepo",
    "LlmCallLog",
    "MemoryRepo",
    "RateLimitStateStore",
    "SearchHit",
    "SettingsLike",
    "SourceConfigLike",
    "StateRepo",
    "VectorStore",
    "WarehouseRepo",
]
