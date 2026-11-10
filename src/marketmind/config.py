"""Central configuration for MarketMind.

Date windows (lookback, cutoffs) that are TBD/data-dependent live here as
explicit placeholders. Do not treat placeholder None/empty values as final
business decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
FIXTURES_DIR = DATA_DIR / "fixtures"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

DEFAULT_RAW_XLSX = RAW_DATA_DIR / "online_retail_II.xlsx"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# Source schema mapping
# Confirmed against the downloaded workbook in Phase 2. Keys are canonical
# internal names; values are source column names as found in the file.
# ---------------------------------------------------------------------------
# Placeholder until Phase 2 inspection writes the confirmed mapping.
SOURCE_COLUMN_MAP: dict[str, str] = {
    "invoice": "Invoice",
    "stock_code": "StockCode",
    "description": "Description",
    "quantity": "Quantity",
    "invoice_date": "InvoiceDate",
    "unit_price": "Price",
    "customer_id": "Customer ID",
    "country": "Country",
}

REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = tuple(SOURCE_COLUMN_MAP.values())

# UCI workbook sheets (confirm in Phase 2)
EXPECTED_SHEETS: tuple[str, ...] = ("Year 2009-2010", "Year 2010-2011")

# ---------------------------------------------------------------------------
# Temporal design — TBD / data-dependent (D4)
# Populate after date-coverage analysis. None means unresolved.
# ---------------------------------------------------------------------------
LOOKBACK_DAYS: int | None = None  # TBD D4
TRAIN_CUTOFFS: list[str] = []  # ISO dates; TBD D4
TEST_CUTOFF: str | None = None  # TBD D4
TARGET_WINDOW_DAYS: int = 90  # PDF-required

# ---------------------------------------------------------------------------
# Modeling defaults (non-TBD engineering choices)
# ---------------------------------------------------------------------------
SEGMENTATION_FEATURE_COLS: tuple[str, ...] = ("recency", "frequency", "monetary")
REGRESSION_FEATURE_COLS: tuple[str, ...] = ("recency", "frequency", "monetary")

# Cluster count is TBD/data-dependent (chosen from training diagnostics).
N_CLUSTERS: int | None = None

# ---------------------------------------------------------------------------
# Display / units — D6 resolved (user 2026-11-06)
# UCI dataset description: unit price in sterling (£). No FX conversion.
# ---------------------------------------------------------------------------
CURRENCY_LABEL: str = "GBP (£)"
CURRENCY_CONFIRMED: bool = True

# Marketing actions remain provisional heuristics (D7); never flip without user approval.
ACTIONS_APPROVED: bool = False

# Preferred future deploy host (D1); public publish not approved (D8).
PREFERRED_DEPLOY_HOST: str = "streamlit_community_cloud"

# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def as_dict() -> dict[str, Any]:
    """Serializable snapshot of current config (no secrets)."""
    return {
        "project_root": str(PROJECT_ROOT),
        "default_raw_xlsx": str(DEFAULT_RAW_XLSX),
        "random_seed": RANDOM_SEED,
        "source_column_map": dict(SOURCE_COLUMN_MAP),
        "expected_sheets": list(EXPECTED_SHEETS),
        "lookback_days": LOOKBACK_DAYS,
        "train_cutoffs": list(TRAIN_CUTOFFS),
        "test_cutoff": TEST_CUTOFF,
        "target_window_days": TARGET_WINDOW_DAYS,
        "n_clusters": N_CLUSTERS,
        "currency_label": CURRENCY_LABEL,
        "currency_confirmed": CURRENCY_CONFIRMED,
        "actions_approved": ACTIONS_APPROVED,
        "preferred_deploy_host": PREFERRED_DEPLOY_HOST,
        "segmentation_feature_cols": list(SEGMENTATION_FEATURE_COLS),
        "regression_feature_cols": list(REGRESSION_FEATURE_COLS),
    }
