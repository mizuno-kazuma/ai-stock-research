"""共有ロジック（docs/01-architecture.md §3）。

サブパッケージ:

- `config`  … 設定とモデル識別子（このワーカーの担当）
- `storage` … DuckDB / SQLite / Parquet / LanceDB（このワーカーの担当）
- `connectors`, `factors`, `models`, `backtest`, `llm` … データ・エージェント担当

このモジュールではサブパッケージを import しない。未実装のサブパッケージが
あっても `packages.core.config` などが読めるようにするため。
"""

__all__: list[str] = []
