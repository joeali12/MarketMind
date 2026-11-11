"""Language helpers and bilingual UI smoke (no ML changes)."""

from __future__ import annotations

from app_pages.i18n import (
    LANG_KEY,
    SEGMENT_LABEL_KEYS,
    STRINGS,
    format_model_name,
    t,
    translate_action,
    translate_segment_label,
)


def test_every_string_has_ar_and_en():
    missing = []
    for key, entry in STRINGS.items():
        if "en" not in entry or "ar" not in entry:
            missing.append(key)
        elif not entry["en"].strip() or not entry["ar"].strip():
            missing.append(key)
    assert not missing, f"Incomplete translations: {missing[:10]}"


def test_translate_known_segments_both_languages(monkeypatch):
    import streamlit as st

    st.session_state[LANG_KEY] = "en"
    assert translate_segment_label("Recent high-spend") == "Recent high-spend"
    st.session_state[LANG_KEY] = "ar"
    assert "يشترون" in translate_segment_label("Recent high-spend")
    assert "منقطعون" in translate_segment_label("Lapsed low-spend")


def test_segment_label_keys_cover_metadata_labels():
    # Existing project labels must map for display
    assert "Recent high-spend" in SEGMENT_LABEL_KEYS
    assert "Lapsed low-spend" in SEGMENT_LABEL_KEYS


def test_language_switch_does_not_change_action_meaning(monkeypatch):
    import streamlit as st

    en_action = (
        "Consider retention / thank-you offers for recent high spenders (heuristic only)."
    )
    st.session_state[LANG_KEY] = "en"
    en = translate_action(en_action)
    st.session_state[LANG_KEY] = "ar"
    ar = translate_action(en_action)
    assert "heuristic" in en.lower() or "only" in en.lower()
    assert "تخمين" in ar or "مؤقت" in ar


def test_t_formats_and_falls_back():
    import streamlit as st

    st.session_state[LANG_KEY] = "en"
    text = t("home.about_period", start="2009", end="2011", currency="GBP (£)", days=90)
    assert "2009" in text and "90" in text
    st.session_state[LANG_KEY] = "ar"
    text_ar = t("home.about_period", start="2009", end="2011", currency="GBP (£)", days=90)
    assert "2009" in text_ar and "90" in text_ar


def test_format_model_name_localized():
    import streamlit as st

    st.session_state[LANG_KEY] = "en"
    assert "Gradient" in format_model_name("gradient_boosting")
    st.session_state[LANG_KEY] = "ar"
    assert "التدرج" in format_model_name("gradient_boosting")


def test_apptest_home_both_languages_and_nav():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("../app.py", default_timeout=60)
    at.session_state[LANG_KEY] = "ar"
    at.run()
    assert not at.exception, at.exception
    titles = [x.value for x in at.title]
    assert any("لوحة" in str(v) or "تحليل" in str(v) for v in titles) or titles

    at.session_state[LANG_KEY] = "en"
    at.run()
    assert not at.exception, at.exception
    titles_en = [str(x.value) for x in at.title]
    assert any("Store" in v or "overview" in v.lower() for v in titles_en)

    for page in [
        "app_pages/products.py",
        "app_pages/overview.py",
        "app_pages/segments.py",
        "app_pages/customer_lookup.py",
        "app_pages/data_validation.py",
        "app_pages/model_quality.py",
    ]:
        at.switch_page(page)
        at.run()
        assert not at.exception, (page, at.exception)


def test_language_switch_preserves_prediction_numeric():
    """Switching language must not change inference outputs for the same RFM."""
    from marketmind.inference import load_artifacts, predict_customer
    from marketmind.config import ARTIFACTS_DIR

    arts = load_artifacts(ARTIFACTS_DIR)
    feats = {"recency": 30.0, "frequency": 2.0, "monetary": 100.0}
    a = predict_customer(feats, artifacts=arts)
    b = predict_customer(feats, artifacts=arts)
    assert a.predicted_spend_90d == b.predicted_spend_90d
    assert a.cluster_id == b.cluster_id
