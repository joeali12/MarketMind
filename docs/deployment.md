# Deployment prep (not published)

**Status:** Local prep only.  
**D1:** Preferred future host = **Streamlit Community Cloud**.  
**D8:** Public deploy / external publication = **not approved**. Do not publish until explicitly authorized.

## Preferred path — Streamlit Community Cloud

When (and only when) publish is approved:

1. Push this repo to GitHub (user action).
2. Create an app at https://share.streamlit.io pointing at `app.py`.
3. Set Python to 3.12; dependencies from `requirements.txt`.
4. Ensure `artifacts/*.joblib` and `artifacts/model_metadata.json` are in the repo.
5. Do **not** upload `data/raw/online_retail_II.xlsx` (gitignored). Demo uses saved customer tables / artifacts.

## Fallback template — Hugging Face Spaces (Docker)

`Dockerfile` and `docs/hf_space_readme_template.md` exist for a Docker Space if the preferred host is later declined. Do not create or publish a Space without approval.

## Smoke checklist after a future public URL exists

- [ ] Opens in a private browser window
- [ ] Demo customer lookup returns segment + prediction
- [ ] Invalid upload shows a message without crash
- [ ] Missing artifacts would show setup error
- [ ] Record URL in README and presentation only after verification
