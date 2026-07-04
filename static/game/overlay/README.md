# Overlay animation assets

Companion HUD sprites and attack clips for the Steam desktop overlay.

Canonical spec: [docs/OVERLAY_ANIMATIONS.md](../../../docs/OVERLAY_ANIMATIONS.md)

## Layout

```
overlay/
  placeholder/     combat target monster (placeholder until art pass)
  base/            sleep overlay
  idle/actions/    out-of-combat idle loops
  attacks/         per weapon + combat mode attack clips
```

Regenerate this tree: `bash scripts/scaffold_overlay_anim_dirs.sh`

