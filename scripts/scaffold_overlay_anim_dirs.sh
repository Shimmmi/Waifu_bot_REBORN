#!/usr/bin/env bash
# Create static/game/overlay asset tree with README.md in each folder.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OVERLAY="$ROOT/static/game/overlay"

write_readme() {
  local dir="$1"
  local body="$2"
  mkdir -p "$dir"
  cat > "$dir/README.md" <<EOF
$body
EOF
}

write_readme "$OVERLAY" "# Overlay animation assets

Companion HUD sprites and attack clips for the Steam desktop overlay.

Canonical spec: [docs/OVERLAY_ANIMATIONS.md](../../../docs/OVERLAY_ANIMATIONS.md)

## Layout

\`\`\`
overlay/
  placeholder/     combat target monster (placeholder until art pass)
  base/            sleep overlay
  idle/actions/    out-of-combat idle loops
  attacks/         per weapon + combat mode attack clips
\`\`\`

Regenerate this tree: \`bash scripts/scaffold_overlay_anim_dirs.sh\`
"

write_readme "$OVERLAY/placeholder" "# Placeholder monster

**File:** \`monster.webp\` (already in repo)

Used by \`#ov-monster-target-img\` during solo dungeon and Abyss combat.
Replace with overlay-specific monster art when ready; path stays the same until renamed in \`pages/overlay.js\`.
"

write_readme "$OVERLAY/base" "# Base overlay states

**Expected file:** \`sleep.webp\`

Optional sleep overlay for \`state-sleep\` / \`state-sleep-dungeon\`.
Until art exists, CSS \`ovBreath\` keyframes are used as fallback.
"

write_readme "$OVERLAY/idle/actions" "# Idle action loops (outside combat)

Five optional WebP loops for \`state-idle\` (\`data-idle-action\` on portrait wrap):

| File | Action ID | Description (RU) |
|------|-----------|-------------------|
| \`stretch.webp\` | stretch | Потянулась |
| \`yawn.webp\` | yawn | Зевок |
| \`wave.webp\` | wave | Помахала |
| \`read.webp\` | read | Читает |
| \`tea.webp\` | tea | Пьёт чай |

Format: WebP, transparent background recommended. CSS keyframe fallbacks exist until art is added.
"

ATTACK_README() {
  local attack_type="$1"
  local weapon="$2"
  local mode="$3"
  local dir="$OVERLAY/attacks/$attack_type/$weapon/$mode"
  write_readme "$dir" "# Attack: ${attack_type} / ${weapon} / ${mode}

**Expected files:**
- \`attack_00.webp\`
- \`attack_01.webp\`

**URL path:**
\`/static/game/overlay/attacks/${attack_type}/${weapon}/${mode}/attack_00.webp\`

**JS key:** \`${mode}-${attack_type}-${weapon}-0\` (variant 0 or 1)

Format: WebP. Portrait-relative motion toward the monster target (+X).
See [docs/OVERLAY_ANIMATIONS.md](../../../../../docs/OVERLAY_ANIMATIONS.md).
"
}

MELEE_WEAPONS=(sword dagger axe mace hammer unarmed)
RANGED_WEAPONS=(bow crossbow)
MAGIC_WEAPONS=(staff wand orb)
MODES=(solo abyss)

for mode in "${MODES[@]}"; do
  for w in "${MELEE_WEAPONS[@]}"; do
    ATTACK_README melee "$w" "$mode"
  done
  for w in "${RANGED_WEAPONS[@]}"; do
    ATTACK_README ranged "$w" "$mode"
  done
  for w in "${MAGIC_WEAPONS[@]}"; do
    ATTACK_README magic "$w" "$mode"
  done
done

echo "Overlay asset tree ready under $OVERLAY/"
