"""T-LEAK-02: prices_live をモデル・バックテストから参照しない。"""

from __future__ import annotations

from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "packages" / "core"


def test_models_and_backtest_do_not_reference_prices_live() -> None:
    violations = []
    for pkg in ["models", "backtest"]:
        for py in (CORE / pkg).rglob("*.py"):
            in_doc = False
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("\"\"\"") or stripped.startswith("'''"):
                    in_doc = not in_doc if stripped.count("\"\"\"") + stripped.count("'''") == 1 else in_doc
                    continue
                if in_doc or stripped.startswith("#"):
                    continue
                if "prices_live" not in line:
                    continue
                if any(tok in line for tok in ("禁止", "raise", "BacktestError", "prices_live を")):
                    continue
                violations.append(f"{py}:{lineno}")
    assert not violations, (
        "prices_live をモデル・バックテストから参照できません。違反:\n"
        + "\n".join(violations)
    )
