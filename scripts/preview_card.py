"""Render sample quote + code cards to tmp/ for visual eyeballing."""

from __future__ import annotations

from pathlib import Path

from agent.generators.image_card import render_code_card, render_quote_card

OUT = Path("tmp")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    (OUT / "preview_quote.png").write_bytes(
        render_quote_card(
            "Three years ago I shipped a model with no test coverage.\n"
            "It cost us a quarter."
        )
    )
    (OUT / "preview_code_sql.png").write_bytes(
        render_code_card(
            "WITH ranked AS (\n"
            "  SELECT id, score,\n"
            "         RANK() OVER (PARTITION BY region ORDER BY score DESC) AS r\n"
            "  FROM customers\n"
            ")\n"
            "SELECT * FROM ranked WHERE r <= 3;",
            language="sql",
        )
    )
    (OUT / "preview_code_python.png").write_bytes(
        render_code_card(
            "def shap_values(model, X):\n"
            "    explainer = shap.TreeExplainer(model)\n"
            "    return explainer(X)",
            language="python",
        )
    )
    print(f"Wrote previews to {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
