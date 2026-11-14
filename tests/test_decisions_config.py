"""Guard resolved product decisions in config + saved metadata."""

from __future__ import annotations

import json

from marketmind.config import (
    ACTIONS_APPROVED,
    ARTIFACTS_DIR,
    CURRENCY_CONFIRMED,
    CURRENCY_LABEL,
    PREFERRED_DEPLOY_HOST,
)


def test_resolved_local_config_decisions():
    assert CURRENCY_LABEL == "GBP (£)"
    assert CURRENCY_CONFIRMED is True
    assert ACTIONS_APPROVED is False
    assert PREFERRED_DEPLOY_HOST == "streamlit_community_cloud"


def test_metadata_matches_resolved_decisions_and_keeps_metrics():
    meta = json.loads((ARTIFACTS_DIR / "model_metadata.json").read_text())
    assert meta["currency_confirmed"] is True
    assert meta["currency_label"] == "GBP (£)"
    assert meta["actions_approved"] is False
    assert "eligible positive spend" in meta["eligible_spend_policy"].lower()
    assert "not net revenue" in meta["eligible_spend_policy"].lower()
    assert meta["deployment"]["preferred_host"] == "streamlit_community_cloud"
    assert meta["deployment"]["public_publish_approved"] is True
    # Verified held-out metrics must remain intact
    assert abs(meta["test_metrics"]["mae"] - 452.1043604769556) < 1e-9
    assert abs(meta["test_metrics"]["rmse"] - 2650.9479236140055) < 1e-9
    assert abs(meta["test_metrics"]["r2"] - 0.347425626856006) < 1e-12
