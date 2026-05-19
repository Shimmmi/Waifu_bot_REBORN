# Tavern static assets

Place the tavern page background image here:

- **`tavern.background.webp`** — full-bleed background (recommended wide art, ~16:9 or taller).
- **`tavern.background_1.webp` … `tavern.background_4.webp`** — variants by remaining hire slots (see `tavernHireBackgroundUrl` in `app.js`).
- **`tavern.keeper.webp`** — фигура тавернщика поверх фона (нижний правый угол/полная высота сцены; при отсутствии скрывается через `onerror`).

The webapp loads them from `/static/game/ui/tavern/...`. If the file is missing, the gradient fallback still shows.

## Ambient music

Optional MP3 files in [`audio/`](audio/README.md) (`/static/game/ui/tavern/audio/`).
