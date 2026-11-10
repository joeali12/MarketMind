# MarketMind UI design system

Calm, premium financial analytics for a busy shop owner. Visual-only; ML unchanged.

## Brand colors

| Token | Hex | Use |
|---|---|---|
| Navy | `#13243A` | Primary text, navigation |
| Teal | `#0F5B5A` | Brand / primary actions |
| Emerald | `#16835D` | Positive financial emphasis |
| Off-white | `#F6F8F7` | Page background |
| White | `#FFFFFF` | Cards / surfaces |
| Muted slate | `#667085` | Secondary text |
| Gold | `#C59A3B` | Occasional highlight only |
| Red | theme error | Errors / negative only |

No gradients, neon, or competing accent rainbows.

## Typography

| Role | Arabic | English |
|---|---|---|
| Headings / short labels | **EYENAmmon Bold** (`static/fonts/EYENAmmon-Bold.ttf`) | System UI sans (`-apple-system`, `BlinkMacSystemFont`, …) |
| Body / tables / forms | Noto Sans Arabic (regular) | Same system UI sans |
| Code | monospace | monospace |

Bold display font is **not** used for long paragraphs.

## Layout

- Wide shell, white bordered cards, generous padding
- Home: four tasks — upload, store dashboard, customer groups, customer profile
- Technical detail behind **Learn more** expanders
- Dual light/dark in `.streamlit/config.toml`; light is the product default

## Motion

- Native Streamlit only + `prefers-reduced-motion`
- No swipe-only controls; language switch in sidebar

## Font hosting

`[server] enableStaticServing = true` + `[[theme.fontFaces]]` for EYENAmmon.
Restart Streamlit after enabling static serving so `/app/static/...` routes register.
