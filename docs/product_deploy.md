# Product deploy (Next.js + FastAPI)

The **real product UI** is `web/` (Next.js) talking to `api/` (FastAPI).  
Streamlit (`app.py` on Community Cloud) is the **academic PDF** app only — segments / CLV / model pages for the course brief. It is not the product shell.

## Why Streamlit looked “like another project”

- Community Cloud entrypoint is `app.py` → classic `app_pages/*` multipage academic UI.
- Next.js routes (`/upload`, `/store`, …) never run on Streamlit Cloud.
- Optional Stitch HTML (`?stitch=1`) is a static export; `/app/static/stitch/...` does not replace the Next app.

## Live (2026-11-14)

| Piece | URL |
|-------|-----|
| Next.js product | https://marketmind-web-ochre.vercel.app/ |
| FastAPI | https://marketmind-api-phi.vercel.app/ |
| Streamlit PDF | https://marketmind-grad.streamlit.app/ |

## Recommended public stack

| Piece | Host | Notes |
|-------|------|--------|
| Next.js `web/` | **Vercel** | Root directory `web`. Set `MARKETMIND_API_URL` to the public API origin (no trailing slash). |
| FastAPI `api/` | **Render** (Docker) or Railway / Fly | Use `Dockerfile.api` + `render.yaml`. Set `ALLOWED_ORIGINS` to the Vercel URL(s). Optional `GEMINI_API_KEY`. |
| Streamlit `app.py` | Streamlit Community Cloud | PDF-only. Live: https://marketmind-grad.streamlit.app/ |

### Vercel (web)

```bash
cd web
vercel link --yes --project marketmind-web
vercel env add MARKETMIND_API_URL production   # https://<api-host>
vercel deploy --prod --yes
```

`next.config.ts` rewrites `/api/*` → `$MARKETMIND_API_URL/api/*` at build time.

### Render (API)

1. Dashboard → New → Blueprint → this repo’s `render.yaml`.
2. After deploy, copy the service URL into Vercel `MARKETMIND_API_URL`.
3. Set `ALLOWED_ORIGINS` to `https://<your-vercel-app>.vercel.app`.

Health check: `GET /api/meta`.
