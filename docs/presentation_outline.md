# Presentation outline (10–12 slides, ~10 min) — UNPUBLISHED DRAFT

Numbers from `artifacts/model_metadata.json` / reports (verified). Live URL: pending publish approval.

1. **Title** — MarketMind: segment customers and estimate next-90-day spend.
2. **Problem** — SMEs treat customers alike; need prioritization for rewards/re-engagement.
3. **Data** — UCI Online Retail II; 1,067,371 source rows; 2009-12-01 → 2011-12-09; DOI credit.
4. **Cleaning** — −34,335 exact duplicates; −235,151 missing ID → 797,885 cleaned; cancellations tagged.
5. **EDA** — Monthly volume varies; spend skewed; UK ~82.8% eligible spend; cancellations ~2.3%; outlier-sensitive monetary values.
6. **RFM** — R=days since last eligible purchase; F=distinct invoices; M=eligible spend; full-history lookback; cutoff-safe.
7. **Segments / PCA** — k=2 (silhouette 0.425 vs k=3 0.329); labels *Recent high-spend* (n=1,632) / *Lapsed low-spend* (n=2,684); PCA ~94% variance in 2D (viz only). Hierarchical ward sil≈0.418.
8. **90-day target** — Train 2010-12-11; test 2011-09-10; features ≤ cutoff; target in (T, T+90].
9. **Results** — Baseline test MAE 609.26 vs GB MAE 452.10, RMSE 2650.95, R² 0.347.
10. **App** — Streamlit demo: validation, segments, customer lookup, provisional heuristics. URL pending.
11. **Limitations / next** — Historical data; high zero-target rate; eligible positive spend (not net revenue); provisional heuristic actions only; public deploy not approved.

Screenshot: `docs/screenshots/home.png` (current Next product upload UI). GIF optional later.
