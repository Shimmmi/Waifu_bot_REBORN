# Overlay RO paperdoll skeleton

Steam overlay character visual when `main_waifus.paperdoll_cosmetics` is set.
Scripts: `pages/ro-paperdoll-compositor.js`, `pages/ro-paperdoll-skeleton.js`, `pages/overlay.js`.

## Bone hierarchy

```
.ov-paperdoll
  .ov-bone[data-bone=root]
    .ov-bone[data-bone=hip]
      .ov-bone[data-bone=torso]
        .ov-bone[data-bone=head]          ← hair, eyes, race_feature, accessory
        .ov-bone[data-bone=arm_r]
          .ov-attach[data-attach=hand_r]  ← weapon (combat only)
        .ov-bone[data-bone=arm_l]
          .ov-attach[data-attach=hand_l]  ← offhand
        layers: base, outfit, equip_costume (on torso)
```

Attachment names are stable for a future Spine/DragonBones swap.

## Equip layer z-order (paint)

1. base  
2. race_feature  
3. outfit  
4. equip_costume (slot 3)  
5. hair / eyes / accessory  
6. equip_offhand (slot 2)  
7. equip_weapon (slot 1; **hidden when not in combat**)

Slots 4–6 (rings, amulet) never get sprites.

## Clip format

Clips live in `RoPaperdollSkeleton.CLIPS` (JS). Each clip:

```json
{
  "durationMs": 200,
  "loop": false,
  "keys": [
    { "t": 0, "bones": { "arm_r": { "rot": -10, "tx": 0, "ty": 0 } } },
    { "t": 1, "bones": { "arm_r": { "rot": 30 } } }
  ]
}
```

- `t` ∈ [0, 1] along the clip  
- Bone fields: `tx`, `ty` (px), `rot` (deg), optional `sx`/`sy`  
- Runtime lerps between keys and writes `transform` on `.ov-bone` / `.ov-attach`

### Built-in clips

| Id | When |
|----|------|
| `idle_sway` / `idle_breathe` | Idle / battle idle |
| `sleep` | AFK sleep states |
| `dead` | HP ≤ 0 |
| `attack_melee`, `attack_melee_sword`, `attack_melee_dagger`, `attack_melee_axe` | Melee by `weapon_type` |
| `attack_ranged` | `attack_type=ranged` |
| `attack_magic` | `attack_type=magic` |

Attack clip selection: `pickAttackClip(attackType, weaponType)`.

## API fields

- `main_waifu.paperdoll_cosmetics` + `has_paperdoll_layers`  
- `equipped_visuals`: `{ costume, weapon, offhand }` with `sprite` URLs under `/static/game/waifu-gen/paperdoll/equip/...`

Fallback: no cosmetics → `#ov-portrait` as before.

See also [OVERLAY_ANIMATIONS.md](OVERLAY_ANIMATIONS.md).
