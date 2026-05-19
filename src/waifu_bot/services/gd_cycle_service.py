"""GD v1.0: registration, round action buffer, cycle lifecycle."""
from __future__ import annotations

import json
import logging
import random
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
from waifu_bot.services.game_config_service import get_game_config_map, cfg_int, cfg_float
from waifu_bot.services.gd_scaling import compute_challenge_level

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
        r = await session.execute(
            select(GDCycle)
            .where(GDCycle.chat_id == chat_id, GDCycle.status == "active")
            .limit(1)
        )
        return r.scalar_one_or_none()

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
        closes = next_monday_0600_msk_utc(datetime.now(timezone.utc))
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
            dur_m = int(float(cfg.get("gd_round_duration_minutes", "30")))
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
            u = users.setdefault(uid, {"text_len": 0, "media": [], "silent": True})
            if text_delta:
                u["text_len"] = int(u.get("text_len") or 0) + text_delta
                u["silent"] = False
            if media_kind:
                u.setdefault("media", []).append(media_kind)
                u["silent"] = False
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
