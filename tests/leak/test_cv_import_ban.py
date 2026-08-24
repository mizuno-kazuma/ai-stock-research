"""T-LEAK-01: 禁止された交差検証手法の使用を検出。"""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "packages" / "core"

FORBIDDEN = {
    "KFold",
    "StratifiedKFold",
    "TimeSeriesSplit",
    "train_test_split",
    "cross_val_score",
}


def test_models_package_does_not_use_naive_cv() -> None:
    violations = []
    for py in (CORE / "models").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "sklearn.model_selection":
                for alias in node.names:
                    if alias.name in FORBIDDEN:
                        violations.append(f"{py}:{node.lineno} {alias.name}")
    assert not violations, (
        "時系列データに対する素朴な交差検証は禁止されています。"
        "PurgedWalkForwardCV を使ってください。違反:\n" + "\n".join(violations)
    )
