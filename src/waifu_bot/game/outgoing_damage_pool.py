"""Unified additive outgoing damage bonus pool (replaces multiplicative chains)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import get_crit_multiplier

BONUS_POOL_MAX = 9.0
BONUS_POOL_MIN = -0.9


@dataclass
class OutgoingBonusContrib:
    source: str
    label_ru: str
    pct_add: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutgoingDamageBonusInput:
    """Inputs for collecting a single additive bonus pool over base damage."""

    attack_type: str = "melee"
    media_type: MediaType = MediaType.TEXT
    passive_rows: list[dict[str, Any]] = field(default_factory=list)
    passive_bonuses: dict[str, float] = field(default_factory=dict)
    hidden_bonuses: dict[str, float] = field(default_factory=dict)
    equipment_bonuses: dict[str, int] = field(default_factory=dict)
    bestiary_dmg_pct: float = 0.0
    legendary_damage_pool_add: float = 0.0
    legendary_contribs: list[Any] = field(default_factory=list)
    first_hit_hour_mult: float = 1.0
    is_group_chat: bool = False
    cur_hp: int = 0
    max_hp: int = 1
    msg_n: int = 0
    has_monster_debuff: bool = False
    monster_family: str | None = None
    stun_proc: bool = False


def sum_passive_pool(
    passive_rows: list[dict[str, Any]],
    effect_type: str,
    pool_label: str,
) -> tuple[float, list[OutgoingBonusContrib]]:
    matching = [r for r in passive_rows if str(r.get("effect_type") or "") == effect_type]
    if not matching:
        return 0.0, []
    contribs: list[OutgoingBonusContrib] = []
    total = 0.0
    for row in matching:
        value = float(row.get("value") or 0)
        if value <= 0:
            continue
        nid = str(row.get("node_id") or "")
        name = str(row.get("name") or nid)
        lvl = int(row.get("level") or 0)
        total += value
        contribs.append(
            OutgoingBonusContrib(
                source=f"passive:{nid}:{effect_type}",
                label_ru=f"Пассив «{name}» (ур. {lvl}): +{value * 100:.1f}% к {pool_label}",
                pct_add=value,
                meta={"node_id": nid, "level": lvl},
            )
        )
    return total, contribs


def _add_pct(contribs: list[OutgoingBonusContrib], source: str, label_ru: str, pct: float) -> float:
    if pct <= 0:
        return 0.0
    contribs.append(OutgoingBonusContrib(source=source, label_ru=label_ru, pct_add=pct))
    return pct


def _add_mult_as_pct(contribs: list[OutgoingBonusContrib], source: str, label_ru: str, mult: float) -> float:
    if mult <= 1.0:
        return 0.0
    pct = float(mult) - 1.0
    contribs.append(OutgoingBonusContrib(source=source, label_ru=label_ru, pct_add=pct))
    return pct


def _add_pct_signed(
    contribs: list[OutgoingBonusContrib],
    source: str,
    label_ru: str,
    pct: float,
    *,
    meta: dict[str, Any] | None = None,
) -> float:
    if abs(float(pct)) < 1e-12:
        return 0.0
    contribs.append(
        OutgoingBonusContrib(source=source, label_ru=label_ru, pct_add=float(pct), meta=meta or {})
    )
    return float(pct)


def cap_bonus_pool(pool: float) -> float:
    return max(BONUS_POOL_MIN, min(float(pool), BONUS_POOL_MAX))


def collect_outgoing_bonus_pool(inp: OutgoingDamageBonusInput) -> tuple[float, list[OutgoingBonusContrib]]:
    """Sum all outgoing % bonuses into one pool fraction (e.g. 1.5 = +150%)."""
    contribs: list[OutgoingBonusContrib] = []
    pool = 0.0
    ps = inp.passive_bonuses
    hs = inp.hidden_bonuses
    eff = inp.equipment_bonuses
    atk = (inp.attack_type or "melee").lower()

    if atk == "melee":
        v, c = sum_passive_pool(inp.passive_rows, "melee_dmg_pct", "ближний бой")
        pool += v
        contribs.extend(c)
    elif atk == "ranged":
        v, c = sum_passive_pool(inp.passive_rows, "ranged_dmg_pct", "дальний бой")
        pool += v
        contribs.extend(c)
    elif atk == "magic":
        v, c = sum_passive_pool(inp.passive_rows, "magic_dmg_pct", "магия")
        pool += v
        contribs.extend(c)

    if inp.media_type in (MediaType.TEXT, MediaType.LINK):
        dt = float(hs.get("dmg_text_pct", 0) or 0)
        if dt > 0:
            pool += _add_pct(contribs, "hidden_dmg_text", f"Скрытый навык: урон от текста +{dt:.0f}%", dt / 100.0)

    if inp.is_group_chat:
        gd = float(hs.get("group_dmg_pct", 0) or 0)
        if gd > 0:
            pool += _add_pct(
                contribs,
                "hidden_group_dmg",
                f"Скрытый «Командный игрок»: урон в группе +{gd:.0f}%",
                gd / 100.0,
            )

    media_mult_key = {
        MediaType.STICKER: "media_sticker_mult",
        MediaType.PHOTO: "media_photo_mult",
        MediaType.GIF: "media_gif_mult",
        MediaType.AUDIO: "media_audio_mult",
        MediaType.VOICE: "media_audio_mult",
        MediaType.VIDEO: "media_video_mult",
    }.get(inp.media_type)
    if media_mult_key:
        mm = float(hs.get(media_mult_key, 0) or 0)
        if mm > 1.0:
            pool += _add_mult_as_pct(
                contribs,
                "hidden_media_mult",
                f"Скрытый навык: множитель медиа ×{mm:.3f}",
                mm,
            )

    if inp.media_type not in (MediaType.TEXT, MediaType.LINK):
        for et, label in (
            ("media_dmg_pct", "урон по медиа"),
            ("media_mult_bonus", "множитель медиа"),
        ):
            v, c = sum_passive_pool(inp.passive_rows, et, label)
            pool += v
            contribs.extend(c)

    if inp.first_hit_hour_mult > 1.0:
        pool += _add_mult_as_pct(
            contribs,
            "hidden_first_hit_hour",
            f"Скрытый: бонус «первый удар часа» ×{inp.first_hit_hour_mult:.3f}",
            inp.first_hit_hour_mult,
        )

    v, c = sum_passive_pool(inp.passive_rows, "active_skill_dmg_pct", "активные навыки")
    pool += v
    contribs.extend(c)

    media_key = {
        MediaType.TEXT: "media_damage_text_percent",
        MediaType.STICKER: "media_damage_sticker_percent",
        MediaType.PHOTO: "media_damage_photo_percent",
        MediaType.GIF: "media_damage_gif_percent",
        MediaType.AUDIO: "media_damage_audio_percent",
        MediaType.VIDEO: "media_damage_video_percent",
        MediaType.VOICE: "media_damage_voice_percent",
        MediaType.LINK: "media_damage_link_percent",
    }.get(inp.media_type)
    if media_key:
        bonus_pct = int(eff.get(media_key, 0) or 0)
        if bonus_pct > 0:
            pool += _add_pct(
                contribs,
                "affix_media_type",
                f"Экипировка: урон по типу медиа +{bonus_pct}%",
                bonus_pct / 100.0,
            )

    monster_family = (inp.monster_family or "").strip().lower()
    if monster_family:
        pct_key = f"damage_vs_monster_type_percent:{monster_family}"
        pct_bonus = int(eff.get(pct_key, 0) or 0)
        if pct_bonus > 0:
            pool += _add_pct(
                contribs,
                "affix_vs_family_pct",
                f"Экипировка: урон против «{monster_family}» +{pct_bonus}%",
                pct_bonus / 100.0,
            )

    if inp.bestiary_dmg_pct > 0:
        pool += _add_pct(
            contribs,
            "bestiary_dmg",
            f"Бестиарий: знание монстра +{round(inp.bestiary_dmg_pct * 100)}% урона",
            float(inp.bestiary_dmg_pct),
        )

    if inp.stun_proc:
        pool += _add_pct(contribs, "passive_stun_proc", "Пассив: срабатывание оглушения +20%", 0.20)

    max_hp_w = max(1, int(inp.max_hp))
    cur_hp_w = int(inp.cur_hp)
    lhp = float(ps.get("low_hp_dmg_pct", 0) or 0)
    if lhp > 0 and cur_hp_w * 2 <= max_hp_w:
        v, c = sum_passive_pool(inp.passive_rows, "low_hp_dmg_pct", "низкое HP")
        pool += v
        contribs.extend(c)

    hld = float(ps.get("hp_loss_dmg_pct", 0) or 0)
    if hld > 0 and max_hp_w > 0:
        missing = 1.0 - (float(cur_hp_w) / float(max_hp_w))
        steps = int(missing / 0.1)
        if steps > 0:
            hp_loss_add = hld * float(steps)
            pool += _add_pct(
                contribs,
                "passive_hp_loss",
                f"Пассив: потеря HP (+{steps} ступеней × {hld:.2f})",
                hp_loss_add,
            )

    dbf = float(ps.get("debuff_dmg_pct", 0) or 0)
    if dbf > 0 and inp.has_monster_debuff:
        v, c = sum_passive_pool(inp.passive_rows, "debuff_dmg_pct", "ослабленные")
        pool += v
        contribs.extend(c)

    fhd = float(ps.get("first_hit_dmg_pct", 0) or 0)
    if fhd > 0 and inp.msg_n == 0:
        v, c = sum_passive_pool(inp.passive_rows, "first_hit_dmg_pct", "первый удар")
        pool += v
        contribs.extend(c)

    mat = float(ps.get("media_after_text_pct", 0) or 0)
    if mat > 0 and inp.msg_n >= 3 and inp.media_type not in (MediaType.TEXT, MediaType.LINK):
        v, c = sum_passive_pool(inp.passive_rows, "media_after_text_pct", "медиа после текста")
        pool += v
        contribs.extend(c)

    leg_add = float(inp.legendary_damage_pool_add)
    if inp.legendary_contribs:
        for lc in inp.legendary_contribs:
            pct = float(getattr(lc, "pool_pct_add", 0) or 0)
            if abs(pct) < 1e-12:
                continue
            key = str(getattr(lc, "bonus_key", "") or "")
            iid = int(getattr(lc, "inventory_item_id", 0) or 0)
            lbl = str(getattr(lc, "label_ru", "") or key)
            sign = "+" if pct >= 0 else ""
            _add_pct_signed(
                contribs,
                f"legendary:{key}:{iid}",
                f"Легендарка «{lbl}»: {sign}{pct * 100:.1f}% урона",
                pct,
                meta={"bonus_key": key, "inventory_item_id": iid},
            )
        if abs(leg_add) >= 1e-12:
            pool += leg_add
    elif abs(leg_add) >= 1e-12:
        pool += _add_pct_signed(
            contribs,
            "legendary_damage_pool",
            f"Легендарные бонусы: {'+' if leg_add >= 0 else ''}{leg_add * 100:.1f}% урона",
            leg_add,
        )

    return cap_bonus_pool(pool), contribs


def apply_outgoing_bonus_pool(base_damage: int, pool: float) -> int:
    """Apply unified bonus pool: floor(base × (1 + pool))."""
    pool = cap_bonus_pool(pool)
    if abs(pool) < 1e-12:
        return int(base_damage)
    return int(int(base_damage) * (1.0 + float(pool)))


def compute_crit_multiplier(
    strength: int,
    *,
    crit_mult_add: float = 0.0,
    crit_dmg_melee_pct: float = 0.0,
    leg_crit_add: float = 0.0,
    attack_type: str = "melee",
    crit_roll: float | None = None,
) -> float:
    """Crit multiplier: base roll + additive passives + additive wrath (melee only) + legendary crit add."""
    if crit_roll is not None:
        mult = float(crit_roll)
    else:
        mult = float(get_crit_multiplier(int(strength)))
    mult += float(crit_mult_add or 0)
    if (attack_type or "melee").lower() == "melee":
        mult += float(crit_dmg_melee_pct or 0)
    mult += float(leg_crit_add or 0)
    return max(0.0, mult)


def legendary_pool_add(damage_multiplier: float, *, max_total_mult: float = 10.0) -> float:
    """Convert aggregated legendary damage_multiplier to pool fraction with cap."""
    capped = min(float(damage_multiplier or 1.0), float(max_total_mult))
    return capped - 1.0


def legendary_crit_add(crit_damage_multiplier: float) -> float:
    """Convert aggregated legendary crit_damage_multiplier to additive crit bonus."""
    mult = float(crit_damage_multiplier or 1.0)
    if mult <= 1.0:
        return 0.0
    return mult - 1.0
