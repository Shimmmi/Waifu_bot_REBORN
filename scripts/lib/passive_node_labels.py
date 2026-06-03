"""RU display labels for passive skill node ids (affix LLM prompts)."""

from __future__ import annotations

# Mirrors src/waifu_bot/webapp/app.js PASSIVE_NODE_DISPLAY_NAMES_RU
PASSIVE_NODE_LABELS_RU: dict[str, str] = {
    "w_bash": "Удар",
    "w_tough": "Закалка",
    "w_cry": "Боевой дух",
    "w_heavy": "Тяжёлый удар",
    "w_iron": "Железная кожа",
    "w_blood": "Кров. ярость",
    "w_berserk": "Берсерк",
    "w_fort": "Крепость",
    "w_last": "Последний рубеж",
    "w_wrath": "Гнев героя",
    "w_imm": "Бессмертный",
    "s_keen": "Острый глаз",
    "s_nimble": "Проворство",
    "s_media": "Чутьё",
    "s_crit_m": "Мастер крита",
    "s_shadow": "Шаг тени",
    "s_exploit": "Уязвимость",
    "s_nth": "Серия смерти",
    "s_ghost": "Призрак",
    "s_amp": "Усил. медиа",
    "s_lethal": "Смерт. удар",
    "s_phantom": "Фантом",
    "m_arcane": "Аркана",
    "m_wisdom": "Мудрость",
    "m_trade": "Торговец",
    "m_media_m": "Медиамаг",
    "m_lore": "Знания",
    "m_bargain": "Сделка",
    "m_surge": "Маг. всплеск",
    "m_cmd": "Командование",
    "m_rune": "Рун. броня",
    "m_trans": "Трансценд.",
    "m_arch": "Архимаг",
}

PASSIVE_BRANCH_LABELS_RU: dict[str, str] = {
    "warrior": "воина",
    "shadow": "тени",
    "sage": "мудреца",
}


def passive_node_id_from_family_id(family_id: str) -> str | None:
    fid = str(family_id or "")
    for prefix in ("p_passive_lvl_", "s_passive_lvl_", "p_passive_branch_", "s_passive_branch_"):
        if fid.startswith(prefix):
            return fid[len(prefix) :]
    if fid in ("p_passive_all", "s_passive_all"):
        return None
    return None


def passive_node_label_ru(family_id: str, effect_key: str) -> str | None:
    node = passive_node_id_from_family_id(family_id)
    if node and node in PASSIVE_NODE_LABELS_RU:
        return PASSIVE_NODE_LABELS_RU[node]
    low = str(effect_key or "").lower()
    if low.startswith("passive_node_level_add:"):
        nid = low.split(":", 1)[1].strip()
        return PASSIVE_NODE_LABELS_RU.get(nid) or nid
    if low.startswith("passive_branch_level_add:"):
        br = low.split(":", 1)[1].strip().lower()
        return f"ветки {PASSIVE_BRANCH_LABELS_RU.get(br, br)}"
    if low == "passive_all_nodes_level_add":
        return "всех пассивов"
    return None
