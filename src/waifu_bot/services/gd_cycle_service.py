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
    """Snapshot for GD combat: effective stats (gear + passives + perfection), not raw base only."""
    from waifu_bot.core.redis import get_redis
    from waifu_bot.game.formulas import calculate_max_hp
    from waifu_bot.services.combat import CombatService

    w = (
        await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    if not w:
        return None
    combat = CombatService(get_redis())
    try:
        eff = await combat._get_effective_combat_profile(session, player_id, w)
    except Exception:
        logger.exception("GD snapshot effective profile failed player_id=%s", player_id)
        eff = {
            "strength": int(w.strength or 10),
            "agility": int(w.agility or 10),
            "intelligence": int(w.intelligence or 10),
            "luck": int(w.luck or 10),
            "weapon_damage": None,
        }
    strength = int(eff.get("strength") or w.strength or 10)
    agility = int(eff.get("agility") or w.agility or 10)
    intelligence = int(eff.get("intelligence") or w.intelligence or 10)
    luck = int(eff.get("luck") or w.luck or 10)
    endurance = int(w.endurance or 10)
    try:
        from waifu_bot.services.passive_skills import get_passive_skill_bonuses

        psb = await get_passive_skill_bonuses(session, player_id)
        endurance += int(psb.get("main_stats_flat", 0) or 0)
    except Exception:
        pass
    level = int(w.level or 1)
    max_hp = max(1, calculate_max_hp(level, endurance, strength))
    # Prefer live HP ratio on new max, never start dead
    cur_live = int(w.current_hp or 0)
    old_max = max(1, int(w.max_hp or max_hp))
    if cur_live <= 0:
        current_hp = max(1, max_hp)
    else:
        current_hp = max(1, min(max_hp, int(max_hp * cur_live / old_max)))
    weapon_damage = eff.get("weapon_damage")
    if weapon_damage is None:
        weapon_damage = max(1, 5 + level // 2)
    else:
        weapon_damage = max(1, int(weapon_damage))
    return {
        "user_id": player_id,
        "name": w.name,
        "class_id": int(w.class_),
        "race_id": int(w.race),
        "level": level,
        "strength": strength,
        "agility": agility,
        "intelligence": intelligence,
        "endurance": endurance,
        "charm": int(w.charm or 10),
        "luck": luck,
        "weapon_damage": weapon_damage,
        "current_hp": current_hp,
        "max_hp": max_hp,
        "gear_aware": True,
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
            # Negative sentinel can be poisoned after rollback; always re-check DB
            pass
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
            # Do not write long-lived "none" — DELETE key so next caller re-queries
            await gd_active_cache_mod.invalidate_active_cycle_cache(self.redis, chat_id)
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
        """Open registration if none; pick random GD template. Respects per-chat cooldown."""
        existing = await self.get_registration_cycle_any(session, chat_id)
        if existing:
            return existing
        active = await self.get_active_v1_cycle(session, chat_id)
        if active:
            return None
        cfg = await get_game_config_map(session)
        cooldown_h = cfg_float(cfg, "gd_cooldown_after_finish_hours", 168.0)
        if cooldown_h > 0:
            last = (
                await session.execute(
                    select(GDCycle)
                    .where(
                        GDCycle.chat_id == chat_id,
                        GDCycle.status == "finished",
                        GDCycle.finished_at.isnot(None),
                    )
                    .order_by(GDCycle.finished_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last and last.finished_at:
                fin = last.finished_at
                if fin.tzinfo is None:
                    fin = fin.replace(tzinfo=timezone.utc)
                unlock = fin + timedelta(hours=float(cooldown_h))
                now = datetime.now(timezone.utc)
                if unlock > now:
                    # Signal cooldown via sentinel attribute consumed by register_join
                    self._last_cooldown_unlock_at = unlock
                    return None
        templates = (await session.execute(select(GDDungeonTemplate))).scalars().all()
        if not templates:
            logger.warning(
                "GD v1: no GDDungeonTemplate rows in DB — run scripts/seed_gd_content.py; "
                "/gd_join will always fail until templates are seeded"
            )
            return None
        tpl = random.choice(templates)
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
        self._last_cooldown_unlock_at = None
        cycle = await self.ensure_registration_cycle(session, chat_id)
        if not cycle:
            if getattr(self, "_last_cooldown_unlock_at", None) is not None:
                unlock = self._last_cooldown_unlock_at
                return {
                    "error": "cooldown",
                    "message": (
                        "В этом чате поход недавно завершён. "
                        f"Новая регистрация с {unlock.astimezone(MSK).strftime('%d.%m %H:%M')} МСК. "
                        "Запускайте /gd_join осознанно в нужном чате."
                    ),
                    "unlock_at": unlock.isoformat(),
                }
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
        was_first = (count or 0) == 0
        session.add(
            GDRegistration(
                cycle_id=cycle.id,
                user_id=user_id,
                waifu_snapshot=snap,
                joined_at_round=1,
            )
        )
        await session.flush()
        tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
        party_now = int(count or 0) + 1
        return {
            "success": True,
            "late_join": False,
            "name": snap["name"],
            "class_id": snap["class_id"],
            "level": snap.get("level"),
            "cycle_id": cycle.id,
            "was_first": was_first,
            "party_count": party_now,
            "max_party": max_party,
            "joined_at_round": 1,
            "reward_stage_mult": 1.0,
            "dungeon_name": tpl.name if tpl else "Подземелье",
            "registration_closes": cycle.registration_closes.isoformat()
            if cycle.registration_closes
            else None,
        }

    async def register_late_join(
        self, session: AsyncSession, chat_id: int, user_id: int
    ) -> dict[str, Any]:
        """Join an already-active cycle mid-run (append to party)."""
        cfg = await get_game_config_map(session)
        if cfg_int(cfg, "gd_late_join_enabled", 1) != 1:
            return {
                "error": "late_disabled",
                "message": "Вступление в уже идущий поход отключено.",
            }
        cycle = await self.get_active_v1_cycle(session, chat_id)
        if not cycle:
            return {"error": "no_active", "message": "Нет активного похода в этом чате."}
        state = dict(cycle.battle_state_json or {})
        wave = str(state.get("wave") or "")
        if wave == "done":
            return {
                "error": "finished",
                "message": "Поход уже завершается — вступление недоступно.",
            }
        max_party = cfg_int(cfg, "gd_max_party_size", 10)
        party: list[dict[str, Any]] = list(state.get("party") or [])
        if any(int(p.get("user_id") or 0) == int(user_id) for p in party):
            return {"error": "duplicate", "message": "Вы уже в отряде этого похода."}
        exists = await session.scalar(
            select(GDRegistration.id).where(
                GDRegistration.cycle_id == cycle.id, GDRegistration.user_id == user_id
            )
        )
        if exists:
            return {"error": "duplicate", "message": "Вы уже записаны в этот поход."}
        if len(party) >= max_party:
            return {"error": "full", "message": "Отряд полон."}
        snap = await build_waifu_snapshot(session, user_id)
        if not snap:
            return {"error": "no_waifu", "message": "Сначала создайте основную вайфу."}
        joined_round = max(1, int(state.get("collecting_for_round") or 1))
        total_est = max(8, int(cycle.total_rounds or 12))
        from waifu_bot.services.gd_scaling import late_join_reward_stage_mult

        stage_mult = late_join_reward_stage_mult(joined_round, total_est, cfg)
        snap["user_id"] = user_id
        snap.setdefault("fallen", False)
        party.append(snap)
        state["party"] = party
        cycle.battle_state_json = state
        session.add(
            GDRegistration(
                cycle_id=cycle.id,
                user_id=user_id,
                waifu_snapshot=snap,
                joined_at_round=joined_round,
            )
        )
        await session.flush()
        await gd_active_cache_mod.set_active_cycle_cache(
            self.redis, chat_id, cycle.id
        )
        tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
        return {
            "success": True,
            "late_join": True,
            "name": snap["name"],
            "class_id": snap["class_id"],
            "level": snap.get("level"),
            "cycle_id": cycle.id,
            "party_count": len(party),
            "max_party": max_party,
            "joined_at_round": joined_round,
            "reward_stage_mult": round(stage_mult, 3),
            "dungeon_name": tpl.name if tpl else "Подземелье",
            "wave": wave,
            "collecting_for_round": joined_round,
        }

    async def join_chat(
        self, session: AsyncSession, chat_id: int, user_id: int
    ) -> dict[str, Any]:
        """Registration join or late join depending on cycle status."""
        if await self.get_active_v1_cycle(session, chat_id):
            return await self.register_late_join(session, chat_id, user_id)
        return await self.register_join(session, chat_id, user_id)

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
            tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
            thematic_ids = None
            if tpl and tpl.thematic_bonus_class_ids is not None:
                raw = tpl.thematic_bonus_class_ids
                if isinstance(raw, list):
                    thematic_ids = raw
                elif isinstance(raw, dict) and "class_ids" in raw:
                    thematic_ids = raw.get("class_ids")
            cycle.battle_state_json = {
                "collecting_for_round": 1,
                "party": party,
                "monsters": [],
                "taunt_user_id": None,
                "wave": "pending_init",
                "contribution": {},
                "challenge_level": challenge_level,
                "activity_totals": {},
                "wipe_count": 0,
                "assists": {},
                "used_narrative_seed_ids": [],
                "thematic_bonus_class_ids": thematic_ids,
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
            await gd_active_cache_mod.invalidate_active_cycle_cache(
                self.redis, cycle.chat_id
            )
        return {"status": cycle.status, "registrations": len(regs)}

    async def cancel_active_cycle(
        self,
        session: AsyncSession,
        cycle: GDCycle,
        *,
        reason: str,
    ) -> dict[str, Any]:
        """End an active GD without victory rewards (idle / defeat / player_stop)."""
        if cycle.status != "active":
            return {"error": "not_active", "message": "Поход не активен."}
        state = dict(cycle.battle_state_json or {})
        state["cancel_reason"] = str(reason or "cancelled")
        cycle.battle_state_json = state
        cycle.status = "cancelled"
        cycle.finished_at = datetime.now(timezone.utc)
        cycle.round_deadline_at = None
        await session.flush()
        # Invalidate (delete) rather than write "none" before commit — avoids poison on rollback
        await gd_active_cache_mod.invalidate_active_cycle_cache(self.redis, cycle.chat_id)
        if self.redis:
            try:
                await self.redis.delete(_buf_key(cycle.id))
            except Exception:
                logger.debug("GD cancel: redis buf delete failed", exc_info=True)
        return {
            "success": True,
            "cycle_id": cycle.id,
            "chat_id": int(cycle.chat_id),
            "reason": state["cancel_reason"],
        }

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
