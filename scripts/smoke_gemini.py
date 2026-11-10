#!/usr/bin/env python3
"""Opt-in manual smoke test for Gemini 2.5 Flash.

Requires a local GEMINI_API_KEY (e.g. from .env). Never prints the key.
Does not run in CI. Usage:

  source .venv/bin/activate
  export PYTHONPATH=src:.
  python scripts/smoke_gemini.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from api.services import gemini_provider
    from api.settings import GEMINI_MODEL, gemini_key_configured, public_gemini_settings

    pub = public_gemini_settings()
    print("public_settings:", pub)
    if not gemini_key_configured():
        print("SKIP: GEMINI_API_KEY not configured. Set it in .env locally.")
        return 2

    # Fixed safe template only — never free-text from a human chat session
    from api.services import gemini_intents

    intent = gemini_intents.SAFE_INTENTS["explain_counts"]
    result = gemini_provider.generate_explanation(
        safe_question=gemini_intents.template_for(intent, lang="en"),
        context_json=(
            '{"source":"upload_session_aggregates","lang":"en",'
            '"safe_intent":"explain_counts",'
            '"disclaimer_en":"server-computed only",'
            '"baseline":{"eligible_spend":1234.5,"currency_code":"EGP"},'
            '"file":{"row_count":100},'
            '"structure":{"eligible_spend":1234.5,"eligible_rows":50},'
            '"findings":[],"cleaning_proposals":[],"segments":[],'
            '"gap_fill_policy":{}}'
        ),
        lang="en",
    )
    if result.ok:
        print(f"OK model={result.model or GEMINI_MODEL}")
        print("answer:", result.text[:500])
        return 0
    print(f"FALLBACK code={result.error_code}")
    print(result.error_en)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
