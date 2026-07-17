"""Человекочитаемый журнал раунда GD v1 из actions_json + context_json (+ outcomes для старых записей)."""
from __future__ import annotations

from typing import Any

# Compact group post: narrative + short status (Telegram-friendly).
GD_COMPACT_GROUP_MSG_LIMIT = 900


def _party_map(ctx: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in (ctx or {}).get("party") or []:
        uid = p.get("user_id")
        if uid is not None:
            out[int(uid)] = p
    return out


def _party_slot_by_user(ctx: dict[str, Any] | None) -> dict[int, int]:
    """Порядковый номер в отряде (1-based) по списку party в контексте раунда."""
    out: dict[int, int] = {}
    for i, p in enumerate((ctx or {}).get("party") or []):
        uid = p.get("user_id")
        if uid is not None:
            out[int(uid)] = i + 1
    return out


def _monster_map(ctx: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for m in (ctx or {}).get("monsters") or []:
        mid = m.get("id")
        if mid is not None:
            out[int(mid)] = m
    return out


def _pname(pmap: dict[int, dict[str, Any]], uid: int) -> str:
    p = pmap.get(int(uid), {})
    return str(p.get("name") or f"игрок {uid}")


def _ov_label(pmap: dict[int, dict[str, Any]], slots: dict[int, int], uid: int) -> str:
    """«ОВ игрока N (имя)» по порядку в party; без слота — только имя."""
    name = _pname(pmap, uid)
    slot = slots.get(int(uid))
    if slot:
        return f"ОВ игрока {slot} ({name})"
    return f"ОВ ({name})"


def _mname(mmap: dict[int, dict[str, Any]], mid: int) -> str:
    m = mmap.get(int(mid), {})
    return str(m.get("name") or f"монстр #{mid}")


_SKILL_VERB_RU: dict[str, str] = {
    "DAMAGE_SINGLE": "способность: урон по монстру",
    "DAMAGE_ALL": "способность: урон по всем целям",
    "DAMAGE_SELF_BOOST": "способность: урон и потеря собственного HP",
    "DOT": "способность: периодический урон (DoT) на монстра",
    "TAUNT": "провокация: монстры целятся в эту ОВ",
    "HEAL_SINGLE": "исцеление союзника",
    "HEAL_ALL": "массовое исцеление отряда",
    "REVIVE": "воскрешение союзника",
    "SHIELD_PARTY": "щит на отряд",
    "DEBUFF_MONSTER_SKIP": "пропуск хода монстра",
    "DEBUFF_MONSTER_INITIATIVE": "штраф к инициативе монстра",
    "DEBUFF_MONSTER_ARMOR": "ослабление брони монстра",
    "EVASION_PARTY": "уклонение отряда",
    "BUFF_CRIT_NEXT": "усиление следующего удара",
    "BUFF_PARTY_DAMAGE": "бафф урона отряда",
    "REFLECT": "отражение урона",
    "REGEN": "регенерация союзников",
    "GOLD_BONUS": "бонус к золоту с лута",
}


def format_gd_round_log_lines_ru(
    resolved: list[dict[str, Any]] | None,
    context_json: dict[str, Any] | None,
    outcomes_json: dict[str, Any] | None = None,
) -> list[str]:
    """
    Строки журнала одного раунда (инициатива и действия по порядку из resolved).
    """
    pmap = _party_map(context_json)
    slots = _party_slot_by_user(context_json)
    mmap = _monster_map(context_json)
    lines: list[str] = []
    resolved = resolved or []

    for entry in resolved:
        kind = entry.get("kind")

        if kind == "cycle_start":
            lines.append(f"— Цикл {int(entry.get('cycle') or 0)} —")
            continue

        if kind == "initiative_order":
            q = entry.get("queue") or []
            parts: list[str] = []
            for i, item in enumerate(q, start=1):
                actor = item.get("actor")
                aid = item.get("id")
                sc = item.get("score")
                if actor == "player":
                    parts.append(
                        f"{i}. {_ov_label(pmap, slots, int(aid or 0))} (инициатива {sc})"
                    )
                elif actor == "monster":
                    parts.append(f"{i}. «{_mname(mmap, int(aid or 0))}» (монстр, инициатива {sc})")
                else:
                    parts.append(f"{i}. {actor} id={aid} ({sc})")
            lines.append("Инициатива: " + "; ".join(parts) if parts else "Инициатива: —")
            continue

        if kind == "monster_hit":
            mid = int(entry.get("monster_id") or 0)
            tuid = int(entry.get("target_user_id") or 0)
            dmg = int(entry.get("damage") or 0)
            lines.append(
                f"• Монстр «{_mname(mmap, mid)}»: удар по {_ov_label(pmap, slots, tuid)} — {dmg} урона."
            )
            continue

        if kind == "dot_tick":
            mid = int(entry.get("monster_id") or 0)
            dmg = int(entry.get("damage") or 0)
            su = entry.get("source_user_id")
            src = f" (DoT от {_ov_label(pmap, slots, int(su))})" if su else ""
            lines.append(f"• DoT по «{_mname(mmap, mid)}» — {dmg} урона{src}.")
            continue

        if entry.get("kind") == "admin_force_victory":
            aid = entry.get("admin_user_id")
            lines.append(f"• [Админ] принудительная победа цикла (user_id={aid}).")
            continue

        uid_e = entry.get("user_id")
        if uid_e is not None:
            uid = int(uid_e)
            ov = _ov_label(pmap, slots, uid)
            if entry.get("kind") == "silent":
                lines.append(f"• {ov}: молчание в буфере (ход без урона).")
                continue
            if entry.get("kind") == "text":
                dmg = int(entry.get("damage") or 0)
                series = int(entry.get("series") or 1)
                guild_lines = entry.get("guild_skill_lines") or []
                suffix = ""
                if guild_lines:
                    suffix = " (" + ", ".join(str(x) for x in guild_lines) + ")"
                elif entry.get("guild_damage_pct"):
                    pct = float(entry["guild_damage_pct"]) * 100
                    shown = int(pct) if pct == int(pct) else round(pct, 1)
                    suffix = f" (Боевой клич +{shown}%)"
                series_bit = f" серия из {series} сообщений," if series > 1 else ""
                lines.append(f"• {ov}:{series_bit} урон от сообщений в чате — {dmg}{suffix}.")
                continue
            sk = entry.get("skill")
            if sk == "REGEN_TICK":
                if entry.get("party"):
                    lines.append("• Регенерация: отряд восстановил HP.")
                else:
                    h = int(entry.get("heal") or 0)
                    lines.append(f"• {ov}: тик регенерации +{h} HP.")
                continue
            if sk:
                verb = _SKILL_VERB_RU.get(str(sk), f"навык {sk}")
                extra = []
                if entry.get("damage") is not None:
                    extra.append(f"урон {int(entry['damage'])}")
                if entry.get("heal") is not None:
                    extra.append(f"исцеление {int(entry['heal'])}")
                if entry.get("absorb") is not None:
                    extra.append(f"поглощение щита {entry['absorb']}")
                if entry.get("whiff"):
                    extra.append("не удалось")
                if entry.get("value") is not None:
                    extra.append(f"значение {entry['value']}")
                if entry.get("duration") is not None:
                    extra.append(f"длительность {int(entry['duration'])} р.")
                if entry.get("self_cost_pct") is not None:
                    extra.append(f"цена HP {entry['self_cost_pct']}%")
                tail = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"• {ov}: {verb}{tail}.")
                continue

        if entry.get("monster") is not None:
            mid = int(entry["monster"])
            if entry.get("skipped"):
                lines.append(f"• «{_mname(mmap, mid)}»: пропуск хода.")
                continue
            tuid = entry.get("target")
            if entry.get("evaded"):
                lines.append(
                    f"• «{_mname(mmap, mid)}»: атака по {_ov_label(pmap, slots, int(tuid or 0))} — уклонение."
                )
                continue
            if entry.get("shielded"):
                lines.append(
                    f"• «{_mname(mmap, mid)}»: атака по {_ov_label(pmap, slots, int(tuid or 0))} — поглощено щитом."
                )
                continue

        lines.append(f"• (запись) {entry}")

    if not any(x.get("kind") == "monster_hit" for x in resolved):
        legacy: list[str] = []
        for h in (outcomes_json or {}).get("hits") or []:
            if h.get("dot") or h.get("reflect"):
                continue
            mid = h.get("monster")
            tid = h.get("target")
            dmg = h.get("damage")
            if mid is None or tid is None or dmg is None:
                continue
            legacy.append(
                f"• Монстр «{_mname(mmap, int(mid))}»: удар по {_ov_label(pmap, slots, int(tid))} — {int(dmg)} урона."
            )
        if legacy:
            lines.append("— Удары монстров (из сводки раунда; в старых логах порядок мог не сохраняться) —")
            lines.extend(legacy)

    return lines


def _wave_label_ru(wave: Any) -> str:
    return {
        "pending_init": "старт",
        "trash": "обычные враги",
        "boss": "босс",
        "done": "завершено",
    }.get(str(wave or ""), str(wave) if wave is not None else "—")


def format_gd_compact_round_status(
    battle_state: dict[str, Any] | None,
    *,
    round_number: int | str = "?",
    round_outcome: str | None = None,
    top_contributor_name: str | None = None,
) -> str:
    """3–5 строк статуса для группового чата (без полного roster)."""
    st = battle_state or {}
    monsters: list[dict[str, Any]] = list(st.get("monsters") or [])
    alive = [m for m in monsters if int(m.get("hp") or 0) > 0]
    lines: list[str] = [f"📊 Раунд {round_number} · {_wave_label_ru(st.get('wave'))}"]
    if round_outcome:
        outcome_ru = {
            "ongoing": "бой продолжается",
            "idle": "отряд молчит — раунд пропущен",
            "victory": "победа",
            "party_wiped": "отряд нокаутирован (продолжаем)",
            "cancelled_idle": "поход свёрнут (тишина)",
            "cancelled_defeat": "поход свёрнут (нокауты)",
            "cancelled_player_stop": "поход завершён игроком",
        }.get(str(round_outcome), str(round_outcome))
        lines.append(f"Итог: {outcome_ru}")
    if alive:
        m = max(alive, key=lambda x: int(x.get("hp") or 0))
        mx = max(1, int(m.get("max_hp") or 1))
        cur = int(m.get("hp") or 0)
        pct = int(100 * cur / mx)
        boss = " (босс)" if m.get("is_boss") else ""
        lines.append(f"Цель: {m.get('name', 'Монстр')}{boss} — {pct}% HP")
    elif monsters:
        lines.append("Цель: волна зачищена")
    else:
        lines.append("Цель: —")
    party = list(st.get("party") or [])
    up = sum(
        1
        for p in party
        if not p.get("fallen") and int(p.get("current_hp") or 0) > 0
    )
    lines.append(f"Отряд: {up}/{len(party)} в строю")
    if top_contributor_name:
        lines.append(f"Топ раунда: {top_contributor_name}")
    wipe_n = int(st.get("wipe_count") or 0)
    if wipe_n > 0:
        lines.append(f"Нокаутов за поход: {wipe_n}")
    return "\n".join(lines)


def format_gd_group_compact_message(
    narrative: str,
    battle_state: dict[str, Any] | None,
    *,
    round_number: int | str = "?",
    round_outcome: str | None = None,
    top_contributor_name: str | None = None,
    limit: int = GD_COMPACT_GROUP_MSG_LIMIT,
) -> str:
    """Один пост в группу: нарратив + compact status, усечённый до limit."""
    status = format_gd_compact_round_status(
        battle_state,
        round_number=round_number,
        round_outcome=round_outcome,
        top_contributor_name=top_contributor_name,
    )
    narr = (narrative or "").strip()
    sep = "\n\n"
    budget = max(80, int(limit) - len(status) - len(sep))
    if len(narr) > budget:
        cut = narr[: max(0, budget - 1)].rstrip()
        # Prefer cutting on sentence/word boundary
        for sep_ch in (". ", "! ", "? ", "\n"):
            idx = cut.rfind(sep_ch)
            if idx >= budget // 3:
                cut = cut[: idx + 1].rstrip()
                break
        narr = cut + "…"
    return f"{narr}{sep}{status}" if narr else status


def format_gd_battle_hp_system_message(battle_state: dict[str, Any] | None) -> str:
    """Текст системного сообщения: HP отряда и монстров после раунда."""
    st = battle_state or {}
    party: list[dict[str, Any]] = list(st.get("party") or [])
    monsters: list[dict[str, Any]] = list(st.get("monsters") or [])
    lines: list[str] = [
        "📊 Система: состояние после раунда",
        "",
        "Отряд:",
    ]
    if not party:
        lines.append("• (пусто)")
    else:
        for p in party:
            name = str(p.get("name") or f"Игрок {p.get('user_id', '?')}")
            cur = int(p.get("current_hp") or 0)
            mx = max(1, int(p.get("max_hp") or 1))
            fallen = bool(p.get("fallen")) or cur <= 0
            if fallen:
                lines.append(f"• {name} — нокдаун, {cur} / {mx} HP")
            else:
                pct = int(100 * cur / mx)
                lines.append(f"• {name} — {cur} / {mx} HP (~{pct}%)")
    lines.extend(["", "Монстры:"])
    if not monsters:
        lines.append("• нет активных записей")
    else:
        for m in monsters:
            name = str(m.get("name") or "Монстр")
            boss = " (босс)" if m.get("is_boss") else ""
            cur = int(m.get("hp") or 0)
            mx = max(1, int(m.get("max_hp") or 1))
            if cur <= 0:
                lines.append(f"• {name}{boss} — повержен (было {mx} HP)")
            else:
                pct = int(100 * cur / mx)
                lines.append(f"• {name}{boss} — {cur} / {mx} HP (~{pct}%)")
    return "\n".join(lines)


def format_gd_round_battle_log_message(
    result: dict[str, Any], ctx: dict[str, Any]
) -> str:
    """Полный лог боя за раунд (по циклам, с цифрами)."""
    resolved = (result.get("actions_json") or {}).get("resolved")
    lines = format_gd_round_log_lines_ru(resolved, ctx, result.get("outcomes_json"))
    rnd = result.get("round_number", "?")
    header = f"🧾 Журнал боя — раунд {rnd}"
    if not lines:
        return header + "\n• (нет зафиксированных действий)"
    return header + "\n" + "\n".join(lines)
