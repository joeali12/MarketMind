"""Derive provisional segment labels from observed RFM profiles only."""

from __future__ import annotations

import pandas as pd


def derive_segment_labels(profiles: pd.DataFrame) -> dict[str, str]:
    """Map cluster_id → descriptive label grounded in profile means.

    Uses median splits on recency (lower = more recent) and monetary value.
    Labels are provisional descriptors, not approved marketing personas.
    """
    required = {"cluster_id", "recency_mean", "monetary_mean"}
    missing = required - set(profiles.columns)
    if missing:
        raise ValueError(f"profiles missing columns: {sorted(missing)}")

    med_r = float(profiles["recency_mean"].median())
    med_m = float(profiles["monetary_mean"].median())
    labels: dict[str, str] = {}
    used: set[str] = set()
    for _, row in profiles.iterrows():
        cid = str(int(row["cluster_id"]))
        recent = float(row["recency_mean"]) <= med_r
        high_m = float(row["monetary_mean"]) >= med_m
        if recent and high_m:
            name = "Recent high-spend"
        elif (not recent) and (not high_m):
            name = "Lapsed low-spend"
        elif recent and (not high_m):
            name = "Recent lower-spend"
        else:
            name = "Older higher-spend"
        # Ensure uniqueness if medians collide
        base = name
        n = 2
        while name in used:
            name = f"{base} ({n})"
            n += 1
        used.add(name)
        labels[cid] = name
    return labels


def provisional_actions_for_labels(labels: dict[str, str]) -> dict[str, str]:
    """Heuristic action text keyed by cluster id. Not approved policy (D7)."""
    actions: dict[str, str] = {}
    for cid, name in labels.items():
        lower = name.lower()
        if "high-spend" in lower and "recent" in lower:
            actions[cid] = (
                "Consider retention / thank-you offers for recent high spenders "
                "(heuristic only)."
            )
        elif "lapsed" in lower or "low-spend" in lower:
            actions[cid] = (
                "Consider cautious re-engagement; expected spend may be low "
                "(heuristic only)."
            )
        elif "recent" in lower:
            actions[cid] = (
                "Consider light nurture / product discovery messages "
                "(heuristic only)."
            )
        else:
            actions[cid] = "Review manually before any outreach (heuristic only)."
    return actions
