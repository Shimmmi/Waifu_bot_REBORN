"""GD v1.0: registration, round action buffer, cycle lifecycle."""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from redis.exceptions import RedisError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from waifu_bot.db.models import (
    GDCycle,
    GDRegistration,
    GDDungeonTemplate,
    MainWaifu,
    Player,
)
from waifu_bot.game.constants import (
    GD_MAX_ACTIONS_PER_ROUND_DEFAULT,
    GD_REGISTRATION_WINDOW_MINUTES_DEFAULT,
    GD_ROUND_DURATION_MINUTES_DEFAULT,
    GD_SERIES_WINDOW_SECONDS_DEFAULT,
)
from waifu_bot.services.game_config_service import get_game_config_map, cfg_int, cfg_float
from waifu_bot.services.gd_scaling import compute_challenge_level
from waifu_bot.services import gd_active_cache as gd_active_cache_mod

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
REDIS_GD_V1_BUF = "gd_v1_buf:"


def next_monday_0600_msk_utc(after: datetime) -> datetime:
    """Next Monday 06:00 Europe/Moscow as UTC-aware datetime."""
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    msk = after.astimezone(MSK)
    monday_same_week = msk - timedelta(days=msk.weekday())
    candidate = monday_same_week.replace(hour=6, minute=0, second=0, microsecond=0)
    if candidate > msk:
        return candidate.astimezone(timezone.utc)
    return (candidate + timedelta(days=7)).astimezone(timezone.utc)


def _buf_key(cycle_id: int) -> str:
    return f"{REDIS_GD_V1_BUF}{cycle_id}"


def coalesce_round_action(
    actions: list[dict[str, Any]],
    *,
    kind: str,
    now_ts: float,
    text_len: int = 0,
    media_kind: str | None = None,
    window_seconds: float = float(GD_SERIES_WINDOW_SECONDS_DEFAULT),
    max_actions: int = GD_MAX_ACTIONS_PER_ROUND_DEFAULT,
) -> None:
    """Анти-спам склейка: сообщения одного типа в пределах окна объединяются в «серию».

    Мутирует `actions` (упорядоченный список действий игрока за раунд):
      - text:  {"kind": "text", "len": <сумма длин>, "count": <число сообщений>, "ts": <last>}
      - media: {"kind": "media", "media_kind": <тип>, "count": <число>, "ts": <last>}
    Если достигнут лимит max_actions — новое сообщение вливается в последнее действие.
    """
    last = actions[-1] if actions else None

    def _same_kind(a: dict[str, Any]) -> bool:
        if a.get("kind") != kind:
            return False
        if kind == "media":
            return a.get("media_kind") == media_kind
        return True

    can_merge = (
        last is not None
        and _same_kind(last)
        and (now_ts - float(last.get("ts") or 0.0)) <= window_seconds
    )
    at_cap = len(actions) >= max(1, int(max_actions))
    if can_merge or (at_cap and last is not None and _same_kind(last)):
        last["count"] = int(last.get("count") or 1) + 1
        if kind == "text":
            last["len"] = int(last.get("len") or 0) + max(0, int(text_len))
        last["ts"] = now_ts
        return
    if at_cap and last is not None:
        # Лимит достигнут, тип отличается — вливаем в последнее действие, не плодя циклы.
        last["count"] = int(last.get("count") or 1) + 1
        last["ts"] = now_ts
        return
    if kind == "text":
        actions.append({"kind": "text", "len": max(0, int(text_len)), "count": 1, "ts": now_ts})
    else:
        actions.append(
            {"kind": "media", "media_kind": media_kind, "count": 1, "ts": now_ts}
        )


async def build_waifu_snapshot(session: AsyncSession, player_id: int) -> dict[str, Any] | None:
    w = (
        await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    if not w:
        return None
    hp = int(w.current_hp or 0)
    if hp <= 0:
        hp = 1
    return {
        "user_id": player_id,
        "name": w.name,
        "class_id": int(w.class_),
        "race_id": int(w.race),
        "level": int(w.level or 1),
        "strength": int(w.strength or 10),
        "agility": int(w.agility or 10),
        "intelligence": int(w.intelligence or 10),
        "endurance": int(w.endurance or 10),
        "charm": int(w.charm or 10),
        "luck": int(w.luck or 10),
        "current_hp": hp,
        "max_hp": int(w.max_hp or 100),
    }


class GDCycleService:
    def __init__(self, redis_client: Any | None):
        self.redis = redis_client
        # Анти-спам параметры буфера раунда (без сессии БД — дефолты из constants).
        self._series_window_seconds: float = float(GD_SERIES_WINDOW_SECONDS_DEFAULT)
        self._max_actions_per_round: int = int(GD_MAX_ACTIONS_PER_ROUND_DEFAULT)

    async def get_registration_cycle(
        self, session: AsyncSession, chat_id: int
    ) -> GDCycle | None:
        r = await session.execute(
            select(GDCycle)
            .where(GDCycle.chat_id == chat_id, GDCycle.status == "registration")
            .order_by(GDCycle.id.desc())
            .limit(1)
        )
        c = r.scalar_one_or_none()
        if not c:
            return None
        now = datetime.now(timezone.utc)
        if c.registration_closes <= now:
            return None
        return c

    async def get_registration_cycle_any(
        self, session: AsyncSession, chat_id: int
    ) -> GDCycle | None:
        """Latest registration cycle for chat (ignores deadline; for test start / join coalescing)."""
        r = await session.execute(
            select(GDCycle)
            .where(GDCycle.chat_id == chat_id, GDCycle.status == "registration")
            .order_by(GDCycle.id.desc())
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def get_active_v1_cycle(self, session: AsyncSession, chat_id: int) -> GDCycle | None:
        cached = await gd_active_cache_mod.get_cached_active_cycle_id(self.redis, chat_id)
        if cached is False:
            pass  # cache miss — query DB below
        elif cached is None:
            return None
        else:
            cycle = await session.get(GDCycle, int(cached))
            if cycle and cycle.status == "active" and int(cycle.chat_id) == int(chat_id):
                return cycle
            await gd_active_cache_mod.invalidate_active_cycle_cache(self.redis, chat_id)

        r = await session.execute(
            select(GDCycle)
            .where(GDCycle.chat_id == chat_id, GDCycle.status == "active")
            .limit(1)
        )
        cycle = r.scalar_one_or_none()
        if cycle:
            await gd_active_cache_mod.set_active_cycle_cache(
                self.redis, chat_id, cycle.id
            )
        else:
            await gd_active_cache_mod.set_active_cycle_cache(self.redis, chat_id, None)
        return cycle

    async def get_party_roster(
        self, session: AsyncSession, chat_id: int
    ) -> dict[str, Any] | None:
        """Состав текущего отряда (для всех игроков): активный бой или открытая регистрация.

        Возвращает {phase, cycle_id, members:[{user_id,name,level,race_id,class_id,fallen}], closes?}.
        """
        active = await self.get_active_v1_cycle(session, chat_id)
        if active:
            members: list[dict[str, Any]] = []
            for p in (active.battle_state_json or {}).get("party") or []:
                members.append(
                    {
                        "user_id": p.get("user_id"),
                        "name": p.get("name"),
                        "level": p.get("level"),
                        "race_id": p.get("race_id"),
                        "class_id": p.get("class_id"),
                        "fallen": bool(p.get("fallen")) or int(p.get("current_hp") or 0) <= 0,
                    }
                )
            return {"phase": "active", "cycle_id": active.id, "members": members}

        reg = await self.get_registration_cycle(session, chat_id)
        if reg:
            rows = (
                await session.execute(
                    select(GDRegistration).where(GDRegistration.cycle_id == reg.id)
                )
            ).scalars().all()
            members = []
            for r in rows:
                s = dict(r.waifu_snapshot or {})
                members.append(
                    {
                        "user_id": r.user_id,
                        "name": s.get("name"),
                        "level": s.get("level"),
                        "race_id": s.get("race_id"),
                        "class_id": s.get("class_id"),
                        "fallen": False,
                    }
                )
            return {
                "phase": "registration",
                "cycle_id": reg.id,
                "closes": reg.registration_closes,
                "members": members,
            }
        return None

    async def ensure_registration_cycle(
        self, session: AsyncSession, chat_id: int
    ) -> GDCycle | None:
        """Open registration if none; pick random GD template."""
        existing = await self.get_registration_cycle_any(session, chat_id)
        if existing:
            return existing
        active = await self.get_active_v1_cycle(session, chat_id)
        if active:
            return None
        templates = (await session.execute(select(GDDungeonTemplate))).scalars().all()
        if not templates:
            logger.warning(
                "GD v1: no GDDungeonTemplate rows in DB — run scripts/seed_gd_content.py; "
                "/gd_join will always fail until templates are seeded"
            )
            return None
        tpl = random.choice(templates)
        cfg = await get_game_config_map(session)
        window_m = cfg_int(
            cfg, "gd_registration_window_minutes", GD_REGISTRATION_WINDOW_MINUTES_DEFAULT
        )
        closes = datetime.now(timezone.utc) + timedelta(minutes=max(1, window_m))
        cycle = GDCycle(
            chat_id=chat_id,
            dungeon_template_id=tpl.id,
            status="registration",
            registration_closes=closes,
            current_round_number=0,
            battle_state_json=None,
        )
        session.add(cycle)
        await session.flush()
        return cycle

    async def register_join(
        self, session: AsyncSession, chat_id: int, user_id: int
    ) -> dict[str, Any]:
        if await self.get_active_v1_cycle(session, chat_id):
            return {"error": "active", "message": "Поход уже идёт — регистрация закрыта."}
        cfg = await get_game_config_map(session)
        max_party = cfg_int(cfg, "gd_max_party_size", 10)
        cycle = await self.ensure_registration_cycle(session, chat_id)
        if not cycle:
            has_templates = await session.scalar(
                select(func.count()).select_from(GDDungeonTemplate)
            )
            if not has_templates:
                return {
                    "error": "no_templates",
                    "message": "GD v1 не настроен: нет шаблонов подземелий. "
                    "Администратору нужно выполнить seed_gd_content.py.",
                }
            return {"error": "closed", "message": "Регистрация сейчас закрыта или уже идёт поход."}
        count = await session.scalar(
            select(func.count()).select_from(GDRegistration).where(GDRegistration.cycle_id == cycle.id)
        )
        if (count or 0) >= max_party:
            return {"error": "full", "message": "Отряд полон."}
        exists = await session.scalar(
            select(GDRegistration.id).where(
                GDRegistration.cycle_id == cycle.id, GDRegistration.user_id == user_id
            )
        )
        if exists:
            return {"error": "duplicate", "message": "Вы уже записаны в этот поход."}
        snap = await build_waifu_snapshot(session, user_id)
        if not snap:
            return {"error": "no_waifu", "message": "Сначала создайте основную вайфу."}
        session.add(GDRegistration(cycle_id=cycle.id, user_id=user_id, waifu_snapshot=snap))
        await session.flush()
        return {
            "success": True,
            "name": snap["name"],
            "class_id": snap["class_id"],
            "cycle_id": cycle.id,
        }

    async def close_registration_and_maybe_start(
        self, session: AsyncSession, cycle: GDCycle, *, force: bool = False
    ) -> dict[str, Any]:
        """Close registration: start if party >= min (or >= 1 when force for admin test)."""
        cfg = await get_game_config_map(session)
        min_p = cfg_int(cfg, "gd_min_party_size", 2)
        regs = (
            await session.execute(
                select(GDRegistration).where(GDRegistration.cycle_id == cycle.id)
            )
        ).scalars().all()
        need = 1 if force else min_p
        cycle.status = "cancelled" if len(regs) < need else "active"
        if cycle.status == "active":
            now = datetime.now(timezone.utc)
            cycle.started_at = now
            dur_m = int(float(cfg.get("gd_round_duration_minutes", str(GD_ROUND_DURATION_MINUTES_DEFAULT))))
            cycle.round_deadline_at = now + timedelta(minutes=dur_m)
            party = []
            for r in regs:
                s = dict(r.waifu_snapshot or {})
                s["user_id"] = r.user_id
                s.setdefault("fallen", False)
                party.append(s)
            levels = [int(p.get("level") or 1) for p in party]
            challenge_level = compute_challenge_level(levels, cfg)
            cycle.battle_state_json = {
                "collecting_for_round": 1,
                "party": party,
                "monsters": [],
                "taunt_user_id": None,
                "wave": "pending_init",
                "contribution": {},
                "challenge_level": challenge_level,
                "activity_totals": {},
            }
        else:
            cycle.finished_at = datetime.now(timezone.utc)
            cycle.round_deadline_at = None
        await session.flush()
        if cycle.status == "active":
            await gd_active_cache_mod.set_active_cycle_cache(
                self.redis, cycle.chat_id, cycle.id
            )
        else:
            await gd_active_cache_mod.set_active_cycle_cache(
                self.redis, cycle.chat_id, None
            )
        return {"status": cycle.status, "registrations": len(regs)}

    async def reset_v1_cycles_for_chat(self, session: AsyncSession, chat_id: int) -> int:
        """Delete registration/active cycles for chat; CASCADE clears related rows; Redis round buffers cleared."""
        r = await session.execute(
            select(GDCycle).where(
                GDCycle.chat_id == chat_id,
                GDCycle.status.in_(("registration", "active")),
            )
        )
        cycles = list(r.scalars().all())
        n = 0
        for c in cycles:
            if self.redis:
                try:
                    await self.redis.delete(_buf_key(c.id))
                except Exception:
                    logger.exception("GD v1 reset: redis delete failed cycle_id=%s", c.id)
            await session.delete(c)
            n += 1
        if n:
            await session.flush()
        await gd_active_cache_mod.invalidate_active_cycle_cache(self.redis, chat_id)
        return n

    async def record_round_action(
        self,
        chat_id: int,
        cycle_id: int,
        user_id: int,
        *,
        text_delta: int = 0,
        media_kind: str | None = None,
        is_silent: bool = False,
    ) -> None:
        if not self.redis:
            return
        key = _buf_key(cycle_id)
        try:
            raw = await self.redis.get(key)
            buf: dict[str, Any] = {"users": {}}
            if raw:
                try:
                    buf = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    buf = {"users": {}}
            users: dict[str, Any] = buf.setdefault("users", {})
            uid = str(user_id)
            u = users.setdefault(uid, {"text_len": 0, "media": [], "silent": True, "actions": []})
            actions: list[dict[str, Any]] = u.setdefault("actions", [])
            now_ts = time.time()
            window = float(self._series_window_seconds)
            max_acts = int(self._max_actions_per_round)
            if text_delta:
                u["text_len"] = int(u.get("text_len") or 0) + text_delta
                u["silent"] = False
                coalesce_round_action(
                    actions,
                    kind="text",
                    now_ts=now_ts,
                    text_len=int(text_delta),
                    window_seconds=window,
                    max_actions=max_acts,
                )
            if media_kind:
                u.setdefault("media", []).append(media_kind)
                u["silent"] = False
                coalesce_round_action(
                    actions,
                    kind="media",
                    now_ts=now_ts,
                    media_kind=media_kind,
                    window_seconds=window,
                    max_actions=max_acts,
                )
            if is_silent:
                u["silent"] = u.get("text_len", 0) == 0 and not u.get("media")
            await self.redis.set(key, json.dumps(buf), ex=86400 * 2)
        except RedisError:
            logger.exception(
                "GD v1 record_round_action: Redis error (chat_id=%s cycle_id=%s user_id=%s) — "
                "буфер не обновлён; обработчик группы продолжит (GXP и т.д.)",
                chat_id,
                cycle_id,
                user_id,
            )

    async def pop_round_buffer(self, cycle_id: int) -> dict[str, Any]:
        if not self.redis:
            return {}
        key = _buf_key(cycle_id)
        raw = await self.redis.get(key)
        await self.redis.delete(key)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def peek_round_buffer(self, cycle_id: int) -> dict[str, Any]:
        """Текущий буфер действий раунда в Redis без удаления (диагностика)."""
        if not self.redis:
            return {}
        key = _buf_key(cycle_id)
        raw = await self.redis.get(key)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def process_due_registration_closures(self, session: AsyncSession) -> list[GDCycle]:
        now = datetime.now(timezone.utc)
        q = await session.execute(
            select(GDCycle).where(
                GDCycle.status == "registration",
                GDCycle.registration_closes <= now,
            )
        )
        out = list(q.scalars().all())
        for c in out:
            await self.close_registration_and_maybe_start(session, c)
        return out
