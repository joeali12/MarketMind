"""Reusable plotting helpers (matplotlib figures saved by training/EDA scripts)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def save_residual_plots(predictions: pd.DataFrame, path: Path) -> Path:
    """Save residual scatter + histogram from columns y_pred, residual."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].scatter(predictions["y_pred"], predictions["residual"], s=8, alpha=0.35)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xlabel("Predicted 90-day spend")
    axes[0].set_ylabel("Residual (actual − predicted)")
    axes[0].set_title("Test residuals vs prediction")
    axes[1].hist(predictions["residual"], bins=40)
    axes[1].set_xlabel("Residual")
    axes[1].set_title("Residual distribution (test)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
