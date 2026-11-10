"""Schema validation and canonical column mapping for Online Retail II."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from marketmind.config import REQUIRED_SOURCE_COLUMNS, SOURCE_COLUMN_MAP


class SchemaError(ValueError):
    """Raised when an input file is missing required fields or types."""


@dataclass(frozen=True)
class SchemaValidationResult:
    ok: bool
    missing_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    message: str


def validate_source_columns(columns: list[str] | pd.Index) -> SchemaValidationResult:
    present = set(map(str, columns))
    required = set(REQUIRED_SOURCE_COLUMNS)
    missing = tuple(sorted(required - present))
    extra = tuple(sorted(present - required))
    if missing:
        return SchemaValidationResult(
            ok=False,
            missing_columns=missing,
            extra_columns=extra,
            message=(
                "Missing required columns: "
                + ", ".join(missing)
                + ". Expected: "
                + ", ".join(REQUIRED_SOURCE_COLUMNS)
            ),
        )
    return SchemaValidationResult(
        ok=True,
        missing_columns=(),
        extra_columns=extra,
        message="Schema OK.",
    )


def to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Rename source columns to internal canonical names."""
    result = validate_source_columns(df.columns)
    if not result.ok:
        raise SchemaError(result.message)
    rename = {src: canon for canon, src in SOURCE_COLUMN_MAP.items()}
    out = df.rename(columns=rename)
    # Keep only canonical + any unexpected extras dropped for modeling path
    keep = list(SOURCE_COLUMN_MAP.keys())
    return out[keep].copy()
