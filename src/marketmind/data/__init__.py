"""Data loading, schema validation, quality, and cleaning."""

from marketmind.data.cleaning import CleaningResult, clean_transactions, eligible_positive_spend_mask
from marketmind.data.loader import inspect_workbook, load_online_retail_ii
from marketmind.data.quality import quality_summary_to_frame, summarize_transactions
from marketmind.data.schema import SchemaError, validate_source_columns

__all__ = [
    "CleaningResult",
    "SchemaError",
    "clean_transactions",
    "eligible_positive_spend_mask",
    "inspect_workbook",
    "load_online_retail_ii",
    "quality_summary_to_frame",
    "summarize_transactions",
    "validate_source_columns",
]
