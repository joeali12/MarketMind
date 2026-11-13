# MarketMind UI design system

Calm, premium financial analytics for a busy shop owner. Visual-only; ML unchanged.

## Brand colors

| Token | Hex | Use |
|---|---|---|
| Ink | `#0B1C30` | Primary text |
| Indigo | `#3525CD` | Links and active brand color |
| Violet | `#4F46E5` | Spend chart stroke |
| Inverse pill | `#213145` | Active navigation pill |
| Surface | `#F8F9FF` | Page background |
| White | `#FFFFFF` | Cards |
| Muted | `#464555` | Secondary text |
| Line | `#C7C4D8` | Card and pill borders |

The public shell follows the approved Stitch store screen: pill navigation, rounded cards, and one indigo area chart. Figures stay the UK sample in GBP.

## Typography

| Role | Arabic | English |
|---|---|---|
| Headings / short labels | **EYENAmmon Bold** (`static/fonts/EYENAmmon-Bold.ttf`) | System UI sans (`-apple-system`, `BlinkMacSystemFont`, …) |
| Body / tables / forms | Noto Sans Arabic (regular) | Same system UI sans |
| Code | monospace | monospace |

Bold display font is **not** used for long paragraphs.

## Layout

- Wide shell, white bordered cards, generous padding
- Landing page is the store dashboard: KPI cards, monthly eligible spend, evidence notes, top products
- Top bar only: Dashboard, Products, Groups, Upload, Profile. Summary and Quality stay as text links. Language is a link in the same bar.
- No permanent sidebar. Language switch sits in the top bar on every page
- Technical detail behind **Learn more** expanders
- Dual light/dark in `.streamlit/config.toml`; light is the product default

## Motion

- Native Streamlit only + `prefers-reduced-motion`
- No swipe-only controls

## Font hosting

`[server] enableStaticServing = true` + `[[theme.fontFaces]]` for EYENAmmon.
Restart Streamlit after enabling static serving so `/app/static/...` routes register.
