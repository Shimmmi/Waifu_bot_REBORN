"""Человекочитаемый журнал раунда GD v1 из actions_json + context_json (+ outcomes для старых записей)."""
from __future__ import annotations

from typing import Any


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
