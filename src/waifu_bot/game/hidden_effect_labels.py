"""Русские подписи и форматирование значений скрытых навыков (UI / API)."""

from __future__ import annotations

from typing import Any

HIDDEN_EFFECT_LABELS: dict[str, str] = {
    "dmg_text_pct": "Урон текстовыми сообщениями",
    "first_hit_per_hour_pct": "Бонус первого удара в час",
    "hp_regen_per_active_hour": "Регенерация HP в бою",
    "gold_night_pct": "Золото с монстров ночью (00:00–04:00 МСК)",
    "exp_bonus_pct": "Опыт с монстров",
    "first_hit_crit_pct": "Крит первого удара (быстрое убийство)",
    "final_armor_pct": "Снижение урона на последних ударах по монстру",
    "media_sticker_mult": "Множитель урона стикерами",
    "media_photo_mult": "Множитель урона фото",
    "media_audio_mult": "Множитель урона аудио/голосом",
    "media_video_mult": "Множитель урона видео",
    "media_gif_mult": "Множитель урона GIF",
    "finisher_dmg_pct": "Урон добивания (последний удар по монстру)",
    "boss_reward_pct": "Награды с боссов",
    "elite_drop_pct": "Дроп с элитных монстров",
    "low_hp_dmg_reduce": "Снижение входящего урона при низком HP",
    "first_hits_evade_pct": "Уклонение от первых ударов монстра",
    "first_clear_exp_pct": "Опыт за первое прохождение подземелья",
    "gold_drop_pct": "Золото с монстров",
    "shop_discount_pct": "Скидка в магазине",
    "gamble_legendary_pct": "Шанс легендарки в гембле",
    "group_dmg_pct": "Урон в групповом подземелье",
    "expedition_reward_pct": "Награды экспедиций",
    "loyal_unit_success_pct": "Успех экспедиций с одной наёмницей",
    "perfect_rarity_pct": "Шанс более редкого дропа",
    "enchant_cost_pct": "Стоимость заточки",
    "enchant_chance_pct": "Шанс успеха заточки",
    "all_stats_pct": "СИЛ, ЛОВ, ИНТ, УДЧ",
}

HIDDEN_SKILL_IMAGE_PATH = "/static/game/hidden-skills/webp/{skill_id}.webp"


def hidden_skill_image_url(skill_id: str) -> str:
    sid = str(skill_id or "").strip()
    return HIDDEN_SKILL_IMAGE_PATH.format(skill_id=sid)


def format_hidden_effect_value(effect_type: str, raw: Any) -> str:
    """Человекочитаемое значение одного эффекта."""
    if raw is None:
        return "—"
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return str(raw)

    t = str(effect_type or "")

    if t.startswith("media_") and t.endswith("_mult"):
        return f"×{n:.2f}"

    if t == "all_stats_pct":
        return f"+{int(round(n))} п.п."

    if t == "hp_regen_per_active_hour":
        per_min = max(0, int(round(n)))
        if per_min > 0:
            return f"+{per_min} HP/мин в бою"
        return "—"

    if t == "enchant_cost_pct":
        iv = int(round(n))
        return f"{iv:+d}% к стоимости"

    if t == "enchant_chance_pct":
        iv = int(round(-n))
        return f"{iv:+d}% к шансу"

    if t.endswith("_pct") or t.endswith("_reduce"):
        iv = int(round(n))
        sign = "+" if iv >= 0 else ""
        return f"{sign}{iv}%"

    return f"+{int(round(n))}"


def label_for_effect_type(effect_type: str) -> str:
    return HIDDEN_EFFECT_LABELS.get(str(effect_type or ""), str(effect_type or "Бонус"))


def labeled_effects_from_dict(effects: dict[str, float] | None) -> list[dict[str, str]]:
    if not effects:
        return []
    out: list[dict[str, str]] = []
    for et, val in effects.items():
        out.append(
            {
                "type": str(et),
                "label": label_for_effect_type(et),
                "value_text": format_hidden_effect_value(et, val),
            }
        )
    return out


def bonus_summary_from_dict(effects: dict[str, float] | None) -> str:
    parts = labeled_effects_from_dict(effects)
    if not parts:
        return "—"
    return " · ".join(f"{p['label']}: {p['value_text']}" for p in parts)
