# Tavern ambient music

Served at `/static/game/ui/tavern/audio/`.

## Files

Add one or more loop-friendly tracks. Names must match the list in `TAVERN_BGM_TRACKS` in `src/waifu_bot/webapp/app.js` (default: `tavern-01.mp3`, `tavern-02.mp3`, `tavern-03.mp3`).

## Format

- **MP3** (recommended for Telegram WebView), 128–192 kbps.
- Length about 30–90 seconds with seamless loop in mind.

The client picks a random track on each full tavern load (after the loading overlay), fades volume from 0 to 100% over ~3.2s, and stops on `pagehide` / tab hidden. If no files are present, the page works without audio.
