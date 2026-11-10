# MarketMind assistant — Gemini 2.5 Flash (open-ended + tools)

Gemini explains **server-computed aggregate facts** via an allowlisted **tool-calling** loop. It does **not** replace the PDF-required classical ML models (RFM, K-Means, 90-day spend regression), and it does **not** invent cell values.

## Product behavior

- Ask naturally in Egyptian Arabic or English (including follow-ups). Quick replies are optional hints only.
- Gemini may choose approved analytics tools; the **backend executes every calculation** and validates arguments.
- Deterministic setup (currency, date format, cleaning accept/reject) stays authoritative and never invents IDs/dates.
- Safe fill: preview first; apply only with an explicit user request and only for high-confidence same-file price/description patterns. **Quantity, customer IDs, invoices, and dates stay manual.**

## Privacy (accurate product behavior)

When Gemini is enabled and a request passes the privacy gate:

**May be sent to Google’s Gemini API**

- The user’s free-text question (privacy-cleared; blocked if it looks like identifiers / pasted rows)
- Bounded prior chat turns (scrubbed, short)
- Structured **tool results** that contain only allowlisted aggregates (KPIs, period comparison, product names + units/spend, segment aggregates, forecast status, fill candidate counts)

**Never sent**

- The uploaded file or raw transaction rows / table previews
- Customer IDs, personal names, emails, phones, addresses, invoice IDs, stock codes
- Customer-level purchase histories
- Questions that fail the privacy gate (those stay on the grounded tool path only)

Do not promise unlimited free quota. Chat brands the assistant as **MarketMind** / **مساعد MarketMind**. Model IDs and tool JSON are not shown in bubbles.

## Approved tools

| Tool | Purpose |
|---|---|
| `get_upload_profile` | Structure + findings |
| `get_sales_kpis` | KPIs + month comparison |
| `get_product_leaders` | Top products by units/revenue |
| `get_category_performance` | Categories when mapped |
| `get_customer_segments` | Descriptive RFM aggregates |
| `get_forecast_status` | Availability + limitations |
| `get_missing_and_fill_preview` | Preview only |
| `get_cleaning_impact` | Proposal impacts |
| `apply_safe_fills` | Explicit apply; `confirm_apply=true` required |

Tool rounds are bounded (≤3). Invalid tools/args fail safely. If Gemini is missing/quota/timeout, grounded tool answers keep analytics usable.

## Local setup

1. Create an API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Copy `.env.example` → `.env` and set `GEMINI_API_KEY` (never commit it).
3. `uv pip install -r requirements.txt` then start `uvicorn` with `PYTHONPATH=src:.`.

## Manual smoke (opt-in)

```bash
MARKETMIND_SMOKE_LIVE=1 GEMINI_API_KEY=… PYTHONPATH=src:. python scripts/smoke_open_assistant.py
```

Automated tests mock Gemini and do not spend quota.
