"""GD v1.0: OpenRouter narrative for rounds and finale (spec §6–7)."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from waifu_bot.core.config import settings
from waifu_bot.game.constants import (
    AI_NARRATIVE_GROTESQUE_HUMOR_RU,
    WAIFU_CLASS_LABEL_RU,
    WAIFU_RACE_LABEL_RU,
)
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

GD_SYSTEM_PROMPT = f"""Ты рассказчик в фэнтезийной RPG-игре про вайфу.
Пишешь о событиях групповых походов в Telegram-группе.
Стиль: ярко, с юмором, с характером персонажей. {AI_NARRATIVE_GROTESQUE_HUMOR_RU}
3–5 предложений на раунд.
Язык: русский. Без markdown. Без чисел и игровых механик в тексте.
Персонажи — девушки с именами и характерами.
Для каждого применённого навыка придумай органичное название (1–3 слова),
соответствующее классу: маг — магия/стихии, воин — сила/ярость,
ассассин — скрытность/яд, лекарь — исцеление/свет,
рыцарь — защита/команда, лучник — точность/скорость, торговец — хитрость/алхимия.
Для каждого молчавшего — обязательная персональная шутка по классу и расе.
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
    dungeon = ctx.get("dungeon_name") or "Подземелье"
    biome = ctx.get("biome_tag") or "неизвестно"
    n = ctx.get("round", 1)
    total_est = ctx.get("total_est") or "?"
    outcome = ctx.get("round_outcome") or "ongoing"
    lines = [
        f"Подземелье: {dungeon} (биом: {biome})",
        f"Раунд {n} из ~{total_est}, следующий через 30 мин.",
        f"Статус раунда: {outcome}",
        "СОСТАВ ОТРЯДА:",
    ]
    lines.append(
        "Класс и раса каждой указаны словами и id — не подменяй архетип (маг ≠ воин с мечом)."
    )
    for p in ctx.get("party") or []:
        lines.append(format_gd_party_member_line(p, for_start=False))
    lines.append("ПРОТИВНИКИ:")
    for m in ctx.get("monsters") or []:
        mx = max(1, int(m.get("max_hp") or 1))
        hp = int(m.get("hp") or 0)
        pct = int(100 * hp / mx)
        lines.append(f"- {m.get('name', 'Монстр')} Lv{m.get('level', '?')}, HP: {pct}%")
    lines.append("ДЕЙСТВИЯ ЗА РАУНД:")
    for a in ctx.get("actions") or []:
        if a.get("kind") == "silent":
            lines.append(f"- user {a.get('user_id')}: молчала")
        elif a.get("kind") == "text":
            lines.append(f"- user {a.get('user_id')}: текстовые атаки, суммарный урон условный")
        elif a.get("skill"):
            lines.append(
                f"- user {a.get('user_id')}: навык effect_type={a.get('skill')}"
            )
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
    lines.append(
        "Напиши 4–6 предложений на русском: отряд собирается у входа, "
        "настрой, короткие реплики или мысли в духе персонажей, ощущение угрозы впереди. "
        "Без markdown. Не повторяй дословно системные фразы про «30 минут»."
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
            return text, text
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
            return text, text
    except Exception:
        logger.exception("GD narrative OpenRouter failed")
        return None, stub


async def generate_gd_finale_narrative(ctx: dict[str, Any], *, timeout_sec: float = 20.0) -> tuple[str | None, str]:
    """§7.3 epilogue: MVP + lowest contributor."""
    stub = "Герои вышли из подземелья — впереди новые приключения."
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    if not api_key.strip():
        return None, stub
    extra = (
        "Напиши эпичный короткий итог похода по данным ниже. "
        "Выдели MVP (лучший вклад) и одного с наименьшим вкладом — шутливо, без оскорблений. "
        "Без markdown и без цифр.\n\n"
        + json.dumps(ctx, ensure_ascii=False, default=str)
    )
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
            return text, text
    except Exception:
        logger.exception("GD finale narrative failed")
        return None, stub
