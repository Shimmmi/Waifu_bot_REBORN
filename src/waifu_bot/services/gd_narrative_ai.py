"""GD v1.0: OpenRouter narrative for rounds and finale (spec §6–7)."""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx

from waifu_bot.core.config import settings
from waifu_bot.game.constants import (
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
    GD_EFFECT_TYPE_LABEL_RU,
    GD_NARRATIVE_FORMATTING_RU,
    WAIFU_CLASS_LABEL_RU,
    WAIFU_RACE_LABEL_RU,
)
from waifu_bot.services.ai_narrative_rewrite import escape_telegram_html, rhythm_rewrite_narrative
from waifu_bot.services.gd_round_engine import _attack_type_for_class

logger = logging.getLogger(__name__)


def waifu_race_label_ru(race_id: int | None) -> str:
    if race_id is None:
        return "неизвестная раса"
    return WAIFU_RACE_LABEL_RU.get(int(race_id), f"раса (id {race_id})")


def waifu_class_label_ru(class_id: int | None) -> str:
    if class_id is None:
        return "неизвестный класс"
    return WAIFU_CLASS_LABEL_RU.get(int(class_id), f"класс (id {class_id})")


def gd_attack_style_hint_ru(class_id: int | None) -> str:
    cid = int(class_id or 0)
    atk = _attack_type_for_class(cid)
    if atk == "spell":
        return "стиль боя: магия и заклинания (не воин с мечом)"
    if atk == "ranged":
        return "стиль боя: дальний бой, лук/метательное"
    return "стиль боя: ближний бой, сила"


def format_gd_party_member_line(p: dict[str, Any], *, for_start: bool) -> str:
    """Одна строка отряда для промпта: словесные класс/раса + id, чтобы не путать LLM (напр. маг и ангел оба id 4)."""
    name = p.get("name", "Вайфу")
    cid = p.get("class_id")
    rid = p.get("race_id")
    lvl = p.get("level", "?")
    cls_word = waifu_class_label_ru(int(cid) if cid is not None else None)
    race_word = waifu_race_label_ru(int(rid) if rid is not None else None)
    atk = gd_attack_style_hint_ru(int(cid) if cid is not None else None)
    uid = p.get("user_id")
    uid_bit = f", telegram user_id={uid}" if uid is not None else ""
    base = (
        f"- Имя: {name}{uid_bit}. "
        f"Класс (роль в бою): {cls_word} [внутр. id класса: {cid}]. "
        f"Раса: {race_word} [внутр. id расы: {rid}]. "
        f"Уровень персонажа: {lvl}. {atk}."
    )
    if for_start:
        return base
    mx = max(1, int(p.get("max_hp") or 1))
    hp = int(p.get("current_hp") or 0)
    pct = int(100 * hp / mx)
    return f"{base} HP в бою: ~{pct}%."


def _member_display_name(p: dict[str, Any]) -> str:
    return str(p.get("name") or f"Игрок {p.get('user_id', '?')}")


def _party_by_uid(party: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in party:
        uid = p.get("user_id")
        if uid is not None:
            out[int(uid)] = p
    return out


def gd_party_size_mode(party: list[dict[str, Any]]) -> Literal["solo", "small", "large"]:
    n = len(party)
    if n <= 1:
        return "solo"
    if n <= 4:
        return "small"
    return "large"


def gd_silent_members(
    party: list[dict[str, Any]],
    actions_log: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    by_uid = _party_by_uid(party)
    silent_uids = {
        int(a.get("user_id") or 0)
        for a in (actions_log or [])
        if a.get("kind") == "silent" and a.get("user_id") is not None
    }
    return [by_uid[uid] for uid in silent_uids if uid in by_uid]


def _member_activity_score(
    uid: int,
    actions_log: list[dict[str, Any]] | None,
    raw_buffer_users: dict[str, Any] | None,
) -> int:
    score = 0
    rb = (raw_buffer_users or {}).get(str(uid))
    if isinstance(rb, dict):
        score += int(rb.get("text_len") or 0) * 10
        score += len(rb.get("media") or []) * 50
    for a in actions_log or []:
        if int(a.get("user_id") or 0) != uid:
            continue
        if a.get("kind") == "text":
            score += 100 + int(a.get("damage") or 0)
        elif a.get("skill"):
            score += 150
    return score


def gd_active_members(
    party: list[dict[str, Any]],
    actions_log: list[dict[str, Any]] | None,
    raw_buffer_users: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    by_uid = _party_by_uid(party)
    silent_uids = {
        int(a.get("user_id") or 0)
        for a in (actions_log or [])
        if a.get("kind") == "silent"
    }
    active_uids: set[int] = set()
    for uid in by_uid:
        if uid not in silent_uids:
            active_uids.add(uid)
    for a in actions_log or []:
        uid = int(a.get("user_id") or 0)
        if uid in by_uid and (a.get("kind") == "text" or a.get("skill")):
            active_uids.add(uid)
    rb = raw_buffer_users or {}
    for uid_str, u in rb.items():
        if not isinstance(u, dict):
            continue
        uid = int(uid_str)
        if uid not in by_uid:
            continue
        if int(u.get("text_len") or 0) > 0 or u.get("media"):
            active_uids.add(uid)
    ranked = sorted(
        active_uids,
        key=lambda uid: _member_activity_score(uid, actions_log, raw_buffer_users),
        reverse=True,
    )
    return [by_uid[uid] for uid in ranked]


def build_gd_composition_instructions(
    party: list[dict[str, Any]],
    actions_log: list[dict[str, Any]] | None = None,
    *,
    phase: Literal["start", "round", "finale"] = "round",
    raw_buffer_users: dict[str, Any] | None = None,
    contributions: dict[int, float] | None = None,
) -> str:
    """Динамические правила: solo / small / large + только реальный состав."""
    mode = gd_party_size_mode(party)
    names_all = [_member_display_name(p) for p in party]
    silent_names = [_member_display_name(p) for p in gd_silent_members(party, actions_log)]
    active_focus = [
        _member_display_name(p)
        for p in gd_active_members(party, actions_log, raw_buffer_users)[:3]
    ]

    lines = [
        "ПРАВИЛА СОСТАВА (обязательны):",
        (
            f"В походе ровно {len(party)} участник(ов). Упоминай в тексте ТОЛЬКО персонажей "
            f"из блока СОСТАВ ОТРЯДА: {', '.join(names_all) if names_all else '—'}."
        ),
        (
            "ЗАПРЕЩЕНО придумывать дополнительных союзников, «остальных в отряде», "
            "рыцарей, целительниц и любых NPC, которых нет в списке."
        ),
    ]

    if mode == "solo":
        solo_name = _member_display_name(party[0]) if party else "боец"
        lines.append(
            f"Режим: одиночный поход. Единственный боец — {solo_name}. "
            "Не пиши про «остальных», «товарищей в отряде» или бездействующих союзников — их нет. "
            "Можно обыграть одиночество, отсутствие подкрепления или самостоятельность."
        )
    elif mode == "small":
        lines.append(
            f"Режим: небольшой отряд ({len(party)} чел.). Можешь кратко затронуть каждого из списка по имени."
        )
    else:
        focus = ", ".join(active_focus) if active_focus else ", ".join(names_all[:3])
        lines.append(
            f"Режим: большой отряд ({len(party)} чел.). В фокусе повествования до 3 наиболее "
            f"активных за раунд: {focus}. Остальных из списка — не более одной-двух коротких фраз "
            "суммарно, без выдуманных персонажей."
        )

    if phase == "round":
        if silent_names:
            lines.append(
                "За этот раунд молчали (персональная шутка по классу и расе — только про них): "
                + ", ".join(silent_names)
                + "."
            )
        else:
            lines.append(
                "За этот раунд в данных нет молчавших — не выдумывай бездействующих союзников "
                "и не шути про «тех, кто отсиживался в стороне»."
            )
    elif phase == "start":
        if mode == "solo":
            lines.append(
                "На старте: настрой одиночки у входа, без ожидания подмоги от несуществующих союзников."
            )
        else:
            lines.append("На старте: отрази настрой всего реального состава, без лишних персонажей.")
    elif phase == "finale":
        lines.append(
            "Финал: итог похода только по реальным участникам. MVP и наименьший вклад — "
            "только из списка состава и данных вклада ниже."
        )
        if contributions and party:
            by_uid = _party_by_uid(party)
            ranked = sorted(contributions.items(), key=lambda x: -float(x[1]))
            if ranked:
                mvp_uid, _ = ranked[0]
                low_uid, _ = ranked[-1]
                mvp_p = by_uid.get(int(mvp_uid))
                low_p = by_uid.get(int(low_uid))
                if mvp_p:
                    lines.append(f"MVP по вкладу: {_member_display_name(mvp_p)}.")
                if low_p and int(low_uid) != int(mvp_uid):
                    lines.append(
                        f"Наименьший вклад (шутливо, без оскорблений): {_member_display_name(low_p)}."
                    )

    return "\n".join(lines)


def _party_names_by_uid(party: list[dict[str, Any]]) -> dict[int, str]:
    return {int(p["user_id"]): _member_display_name(p) for p in party if p.get("user_id") is not None}


def _format_gd_action_line(a: dict[str, Any], names: dict[int, str]) -> str | None:
    if a.get("kind") == "cycle_start":
        return None
    uid = a.get("user_id")
    if uid is None and not a.get("skill"):
        return None
    label = names.get(int(uid or 0), f"user {uid}") if uid is not None else ""
    uid_bit = f" (user {uid})" if uid is not None else ""
    if a.get("kind") == "silent":
        return f"- {label}{uid_bit}: молчала"
    if a.get("kind") == "text":
        dmg = int(a.get("damage") or 0)
        series = int(a.get("series") or 1)
        series_bit = f" (серия из {series} сообщений)" if series > 1 else ""
        return f"- {label}{uid_bit}: текстовая атака{series_bit}, урон {dmg}"
    if a.get("skill"):
        who = label or "отряд"
        eff = GD_EFFECT_TYPE_LABEL_RU.get(str(a.get("skill")), "эффект")
        parts = [eff]
        if a.get("damage") is not None:
            parts.append(f"урон {int(a['damage'])}")
        if a.get("heal") is not None:
            parts.append(f"лечение {int(a['heal'])}")
        return f"- {who}{uid_bit}: навык {', '.join(parts)}"
    return None


def build_gd_actions_format_block(ctx: dict[str, Any]) -> str:
    """Подсказки для HTML-вёрстки навыков по действиям раунда."""
    party = list(ctx.get("party") or [])
    actions = list(ctx.get("actions") or [])
    names = _party_names_by_uid(party)
    lines = ["НАВЫКИ И ЭФФЕКТЫ (для вёрстки):"]
    has_skill = False
    for a in actions:
        uid = a.get("user_id")
        skill = a.get("skill")
        if skill:
            has_skill = True
            who = names.get(int(uid or 0), f"user {uid}") if uid is not None else "отряд"
            effect_label = GD_EFFECT_TYPE_LABEL_RU.get(str(skill), "эффект")
            amount = ""
            if a.get("damage") is not None:
                amount = f", урон {int(a['damage'])}"
            elif a.get("heal") is not None:
                amount = f", лечение {int(a['heal'])}"
            lines.append(
                f"- {who}: придумай название навыка (1–3 слова) → "
                f"<b>Название</b> ({effect_label}{amount}); имя вайфу в <b>{who}</b>"
            )
        elif a.get("kind") == "text" and uid is not None:
            who = names.get(int(uid), f"user {uid}")
            dmg = int(a.get("damage") or 0)
            series = int(a.get("series") or 1)
            series_bit = " серия ударов," if series > 1 else ""
            lines.append(
                f"- {who}: текстовая атака → имя в <b>{who}</b>,{series_bit} эффект (урон {dmg})"
            )
    if not has_skill and not any(a.get("kind") == "text" for a in actions):
        lines.append("- Нет навыков и текстовых атак — опиши общий ход боя.")
    return "\n".join(lines)


GD_SYSTEM_PROMPT = f"""Ты рассказчик в фэнтезийной RPG-игре про вайфу.
Пишешь о событиях групповых походов в Telegram-группе.
Стиль: ярко, с юмором, с характером персонажей. {AI_NARRATIVE_GROTESQUE_HUMOR_RU}
3–5 предложений на раунд, 2–3 абзаца с пустой строкой между ними.
{GD_NARRATIVE_FORMATTING_RU}
Язык: русский. Без markdown (#, *, списки). Без чисел и игровых механик в тексте.
Персонажи — девушки с именами и характерами.
Состав отряда и правила, кого упоминать, заданы в user-сообщении — следуй им строго.
Для каждого применённого навыка придумай органичное название (1–3 слова),
соответствующее классу: маг — магия/стихии, воин — сила/ярость,
ассассин — скрытность/яд, лекарь — исцеление/свет,
рыцарь — защита/команда, лучник — точность/скорость, торговец — хитрость/алхимия.
Статус раунда определяет тон:
victory — финальный удар, гибель монстра, ощущение завершённости.
ongoing — стычка не закончена. НЕ убивай монстра. Намёк на продолжение.
party_wiped — монстр торжествует, отряд без сознания, намёк на возвращение."""


def _openrouter_url() -> str:
    base = (getattr(settings, "openrouter_base_url", None) or "https://openrouter.ai/api/v1").rstrip("/")
    return f"{base}/chat/completions"


def _headers() -> dict[str, str]:
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    referer = str(getattr(settings, "public_base_url", "https://waifu-bot.reborn")).rstrip("/")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Referer": referer,
        "HTTP-Referer": referer,
        "X-Title": "Waifu Bot",
    }


def _assistant_text(choice: object) -> str:
    if not isinstance(choice, dict):
        return ""
    msg = choice.get("message")
    if isinstance(msg, dict):
        raw = msg.get("content")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            parts = []
            for block in raw:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            if parts:
                return "\n".join(parts).strip()
        r = msg.get("reasoning")
        if isinstance(r, str) and r.strip():
            return r.strip()
    return ""


def build_user_prompt_round(ctx: dict[str, Any]) -> str:
    """§6.3 dynamic user prompt from structured_context."""
    party = list(ctx.get("party") or [])
    actions = list(ctx.get("actions") or [])
    raw_buffer = ctx.get("raw_buffer_users") or {}
    dungeon = ctx.get("dungeon_name") or "Подземелье"
    biome = ctx.get("biome_tag") or "неизвестно"
    n = ctx.get("round", 1)
    total_est = ctx.get("total_est") or "?"
    outcome = ctx.get("round_outcome") or "ongoing"
    names = _party_names_by_uid(party)
    lines = [
        f"Подземелье: {dungeon} (биом: {biome})",
        f"Раунд {n} из ~{total_est}, следующий через 15 мин.",
        f"Статус раунда: {outcome}",
        "СОСТАВ ОТРЯДА:",
    ]
    lines.append(
        "Класс и раса каждой указаны словами и id — не подменяй архетип (маг ≠ воин с мечом)."
    )
    for p in party:
        lines.append(format_gd_party_member_line(p, for_start=False))
    lines.append(
        build_gd_composition_instructions(
            party,
            actions,
            phase="round",
            raw_buffer_users=raw_buffer,
        )
    )
    lines.append("ПРОТИВНИКИ:")
    for m in ctx.get("monsters") or []:
        mx = max(1, int(m.get("max_hp") or 1))
        hp = int(m.get("hp") or 0)
        pct = int(100 * hp / mx)
        lines.append(f"- {m.get('name', 'Монстр')} Lv{m.get('level', '?')}, HP: {pct}%")
    lines.append("ДЕЙСТВИЯ ЗА РАУНД:")
    for a in actions:
        line = _format_gd_action_line(a, names)
        if line:
            lines.append(line)
    lines.append(build_gd_actions_format_block(ctx))
    if outcome == "victory":
        mvp_name = ctx.get("mvp_name")
        victory_line = (
            "ПОБЕДА: все монстры повержены — это финальный, победный раунд. "
            "Заверши сцену триумфально, опиши добивающий удар и гибель противника."
        )
        if mvp_name:
            victory_line += f" Отдельно отметь MVP похода — <b>{mvp_name}</b> (похвали за вклад)."
        lines.append(victory_line)
    fl = ctx.get("flags") or {}
    if fl.get("revive_no_target"):
        lines.append("Особое: воскрешение — целей не было, обыграй.")
    if fl.get("heal_no_target"):
        lines.append("Особое: лечение не нашло раненых, обыграй.")
    lines.append("ИСХОД (для тона, не выводи числа в ответе):")
    lines.append(json.dumps(ctx.get("outcomes_summary") or {}, ensure_ascii=False))
    rb = ctx.get("raw_buffer_users") or {}
    if rb:
        lines.append("СЫРОЙ СБОР СООБЩЕНИЙ (telegram user_id → длина текста, медиа-типы, молчание):")
        lines.append(json.dumps(rb, ensure_ascii=False))
    oh = ctx.get("outcomes_hits") or []
    if oh:
        lines.append("СВОДКА УДАРОВ/ЭФФЕКТОВ (до 50 записей, для тона):")
        lines.append(json.dumps(oh, ensure_ascii=False, default=str))
    ohl = ctx.get("outcomes_heals") or []
    if ohl:
        lines.append("ИСЦЕЛЕНИЯ:")
        lines.append(json.dumps(ohl, ensure_ascii=False, default=str))
    return "\n".join(lines)


def build_user_prompt_start(
    dungeon_name: str,
    biome_tag: str,
    party: list[dict[str, Any]],
) -> str:
    """Промпт для вступления: отряд у входа в подземелье, без боя."""
    lines = [
        "Этап: СТАРТ ПОХОДА (ещё нет боя, только вход в зону).",
        f"Подземелье: {dungeon_name}",
        f"Краткий антураж/биом: {biome_tag or 'не указан'}.",
        "СОСТАВ ОТРЯДА. Строго соблюдай класс и расу по строкам ниже; не приписывай меч или ярость воина магу, лучнику, лекарю и т.д.",
        "В ответе не перечисляй сухие числа статов, но отрази уровень каждой намёком (опыт, новичок, бывалая, ветеран) согласно указанному уровню.",
    ]
    for p in party:
        lines.append(format_gd_party_member_line(p, for_start=True))
    lines.append(build_gd_composition_instructions(party, phase="start"))
    lines.append(GD_NARRATIVE_FORMATTING_RU)
    lines.append(
        "Напиши 4–6 предложений на русском в 2 абзаца: отряд собирается у входа, "
        "настрой, короткие реплики или мысли в духе персонажей, ощущение угрозы впереди. "
        "Не повторяй дословно системные фразы про «15 минут»."
    )
    return "\n".join(lines)


def build_user_prompt_finale(ctx: dict[str, Any]) -> str:
    """Эпилог похода: состав, вклад, правила без выдуманных участников."""
    party = list(ctx.get("party") or [])
    contributions_raw = ctx.get("contributions") or {}
    contributions: dict[int, float] = {}
    for k, v in contributions_raw.items():
        try:
            contributions[int(k)] = float(v)
        except (TypeError, ValueError):
            continue
    dungeon = ctx.get("dungeon_name") or "Подземелье"
    lines = [
        "Этап: ФИНАЛ ПОХОДА (победа, выход из подземелья).",
        f"Подземелье: {dungeon}",
        "СОСТАВ ОТРЯДА (только эти участники существовали в походе):",
    ]
    for p in party:
        lines.append(format_gd_party_member_line(p, for_start=True))
    lines.append(
        build_gd_composition_instructions(
            party,
            phase="finale",
            contributions=contributions or None,
        )
    )
    if contributions:
        by_uid = _party_by_uid(party)
        contrib_lines = []
        for uid, score in sorted(contributions.items(), key=lambda x: -x[1]):
            p = by_uid.get(uid)
            nm = _member_display_name(p) if p else f"user {uid}"
            contrib_lines.append(f"- {nm} (user {uid}): относительный вклад {score:.1f}")
        lines.append("ВКЛАД УЧАСТНИКОВ (для MVP и аутсайдера, не выводи числа в ответе):")
        lines.extend(contrib_lines)
    lines.append(GD_NARRATIVE_FORMATTING_RU)
    lines.append(
        "Напиши эпичный короткий итог похода (4–6 предложений, 2 абзаца). "
        "Выдели MVP и одного с наименьшим вкладом — шутливо, без оскорблений. "
        "Без цифр."
    )
    return "\n".join(lines)


async def generate_gd_start_narrative(
    *,
    dungeon_name: str,
    biome_tag: str,
    party: list[dict[str, Any]],
    timeout_sec: float = 18.0,
    model: str | None = None,
) -> tuple[str | None, str]:
    """Старт похода: нарратив о составе и входе. Без API — короткий stub."""
    stub = (
        f"Отряд собирается у входа в «{dungeon_name}». "
        "Впереди тёмные коридоры — пора действовать."
    )
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    if not api_key.strip() or not party:
        return None, stub
    user_prompt = build_user_prompt_start(dungeon_name, biome_tag, party)
    payload = {
        "model": model or getattr(settings, "openrouter_model", None) or "anthropic/claude-3.5-sonnet",
        "max_tokens": 400,
        "temperature": 0.85,
        "messages": [
            {"role": "system", "content": GD_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(_openrouter_url(), headers=_headers(), json=payload)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return None, stub
            text = _assistant_text(choices[0])
            if not text:
                return None, stub
            final = await rhythm_rewrite_narrative(
                text,
                caller="gd-start",
                length_hint="4–6 предложений, 2 абзаца",
                preserve_html=True,
            )
            out = final or escape_telegram_html(text)
            return out, out
    except Exception:
        logger.exception("GD start narrative OpenRouter failed")
        return None, stub


async def generate_gd_round_narrative(
    ctx: dict[str, Any],
    *,
    timeout_sec: float = 15.0,
    model: str | None = None,
) -> tuple[str | None, str]:
    """
    Returns (ai_narrative_for_db_or_none, message_for_chat).
    On failure: (None, stub).
    """
    stub = f"[Раунд {ctx.get('round', 1)}. Бой продолжается...]"
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    if not api_key.strip():
        return None, stub
    user_prompt = build_user_prompt_round(ctx)
    payload = {
        "model": model or getattr(settings, "openrouter_model", None) or "anthropic/claude-3.5-sonnet",
        "max_tokens": 512,
        "temperature": 0.85,
        "messages": [
            {"role": "system", "content": GD_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(_openrouter_url(), headers=_headers(), json=payload)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return None, stub
            text = _assistant_text(choices[0])
            if not text:
                return None, stub
            final = await rhythm_rewrite_narrative(
                text,
                caller="gd-round",
                length_hint="3–5 предложений, 2–3 абзаца",
                preserve_html=True,
            )
            out = final or escape_telegram_html(text)
            return out, out
    except Exception:
        logger.exception("GD narrative OpenRouter failed")
        return None, stub


async def generate_gd_finale_narrative(ctx: dict[str, Any], *, timeout_sec: float = 20.0) -> tuple[str | None, str]:
    """§7.3 epilogue: MVP + lowest contributor."""
    stub = "Герои вышли из подземелья — впереди новые приключения."
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    if not api_key.strip():
        return None, stub
    extra = build_user_prompt_finale(ctx)
    payload = {
        "model": getattr(settings, "openrouter_model", None) or "anthropic/claude-3.5-sonnet",
        "max_tokens": 500,
        "temperature": 0.85,
        "messages": [
            {"role": "system", "content": GD_SYSTEM_PROMPT},
            {"role": "user", "content": extra},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(_openrouter_url(), headers=_headers(), json=payload)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return None, stub
            text = _assistant_text(choices[0])
            if not text:
                return None, stub
            final = await rhythm_rewrite_narrative(
                text,
                caller="gd-finale",
                length_hint="4–6 предложений, 2 абзаца",
                preserve_html=True,
            )
            out = final or escape_telegram_html(text)
            return out, out
    except Exception:
        logger.exception("GD finale narrative failed")
        return None, stub
