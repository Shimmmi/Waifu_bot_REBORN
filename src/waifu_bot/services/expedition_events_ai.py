"""ИИ-генерация текста событий экспедиции через OpenRouter (ТЗ)."""

from __future__ import annotations

import base64
import json
import logging
import random
import re
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models.dungeon import MonsterTemplate
from waifu_bot.db.models.skill import Skill, SkillType
from waifu_bot.game.constants import AI_NARRATIVE_GROTESQUE_HUMOR_RU

logger = logging.getLogger(__name__)


def _openrouter_url() -> str:
    base = (getattr(settings, "openrouter_base_url", None) or "https://openrouter.ai/api/v1").rstrip("/")
    return f"{base}/chat/completions"


def _openrouter_headers() -> dict[str, str]:
    api_key = getattr(settings, "openrouter_api_key", None) or ""
    referer = str(getattr(settings, "public_base_url", "https://waifu-bot.reborn")).rstrip("/")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter ожидает site URL для рейтинга; в HTTP это стандартный заголовок Referer
        "Referer": referer,
        "HTTP-Referer": referer,
        "X-Title": "Waifu Bot",
    }


def _string_from_openrouter_content_part(block: object) -> str:
    """Текст из одного элемента message.content (строка или объект блока)."""
    if isinstance(block, str) and block.strip():
        return block.strip()
    if not isinstance(block, dict):
        return ""
    for key in ("text", "output_text", "content"):
        val = block.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for inner_key in ("value", "text", "content"):
                inner = val.get(inner_key)
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
    return ""


def _extract_openrouter_assistant_text(choice: object) -> str:
    """
    Достаёт текст ответа из choices[0] независимо от варианта схемы OpenRouter/OpenAI.
    У части моделей content — строка, у части — список блоков {type,text} или {type, text}.
    У reasoning/thinking-моделей (в т.ч. часть Gemini через OpenRouter) иногда пустой content,
    а видимый ответ — в message.reasoning; encrypted reasoning_details не используем.
    """
    if not isinstance(choice, dict):
        return ""
    msg = choice.get("message")
    if isinstance(msg, dict):
        raw = msg.get("content")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            parts: list[str] = []
            for block in raw:
                piece = _string_from_openrouter_content_part(block)
                if piece:
                    parts.append(piece)
            if parts:
                return "\n".join(parts).strip()
        reasoning = msg.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
    # legacy / альтернативные ответы
    t = choice.get("text")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return ""


def _openrouter_text_extra() -> dict[str, object]:
    """Не отдавать reasoning-токены в ответе: экономия лимита и меньше пустого content у Gemini."""
    return {"reasoning": {"exclude": True}}


def _warn_if_empty_assistant(caller: str, choice: object, extracted: str) -> None:
    if extracted:
        return
    if not isinstance(choice, dict):
        return
    msg = choice.get("message")
    if not isinstance(msg, dict):
        logger.warning("OpenRouter %s: пустой текст, нет message в choice", caller)
        return
    raw = msg.get("content")
    logger.warning(
        "OpenRouter %s: пустой текст; message keys=%s content_type=%s",
        caller,
        list(msg.keys()),
        type(raw).__name__,
    )


async def generate_expedition_tick_narrative(
    *,
    location: str,
    biome_tags: list[str],
    challenge_name: str,
    challenge_category: str,
    challenge_level: int,
    squad_snapshot: list[dict],
    outcome: str,
    event_num: int,
    total_events: int,
    is_final: bool,
    twist: dict | None,
    prev_summary: str,
    squad_hp_ratio: float = 0.0,
) -> Optional[str]:
    """
    Короткий нарратив одного тика экспедиции v1.3 (2–4 предложения, RU).
    Контекст структурирован по ТЗ (биом, испытание, отряд, исход, твист).
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        return None

    model = settings.openrouter_model
    ctx = {
        "location": location,
        "biome_tags": [t for t in biome_tags if t],
        "challenge": {
            "name": challenge_name,
            "category": challenge_category,
            "level": challenge_level,
        },
        "squad": squad_snapshot,
        "outcome": outcome,
        "event_num": event_num,
        "total_events": total_events,
        "is_final": is_final,
        "twist": twist,
        "prev_summary": (prev_summary or "")[:500],
        "squad_hp_ratio": round(float(squad_hp_ratio), 3),
    }
    prompt = (
        "Напиши короткое повествование (2–4 предложения, на русском) об одном эпизоде экспедиции в фэнтези-стиле. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        "Это эпизод номер event_num из total_events — обязательно другая сцена, другой момент конфликта, чем раньше. "
        "Не повторяй дословно и не копируй структуру предыдущего текста из prev_summary: придумай новое развитие. "
        "Поле squad_hp_ratio — доля суммарного здоровья отряда (0..1), без названия чисел: при низком значении больше угрозы, ран, усталости; при высоком — можно увереннее. "
        "Если is_final true — это последний эпизод перед возвращением; передай напряжение и состояние отряда, без спойлера итога всей экспедиции. "
        "Следуй контексту JSON; не перечисляй числа и механики вслух, покажи действие и атмосферу. "
        "Исход outcome эпизода (не финал экспедиции): triumph — уверенный успех; struggle — с трудом; survived_barely — едва выстояли. "
        f"Контекст: {json.dumps(ctx, ensure_ascii=False)}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 320,
                    "temperature": 0.82,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "OpenRouter expedition tick: HTTP %s body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("expedition tick", first, text)
            return text or None
    except Exception as e:
        logger.warning("OpenRouter expedition tick error: %s", e)
        return None


async def generate_expedition_event(
    expedition_name: str,
    success: bool,
    duration_minutes: int,
    squad_names: list[str],
    reward_gold: int,
    reward_experience: int,
) -> Optional[str]:
    """
    Генерирует короткое описание исхода экспедиции (2–3 предложения) через OpenRouter.
    Возвращает None, если ключ не задан или запрос не удался.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        return None

    model = settings.openrouter_model

    outcome = "успешно завершили" if success else "не справились и вернулись ни с чем"
    names = ", ".join(squad_names[:5]) if squad_names else "отряд"
    prompt = (
        f"Напиши коротко (2–3 предложения, на русском) описание исхода экспедиции в фэнтези-стиле. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        f"Экспедиция: «{expedition_name}». {names} {outcome}. "
        f"Длительность: {duration_minutes} мин. "
        + (f"Награда: {reward_gold} золота, {reward_experience} опыта." if success else "")
        + " Без вступления, только сам текст события."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.7,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "OpenRouter expedition event: HTTP %s (400=bad request, 401=key, 402=quota, 429=rate limit). body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("expedition event", first, text)
            return text or None
    except Exception as e:
        logger.warning("OpenRouter expedition event error: %s", e)
        return None


def _parse_name_bio_json(raw: str) -> Optional[tuple[str, str]]:
    """Извлекает name и bio из ответа ИИ. Защита от лишнего текста и markdown."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # Снимаем обёртку ```json ... ``` если модель её добавила
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    # Сначала пробуем распарсить целиком
    try:
        data = json.loads(raw)
        name = (data.get("name") or "").strip()
        bio = (data.get("bio") or "").strip()
        if name and bio:
            return (name, bio)
    except json.JSONDecodeError:
        pass
    # Вырезаем блок {...} на случай пояснений вокруг JSON
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            name = (data.get("name") or "").strip()
            bio = (data.get("bio") or "").strip()
            if name and bio:
                return (name, bio)
        except json.JSONDecodeError:
            pass
    return None


async def generate_hire_waifu_name_and_bio(
    race_ru: str,
    class_ru: str,
    level: int,
    perk_names: list[str],
) -> Optional[tuple[str, str]]:
    """
    Генерирует имя и биографию наёмницы через OpenRouter.
    ИИ придумывает короткое фэнтезийное женское имя (1–2 слога) по расе/классу и 2–3 предложения био.
    Возвращает (name, bio) или None при ошибке/недоступности.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        return None

    model = settings.openrouter_model_hire or settings.openrouter_model
    skills_str = ", ".join(perk_names) if perk_names else "разнообразный опыт"

    prompt = f"""Ты — рассказчик в фэнтезийной RPG-игре про вайфу-наёмниц.
Придумай имя и биографию для наёмницы со следующими параметрами:
Раса: {race_ru}
Класс: {class_ru}
Уровень: {level}
Умения: {skills_str}

Требования к имени: фэнтезийное женское имя, подходящее под расу и класс (длина любая). Не используй имена из популярных аниме.
Требования к биографии: 2–3 предложения, русский язык, живо и с характером, без механик и чисел. Упомяни умения через образы и действия.
{AI_NARRATIVE_GROTESQUE_HUMOR_RU} Имя и био — в том же духе.

Ответь СТРОГО в формате JSON без пояснений и markdown:
{{"name": "Имя", "bio": "Биография..."}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.85,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "OpenRouter hire name+bio: HTTP %s (400=bad request, 401=key, 402=quota, 429=rate limit). body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("hire name+bio", first, text)
            parsed = _parse_name_bio_json(text)
            if not parsed and text:
                logger.warning(
                    "OpenRouter hire name+bio: не удалось распарсить JSON, фрагмент ответа: %s",
                    text[:240].replace("\n", " "),
                )
            return parsed
    except Exception as e:
        logger.warning("OpenRouter hire name+bio error: %s", e)
        return None


async def generate_shop_merchant_line(
    item_name: str,
    item_level: int,
    item_rarity: str,
    item_bonuses: str = "",
    context: str = "buy",
) -> Optional[str]:
    """
    Генерирует короткую реплику торговца для магазина (1–2 предложения, RU).
    context: buy — продаёшь со витрины; sell — покупаешь у странника; gamble — зовёшь на гембу.
    Использует ту же модель, что и генерация BIO наёмных вайфу (OPENROUTER_MODEL_HIRE или OPENROUTER_MODEL).
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.warning("[shop merchant-line] Пропуск: не задан OPENROUTER_API_KEY")
        return None

    model = settings.openrouter_model_hire or settings.openrouter_model
    ctx = (context or "buy").strip().lower()
    if ctx not in ("buy", "sell", "gamble", "smith"):
        ctx = "buy"

    logger.info(
        "[shop merchant-line] Запрос OpenRouter: model=%s context=%s item=%s level=%s rarity=%s",
        model,
        ctx,
        item_name,
        item_level,
        item_rarity,
    )
    bonuses_hint = ""
    if item_bonuses and item_bonuses.strip():
        bonuses_hint = f" Бонусы предмета (упомяни, если уместно): {item_bonuses.strip()}."

    if ctx == "gamble":
        prompt = (
            "Ты хитрый, но обаятельный барыга с мистической лавкой. "
            "1–2 предложения на русском: шепчешь страннику о скрытых сокровищах в мешках, лёгкий намёк на риск и награду. "
            "Обращение — «странник». Разрешены только теги <b>...</b>. Без markdown и без пояснений."
        )
    elif ctx == "smith":
        prompt = (
            "Ты старый кузнец в фэнтезийной кузнице. "
            "1–2 предложения на русском: расскажи о заточке предметов, шансе успеха и риске поломки после +7. "
            "Обращайся к клиенту как к «страннику». Разрешены только теги <b>...</b>. Без markdown и без пояснений."
        )
    elif ctx == "sell":
        prompt = (
            "Ты лавочник, который **покупает** б/у добычу у странников (не продаёшь). "
            f"1–2 предложения на русском: торгуйся шутливо, интересуйся товаром, зови показать вещи из сумки. "
            f"Конкретный лот на прилавке в уме: {item_name}, уровень {int(item_level)}, редкость {item_rarity}.{bonuses_hint} "
            "Обращайся к клиенту как к «страннику». Разрешены только теги <b>...</b> для названия вещи. Без markdown и без пояснений."
        )
    else:
        prompt = (
            "Ты торговец в фэнтезийном магазине. "
            f"1-2 предложения на русском, порекомендуй предмет со витрины: {item_name}, уровень {int(item_level)}, редкость {item_rarity}.{bonuses_hint} "
            "Обращайся к покупателю как \"странник\". "
            "Разрешены только теги <b>...</b> для названия предмета. Без markdown и без пояснений."
        )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0.8,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "[shop merchant-line] OpenRouter HTTP %s (400=bad request, 401=key, 402=quota, 429=rate limit). body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                logger.warning("[shop merchant-line] OpenRouter вернул пустой или некорректный choices: %s", data.get("error") or data)
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("shop merchant-line", first, text)
                return None
            logger.info("[shop merchant-line] Успех, длина текста=%d", len(text))
            return text
    except Exception as e:
        logger.warning("[shop merchant-line] Ошибка запроса: %s", e, exc_info=True)
        return None


def _caravan_gk_truncate_text(text: Optional[str], max_len: int = 280) -> str:
    if not text:
        return ""
    s = str(text).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def monster_template_dominant_trait_ru(mt: MonsterTemplate) -> str:
    """Одна человекочитаемая метка угрозы по кривым шаблона (без сравнения с героем)."""
    dpl = float(mt.dmg_per_level or 0)
    hpl = float(mt.hp_per_level or 0)
    bd = float(mt.base_difficulty or 0)
    tr = float(mt.tier or 0)
    candidates: list[tuple[float, str]] = [
        (dpl / 2.5, "в бою особенно опасен быстрым ростом урона с уровнем"),
        (hpl / 12.0, "пугает плотностью — много здоровья на уровень"),
        (bd / 40.0, "отличается высокой базовой сложностью шаблона"),
        (tr / 4.0, "считается серьёзной угрозой по рангу"),
    ]
    score, label = max(candidates, key=lambda x: x[0])
    if score <= 0:
        return "на дороге встречается как обычная угроза акта"
    return label


_CARAVAN_GK_SKILLS_LIMIT = 28
_CARAVAN_GK_SKILL_DESC_MAX = 280
_CARAVAN_GK_MONSTERS_FETCH_CAP = 160
_CARAVAN_GK_MONSTERS_SAMPLE = 18


async def build_caravan_driver_game_knowledge(
    session: AsyncSession,
    current_act: int,
) -> dict[str, Any]:
    """Активные навыки и выборка шаблонов монстров по акту для совета погонщицы."""
    act = int(current_act)
    skill_rows = (
        await session.execute(
            select(Skill.id, Skill.name, Skill.description)
            .where(Skill.skill_type == int(SkillType.ACTIVE))
            .order_by(Skill.id)
            .limit(_CARAVAN_GK_SKILLS_LIMIT)
        )
    ).all()
    skills: list[dict[str, Any]] = [
        {
            "id": row[0],
            "name": row[1],
            "description": _caravan_gk_truncate_text(row[2], _CARAVAN_GK_SKILL_DESC_MAX),
        }
        for row in skill_rows
    ]

    monster_q = await session.execute(
        select(MonsterTemplate).where(
            MonsterTemplate.act_min <= act,
            MonsterTemplate.act_max >= act,
        ).limit(_CARAVAN_GK_MONSTERS_FETCH_CAP)
    )
    pool = list(monster_q.scalars().all())
    random.shuffle(pool)
    pool = pool[:_CARAVAN_GK_MONSTERS_SAMPLE]
    monsters: list[dict[str, Any]] = [
        {
            "id": m.id,
            "name": m.name,
            "dominant_trait_ru": monster_template_dominant_trait_ru(m),
            "family": m.family,
            "tier": m.tier,
        }
        for m in pool
    ]
    return {"skills": skills, "monsters": monsters}


async def generate_caravan_driver_tip(
    *,
    current_act: int,
    max_act: int,
    gold: int,
    game_knowledge: Optional[dict[str, Any]] = None,
    narrative_context: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """
    Короткий совет погонщицы каравана (2–4 предложения, RU), опирается на переданные игровые факты из БД.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.warning("[caravan driver-tip] Пропуск: не задан OPENROUTER_API_KEY")
        return None

    gk = game_knowledge if game_knowledge is not None else {"skills": [], "monsters": []}
    skills = gk.get("skills") or []
    monsters = gk.get("monsters") or []
    if not isinstance(skills, list):
        skills = []
    if not isinstance(monsters, list):
        monsters = []
    facts_payload = {"skills": skills, "monsters": monsters}
    facts_json = json.dumps(facts_payload, ensure_ascii=False)
    nar_block = ""
    if narrative_context:
        from waifu_bot.services.narrative import narrative_context_for_prompt_json

        nar_block = (
            "СЮЖЕТНЫЙ_КОНТЕКСТ (JSON, канон мира без спойлеров выше max_act):\n"
            f"{narrative_context_for_prompt_json(narrative_context)}\n\n"
        )

    model = settings.openrouter_model_hire or settings.openrouter_model
    prompt = (
        "Ты опытная погонщица каравана в фэнтезийном мире. Обращайся к собеседнику на «вы» как к страннику или командиру каравана. "
        f"Сейчас путь проходит через акт {int(current_act)} (доступно до акта {int(max_act)}); у странника примерно {int(gold)} монет золота — не перечисляй цифры сухим списком, можно намёк.\n\n"
        f"{nar_block}"
        "ИГРОВЫЕ_ФАКТЫ (JSON):\n"
        f"{facts_json}\n\n"
        "Правила ответа:\n"
        "- Дай 2–4 предложения, атмосферно, без списков и без markdown.\n"
        "- Если в JSON непустой массив skills или непустой массив monsters: опирайся на РОВНО ОДИН факт — либо один навык из skills (имя как в JSON, описание можно перефразировать), либо одного монстра из monsters (имя как в JSON, про угрозу используй только dominant_trait_ru и при желании family/tier из JSON). "
        "Не придумывай названий навыков или монстров, которых нет в JSON; не утверждай числовых формул или цифр, которых нет в переданных полях.\n"
        "- Если оба массива skills и monsters пусты: дай общий практический совет по дороге, осторожности и золоту в этом акте, без вымышленных имён навыков или чудовищ.\n"
        "- Если передан СЮЖЕТНЫЙ_КОНТЕКСТ: атмосфера и story_beats должны согласоваться с регионом; не раскрывай то, что в do_not_mention.\n"
        "- Если в JSON есть story_next_dungeon_name и story_focus_summary: кратко напомни этап пути (к цели или после этапа); "
        "не выдумывай названий подземелий — только story_next_dungeon_name из JSON.\n"
        "- Не выдавай точные коэффициенты баланса игры, кроме того что явно передано в JSON."
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 280,
                    "temperature": 0.75,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "[caravan driver-tip] OpenRouter HTTP %s body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("caravan driver-tip", first, text)
            return text or None
    except Exception as e:
        logger.warning("[caravan driver-tip] Ошибка: %s", e)
        return None


async def generate_tavern_keeper_banter(
    *,
    current_act: int,
    max_act: int,
    gold: int,
    narrative_context: Optional[dict[str, Any]] = None,
    tavern_facts: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Короткая реплика тавернщика (слухи, быт), RU — OpenRouter."""
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.warning("[tavern keeper] Пропуск: не задан OPENROUTER_API_KEY")
        return None

    tf = tavern_facts if isinstance(tavern_facts, dict) else {}
    facts_json = json.dumps(tf, ensure_ascii=False)
    nar_block = ""
    if narrative_context:
        from waifu_bot.services.narrative import narrative_context_for_prompt_json

        nar_block = (
            "СЮЖЕТНЫЙ_КОНТЕКСТ (JSON):\n"
            f"{narrative_context_for_prompt_json(narrative_context)}\n\n"
        )

    model = settings.openrouter_model_hire or settings.openrouter_model
    prompt = (
        "Ты хозяин постоялого двора в фэнтезийном мире: грубоватый, но не злой. Обращайся на «вы». "
        f"Регион по акту {int(current_act)} (гость видел дороги до акта {int(max_act)}); в кошельке у гостя примерно {int(gold)} монет — без сухого перечисления цифр.\n\n"
        f"{nar_block}"
        "ФАКТЫ_О_ТАВЕРНЕ (JSON, может быть пусто):\n"
        f"{facts_json}\n\n"
        "Дай 2–4 предложения: слух у очага, быт, намёк на дорогу или найм — без markdown и списков. "
        "Не придумывай имён из игры, которых нет в JSON. Соблюдай do_not_mention из сюжетного контекста. "
        "Если в JSON есть story_next_dungeon_name и story_focus_summary — можно намекнуть на этап сюжета, "
        "не выдумывая других названий данжей."
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.78,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "[tavern keeper] OpenRouter HTTP %s body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("tavern keeper", first, text)
            return text or None
    except Exception as e:
        logger.warning("[tavern keeper] Ошибка: %s", e)
        return None


def fallback_main_waifu_bio(name: str, race_ru: str, class_ru: str) -> str:
    """Короткая биография без ИИ."""
    n = (name or "Героиня").strip() or "Героиня"
    r = (race_ru or "путница").strip()
    c = (class_ru or "искательница").strip()
    return f"{n} — {r} и {c} по призванию; дорога впереди длиннее, чем кажется."


async def generate_main_waifu_bio(
    *,
    name: str,
    race_ru: str,
    class_ru: str,
) -> Optional[str]:
    """2–4 предложения на русском для основной вайфу при создании (OpenRouter)."""
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.warning("[main waifu bio] Пропуск: не задан OPENROUTER_API_KEY")
        return None

    from waifu_bot.services.narrative import load_narrative_bible

    bible = load_narrative_bible()
    r1 = (bible.get("regions") or {}).get("1") or {}
    region_name = str(r1.get("name_ru") or "").strip() or "первый регион"
    region_mood = str(r1.get("mood") or "").strip()
    ab = bible.get("act_beats") or {}
    act1 = ab.get("1") or ab.get(1)
    hook = ""
    if isinstance(act1, list) and act1:
        hook = str(act1[0]).strip()

    model = settings.openrouter_model_hire or settings.openrouter_model
    prompt = (
        "Напиши краткую биографию героини для игры в жанре фэнтези (аниме-стилистика допустима). "
        "Только русский язык, 2–4 предложения, без списков и без markdown.\n\n"
        f"Имя: {name}\n"
        f"Раса: {race_ru}\n"
        f"Класс: {class_ru}\n"
        f"Стартовый регион (акт 1): {region_name}"
        + (f"; настроение: {region_mood}" if region_mood else "")
        + "\n"
    )
    if hook:
        prompt += f"Намёк на сюжет (не раскрывай будущие акты): {hook}\n"
    prompt += (
        "\nПравила: не упоминай концовку игры, империю целиком и «Грань» подробно; "
        "покажи мотивацию идти в приключение и лёгкую тень угрозы."
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                _openrouter_url(),
                headers=_openrouter_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 400,
                    "temperature": 0.72,
                    **_openrouter_text_extra(),
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "[main waifu bio] OpenRouter HTTP %s body=%s",
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            data = r.json()
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return None
            first = choices[0]
            text = _extract_openrouter_assistant_text(first)
            if not text:
                _warn_if_empty_assistant("main waifu bio", first, text)
            return text.strip() or None
    except Exception as e:
        logger.warning("[main waifu bio] Ошибка: %s", e)
        return None


# Визуальные описания для промпта портрета (cursor_plan_7)
_CLASS_VISUAL = {
    "рыцарь": "female knight, armor, sword",
    "воин": "female warrior, armor, sword",
    "лучник": "female archer, forest ranger, bow and quiver",
    "маг": "female mage, magical staff, arcane robes",
    "ассасин": "female rogue, dark leather armor, daggers",
    "целительница": "female healer, white robes, glowing staff",
    "торговка": "female merchant, traveler coat, coin purse",
}
_RACE_VISUAL = {
    "человек": "human girl",
    "эльфийка": "elf girl, pointed ears, elegant",
    "зверолюдка": "kemonomimi girl, animal ears and tail",
    "ангел": "angel girl, white feathered wings, halo",
    "вампирша": "vampire girl, pale skin, red eyes, small fangs",
    "демоница": "demon girl, small curved horns, dark aura",
    "фея": "fairy girl, small iridescent wings, magical glow",
}


_MAIN_WAIFU_RACE_VISUAL_EN: dict[int, str] = {
    1: "human girl",
    2: "elf girl, pointed ears, elegant",
    3: "kemonomimi girl, animal ears and tail",
    4: "angel girl, white feathered wings, halo",
    5: "vampire girl, pale skin, subtle fangs",
    6: "demon girl, small curved horns, dark aura",
    7: "fairy girl, small iridescent wings, magical glow",
}
_MAIN_WAIFU_CLASS_VISUAL_EN: dict[int, str] = {
    1: "female knight, sword",
    2: "female warrior, armor",
    3: "female archer, bow and quiver",
    4: "female mage, magical staff, arcane robes",
    5: "female rogue, dark leather, daggers",
    6: "female healer, white robes, glowing staff",
    7: "female merchant, traveler coat",
}
_MAIN_WAIFU_HAIR_EN: dict[str, str] = {
    "blonde": "blonde hair",
    "black": "black hair",
    "brown": "brown hair",
    "red": "red hair",
    "white": "white hair",
    "silver": "silver hair",
    "blue": "blue hair",
    "pink": "pink hair",
    "green": "green hair",
}
_MAIN_WAIFU_EYES_EN: dict[str, str] = {
    "red": "red eyes",
    "burgundy": "burgundy eyes",
    "pink": "pink eyes",
    "sky_blue": "sky blue eyes",
    "blue": "deep blue eyes",
    "turquoise": "turquoise eyes",
    "aquamarine": "aquamarine eyes",
    "green": "green eyes",
    "emerald": "emerald green eyes",
    "lime": "lime green eyes",
    "yellow": "yellow eyes",
    "amber": "amber eyes",
    "gold": "golden eyes",
    "orange": "orange eyes",
    "violet": "violet eyes",
    "gray": "gray eyes",
}
_MAIN_WAIFU_HAIRSTYLE_EN: dict[str, str] = {
    "short_bob": "short bob haircut",
    "spiky_short": "short spiky hair",
    "pixie": "pixie cut",
    "shaggy": "shaggy messy hair",
    "medium_straight": "medium length straight hair",
    "medium_wavy": "medium wavy hair",
    "medium_straight_bangs": "medium straight hair with bangs",
    "medium_wavy_2": "medium wavy hair style",
    "messy_medium": "messy medium length hair",
    "side_pony": "side ponytail",
    "twin_tails": "twin tails hairstyle",
    "long_pony": "long ponytail",
    "long_straight": "long straight hair",
    "long_curls": "long curly hair",
    "twin_tails_alt": "twin tails hairstyle variant",
    "side_braid": "side braid hairstyle",
    "space_buns": "space buns hairstyle",
    "hime_cut": "hime cut hairstyle",
}
_MAIN_WAIFU_EYE_SHAPE_EN: dict[str, str] = {
    "bright": "bright vivid eyes",
    "tsundere": "tsundere-style sharp but cute eyes",
    "cute": "cute large innocent eyes",
    "melancholy": "melancholic sad eyes",
    "serious": "serious stern eyes",
    "energetic": "energetic sparkling eyes",
    "mystic": "mystical glowing eyes",
    "gentle": "gentle soft eyes",
    "dormant_sleepy": "half-lidded sleepy eyes",
    "shocked": "wide shocked eyes",
    "playful": "playful mischievous eyes",
    "cold": "cold emotionless eyes",
    "confused": "confused uncertain eyes",
    "determination": "determined intense eyes",
    "yandere": "yandere obsessive eyes",
    "shyness": "shy averted eyes",
    "confidence": "confident sharp eyes",
    "tearful": "tearful glistening eyes",
    "joyful": "joyful bright eyes",
    "anger": "angry glaring eyes",
    "sleepy": "sleepy droopy eyes",
    "annoyed": "annoyed irritated eyes",
    "pouty": "pouty sulking eyes",
    "seductive": "seductive alluring eyes",
}
_MAIN_WAIFU_OUTFIT_EN: dict[str, str] = {
    "plate_armor": "full plate armor, fantasy knight",
    "leather_armor": "leather armor, ranger style",
    "chainmail": "chainmail armor under padding",
    "dress": "elegant fantasy dress",
    "robes": "flowing mage robes",
    "casual": "stylish casual modern clothes",
    "swimsuit": "one-piece swimsuit",
    "bikini": "bikini, beach-appropriate",
    "uniform": "smart uniform outfit",
    "kimono": "decorative kimono",
    "cloak": "hooded cloak over adventurer clothes",
}
_MAIN_WAIFU_ACC_MULTI_EN: dict[str, str] = {
    "none": "",
    "necklace": "visible necklace",
    "earrings": "earrings",
    "makeup_light": "light natural makeup",
    "makeup_bold": "bold makeup, eyeliner",
    "scars": "small facial scars",
    "freckles": "cute freckles",
    "glasses": "stylish glasses",
    "eyepatch": "eyepatch over one eye",
    "face_paint": "tribal face paint",
    "choker": "choker collar",
    "gloves": "fingerless gloves",
    "hat": "stylish hat",
    "hood": "hood up partially",
    "circlet": "ornate circlet on forehead",
    "hair_ribbon": "ribbon in hair",
}


def _b64_from_data_image_url(url: str) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", url.strip(), re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _image_url_block_url(block: object) -> str:
    if isinstance(block, dict):
        u = block.get("url")
        return str(u).strip() if u is not None else ""
    return ""


def _openrouter_image_part_url(part: object) -> str:
    """Поле image_url / imageUrl в ответе OpenRouter: объект {{url}} или сразу строка data:/https:."""
    if isinstance(part, str):
        return part.strip()
    if isinstance(part, dict):
        return _image_url_block_url(part)
    return ""


def _extract_openrouter_image_b64_sync(message: dict) -> Optional[str]:
    """Сырой base64 без префикса data: — только inline data URL."""
    images = message.get("images")
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(item.get(key))
                if u:
                    b64 = _b64_from_data_image_url(u)
                    if b64:
                        return b64
            u = item.get("url")
            if isinstance(u, str):
                b64 = _b64_from_data_image_url(u)
                if b64:
                    return b64
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "image_url":
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(block.get(key))
                if u:
                    b64 = _b64_from_data_image_url(u)
                    if b64:
                        return b64
    if isinstance(content, str) and "base64," in content:
        m = re.search(r"data:image/[\w.+-]+;base64,([A-Za-z0-9+/=\s]+)", content)
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


async def _fetch_http_image_as_b64(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, follow_redirects=True, timeout=60.0)
        r.raise_for_status()
        return base64.standard_b64encode(r.content).decode("ascii")
    except Exception:
        logger.warning("[OPENROUTER IMAGE] fetch url failed prefix=%s", (url or "")[:96])
        return None


async def _extract_openrouter_image_b64(
    message: dict,
    client: httpx.AsyncClient,
) -> Optional[str]:
    sync = _extract_openrouter_image_b64_sync(message)
    if sync:
        return sync
    images = message.get("images")
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(item.get(key))
                if u.startswith("http"):
                    got = await _fetch_http_image_as_b64(client, u)
                    if got:
                        return got
            u = item.get("url")
            if isinstance(u, str) and u.startswith("http"):
                got = await _fetch_http_image_as_b64(client, u)
                if got:
                    return got
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                continue
            for key in ("image_url", "imageUrl"):
                u = _openrouter_image_part_url(block.get(key))
                if u.startswith("http"):
                    got = await _fetch_http_image_as_b64(client, u)
                    if got:
                        return got
    return None


async def generate_main_waifu_portrait(
    race_id: int,
    class_id: int,
    hair_color: str,
    eye_colors: list[str],
    hairstyle: str,
    eye_shape: str,
    outfit: str,
    accessories: list[str],
) -> Optional[str]:
    """
    Портрет основной вайфу (превью при создании): OpenRouter image API, anime 2:3.
    Возвращает только base64 без префикса data: или None.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.info("[MAIN OV IMAGE] Skip: no OPENROUTER_API_KEY")
        return None

    model = settings.openrouter_model_image
    race_en = _MAIN_WAIFU_RACE_VISUAL_EN.get(int(race_id), "human girl")
    class_en = _MAIN_WAIFU_CLASS_VISUAL_EN.get(int(class_id), "female adventurer")
    hair = _MAIN_WAIFU_HAIR_EN.get(str(hair_color), "brown hair")
    ec_raw: list[str] = []
    for x in eye_colors or []:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            ec_raw.append(s)
    ec_raw = ec_raw[:2]
    if len(ec_raw) >= 2:
        e1 = _MAIN_WAIFU_EYES_EN.get(ec_raw[0], "brown eyes")
        e2 = _MAIN_WAIFU_EYES_EN.get(ec_raw[1], "brown eyes")
        eyes = f"heterochromia, one eye {e1}, other eye {e2}"
    elif len(ec_raw) == 1:
        eyes = _MAIN_WAIFU_EYES_EN.get(ec_raw[0], "brown eyes")
    else:
        eyes = "brown eyes"
    hstyle = _MAIN_WAIFU_HAIRSTYLE_EN.get(str(hairstyle), "long hair")
    eye_sh = _MAIN_WAIFU_EYE_SHAPE_EN.get(str(eye_shape), "expressive eyes")
    outf = _MAIN_WAIFU_OUTFIT_EN.get(str(outfit), "fantasy outfit")
    acc_parts: list[str] = []
    if isinstance(accessories, list):
        for key in accessories:
            frag = _MAIN_WAIFU_ACC_MULTI_EN.get(str(key), "")
            if frag:
                acc_parts.append(frag)
    acc_joined = ", ".join(acc_parts)

    prompt = (
        f"anime style portrait, {race_en}, {class_en}, {hair}, {eyes}, {eye_sh}, {hstyle}, {outf}"
        + (f", {acc_joined}" if acc_joined else "")
        + ", fantasy RPG heroine, upper body, detailed face, soft lighting, "
        "high quality illustration, 1girl, safe for work"
    )
    logger.info(
        "[MAIN OV IMAGE] model=%s race=%s class=%s prompt_preview=%s",
        model,
        race_id,
        class_id,
        (prompt[:420] + "…") if len(prompt) > 420 else prompt,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = (("image",), ("image", "text"))
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "2:3",
                        "image_size": "1K",
                    },
                }
                r = await client.post(
                    _openrouter_url(),
                    headers=_openrouter_headers(),
                    json=body,
                )
                if r.status_code == 402:
                    logger.error("[MAIN OV IMAGE] OpenRouter 402")
                    return None
                if r.status_code == 401:
                    logger.error("[MAIN OV IMAGE] OpenRouter 401")
                    return None
                if not r.is_success:
                    logger.error("[MAIN OV IMAGE] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[MAIN OV IMAGE] no choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    return b64_out
                logger.info(
                    "[MAIN OV IMAGE] no image in message modalities=%s keys=%s",
                    modalities,
                    list(last_message.keys()),
                )
            logger.warning(
                "[MAIN OV IMAGE] no base64 after attempts; last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:700],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[MAIN OV IMAGE] timeout")
        return None
    except Exception as e:
        logger.exception("[MAIN OV IMAGE] %s", e)
        return None


_PAPERDOLL_POSES_EN: tuple[str, ...] = (
    "waist-up, slight three-quarter view, confident battle-ready stance, weight on back foot, ready to strike",
    "waist-up, dynamic mid-action pose with subtle motion in hair and cloth, energetic but controlled",
    "waist-up, relaxed heroic standing pose, one hand on hip, friendly adventurer energy",
    "waist-up, casting or channeling pose, off-hand raised with faint magical intent, focused expression",
    "waist-up, alert guard stance, knees slightly bent, weapons or shield held naturally for equipped gear",
    "waist-up, charismatic three-quarter pose, slight lean forward, expressive and lively",
)


def _paperdoll_background_for_avg_tier(avg_tier: float) -> str:
    t = float(avg_tier or 1.0)
    if t >= 9.0:
        return (
            "Background: legendary divine atmosphere — rich deep gradient (royal violet to gold), "
            "intense golden god-rays, radiant halo glow behind the character, sparkling particles and arcane energy wisps, "
            "premium loot aura; no scenery, no text."
        )
    if t >= 7.0:
        return (
            "Background: epic high-tier fantasy — dramatic purple-blue gradient with bright rim light, "
            "floating sparkles, soft energy wisps and subtle lens flare; heroic showcase feel; no scenery, no text."
        )
    if t >= 5.0:
        return (
            "Background: rare gear atmosphere — warm amber and teal gradient, magical particle motes, "
            "soft rim glow around the silhouette, light VFX sparkles; no scenery, no text."
        )
    if t >= 3.0:
        return (
            "Background: uncommon quality — soft vertical gradient (warm cream to pale gold), "
            "gentle warm aura and faint glow behind shoulders; no scenery, no text."
        )
    return (
        "Background: solid or very soft vertical gradient light beige (#f5f0e6 to #ebe4d6), warm parchment tone, "
        "minimal effects; no scenery, no patterns, no text — must harmonize with a soft UI paperdoll panel."
    )


async def generate_main_waifu_paperdoll_from_portrait(
    *,
    portrait_b64: str,
    portrait_mime: str,
    race_id: int,
    class_id: int,
    equipment_prompt_en: str | None = None,
    equipment_references: list[tuple[str, str]] | None = None,
    avg_equipment_tier: float = 1.0,
) -> Optional[str]:
    """
    2D JRPG-style paperdoll (waist-up) from existing portrait: multimodal request to OPENROUTER_MODEL_IMAGE.
    Returns raw base64 or None.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.info("[MAIN OV PAPERDOLL] Skip: no OPENROUTER_API_KEY")
        return None

    raw_b64 = str(portrait_b64 or "").strip()
    if not raw_b64:
        logger.info("[MAIN OV PAPERDOLL] Skip: empty portrait")
        return None

    mime = (portrait_mime or "image/png").strip() or "image/png"
    if ";" in mime or "/" not in mime:
        mime = "image/png"
    data_url = f"data:{mime};base64,{raw_b64}"

    model = settings.openrouter_model_image
    race_en = _MAIN_WAIFU_RACE_VISUAL_EN.get(int(race_id), "human girl")
    class_en = _MAIN_WAIFU_CLASS_VISUAL_EN.get(int(class_id), "female adventurer")
    raw_eq = str(equipment_prompt_en or "").strip()
    equip_extra = "\n\n" + raw_eq if raw_eq else ""
    pose_en = random.choice(_PAPERDOLL_POSES_EN)
    bg_en = _paperdoll_background_for_avg_tier(avg_equipment_tier)
    gear_ref_note = ""
    refs = equipment_references or []
    if refs:
        gear_ref_note = (
            f"\nAttached after the portrait: {len(refs)} reference image(s) of equipped gear — "
            "integrate each item's design onto the character in the matching slot."
        )
    prompt = (
        "Using the attached reference portrait, generate a single JRPG-style 2D full-color illustration of the "
        "SAME character. CRITICAL: preserve the face exactly — same facial features, eyes, nose, mouth, expression, "
        "hairstyle, hair color, skin tone, and overall identity as the reference; do not redesign the face."
        f"\nBody framing: {pose_en}; hands positioned so equipped weapons or shields can be held naturally where applicable."
        f"\nCharacter flavor: {race_en}, {class_en}."
        f"{equip_extra}"
        f"{gear_ref_note}"
        "\nArt style: soft cel-shading, clean line art, not photorealistic, not 3D render, fantasy JRPG character art. "
        "Safe for work, 1girl."
        f"\n{bg_en}"
    )
    logger.info(
        "[MAIN OV PAPERDOLL] model=%s race=%s class=%s equip_chars=%s refs=%s avg_tier=%.2f pose=%s",
        model,
        race_id,
        class_id,
        len(raw_eq),
        len(refs),
        float(avg_equipment_tier or 1.0),
        pose_en[:48],
    )

    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    for slot_label, ref_url in refs:
        label = str(slot_label or "Gear").strip() or "Gear"
        url = str(ref_url or "").strip()
        if not url:
            continue
        user_content.append(
            {"type": "text", "text": f"Reference gear image for {label} — match this item on the character:"}
        )
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = (("image",), ("image", "text"))
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": user_content}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "3:4",
                        "image_size": "1K",
                    },
                }
                r = await client.post(
                    _openrouter_url(),
                    headers=_openrouter_headers(),
                    json=body,
                )
                if r.status_code == 402:
                    logger.error("[MAIN OV PAPERDOLL] OpenRouter 402")
                    return None
                if r.status_code == 401:
                    logger.error("[MAIN OV PAPERDOLL] OpenRouter 401")
                    return None
                if not r.is_success:
                    logger.error("[MAIN OV PAPERDOLL] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[MAIN OV PAPERDOLL] no choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    return b64_out
                logger.info(
                    "[MAIN OV PAPERDOLL] no image in message modalities=%s keys=%s",
                    modalities,
                    list(last_message.keys()),
                )
            logger.warning(
                "[MAIN OV PAPERDOLL] no base64 after attempts; last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:700],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[MAIN OV PAPERDOLL] timeout")
        return None
    except Exception as e:
        logger.exception("[MAIN OV PAPERDOLL] %s", e)
        return None


async def generate_hire_waifu_image(
    race_ru: str,
    class_ru: str,
    bio: str,
    name: str = "",
) -> Optional[str]:
    """
    Генерирует портрет наёмницы через OpenRouter image API (cursor_plan_7).
    Возвращает base64-строку изображения или None при ошибке.
    Парсинг: message.images[0].image_url.url, не content.
    """
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.info("[IMAGE GEN] Skip: no OPENROUTER_API_KEY")
        return None

    model = settings.openrouter_model_image
    race_key = (race_ru or "человек").strip().lower()
    class_key = (class_ru or "маг").strip().lower()
    prompt = (
        f"anime style portrait, {_RACE_VISUAL.get(race_key, 'human girl')}, "
        f"{_CLASS_VISUAL.get(class_key, 'adventurer')}, "
        "fantasy RPG character, upper body, detailed face, "
        "dark atmospheric background, dramatic lighting, "
        "high quality illustration, 1girl"
    )
    logger.info("[IMAGE GEN] Starting for %s (%s), model: %s", name or "waifu", race_ru, model)
    logger.info("[IMAGE GEN] Prompt: %s...", prompt[:100])

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = (("image",), ("image", "text"))
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "2:3",
                        "image_size": "1K",
                    },
                }
                r = await client.post(
                    _openrouter_url(),
                    headers=_openrouter_headers(),
                    json=body,
                )
                logger.info("[IMAGE GEN] Status: %s modalities=%s", r.status_code, modalities)

                if r.status_code == 402:
                    logger.error("[IMAGE GEN] OpenRouter: недостаточно средств (402)")
                    return None
                if r.status_code == 401:
                    logger.error("[IMAGE GEN] OpenRouter: неверный API ключ (401)")
                    return None
                if not r.is_success:
                    logger.error("[IMAGE GEN] Error body: %s", r.text[:500])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[IMAGE GEN] No choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    logger.warning("[IMAGE GEN] choices[0] is not dict: %s", type(first))
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                logger.info("[IMAGE GEN] Response keys: %s", list(last_message.keys()))
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    return b64_out
                logger.info("[IMAGE GEN] parse miss modalities=%s", modalities)

            logger.warning(
                "[IMAGE GEN] Image not found. last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:700],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[IMAGE GEN] OpenRouter image: timeout (120s)")
        return None
    except Exception as e:
        logger.exception("[IMAGE GEN] Exception: %s", e)
        return None
