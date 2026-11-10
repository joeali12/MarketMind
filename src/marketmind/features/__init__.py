"""Feature and target construction."""

from marketmind.features.rfm import build_rfm
from marketmind.features.target import (
    assert_full_target_window,
    build_customer_modeling_table,
    build_target_spend,
)

__all__ = [
    "assert_full_target_window",
    "build_customer_modeling_table",
    "build_rfm",
    "build_target_spend",
]
