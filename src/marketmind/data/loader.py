"""Load Online Retail II workbooks and prepared tabular files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from marketmind.config import DEFAULT_RAW_XLSX, EXPECTED_SHEETS
from marketmind.data.schema import SchemaError, to_canonical, validate_source_columns


def list_excel_sheets(path: Path | str) -> list[str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    xl = pd.ExcelFile(path)
    return list(xl.sheet_names)


def load_online_retail_ii(
    path: Path | str | None = None,
    *,
    sheets: tuple[str, ...] | None = None,
    canonicalize: bool = True,
) -> pd.DataFrame:
    """Load and concatenate UCI Online Retail II sheets.

    Parameters
    ----------
    path:
        Path to the `.xlsx` workbook. Defaults to `data/raw/online_retail_II.xlsx`.
    sheets:
        Sheet names to load. Defaults to config EXPECTED_SHEETS; if a sheet is
        missing, raises with the actual sheet list.
    canonicalize:
        If True, rename to internal column names after validation.
    """
    path = Path(path) if path is not None else DEFAULT_RAW_XLSX
    if not path.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {path}. "
            "Run: python scripts/download_online_retail_ii.py"
        )

    available = list_excel_sheets(path)
    wanted = list(sheets) if sheets is not None else list(EXPECTED_SHEETS)
    missing = [s for s in wanted if s not in available]
    if missing:
        raise SchemaError(
            f"Missing sheet(s) {missing}. Available sheets: {available}"
        )

    frames: list[pd.DataFrame] = []
    for sheet in wanted:
        part = pd.read_excel(path, sheet_name=sheet)
        part = part.copy()
        part["_source_sheet"] = sheet
        frames.append(part)

    raw = pd.concat(frames, ignore_index=True)
    # Excel may mix int/str invoice codes (e.g. cancellations starting with C).
    for col in ("Invoice", "StockCode", "Description", "Country"):
        if col in raw.columns:
            raw[col] = raw[col].astype("string")

    # Validate on business columns only
    business_cols = [c for c in raw.columns if c != "_source_sheet"]
    result = validate_source_columns(business_cols)
    if not result.ok:
        raise SchemaError(result.message)

    if canonicalize:
        source_sheet = raw["_source_sheet"].copy()
        canon = to_canonical(raw.drop(columns=["_source_sheet"]))
        canon["_source_sheet"] = source_sheet
        return canon
    return raw


def inspect_workbook(path: Path | str | None = None) -> dict[str, Any]:
    """Return sheet names, per-sheet columns/dtypes/row counts without full concat canon."""
    path = Path(path) if path is not None else DEFAULT_RAW_XLSX
    sheets = list_excel_sheets(path)
    info: dict[str, Any] = {"path": str(path), "sheets": {}}
    for sheet in sheets:
        df = pd.read_excel(path, sheet_name=sheet)
        info["sheets"][sheet] = {
            "n_rows": int(len(df)),
            "n_cols": int(df.shape[1]),
            "columns": [str(c) for c in df.columns],
            "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        }
    info["total_rows_all_sheets"] = int(
        sum(v["n_rows"] for v in info["sheets"].values())
    )
    return info
