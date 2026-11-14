"""Flexible CSV / Excel reading for retail POS exports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd


def list_excel_sheets(path: Path | str) -> list[str]:
    xl = pd.ExcelFile(path)
    return list(xl.sheet_names)


def read_excel_sheet(
    path: Path | str,
    *,
    sheet_name: str | int | None = 0,
    nrows: int | None = None,
) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name if sheet_name is not None else 0, nrows=nrows)


def _try_read_csv(
    path: Path | str,
    *,
    encoding: str,
    sep: str | None,
    nrows: int | None,
) -> pd.DataFrame | None:
    try:
        return pd.read_csv(
            path,
            encoding=encoding,
            sep=sep,
            engine="python" if sep is None else "c",
            nrows=nrows,
            on_bad_lines="skip",
        )
    except Exception:  # noqa: BLE001
        return None


def read_csv_flexible(path: Path | str, *, nrows: int | None = None) -> pd.DataFrame:
    """Try common encodings and delimiters (comma, semicolon, tab) including BOM/UTF-16."""
    encodings = ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "cp1256", "latin-1")
    seps: list[str | None] = [",", ";", "\t", None]  # None → python sniffer
    last_err: Exception | None = None
    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(
                    path,
                    encoding=enc,
                    sep=sep if sep is not None else None,
                    engine="python",
                    nrows=nrows,
                    on_bad_lines="skip",
                )
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
            if df is None or df.empty:
                continue
            # Reject single-column garbage when delimiter was wrong (unless truly 1 col)
            if df.shape[1] == 1 and sep in {",", ";", "\t"}:
                sample = str(df.columns[0]) + str(df.iloc[0, 0] if len(df) else "")
                if any(d in sample for d in (",", ";", "\t")):
                    continue
            return df
    raise ValueError(f"Could not parse CSV with common encodings/delimiters: {last_err}")


def read_upload_source(
    path: Path | str,
    *,
    sheet_name: str | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Read upload bytes with flexible CSV or Excel sheet selection."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return read_csv_flexible(p, nrows=nrows)
    if suffix in {".xlsx", ".xls"}:
        sheets = list_excel_sheets(p)
        if sheet_name:
            if sheet_name not in sheets:
                raise ValueError(f"Worksheet {sheet_name!r} not found. Available: {sheets}")
            return read_excel_sheet(p, sheet_name=sheet_name, nrows=nrows)
        if len(sheets) == 1:
            return read_excel_sheet(p, sheet_name=sheets[0], nrows=nrows)
        # Multi-sheet without selection — still return first for preview only;
        # callers must gate analysis on selected_sheet.
        return read_excel_sheet(p, sheet_name=sheets[0], nrows=nrows)
    raise ValueError("Unsupported file type")


def workbook_info(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() not in {".xlsx", ".xls"}:
        return {"is_workbook": False, "sheets": [], "needs_sheet_selection": False}
    sheets = list_excel_sheets(p)
    return {
        "is_workbook": True,
        "sheets": sheets,
        "needs_sheet_selection": len(sheets) > 1,
    }
