# Hugging Face Space README template (DO NOT publish without approval)

Copy into the Space repo only when the user approves HF Spaces deployment (D1/D8).

```yaml
---
title: MarketMind
emoji: 📊
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: RFM segments and 90-day spend estimates
---
```

Use the repository `Dockerfile`. Streamlit runs on port 7860. Do **not** use Gradio ZeroGPU for this app.

Include `artifacts/*.joblib` + `model_metadata.json` and processed demo customer tables if the Space should run without retraining. Never commit `data/raw/online_retail_II.xlsx`.
