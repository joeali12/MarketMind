"""Per-upload unsupervised anomaly *review flags* — never auto-delete or invent.

Uses IsolationForest on numeric transaction features only when enough rows exist.
Scores are explanatory flags for human review, not proof of error.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def flag_numeric_anomalies(
    parsed: pd.DataFrame,
    *,
    contamination: float = 0.01,
    random_state: int = 0,
    max_examples: int = 5,
) -> dict[str, Any]:
    """Return review flags for unusual qty/price/line_amount combinations."""
    empty = {
        "available": False,
        "model": None,
        "flagged_rows": 0,
        "examples": [],
        "note_en": "Anomaly review unavailable for this file size or feature set.",
        "note_ar": "مراجعة الشذوذ مش متاحة لحجم الملف أو الأعمدة دي.",
        "is_proof_of_error": False,
    }
    feature_cols = [c for c in ("quantity", "unit_price", "line_amount") if c in parsed.columns]
    if len(feature_cols) < 2 or len(parsed) < 50:
        return empty

    X = parsed[feature_cols].apply(pd.to_numeric, errors="coerce")
    mask = X.notna().all(axis=1) & np.isfinite(X).all(axis=1)
    usable = X.loc[mask]
    if len(usable) < 50:
        return empty

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return {**empty, "note_en": "scikit-learn not available for anomaly flags."}

    # Fit only on this upload — no claim of a general cleaning model
    clf = IsolationForest(
        contamination=min(max(contamination, 0.005), 0.05),
        random_state=random_state,
        n_estimators=100,
    )
    labels = clf.fit_predict(usable.values)
    scores = -clf.score_samples(usable.values)  # higher = more anomalous
    flagged_idx = usable.index[labels == -1]
    examples = []
    ranked = (
        pd.DataFrame({"idx": flagged_idx, "score": scores[labels == -1]})
        .sort_values("score", ascending=False)
        .head(max_examples)
    )
    for _, row in ranked.iterrows():
        r = parsed.loc[row["idx"]]
        qty = float(r["quantity"]) if pd.notna(r.get("quantity")) else None
        price = float(r["unit_price"]) if pd.notna(r.get("unit_price")) else None
        evidence = []
        if qty is not None and abs(qty) >= usable["quantity"].quantile(0.99):
            evidence.append(f"quantity {qty} is in the top 1% of this file")
        if price is not None and abs(price) >= usable["unit_price"].quantile(0.99):
            evidence.append(f"unit price {price} is in the top 1% of this file")
        if not evidence:
            evidence.append("unusual combination of quantity and unit price vs this file")
        examples.append(
            {
                "invoice": None if pd.isna(r.get("invoice")) else str(r.get("invoice"))[:40],
                "stock_code": None if pd.isna(r.get("stock_code")) else str(r.get("stock_code")),
                "quantity": qty,
                "unit_price": price,
                "anomaly_score": float(row["score"]),
                "evidence_en": "; ".join(evidence),
                "review_only": True,
            }
        )

    return {
        "available": True,
        "model": "IsolationForest (fit on this upload only)",
        "features": feature_cols,
        "flagged_rows": int(len(flagged_idx)),
        "examples": examples,
        "is_proof_of_error": False,
        "note_en": (
            "These are review flags from an unsupervised model fit on this file only. "
            "They are not proof of error and never auto-delete or change rows. "
            "No general-purpose cleaning model is claimed."
        ),
        "note_ar": (
            "دي علامات مراجعة من موديل بدون تسميات اتدرب على الملف ده فقط. "
            "مش إثبات غلط ومش بتمسح أو تعدّل صفوف لوحدها. "
            "مفيش ادعاء بموديل تنظيف عام."
        ),
    }
