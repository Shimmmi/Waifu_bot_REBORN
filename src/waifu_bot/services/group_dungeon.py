"""Group Dungeon (GD) service: sessions, activity, start, damage, events, rewards."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    GDDungeonTemplate,
    GDSession,
    GDPlayerContribution,
    PlayerChatFirstSeen,
    PlayerGameAction,
    GDCompletion,
    GDEventTemplate,
    MainWaifu,
    Player,
)
from waifu_bot.game.constants import (
    GD_STAGES_TOTAL,
    GD_MIN_ACTIVE_PLAYERS_24H,
    GD_MIN_MESSAGES_PER_MIN,
    GD_CHAT_COOLDOWN_MINUTES,
    GD_START_USER_COOLDOWN_SECONDS,
    GD_SAVE_INTERVAL_SECONDS,
    GD_REGRESSION_INTERVAL_SECONDS,
    GD_REGRESSION_HP_PERCENT,
    GD_LOW_ACTIVITY_WINDOW_SECONDS,
    GD_LOW_ACTIVITY_MESSAGES_PER_MIN,
    GD_FORCE_COMPLETE_AFTER_MINUTES,
    GD_FORCE_COMPLETE_HP_THRESHOLD,
    GD_ELIGIBILITY_DAYS_IN_CHAT,
    GD_ELIGIBILITY_GAME_ACTIONS_DAYS,
    GD_ELIGIBILITY_MIN_GAME_ACTIONS,
    GD_ALREADY_ACTIVE_DELAY_SECONDS,
    GD_BOT_MESSAGE_MIN_INTERVAL_SECONDS,
    GD_MIN_UNIQUE_CHARS,
    GD_DAMAGE_COOLDOWN_SECONDS,
    GD_NEW_PLAYER_PENALTY_MINUTES,
    GD_NEW_PLAYER_DAMAGE_MULTIPLIER,
    GD_EMOJI_DAMAGE,
    GD_BASE_EXP_REWARD,
    GD_BASE_GOLD_REWARD,
)
from waifu_bot.game.formulas import calculate_message_damage, calculate_total_experience_for_level
from waifu_bot.game.constants import MediaType
from waifu_bot.core.config import settings

if TYPE_CHECKING:
    from waifu_bot.services.combat import CombatService

logger = logging.getLogger(__name__)

# Redis key prefixes
REDIS_GD_CHAT_MSGS = "gd_chat_msg:"  # sorted set, score=ts
REDIS_GD_START_COOLDOWN = "gd_start_cooldown:"
REDIS_GD_CHAT_COOLDOWN = "gd_chat_cooldown:"
REDIS_GD_LAST_BOT_MSG = "gd_last_bot_msg:"
REDIS_GD_DMG_COOLDOWN = "gd_dmg:"  # {chat_id}:{user_id} -> last ts, ex 8
REDIS_GD_LAST_MSGS = "gd_last_msg:"  # {chat_id}:{user_id} -> list of last 2 text hashes
REDIS_GD_ENGAGE_CHAIN = "gd_engage_chain:"
REDIS_GD_EVENT_STATE = "gd_event_state:"

ENGAGE_CHAIN_DURATION_SECONDS = 60
ENGAGE_CHAIN_UPDATE_INTERVAL_SECONDS = 5
ENGAGE_CHAIN_HP_EFFECT_PERCENT = 35  # −35% monster HP on full completion
GD_EVENT_HP_EFFECT_PERCENT = 25  # −25% boss HP on event completion

# boss_unique: emoji_filter key -> list of acceptable emojis in message
EMOJI_FILTER_TO_EMOJIS: dict[str, list[str]] = {
    "wind": ["✈️", "🌪️", "💨", "🌬️", "🌀"],
    "water": ["💧", "🌊", "🐚", "🐟", "🐙"],
    "sun": ["☀️", "🌞", "🔥", "✨", "🌟"],
    "mirror": ["🪞", "✨", "💫", "🪞", "👁️"],
    "fire": ["🔥", "💥", "⚡", "✨"],
}

# Engage chain task pool: (target, content_type, filter_key, description)
ENGAGE_TASK_POOL: list[dict[str, Any]] = [
    {"target": "any_player", "content_type": "sticker_or_emoji", "filter": "laugh_emoji", "description": "Стикер или эмодзи со смехом (😂/🤣/😆)"},
    {"target": "any_player", "content_type": "text_with_emoji", "filter": "fire_emoji", "description": "Текст с эмодзи огня (🔥)"},
    {"target": "any_player", "content_type": "voice_min", "filter": "duration_2_4", "description": "Голосовое сообщение 2–4 сек"},
    {"target": "any_player", "content_type": "sticker_or_emoji", "filter": "heart_emoji", "description": "Стикер или эмодзи с сердцем (❤️/💕)"},
    {"target": "any_player", "content_type": "text_with_emoji", "filter": "star_emoji", "description": "Текст с эмодзи звезды (⭐/🌟)"},
]
LAUGH_EMOJIS = ["😂", "🤣", "😆", "😄", "💀"]
FIRE_EMOJIS = ["🔥", "💥", "⚡"]
HEART_EMOJIS = ["❤️", "💕", "💗", "❤", "🧡"]
STAR_EMOJIS = ["⭐", "🌟", "✨", "💫"]

# Base HP per stage for GD (before hp_multiplier). Stage 4 = boss.
GD_BASE_HP_PER_STAGE = (500, 600, 700, 2000)
GD_MONSTER_NAMES = ("Страж подземелья", "Охранник залов", "Часовой портала", "Босс подземелья")


class GroupDungeonService:
    """Service for group dungeon (GD) logic."""

    def __init__(self, redis_client, combat_service: CombatService | None = None):
        self.redis = redis_client
        self.combat_service = combat_service

    # --- Activity (Redis + DB) ---

    async def record_chat_message(self, chat_id: int) -> None:
        """Record a message in chat for rate calculation (Redis sliding window 60 min)."""
        if not self.redis:
            return
        key = f"{REDIS_GD_CHAT_MSGS}{chat_id}"
        now = time.time()
        member = f"{now}:{random.randint(0, 999999)}"
        await self.redis.zadd(key, {member: now})
        await self.redis.expire(key, 3600 * 2)  # keep 2 hours
        # Remove older than 60 min
        await self.redis.zremrangebyscore(key, "-inf", now - 3600)

    async def get_chat_message_rate_per_minute(self, chat_id: int) -> float:
        """Messages per minute over last 60 minutes."""
        if not self.redis:
            return 0.0
        key = f"{REDIS_GD_CHAT_MSGS}{chat_id}"
        now = time.time()
        count = await self.redis.zcount(key, now - 3600, "+inf")
        return count / 60.0 if count else 0.0

    async def get_chat_message_count_last_seconds(self, chat_id: int, seconds: int) -> int:
        """Message count in last N seconds (for regression / low activity)."""
        if not self.redis:
            return 0
        key = f"{REDIS_GD_CHAT_MSGS}{chat_id}"
        now = time.time()
        return await self.redis.zcount(key, now - seconds, "+inf")

    async def ensure_player_chat_first_seen(
        self, session: AsyncSession, player_id: int, chat_id: int
    ) -> None:
        """Set first_seen_at if not exists."""
        row = await session.scalar(
            select(PlayerChatFirstSeen).where(
                PlayerChatFirstSeen.player_id == player_id,
                PlayerChatFirstSeen.chat_id == chat_id,
            )
        )
        if not row:
            session.add(
                PlayerChatFirstSeen(
                    player_id=player_id,
                    chat_id=chat_id,
                    first_seen_at=datetime.now(timezone.utc),
                )
            )
            await session.flush()

    async def record_game_action(
        self, session: AsyncSession, player_id: int, chat_id: int, action_type: str
    ) -> None:
        """Record a game action (gd_start, gd_damage, engage, etc.)."""
        session.add(
            PlayerGameAction(
                player_id=player_id,
                chat_id=chat_id,
                action_type=action_type,
            )
        )
        await session.flush()

    async def count_active_players_24h(self, session: AsyncSession, chat_id: int) -> int:
        """Count distinct players with >=2 game actions in 24h (TZ: active = ≥2 game actions OR ≥3 messages)."""
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        subq = (
            select(PlayerGameAction.player_id)
            .where(
                PlayerGameAction.chat_id == chat_id,
                PlayerGameAction.created_at >= since,
            )
            .group_by(PlayerGameAction.player_id)
            .having(func.count(PlayerGameAction.id) >= 2)
        )
        result = await session.execute(select(func.count()).select_from(subq.subquery()))
        return result.scalar() or 0

    async def is_player_eligible_for_gd_start(
        self, session: AsyncSession, player_id: int, chat_id: int
    ) -> tuple[bool, str]:
        """Check: ≥3 days in chat, ≥2 game actions in last 7 days. Returns (ok, error_message)."""
        first_seen = await session.scalar(
            select(PlayerChatFirstSeen.first_seen_at).where(
                PlayerChatFirstSeen.player_id == player_id,
                PlayerChatFirstSeen.chat_id == chat_id,
            )
        )
        if not first_seen:
            return False, "Сначала пообщайтесь в чате и выполните несколько игровых действий."
        days_in_chat = (datetime.now(timezone.utc) - first_seen.replace(tzinfo=timezone.utc)).days
        if days_in_chat < GD_ELIGIBILITY_DAYS_IN_CHAT:
            return False, f"Нужно быть в чате не менее {GD_ELIGIBILITY_DAYS_IN_CHAT} дней."

        since = datetime.now(timezone.utc) - timedelta(days=GD_ELIGIBILITY_GAME_ACTIONS_DAYS)
        count = await session.execute(
            select(func.count()).where(
                PlayerGameAction.player_id == player_id,
                PlayerGameAction.chat_id == chat_id,
                PlayerGameAction.created_at >= since,
            )
        )
        actions = count.scalar() or 0
        if actions < GD_ELIGIBILITY_MIN_GAME_ACTIONS:
            return False, f"Нужно не менее {GD_ELIGIBILITY_MIN_GAME_ACTIONS} игровых действий за последние {GD_ELIGIBILITY_GAME_ACTIONS_DAYS} дней."

        return True, ""

    async def get_active_session(self, session: AsyncSession, chat_id: int) -> GDSession | None:
        """Get active GD session for chat."""
        result = await session.execute(
            select(GDSession)
            .where(GDSession.chat_id == chat_id, GDSession.status == "active")
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def is_chat_on_cooldown(self, chat_id: int) -> bool:
        """True if chat cooldown (60 min after last GD completion) is active."""
        if not self.redis:
            return False
        key = f"{REDIS_GD_CHAT_COOLDOWN}{chat_id}"
        return await self.redis.exists(key) > 0

    async def set_chat_cooldown(self, chat_id: int) -> None:
        """Set chat cooldown 60 min."""
        if not self.redis:
            return
        key = f"{REDIS_GD_CHAT_COOLDOWN}{chat_id}"
        await self.redis.set(key, "1", ex=GD_CHAT_COOLDOWN_MINUTES * 60)

    async def is_user_on_gd_start_cooldown(self, user_id: int) -> bool:
        """True if user already started GD in last 2 hours."""
        if not self.redis:
            return False
        key = f"{REDIS_GD_START_COOLDOWN}{user_id}"
        return await self.redis.exists(key) > 0

    async def set_user_gd_start_cooldown(self, user_id: int) -> None:
        """Set user /gd_start cooldown 2 hours."""
        if not self.redis:
            return
        key = f"{REDIS_GD_START_COOLDOWN}{user_id}"
        await self.redis.set(key, "1", ex=GD_START_USER_COOLDOWN_SECONDS)

    async def await_throttle_bot_message(self, chat_id: int) -> None:
        """If last bot message was < 10 sec ago, sleep until 10 sec passed."""
        if not self.redis:
            return
        key = f"{REDIS_GD_LAST_BOT_MSG}{chat_id}"
        last = await self.redis.get(key)
        if last:
            try:
                last_ts = float(last)
                elapsed = time.time() - last_ts
                if elapsed < GD_BOT_MESSAGE_MIN_INTERVAL_SECONDS:
                    await asyncio.sleep(GD_BOT_MESSAGE_MIN_INTERVAL_SECONDS - elapsed)
            except (ValueError, TypeError):
                pass

    async def set_last_bot_message(self, chat_id: int) -> None:
        """Record that bot sent a message in this chat (for throttling)."""
        if not self.redis:
            return
        key = f"{REDIS_GD_LAST_BOT_MSG}{chat_id}"
        await self.redis.set(key, str(time.time()), ex=3600)

    # --- Start GD ---

    def _build_stage_monsters(self, template: GDDungeonTemplate) -> list[dict[str, Any]]:
        """Build 4 stages: 3 normal + 1 boss. HP = base * hp_multiplier."""
        mult = float(template.hp_multiplier)
        stages = []
        for i in range(GD_STAGES_TOTAL):
            base_hp = GD_BASE_HP_PER_STAGE[i]
            hp = max(1, int(base_hp * mult))
            is_boss = i == GD_STAGES_TOTAL - 1
            name = GD_MONSTER_NAMES[i]
            stages.append({"name": name, "base_hp": hp, "is_boss": is_boss})
        return stages

    async def start_gd(
        self,
        session: AsyncSession,
        chat_id: int,
        user_id: int,
        *,
        dev_mode: bool = False,
        template_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Start a group dungeon in chat. Returns dict with success/error and message fields.
        dev_mode: skip activity/cooldown/eligibility checks; template_id: pick specific template.
        """
        active = await self.get_active_session(session, chat_id)
        if active:
            return {
                "error": "already_active",
                "delay_seconds": GD_ALREADY_ACTIVE_DELAY_SECONDS,
                "monster_name": active.stage_monsters[active.current_stage - 1]["name"] if active.stage_monsters else "монстр",
            }

        if not dev_mode:
            if await self.is_chat_on_cooldown(chat_id):
                return {"error": "chat_cooldown", "message": "Кулдаун чата: подождите 60 минут после прошлого подземелья."}

            if await self.is_user_on_gd_start_cooldown(user_id):
                return {"error": "user_cooldown", "message": "Вы уже запускали подземелье недавно. Подождите 2 часа."}

            if not getattr(settings, "gd_skip_activity_check", False):
                rate = await self.get_chat_message_rate_per_minute(chat_id)
                if rate < GD_MIN_MESSAGES_PER_MIN:
                    return {"error": "low_activity", "message": f"Нужна активность чата не менее {GD_MIN_MESSAGES_PER_MIN} сообщений/мин за последний час."}

                active_count = await self.count_active_players_24h(session, chat_id)
                if active_count < GD_MIN_ACTIVE_PLAYERS_24H:
                    return {"error": "few_players", "message": f"Нужно не менее {GD_MIN_ACTIVE_PLAYERS_24H} активных игроков за 24 часа."}

            ok, err_msg = await self.is_player_eligible_for_gd_start(session, user_id, chat_id)
            if not ok:
                return {"error": "player_ineligible", "message": err_msg}

        templates = (await session.execute(select(GDDungeonTemplate))).scalars().all()
        if not templates:
            return {"error": "no_templates", "message": "Групповые подземелья пока не настроены."}

        if template_id is not None:
            template = next((t for t in templates if t.id == template_id), None)
            if not template:
                template = random.choice(templates)
        else:
            template = random.choice(templates)
        stage_monsters = self._build_stage_monsters(template)
        first = stage_monsters[0]
        now = datetime.now(timezone.utc)

        gd_session = GDSession(
            chat_id=chat_id,
            dungeon_template_id=template.id,
            current_stage=1,
            current_monster_hp=first["base_hp"],
            stage_base_hp=first["base_hp"],
            stage_monsters=stage_monsters,
            started_at=now,
            last_activity_at=now,
            last_save_at=now,
            event_50_done=[False] * GD_STAGES_TOTAL,
            event_10_done=[False] * GD_STAGES_TOTAL,
            status="active",
        )
        session.add(gd_session)
        await session.flush()

        await self.record_game_action(session, user_id, chat_id, "gd_start")
        await self.ensure_player_chat_first_seen(session, user_id, chat_id)
        if not dev_mode:
            await self.set_user_gd_start_cooldown(user_id)
        await session.commit()

        bonus_text = template.thematic_bonus_description or "—"
        progress_bar = "🟢" * 3 + "🔴"  # 3 normal + boss
        return {
            "success": True,
            "session_id": gd_session.id,
            "dungeon_name": template.name,
            "monster_name": first["name"],
            "monster_hp": first["base_hp"],
            "thematic_bonus": bonus_text,
            "progress_bar": progress_bar,
        }

    # --- Message → damage (Phase 2) ---

    async def _gd_damage_cooldown_key(self, chat_id: int, user_id: int) -> str:
        return f"{REDIS_GD_DMG_COOLDOWN}{chat_id}:{user_id}"

    async def _gd_check_damage_cooldown(self, chat_id: int, user_id: int) -> bool:
        """True if user can deal damage (not within 8 sec)."""
        if not self.redis:
            return True
        key = await self._gd_damage_cooldown_key(chat_id, user_id)
        return await self.redis.exists(key) == 0

    async def _gd_set_damage_cooldown(self, chat_id: int, user_id: int) -> None:
        if not self.redis:
            return
        key = await self._gd_damage_cooldown_key(chat_id, user_id)
        await self.redis.set(key, str(time.time()), ex=GD_DAMAGE_COOLDOWN_SECONDS)

    async def _gd_check_duplicate_message(self, chat_id: int, user_id: int, text: str) -> bool:
        """True if text duplicates one of last 2 messages from this user (ignore)."""
        if not self.redis or not (text or "").strip():
            return False
        key = f"{REDIS_GD_LAST_MSGS}{chat_id}:{user_id}"
        text_hash = str(hash(text.strip()))
        recent = await self.redis.lrange(key, 0, 1)
        if text_hash in recent:
            return True
        await self.redis.lpush(key, text_hash)
        await self.redis.ltrim(key, 0, 1)
        await self.redis.expire(key, 300)
        return False

    def _gd_creativity_multiplier(self, message_text: str | None, has_damage_emoji: bool, is_reply: bool) -> float:
        if is_reply:
            return 1.5
        if has_damage_emoji:
            return 1.2
        return 1.0

    def _gd_has_damage_emoji(self, text: str | None) -> bool:
        if not text:
            return False
        for emoji in GD_EMOJI_DAMAGE:
            if emoji in text:
                return True
        return False

    # --- Engage chain (Redis) ---

    def _engage_chain_key(self, chat_id: int) -> str:
        return f"{REDIS_GD_ENGAGE_CHAIN}{chat_id}"

    def _event_state_key(self, chat_id: int) -> str:
        return f"{REDIS_GD_EVENT_STATE}{chat_id}"

    async def generate_event_chain(self, chat_id: int) -> dict[str, Any]:
        """Generate a 3-task engage chain and store in Redis. Returns chain dict (with message_id=None)."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ENGAGE_CHAIN_DURATION_SECONDS)
        pool = list(ENGAGE_TASK_POOL)
        random.shuffle(pool)
        tasks = []
        for i, t in enumerate(pool[:3], 1):
            tasks.append({
                "id": i,
                "target": t["target"],
                "content_type": t["content_type"],
                "filter": t["filter"],
                "description": t["description"],
                "completed": False,
                "completed_by": None,
            })
        chain = {
            "id": f"chain_{uuid.uuid4().hex[:12]}",
            "chat_id": chat_id,
            "length": 3,
            "tasks": tasks,
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "current_task": 1,
            "message_id": None,
        }
        if self.redis:
            key = self._engage_chain_key(chat_id)
            await self.redis.set(key, json.dumps(chain), ex=ENGAGE_CHAIN_DURATION_SECONDS + 60)
        return chain

    async def get_engage_chain(self, chat_id: int) -> dict[str, Any] | None:
        if not self.redis:
            return None
        key = self._engage_chain_key(chat_id)
        raw = await self.redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set_engage_chain(self, chat_id: int, chain: dict[str, Any]) -> None:
        if not self.redis:
            return
        key = self._engage_chain_key(chat_id)
        await self.redis.set(key, json.dumps(chain), ex=ENGAGE_CHAIN_DURATION_SECONDS + 60)

    async def delete_engage_chain(self, chat_id: int) -> None:
        if self.redis:
            await self.redis.delete(self._engage_chain_key(chat_id))

    def _message_matches_engage_task(self, task: dict[str, Any], message: Any) -> bool:
        """Check if message satisfies current engage task. message: aiogram Message."""
        content_type = task.get("content_type", "")
        filter_key = task.get("filter", "")
        text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()

        if content_type == "sticker_or_emoji":
            if filter_key == "laugh_emoji":
                if message.sticker:
                    return True
                for e in LAUGH_EMOJIS:
                    if e in text:
                        return True
            elif filter_key == "heart_emoji":
                if message.sticker:
                    return True
                for e in HEART_EMOJIS:
                    if e in text:
                        return True
            return False

        if content_type == "text_with_emoji":
            if filter_key == "fire_emoji":
                return any(e in text for e in FIRE_EMOJIS)
            if filter_key == "star_emoji":
                return any(e in text for e in STAR_EMOJIS)
            return False

        if content_type == "voice_min":
            if filter_key == "duration_2_4":
                if not getattr(message, "voice", None):
                    return False
                duration = getattr(message.voice, "duration", 0) or 0
                return 2 <= duration <= 4
            return False

        return False

    async def try_advance_engage_chain(
        self, chat_id: int, user_id: int, message: Any
    ) -> Optional[str]:
        """
        If active engage chain and message matches current task: mark completed, advance.
        Returns "completed" if all 3 tasks done, "advanced" if current task done, None if no match or no chain.
        """
        chain = await self.get_engage_chain(chat_id)
        if not chain or not chain.get("tasks"):
            return None
        current = chain["current_task"]
        if current > len(chain["tasks"]):
            return None
        task = chain["tasks"][current - 1]
        if task.get("completed"):
            return None
        if not self._message_matches_engage_task(task, message):
            return None
        task["completed"] = True
        task["completed_by"] = user_id
        chain["current_task"] = current + 1
        await self.set_engage_chain(chat_id, chain)
        if chain["current_task"] > len(chain["tasks"]):
            return "completed"
        return "advanced"

    async def apply_engage_chain_effect(self, session: AsyncSession, chat_id: int) -> bool:
        """Apply −35% monster HP for full chain completion. Returns True if applied."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return False
        reduction = int(gd.stage_base_hp * ENGAGE_CHAIN_HP_EFFECT_PERCENT / 100)
        gd.current_monster_hp = max(0, gd.current_monster_hp - reduction)
        await session.commit()
        return True

    # --- Event state (boss_unique etc., Redis) ---

    async def set_event_state(
        self,
        chat_id: int,
        message_id: int,
        event_info: dict[str, Any],
    ) -> None:
        """Store event state after sending visual block (for participation tracking)."""
        if not self.redis:
            return
        now = datetime.now(timezone.utc)
        duration = event_info.get("duration_seconds", 45)
        expires_at = now + timedelta(seconds=duration)
        state = {
            "active_event_id": event_info.get("template_id"),
            "message_id": message_id,
            "participants": [],
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "min_players_required": event_info.get("min_players_required", 1),
            "name": event_info.get("name", "Событие"),
            "requirement": event_info.get("requirement", ""),
            "emoji_filter": event_info.get("emoji_filter") or "",
            "trigger_type": event_info.get("trigger_type", ""),
        }
        key = self._event_state_key(chat_id)
        await self.redis.set(key, json.dumps(state), ex=duration + 120)

    async def get_event_state(self, chat_id: int) -> dict[str, Any] | None:
        if not self.redis:
            return None
        key = self._event_state_key(chat_id)
        raw = await self.redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def clear_event_state(self, chat_id: int) -> None:
        if self.redis:
            await self.redis.delete(self._event_state_key(chat_id))

    def _message_matches_event_emoji(self, message: Any, emoji_filter_key: str) -> bool:
        """Check if message contains one of the event emojis (for boss_unique)."""
        emojis = EMOJI_FILTER_TO_EMOJIS.get((emoji_filter_key or "").strip().lower(), [])
        if not emojis:
            emojis = ["✈️", "🌪️", "💨"]
        text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
        for e in emojis:
            if e in text:
                return True
        if getattr(message, "sticker", None):
            return True  # accept any sticker as participation for simplicity
        return False

    async def register_event_participation(
        self, chat_id: int, user_id: int, message: Any
    ) -> tuple[int, bool] | None:
        """
        If active event state (boss_unique) and message matches: add user to participants.
        Returns (new_count, completed) or None if no state / no match / already participated.
        """
        state = await self.get_event_state(chat_id)
        if not state or state.get("trigger_type") != "boss_unique":
            return None
        if user_id in (state.get("participants") or []):
            return None
        if not self._message_matches_event_emoji(message, state.get("emoji_filter") or ""):
            return None
        participants = list(state.get("participants") or [])
        participants.append(user_id)
        state["participants"] = participants
        count = len(participants)
        min_required = state.get("min_players_required", 1)
        if self.redis:
            key = self._event_state_key(chat_id)
            await self.redis.set(key, json.dumps(state), ex=3600)
        return (count, count >= min_required)

    async def apply_event_effect_and_clear(
        self, session: AsyncSession, chat_id: int
    ) -> bool:
        """Apply −25% monster HP and clear active_event_id + Redis state. Returns True if applied."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return False
        reduction = int(gd.stage_base_hp * GD_EVENT_HP_EFFECT_PERCENT / 100)
        gd.current_monster_hp = max(0, gd.current_monster_hp - reduction)
        gd.active_event_id = None
        gd.event_started_at = None
        await session.commit()
        await self.clear_event_state(chat_id)
        return True

    async def process_message_damage(
        self,
        session: AsyncSession,
        chat_id: int,
        player_id: int,
        message: Any,
        media_type: MediaType,
        message_text: str | None,
        message_length: int,
    ) -> dict[str, Any] | None:
        """
        Process one message as GD damage. Returns dict with damage/error or None if ignored.
        message: aiogram Message (for reply_to_message check).
        """
        gd_session = await self.get_active_session(session, chat_id)
        if not gd_session:
            return None

        text = (message_text or "").strip()
        if media_type in (MediaType.TEXT, MediaType.LINK) and len(set(text)) < GD_MIN_UNIQUE_CHARS:
            return None
        if await self._gd_check_duplicate_message(chat_id, player_id, text or ""):
            return None
        if not await self._gd_check_damage_cooldown(chat_id, player_id):
            return None

        waifu = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
        ).scalar_one_or_none()
        if not waifu:
            return None

        eff = {}
        if self.combat_service:
            eff = await self.combat_service._get_effective_combat_profile(session, player_id, waifu)
        attack_type = eff.get("attack_type", "melee")
        weapon_damage = eff.get("weapon_damage", 1)
        base_damage = calculate_message_damage(
            media_type,
            eff.get("strength", 10),
            eff.get("agility", 10),
            eff.get("intelligence", 10),
            attack_type,
            message_length=message_length,
            weapon_damage=weapon_damage,
        )
        if base_damage <= 0:
            return None

        has_damage_emoji = self._gd_has_damage_emoji(text)
        is_reply = False
        if message and getattr(message, "reply_to_message", None):
            reply = message.reply_to_message
            if reply and getattr(reply, "from_user", None) and reply.from_user and not reply.from_user.is_bot:
                is_reply = True
        creativity = self._gd_creativity_multiplier(text, has_damage_emoji, is_reply)
        event_mult = 1.0  # Phase 3: buff
        contribution = (
            await session.execute(
                select(GDPlayerContribution).where(
                    GDPlayerContribution.session_id == gd_session.id,
                    GDPlayerContribution.user_id == player_id,
                )
            )
        ).scalar_one_or_none()
        if not contribution:
            contribution = GDPlayerContribution(
                session_id=gd_session.id,
                user_id=player_id,
                total_damage=0,
                events_completed=0,
                joined_at_stage=gd_session.current_stage,
                joined_at=datetime.now(timezone.utc),
                damage_multiplier=1.0,
            )
            session.add(contribution)
            await session.flush()
        now = datetime.now(timezone.utc)
        minutes_in = (now - contribution.joined_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
        if minutes_in < GD_NEW_PLAYER_PENALTY_MINUTES:
            adaptation = GD_NEW_PLAYER_DAMAGE_MULTIPLIER
            if contribution.damage_multiplier > adaptation:
                contribution.damage_multiplier = adaptation
        else:
            adaptation = contribution.damage_multiplier
            if contribution.damage_multiplier < 1.0:
                contribution.damage_multiplier = 1.0
                adaptation = 1.0
        damage = max(1, int(base_damage * creativity * event_mult * adaptation))
        gd_session.current_monster_hp = max(0, gd_session.current_monster_hp - damage)
        gd_session.last_activity_at = now
        contribution.total_damage = (contribution.total_damage or 0) + damage
        await self.record_game_action(session, player_id, chat_id, "gd_damage")
        await self.ensure_player_chat_first_seen(session, player_id, chat_id)
        await self._gd_set_damage_cooldown(chat_id, player_id)

        trigger_event = None
        if gd_session.current_monster_hp > 0 and not gd_session.active_event_id:
            trigger_event = await self._check_hp_events(session, gd_session)

        if gd_session.current_monster_hp <= 0:
            rewards = await self._advance_gd_stage(session, gd_session, chat_id)
            await session.commit()
            if rewards is not None:
                out = {"damage": damage, "monster_hp": 0, "gd_completed": True, "rewards": rewards}
                if trigger_event:
                    out["trigger_event"] = trigger_event
                return out
        await session.commit()
        out = {"damage": damage, "monster_hp": gd_session.current_monster_hp}
        if trigger_event:
            out["trigger_event"] = trigger_event
        return out

    async def _check_hp_events(self, session: AsyncSession, gd_session: GDSession) -> Optional[dict[str, Any]]:
        """Check 50%/10% HP thresholds; set event flags and return trigger_event for bot to announce."""
        stage = gd_session.current_stage
        base_hp = gd_session.stage_base_hp
        current_hp = gd_session.current_monster_hp
        event_50_done = list(gd_session.event_50_done or [False] * GD_STAGES_TOTAL)
        event_10_done = list(gd_session.event_10_done or [False] * GD_STAGES_TOTAL)
        idx = stage - 1
        if idx < 0 or idx >= len(event_50_done):
            return None
        trigger_type = None
        if current_hp <= base_hp * 0.1 and not event_10_done[idx]:
            trigger_type = "hp_10"
            event_10_done[idx] = True
            gd_session.event_10_done = event_10_done
        elif current_hp <= base_hp * 0.5 and not event_50_done[idx]:
            trigger_type = "hp_50"
            event_50_done[idx] = True
            gd_session.event_50_done = event_50_done
        if not trigger_type:
            return None
        templates = (
            await session.execute(
                select(GDEventTemplate).where(GDEventTemplate.trigger_type == trigger_type)
            )
        ).scalars().all()
        if not templates:
            return None
        template = random.choice(templates)
        gd_session.active_event_id = template.id
        gd_session.event_started_at = datetime.now(timezone.utc)
        return self._event_info_from_template(template)

    async def _advance_gd_stage(
        self, session: AsyncSession, gd_session: GDSession, chat_id: int
    ) -> Optional[list[dict[str, Any]]]:
        """Move to next stage or complete dungeon. Returns list of {user_id, text} for DMs when completed."""
        stage = gd_session.current_stage
        stage_monsters = gd_session.stage_monsters or []
        if stage >= GD_STAGES_TOTAL or stage >= len(stage_monsters):
            gd_session.status = "completed"
            await self.set_chat_cooldown(chat_id)
            template = await session.get(GDDungeonTemplate, gd_session.dungeon_template_id)
            if template:
                session.add(
                    GDCompletion(
                        chat_id=chat_id,
                        dungeon_template_id=template.id,
                        started_at=gd_session.started_at,
                        finished_at=datetime.now(timezone.utc),
                    )
                )
            rewards = await self._compute_and_apply_gd_rewards(session, gd_session, template)
            return rewards
        next_stage = stage + 1
        next_monster = stage_monsters[next_stage - 1]
        gd_session.current_stage = next_stage
        gd_session.current_monster_hp = next_monster["base_hp"]
        gd_session.stage_base_hp = next_monster["base_hp"]
        gd_session.event_50_done = gd_session.event_50_done or [False] * GD_STAGES_TOTAL
        gd_session.event_10_done = gd_session.event_10_done or [False] * GD_STAGES_TOTAL
        if next_stage >= len(gd_session.event_50_done):
            gd_session.event_50_done = list(gd_session.event_50_done) + [False] * (next_stage + 1 - len(gd_session.event_50_done))
        if next_stage >= len(gd_session.event_10_done):
            gd_session.event_10_done = list(gd_session.event_10_done) + [False] * (next_stage + 1 - len(gd_session.event_10_done))
        return None

    async def _compute_and_apply_gd_rewards(
        self, session: AsyncSession, gd_session: GDSession, template: GDDungeonTemplate | None
    ) -> list[dict[str, Any]]:
        """Compute contribution %, apply exp/gold to players, return list of {user_id, text} for DM."""
        contribs = (
            await session.execute(
                select(GDPlayerContribution).where(GDPlayerContribution.session_id == gd_session.id)
            )
        ).scalars().all()
        if not contribs:
            return []
        total_damage = sum(c.total_damage or 0 for c in contribs)
        if total_damage <= 0:
            total_damage = 1
        dungeon_name = template.name if template else "Подземелье"
        base_exp = GD_BASE_EXP_REWARD
        base_gold = GD_BASE_GOLD_REWARD
        result = []
        for c in contribs:
            percent = 100.0 * (c.total_damage or 0) / total_damage
            events_bonus = 1.0 + 0.15 * (c.events_completed or 0)
            exp = max(0, int(base_exp * (percent / 100.0) * events_bonus))
            gold = max(0, int(base_gold * (percent / 100.0)))
            player = await session.get(Player, c.user_id)
            if player:
                player.gold = (player.gold or 0) + gold
            waifu = (
                await session.execute(select(MainWaifu).where(MainWaifu.player_id == c.user_id))
            ).scalar_one_or_none()
            if waifu and exp > 0:
                waifu.experience = (waifu.experience or 0) + exp
                from waifu_bot.game.constants import MAX_LEVEL
                while waifu.level < MAX_LEVEL:
                    need = calculate_total_experience_for_level(waifu.level + 1) - calculate_total_experience_for_level(waifu.level)
                    if (waifu.experience or 0) < need:
                        break
                    waifu.experience = (waifu.experience or 0) - need
                    waifu.level = (waifu.level or 1) + 1
            text = (
                f"🎉 ПОБЕДА в «{dungeon_name}»!\n"
                f"Ваш вклад: {c.total_damage or 0} урона ({percent:.1f}% от общего)\n\n"
                f"Награды:\n"
                f"• {exp} опыта для вайфу\n"
                f"• {gold} монет\n"
            )
            result.append({"user_id": c.user_id, "text": text})
        return result

    # --- Background tick (Phase 4) ---

    async def run_background_tick(
        self, session: AsyncSession, run_regression: bool = False
    ) -> None:
        """
        Save all active GD sessions; optionally run regression and force-complete.
        Call every 30 sec with run_regression=True every 3rd call (90 sec).
        """
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(GDSession).where(GDSession.status == "active")
        )
        active_sessions = list(result.scalars().all())
        for gd in active_sessions:
            gd.last_save_at = now
            if gd.active_event_id and gd.event_started_at:
                try:
                    ev = await session.get(GDEventTemplate, gd.active_event_id)
                    if ev and (now - gd.event_started_at.replace(tzinfo=timezone.utc)).total_seconds() >= ev.duration_seconds:
                        gd.active_event_id = None
                        gd.event_started_at = None
                except Exception:
                    pass
            if run_regression:
                msg_count = await self.get_chat_message_count_last_seconds(
                    gd.chat_id, GD_LOW_ACTIVITY_WINDOW_SECONDS
                )
                threshold = int(GD_LOW_ACTIVITY_MESSAGES_PER_MIN * (GD_LOW_ACTIVITY_WINDOW_SECONDS / 60))
                if msg_count < max(1, threshold):
                    regress = max(1, int(gd.stage_base_hp * GD_REGRESSION_HP_PERCENT))
                    gd.current_monster_hp = max(0, gd.current_monster_hp - regress)
                    gd.adaptive_regressions_count = (gd.adaptive_regressions_count or 0) + 1
                duration_minutes = (now - gd.started_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if duration_minutes >= GD_FORCE_COMPLETE_AFTER_MINUTES:
                    if gd.current_monster_hp > gd.stage_base_hp * GD_FORCE_COMPLETE_HP_THRESHOLD:
                        gd.current_monster_hp = 0
                        await self._advance_gd_stage(session, gd, gd.chat_id)
            if gd.current_monster_hp <= 0 and gd.status == "active":
                await self._advance_gd_stage(session, gd, gd.chat_id)
        await session.commit()

    # --- Debug / test commands ---

    async def get_debug_info(self, session: AsyncSession, chat_id: int) -> dict[str, Any] | None:
        """Return debug info for current GD session (L1+)."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return None
        template = await session.get(GDDungeonTemplate, gd.dungeon_template_id)
        monsters = gd.stage_monsters or []
        cur = monsters[gd.current_stage - 1] if gd.current_stage <= len(monsters) else {}
        return {
            "session_id": gd.id,
            "dungeon_name": template.name if template else "—",
            "current_stage": gd.current_stage,
            "current_monster_hp": gd.current_monster_hp,
            "stage_base_hp": gd.stage_base_hp,
            "monster_name": cur.get("name", "—"),
            "adaptive_regressions_count": gd.adaptive_regressions_count or 0,
            "active_event_id": gd.active_event_id,
            "started_at": gd.started_at.isoformat() if gd.started_at else None,
        }

    async def get_active_dungeons_for_player(
        self, session: AsyncSession, user_id: int
    ) -> list[dict[str, Any]]:
        """Return list of active GD sessions where the player participates (for WebApp list)."""
        result = await session.execute(
            select(GDSession, GDPlayerContribution, GDDungeonTemplate)
            .join(
                GDPlayerContribution,
                (GDPlayerContribution.session_id == GDSession.id)
                & (GDPlayerContribution.user_id == user_id),
            )
            .join(GDDungeonTemplate, GDDungeonTemplate.id == GDSession.dungeon_template_id)
            .where(GDSession.status == "active")
            .order_by(GDSession.started_at.desc())
        )
        rows = result.all()
        out = []
        for gd, contrib, template in rows:
            monsters = gd.stage_monsters or []
            cur = monsters[gd.current_stage - 1] if gd.current_stage <= len(monsters) else {}
            hp_max = gd.stage_base_hp
            hp_percent = int(gd.current_monster_hp / hp_max * 100) if hp_max else 0
            duration_sec = 0
            if gd.started_at:
                duration_sec = int(
                    (datetime.now(timezone.utc) - gd.started_at.replace(tzinfo=timezone.utc)).total_seconds()
                )
            out.append({
                "id": gd.id,
                "chat_id": gd.chat_id,
                "dungeon_name": template.name if template else "Подземелье",
                "stage": gd.current_stage,
                "monster_name": cur.get("name", "Монстр"),
                "hp_current": gd.current_monster_hp,
                "hp_max": hp_max,
                "hp_percent": hp_percent,
                "total_damage": contrib.total_damage or 0,
                "joined_at_stage": contrib.joined_at_stage or 1,
                "duration_seconds": duration_sec,
                "active_effects": [],  # placeholder for future
            })
        return out

    async def force_complete(self, session: AsyncSession, chat_id: int) -> list[dict[str, Any]] | None:
        """Force complete current GD and return rewards for DMs (L2+)."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return None
        gd.status = "completed"
        await self.set_chat_cooldown(chat_id)
        template = await session.get(GDDungeonTemplate, gd.dungeon_template_id)
        if template:
            session.add(
                GDCompletion(
                    chat_id=chat_id,
                    dungeon_template_id=template.id,
                    started_at=gd.started_at,
                    finished_at=datetime.now(timezone.utc),
                )
            )
        rewards = await self._compute_and_apply_gd_rewards(session, gd, template)
        await session.commit()
        return rewards

    async def skip_stage(self, session: AsyncSession, chat_id: int) -> bool:
        """Advance to next stage (or complete if boss). Returns True if advanced. L2+."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return False
        gd.current_monster_hp = 0
        await self._advance_gd_stage(session, gd, chat_id)
        await session.commit()
        return True

    async def set_monster_hp_percent(
        self, session: AsyncSession, chat_id: int, percent: int
    ) -> bool:
        """Set current monster HP to percent (1–100) of stage_base_hp. L2+."""
        if not 1 <= percent <= 100:
            return False
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return False
        gd.current_monster_hp = max(1, int(gd.stage_base_hp * percent / 100))
        gd.last_activity_at = datetime.now(timezone.utc)
        await session.commit()
        return True

    async def force_trigger_event(
        self, session: AsyncSession, chat_id: int, event_type: str
    ) -> dict[str, Any] | None:
        """Set active event by trigger_type (e.g. hp_50, boss_unique). L3+. Returns full event info for visual block."""
        gd = await self.get_active_session(session, chat_id)
        if not gd:
            return None
        result = await session.execute(
            select(GDEventTemplate).where(GDEventTemplate.trigger_type == event_type).limit(1)
        )
        template = result.scalar_one_or_none()
        if not template:
            return None
        gd.active_event_id = template.id
        gd.event_started_at = datetime.now(timezone.utc)
        await session.commit()
        return self._event_info_from_template(template)

    def _event_info_from_template(self, template: GDEventTemplate) -> dict[str, Any]:
        """Build event dict for bot (name, duration, requirement text, template_id, trigger_type)."""
        name = template.name or "Событие"
        duration = template.duration_seconds or 45
        min_players = template.min_players_required or 1
        emoji_hint = (template.emoji_filter or "").strip() or "✈️/🌪️/💨"
        requirement = f"{min_players}+ игроков с {emoji_hint} за {duration} сек"
        return {
            "template_id": template.id,
            "trigger_type": template.trigger_type or "",
            "name": name,
            "duration_seconds": duration,
            "min_players_required": min_players,
            "emoji_filter": template.emoji_filter,
            "requirement": requirement,
        }
