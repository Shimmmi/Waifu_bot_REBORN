#!/usr/bin/env python3
"""
Генерирует черновики аффиксов/суффиксов (отдельные JSON для ручного слияния с основными).

  python3 scripts/generate_diablo_affix_draft.py

Файлы:
  scripts/data/diablo_affix_families_draft_addon.json
  scripts/data/diablo_affix_family_tiers_draft_addon.json

Не все effect_key уже обработаны в shop/routes — см. info/SECONDARY_BONUSES.md.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FAM = ROOT / "scripts/data/diablo_affix_families_draft_addon.json"
OUT_TIER = ROOT / "scripts/data/diablo_affix_family_tiers_draft_addon.json"

# 33 пассивных узла (0037_passive_skill_tree)
PASSIVE_NODE_IDS: tuple[str, ...] = (
    "w_bash",
    "w_tough",
    "w_cry",
    "w_heavy",
    "w_iron",
    "w_blood",
    "w_berserk",
    "w_fort",
    "w_last",
    "w_wrath",
    "w_imm",
    "s_keen",
    "s_nimble",
    "s_media",
    "s_crit_m",
    "s_shadow",
    "s_exploit",
    "s_nth",
    "s_ghost",
    "s_amp",
    "s_lethal",
    "s_phantom",
    "m_arcane",
    "m_wisdom",
    "m_trade",
    "m_media_m",
    "m_lore",
    "m_bargain",
    "m_surge",
    "m_cmd",
    "m_rune",
    "m_trans",
    "m_arch",
)

MONSTER_FAMILIES: tuple[str, ...] = (
    "beast",
    "construct",
    "demon",
    "dragon",
    "elemental",
    "fae",
    "humanoid",
    "slime",
    "undead",
)

MEDIA_KEYS: tuple[tuple[str, str], ...] = (
    ("sticker", "media_damage_sticker_percent"),
    ("photo", "media_damage_photo_percent"),
    ("gif", "media_damage_gif_percent"),
    ("audio", "media_damage_audio_percent"),
    ("voice", "media_damage_voice_percent"),
    ("video", "media_damage_video_percent"),
    ("link", "media_damage_link_percent"),
)


def _family_row(
    family_id: str,
    kind: str,
    effect_key: str,
    exclusive_group: str,
    weight: int = 50,
) -> dict:
    return {
        "family_id": family_id,
        "kind": kind,
        "exclusive_group": exclusive_group,
        "effect_key": effect_key,
        "tags_required": None,
        "tags_forbidden": None,
        "allowed_slot_types": None,
        "allowed_attack_types": None,
        "weight_base": weight,
        "max_per_item": 1,
        "is_legendary_aspect": False,
    }


def _tier_rows(family_id: str, base_vmin: int, base_vmax: int) -> list[dict]:
    rows = []
    for tier in range(1, 11):
        lo = (tier - 1) * 5 + 1
        hi = tier * 5
        vmin = base_vmin + (tier - 1) * 8
        vmax = base_vmax + (tier - 1) * 18
        ldm = max(0, (tier - 1) // 2)
        ldx = min(10, 2 + tier // 2)
        rows.append(
            {
                "family_id": family_id,
                "affix_tier": tier,
                "min_total_level": lo,
                "max_total_level": hi,
                "value_min": vmin,
                "value_max": vmax,
                "level_delta_min": ldm,
                "level_delta_max": ldx,
                "weight_mult": 100,
            }
        )
    return rows


def build_families() -> list[dict]:
    out: list[dict] = []

    # Пассивы: +N виртуальных уровней к узлу (реализовано в passive_skills + item_service)
    for nid in PASSIVE_NODE_IDS:
        ek = f"passive_node_level_add:{nid}"
        out.append(
            _family_row(
                f"p_passive_lvl_{nid}",
                "prefix",
                ek,
                "passive_level_add",
                weight=42,
            )
        )
        out.append(
            _family_row(
                f"s_passive_lvl_{nid}",
                "suffix",
                ek,
                "passive_level_add",
                weight=48,
            )
        )

    # Ветка / всё дерево — черновик под будущий код (effect_key зарезервированы)
    for br, w in (("warrior", 35), ("shadow", 35), ("sage", 35)):
        eg = f"passive_branch_level_add_{br}"
        out.append(
            _family_row(
                f"p_passive_branch_{br}",
                "prefix",
                f"passive_branch_level_add:{br}",
                eg,
                weight=25,
            )
        )
        out.append(
            _family_row(
                f"s_passive_branch_{br}",
                "suffix",
                f"passive_branch_level_add:{br}",
                eg,
                weight=28,
            )
        )
    out.append(
        _family_row(
            "p_passive_all",
            "prefix",
            "passive_all_nodes_level_add",
            "passive_all_nodes_level_add",
            weight=15,
        )
    )
    out.append(
        _family_row(
            "s_passive_all",
            "suffix",
            "passive_all_nodes_level_add",
            "passive_all_nodes_level_add",
            weight=18,
        )
    )

    # Урон по семье монстров: flat (undead flat уже есть в основном JSON — здесь остальные + undead %)
    for fam in MONSTER_FAMILIES:
        if fam != "undead":
            out.append(
                _family_row(
                    f"s_monster_{fam}_flat",
                    "suffix",
                    f"damage_vs_monster_type_flat:{fam}",
                    "monster_slayer",
                    weight=38,
                )
            )
        out.append(
            _family_row(
                f"s_monster_{fam}_pct",
                "suffix",
                f"damage_vs_monster_type_percent:{fam}",
                "monster_slayer_pct",
                weight=36,
            )
        )

    # Медиа-урон (текст уже s_media_text в основном файле)
    for short, ek in MEDIA_KEYS:
        out.append(
            _family_row(
                f"p_media_{short}",
                "prefix",
                ek,
                "media_bonus",
                weight=40,
            )
        )
        out.append(
            _family_row(
                f"s_media_{short}",
                "suffix",
                ek,
                "media_bonus",
                weight=44,
            )
        )

    # Тип урона (flat к скору в профиле — уже в calculate_item_bonuses)
    for dmg_key, eg in (
        ("melee_damage_flat", "weapon_damage_affinity"),
        ("ranged_damage_flat", "weapon_damage_affinity"),
        ("magic_damage_flat", "weapon_damage_affinity"),
    ):
        short = dmg_key.replace("_damage_flat", "")
        out.append(_family_row(f"p_dmg_{short}", "prefix", dmg_key, eg, 55))
        out.append(_family_row(f"s_dmg_{short}", "suffix", dmg_key, eg, 60))

    # Торговля / таверна / продажа — черновик под расширение shop/routes
    out.append(
        _family_row("p_merchant_cut", "prefix", "merchant_discount_flat", "commerce_bonus", 50)
    )
    out.append(
        _family_row("s_merchant_cut", "suffix", "merchant_discount_percent", "commerce_bonus", 50)
    )
    out.append(
        _family_row("p_sell_high", "prefix", "sell_price_bonus_percent", "commerce_bonus", 40)
    )
    out.append(
        _family_row("s_sell_high", "suffix", "sell_price_bonus_percent", "commerce_bonus", 45)
    )
    out.append(
        _family_row("p_tavern_favor", "prefix", "tavern_discount_percent", "tavern_bonus", 40)
    )
    out.append(
        _family_row("s_tavern_favor", "suffix", "tavern_discount_percent", "tavern_bonus", 45)
    )

    return out


def build_tiers(families: list[dict]) -> list[dict]:
    tiers: list[dict] = []
    for f in families:
        fid = f["family_id"]
        ek = str(f["effect_key"])

        if ek.startswith("passive_node_level_add:"):
            for tier in range(1, 11):
                lo = (tier - 1) * 5 + 1
                hi = tier * 5
                vmin = 1 + (tier - 1) // 4
                vmax = 1 + tier // 3
                if vmax < vmin:
                    vmin, vmax = vmax, vmin
                ldm = max(0, (tier - 1) // 2)
                ldx = min(10, 2 + tier // 2)
                tiers.append(
                    {
                        "family_id": fid,
                        "affix_tier": tier,
                        "min_total_level": lo,
                        "max_total_level": hi,
                        "value_min": vmin,
                        "value_max": vmax,
                        "level_delta_min": ldm,
                        "level_delta_max": ldx,
                        "weight_mult": 100,
                    }
                )
        elif ek.startswith("passive_branch_level_add:") or ek == "passive_all_nodes_level_add":
            tiers.extend(_tier_rows(fid, 1, 2))
        elif ek.startswith("damage_vs_monster_type_flat:"):
            tiers.extend(_tier_rows(fid, 2, 5))
        elif ek.startswith("damage_vs_monster_type_percent:"):
            tiers.extend(_tier_rows(fid, 3, 8))
        elif ek.startswith("media_damage_"):
            tiers.extend(_tier_rows(fid, 5, 14))
        elif ek in ("melee_damage_flat", "ranged_damage_flat", "magic_damage_flat"):
            tiers.extend(_tier_rows(fid, 4, 12))
        elif "merchant" in ek or "sell_price" in ek or "tavern" in ek:
            tiers.extend(_tier_rows(fid, 2, 6))
        else:
            tiers.extend(_tier_rows(fid, 10, 25))

    return tiers


def main() -> None:
    fams = build_families()
    tiers = build_tiers(fams)
    OUT_FAM.parent.mkdir(parents=True, exist_ok=True)
    OUT_FAM.write_text(json.dumps(fams, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_TIER.write_text(json.dumps(tiers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(fams)} families -> {OUT_FAM}")
    print(f"Wrote {len(tiers)} tier rows -> {OUT_TIER}")


if __name__ == "__main__":
    main()
