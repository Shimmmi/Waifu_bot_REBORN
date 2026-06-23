"""Сборка сюжетного контекста для ИИ (караван, таверна) из narrative_bible.json + dungeon_storyline.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Dungeon, DungeonProgress, MainWaifu, Player, PlayerDungeonStorySeen

logger = logging.getLogger(__name__)

# Плейсхолдер в dungeon_storyline.json для имени основной вайфу (подставляется в рантайме).
WAIFU_NAME_PLACEHOLDER = "{{waifu_name}}"


def apply_waifu_name_template(text: str, name: str | None, *, fallback: str = "героиня") -> str:
    """Подставляет имя ОВ вместо {{waifu_name}}; пустое имя — нейтральное обращение."""
    if not text:
        return ""
    display = (name or "").strip() or fallback
    return text.replace(WAIFU_NAME_PLACEHOLDER, display)


async def _main_waifu_display_name(session: AsyncSession, player_id: int) -> str:
    try:
        row = await session.execute(select(MainWaifu.name).where(MainWaifu.player_id == int(player_id)))
        n = row.scalar_one_or_none()
        return (str(n).strip() if n else "") or ""
    except Exception:
        return ""

_ROOT = Path(__file__).resolve().parents[3]
_BIBLE_PATH = _ROOT / "scripts" / "data" / "narrative_bible.json"
_DUNGEON_STORY_PATH = _ROOT / "scripts" / "data" / "dungeon_storyline.json"
_bible_cache: dict[str, Any] | None = None


def load_narrative_bible() -> dict[str, Any]:
    global _bible_cache
    if _bible_cache is not None:
        return _bible_cache
    bible: dict[str, Any] = {}
    if _BIBLE_PATH.is_file():
        with open(_BIBLE_PATH, encoding="utf-8") as f:
            bible = json.load(f) or {}
    else:
        logger.warning("[narrative] narrative_bible.json not found at %s", _BIBLE_PATH)
    if _DUNGEON_STORY_PATH.is_file():
        with open(_DUNGEON_STORY_PATH, encoding="utf-8") as f:
            ds = json.load(f) or {}
        bible["dungeon_storyline"] = ds
    else:
        logger.warning("[narrative] dungeon_storyline.json not found at %s", _DUNGEON_STORY_PATH)
        bible.setdefault("dungeon_storyline", {})
    _bible_cache = bible
    return _bible_cache


def dungeon_story_key(act: int, dungeon_number: int) -> str:
    return f"{int(act)}_{int(dungeon_number)}"


def get_dungeon_story_node(bible: dict[str, Any], act: int, dungeon_number: int) -> dict[str, Any]:
    ds = bible.get("dungeon_storyline") or {}
    return dict(ds.get(dungeon_story_key(act, dungeon_number)) or {})


async def is_dungeon_plus_globally_unlocked(session: AsyncSession, player_id: int) -> bool:
    """Тот же критерий, что у DungeonService: пройден соло Акт5#5."""
    try:
        q = await session.execute(
            select(Dungeon.id).where(
                Dungeon.act == 5,
                Dungeon.dungeon_type == 1,
                Dungeon.dungeon_number == 5,
            )
        )
        did = q.scalar_one_or_none()
        if not did:
            return False
        pr = await session.execute(
            select(DungeonProgress.is_completed).where(
                DungeonProgress.player_id == player_id,
                DungeonProgress.dungeon_id == int(did),
            )
        )
        row = pr.first()
        return bool(row and row[0])
    except Exception:
        return False


async def _linear_story_dungeons(session: AsyncSession) -> list[Dungeon]:
    res = await session.execute(
        select(Dungeon)
        .where(Dungeon.act.between(1, 5), Dungeon.dungeon_type == 1)
        .order_by(Dungeon.act.asc(), Dungeon.dungeon_number.asc())
    )
    return list(res.scalars().all())


async def _linear_story_dungeon_completed(
    session: AsyncSession, player_id: int, dungeons: list[Dungeon]
) -> dict[int, bool]:
    if not dungeons:
        return {}
    ids = [int(d.id) for d in dungeons]
    res = await session.execute(
        select(DungeonProgress.dungeon_id, DungeonProgress.is_completed).where(
            DungeonProgress.player_id == int(player_id),
            DungeonProgress.dungeon_id.in_(ids),
        )
    )
    completed = {i: False for i in ids}
    for did, done in res.all():
        completed[int(did)] = bool(done)
    return completed


def _linear_story_targets(
    dungeons: list[Dungeon], completed: dict[int, bool]
) -> tuple[Dungeon | None, Dungeon | None, bool]:
    last_completed: Dungeon | None = None
    next_target: Dungeon | None = None
    for d in dungeons:
        if not completed.get(int(d.id)):
            next_target = d
            break
        last_completed = d
    return last_completed, next_target, next_target is None


async def compute_linear_story_position_lite(
    session: AsyncSession, player_id: int
) -> dict[str, Any]:
    """Campaign chip fields only — no narrative bible / waifu templating."""
    dungeons = await _linear_story_dungeons(session)
    completed = await _linear_story_dungeon_completed(session, player_id, dungeons)
    last_completed, next_target, main_campaign_complete = _linear_story_targets(dungeons, completed)
    return {
        "main_campaign_complete": main_campaign_complete,
        "story_next_dungeon_name": next_target.name if next_target else None,
        "story_next_act": int(next_target.act) if next_target else None,
        "story_next_dungeon_number": int(next_target.dungeon_number) if next_target else None,
        "story_last_completed_dungeon_name": last_completed.name if last_completed else None,
    }


async def compute_linear_story_position(session: AsyncSession, player_id: int) -> dict[str, Any]:
    """
    Линейная цепочка соло-данжей 1–1 … 5–5: следующая цель и узел канона для фокуса.
    """
    bible = load_narrative_bible()
    dungeons = await _linear_story_dungeons(session)
    completed = await _linear_story_dungeon_completed(session, player_id, dungeons)
    last_completed, next_target, main_campaign_complete = _linear_story_targets(dungeons, completed)

    focus_dungeon = next_target or (dungeons[-1] if dungeons else None)
    focus_key = (
        dungeon_story_key(int(focus_dungeon.act), int(focus_dungeon.dungeon_number))
        if focus_dungeon
        else "5_5"
    )
    node = get_dungeon_story_node(bible, int(focus_dungeon.act), int(focus_dungeon.dungeon_number)) if focus_dungeon else {}

    last_name = last_completed.name if last_completed else None
    next_name = next_target.name if next_target else None

    wname = await _main_waifu_display_name(session, player_id)
    title = apply_waifu_name_template(str(node.get("title") or "").strip(), wname)
    summary = apply_waifu_name_template(str(node.get("summary") or "").strip(), wname)
    observer = apply_waifu_name_template(str(node.get("observer_line") or "").strip(), wname)

    return {
        "main_campaign_complete": main_campaign_complete,
        "story_focus_key": focus_key,
        "story_next_dungeon_id": int(next_target.id) if next_target else None,
        "story_next_dungeon_name": next_name,
        "story_next_act": int(next_target.act) if next_target else None,
        "story_next_dungeon_number": int(next_target.dungeon_number) if next_target else None,
        "story_last_completed_dungeon_name": last_name,
        "story_focus_title": title,
        "story_focus_summary": summary,
        "story_focus_observer": observer,
    }


async def build_narrative_prompt_context(session: AsyncSession, player_id: int) -> dict[str, Any]:
    """
    Контекст для промптов: без спойлеров выше max_act; Dungeon+ если разблокирован;
    линейный сюжет 25 данжей — фокус на следующей цели.
    """
    bible = load_narrative_bible()
    player = await session.get(Player, int(player_id))
    max_act = int(getattr(player, "max_act", 1) or 1) if player else 1
    current_act = int(getattr(player, "current_act", 1) or 1) if player else 1
    max_act = max(1, min(5, max_act))
    current_act = max(1, min(5, current_act))

    regions = bible.get("regions") or {}
    region = regions.get(str(current_act)) or regions.get(current_act) or {}
    region_name = str(region.get("name_ru") or "") if isinstance(region, dict) else ""

    beats_allowed: list[str] = []
    act_beats = bible.get("act_beats") or {}
    for a in range(1, max_act + 1):
        key = str(a)
        raw = act_beats.get(key) or act_beats.get(a)
        if isinstance(raw, list):
            beats_allowed.extend(str(x) for x in raw)

    global_block = bible.get("global") or {}
    summary = str(global_block.get("summary") or "").strip()
    dungeon_plus_echo = str(global_block.get("dungeon_plus_echo") or "").strip()

    meta = bible.get("meta") or {}
    observer_reminder = str(meta.get("observer_voice") or "").strip()

    taboo: list[str] = []
    if max_act < 5:
        taboo.extend(list(bible.get("taboo_before_act5") or []))

    plus_unlocked = await is_dungeon_plus_globally_unlocked(session, player_id)
    beats_payload = [summary] + beats_allowed
    if plus_unlocked:
        beats_payload.append(dungeon_plus_echo)

    story_pos = await compute_linear_story_position(session, player_id)

    return {
        "max_act": max_act,
        "current_act": current_act,
        "region_name_ru": region_name,
        "region_mood_ru": str(region.get("mood") or "").strip() if isinstance(region, dict) else "",
        "beats_allowed": beats_payload,
        "observer_reminder": observer_reminder,
        "taboo_phrases": taboo,
        "dungeon_plus_unlocked": plus_unlocked,
        **story_pos,
    }


def narrative_context_for_prompt_json(ctx: dict[str, Any]) -> str:
    """Сжатый JSON для user-промпта."""
    safe = {
        "current_act": ctx.get("current_act"),
        "max_act": ctx.get("max_act"),
        "region": ctx.get("region_name_ru"),
        "atmosphere": ctx.get("region_mood_ru"),
        "story_beats": ctx.get("beats_allowed") or [],
        "do_not_mention": ctx.get("taboo_phrases") or [],
        "dungeon_plus_unlocked": bool(ctx.get("dungeon_plus_unlocked")),
        "main_campaign_complete": bool(ctx.get("main_campaign_complete")),
        "story_next_dungeon_name": ctx.get("story_next_dungeon_name"),
        "story_last_completed_dungeon_name": ctx.get("story_last_completed_dungeon_name"),
        "story_focus_title": ctx.get("story_focus_title"),
        "story_focus_summary": ctx.get("story_focus_summary"),
        "story_focus_observer": ctx.get("story_focus_observer"),
        "story_focus_key": ctx.get("story_focus_key"),
    }
    return json.dumps(safe, ensure_ascii=False)


async def build_story_modal_on_dungeon_start(
    session: AsyncSession,
    player_id: int,
    dungeon: Dungeon,
    plus_level: int,
) -> dict[str, Any] | None:
    """Первая сессия соло-данжа (plus 0): вернуть модалку и пометить seen."""
    if int(plus_level or 0) != 0:
        return None
    if int(getattr(dungeon, "dungeon_type", 0) or 0) != 1:
        return None
    seen = await session.get(PlayerDungeonStorySeen, (int(player_id), int(dungeon.id)))
    if seen:
        return None

    wname = await _main_waifu_display_name(session, player_id)
    bible = load_narrative_bible()
    node = get_dungeon_story_node(bible, int(dungeon.act), int(dungeon.dungeon_number))
    title = apply_waifu_name_template(str(node.get("title") or dungeon.name or "Сюжет").strip(), wname)
    parts = [apply_waifu_name_template(str(node.get("summary") or "").strip(), wname)]
    ol = apply_waifu_name_template(str(node.get("observer_line") or "").strip(), wname)
    if ol:
        parts.append(ol)
    body = "\n\n".join(p for p in parts if p)
    key = dungeon_story_key(int(dungeon.act), int(dungeon.dungeon_number))

    session.add(PlayerDungeonStorySeen(player_id=int(player_id), dungeon_id=int(dungeon.id)))
    await session.flush()

    return {
        "dungeon_id": int(dungeon.id),
        "from_bible_key": key,
        "title": title,
        "body": body or title,
    }


async def build_why_next_for_reward_modal(
    session: AsyncSession,
    player_id: int,
    dungeon: Dungeon,
    *,
    is_first_completion: bool,
    plus_level: int,
) -> str | None:
    """Текст после первой зачистки соло (plus 0): зачем идти дальше по сюжету."""
    if not is_first_completion:
        return None
    if int(plus_level or 0) != 0:
        return None
    if int(getattr(dungeon, "dungeon_type", 0) or 0) != 1:  # solo
        return None

    wname = await _main_waifu_display_name(session, player_id)
    bible = load_narrative_bible()
    node = get_dungeon_story_node(bible, int(dungeon.act), int(dungeon.dungeon_number))
    wn = str(node.get("why_next") or "").strip() if node else ""
    wa = str(node.get("why_next_act") or "").strip() if node else ""
    raw = wn if wn else wa
    text = apply_waifu_name_template(raw, wname)
    return text.strip() or None
