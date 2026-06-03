"""Group chat activity rewards: points, gold, exp, milestone chests."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    ItemRarity,
    MainWaifu,
    Player,
    PlayerChatActivityDaily,
    PlayerChatActivityTotal,
    PlayerChatRewardWallet,
)
from waifu_bot.game.constants import INT_EXP_BONUS_COEFF, LCK_GOLD_COEFF, MediaType
from waifu_bot.game.main_waifu_base_stats import chat_exp_pct_for, chat_gold_pct_for
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
from waifu_bot.services.guild_skill_effects import (
    GUILD_SKILL_PARAM_LABELS,
    effect_values_for_player,
    guild_skill_contributions,
    pct_bonus_lines_ru,
)
from waifu_bot.services.passive_skills import get_passive_skill_bonuses

logger = logging.getLogger(__name__)

BUF_PREFIX = "chat_reward:buf:"
CD_PREFIX = "chat_reward:cd:"
DAILY_PTS_PREFIX = "chat_reward:daily_pts:"
AUTHORS_PREFIX = "chat_authors:"
BUF_TTL_SECONDS = 25 * 3600
AUTHORS_TTL_SECONDS = 3600

_MEDIA_POINTS: dict[MediaType, int] = {
    MediaType.TEXT: 1,
    MediaType.STICKER: 1,
    MediaType.PHOTO: 2,
    MediaType.GIF: 2,
    MediaType.AUDIO: 3,
    MediaType.VIDEO: 3,
    MediaType.VOICE: 3,
    MediaType.LINK: 1,
}


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _buf_key(player_id: int) -> str:
    return f"{BUF_PREFIX}{int(player_id)}"


def _cd_key(player_id: int) -> str:
    return f"{CD_PREFIX}{int(player_id)}"


def _daily_pts_key(player_id: int, day: date) -> str:
    return f"{DAILY_PTS_PREFIX}{int(player_id)}:{day.isoformat()}"


def _authors_key(chat_id: int) -> str:
    return f"{AUTHORS_PREFIX}{int(chat_id)}"


def compute_chat_points(media_type: MediaType, text_chars: int, cfg: dict[str, str]) -> int:
    """Raw activity points for one message (before daily cap trim)."""
    media_coef = _MEDIA_POINTS.get(media_type, 1)
    chars_per = max(1, cfg_int(cfg, "chat_reward.chars_per_point", 40))
    max_text = max(0, cfg_int(cfg, "chat_reward.max_text_bonus", 4))
    cap = max(1, cfg_int(cfg, "chat_reward.points_per_msg_cap", 5))
    text_bonus = min(max_text, int(text_chars) // chars_per) if text_chars > 0 else 0
    base = float(media_coef) + float(text_bonus)
    return min(cap, max(0, int(round(base))))


def award_chest_milestones(lifetime_before: int, lifetime_after: int, step: int) -> int:
    """How many milestone chests were crossed between two lifetime point totals."""
    if step <= 0 or lifetime_after <= lifetime_before:
        return 0
    before_m = int(lifetime_before) // step
    after_m = int(lifetime_after) // step
    return max(0, after_m - before_m)


def chest_rarity_for_unlock_index(chest_index: int) -> int:
    """1-based chest unlock count -> item rarity tier."""
    n = max(1, int(chest_index))
    if n <= 4:
        return int(ItemRarity.COMMON)
    if n <= 14:
        return int(ItemRarity.UNCOMMON)
    if n <= 29:
        return int(ItemRarity.RARE)
    return int(ItemRarity.EPIC)


@dataclass
class ChatRewardBreakdown:
    gold_mult: float = 1.0
    exp_mult: float = 1.0
    sources: dict[str, float] = field(default_factory=dict)
    source_labels_ru: dict[str, str] = field(default_factory=dict)
    guild_bonus_lines: list[str] = field(default_factory=list)


_CHAT_SOURCE_LABELS_RU: dict[str, str] = {
    "luck_gold": "Удача",
    "int_exp": "Интеллект",
    "charm_social": "Обаяние",
    "race_class_gold": "Раса/класс",
    "race_class_exp": "Раса/класс",
    "passive_chat_gold": "Пассивка",
    "passive_chat_exp": "Пассивка",
}


def _source_label_ru(key: str) -> str:
    if key in GUILD_SKILL_PARAM_LABELS:
        return GUILD_SKILL_PARAM_LABELS[key]
    if key.startswith("guild_"):
        param = key.replace("guild_", "", 1)
        if param in GUILD_SKILL_PARAM_LABELS:
            return GUILD_SKILL_PARAM_LABELS[param]
    return _CHAT_SOURCE_LABELS_RU.get(key, key)


async def resolve_multipliers(
    session: AsyncSession,
    player_id: int,
    *,
    unique_authors_in_chat: int = 0,
) -> ChatRewardBreakdown:
    """Collect gold/exp multipliers from stats, passives, guild, race/class."""
    waifu = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if not waifu:
        return ChatRewardBreakdown()

    luck = int(waifu.luck or 0)
    intelligence = int(waifu.intelligence or 0)
    charm = int(waifu.charm or 0)
    race = int(waifu.race or 0)
    class_ = int(waifu.class_ or 0)

    gold_mult = 1.0 + luck * float(LCK_GOLD_COEFF)
    exp_mult = 1.0 + intelligence * float(INT_EXP_BONUS_COEFF)
    sources: dict[str, float] = {
        "luck_gold": luck * float(LCK_GOLD_COEFF),
        "int_exp": intelligence * float(INT_EXP_BONUS_COEFF),
    }

    if unique_authors_in_chat > 0 and charm > 0:
        chm_bonus = min(0.25, charm * 0.0005 * float(unique_authors_in_chat))
        gold_mult += chm_bonus
        exp_mult += chm_bonus
        sources["charm_social"] = chm_bonus

    race_gold = chat_gold_pct_for(race, class_)
    race_exp = chat_exp_pct_for(race, class_)
    if race_gold > 0:
        gold_mult += race_gold
        sources["race_class_gold"] = race_gold
    if race_exp > 0:
        exp_mult += race_exp
        sources["race_class_exp"] = race_exp

    try:
        ps = await get_passive_skill_bonuses(session, player_id)
        chat_gold_pct = float(ps.get("chat_gold_pct", 0) or 0)
        chat_exp_pct = float(ps.get("chat_exp_pct", 0) or 0)
        if chat_gold_pct > 0:
            gold_mult += chat_gold_pct
            sources["passive_chat_gold"] = chat_gold_pct
        if chat_exp_pct > 0:
            exp_mult += chat_exp_pct
            sources["passive_chat_exp"] = chat_exp_pct
    except Exception:
        logger.exception("resolve_multipliers: passive bonuses failed player_id=%s", player_id)

    guild_lines: list[str] = []
    try:
        gfx = await effect_values_for_player(session, player_id)
        chat_guild = float(gfx.get("chat_reward_pct", 0) or 0)
        global_pct = float(gfx.get("global_reward_pct", 0) or 0)
        if chat_guild > 0:
            gold_mult += chat_guild
            exp_mult += chat_guild
            sources["chat_reward_pct"] = chat_guild
        if global_pct > 0:
            gold_mult += global_pct
            exp_mult += global_pct
            sources["global_reward_pct"] = global_pct
        guild_lines = pct_bonus_lines_ru(
            await guild_skill_contributions(
                session, player_id, params={"chat_reward_pct", "global_reward_pct"}
            )
        )
    except Exception:
        logger.exception("resolve_multipliers: guild effects failed player_id=%s", player_id)

    source_labels_ru = {k: _source_label_ru(k) for k, v in sources.items() if v}
    return ChatRewardBreakdown(
        gold_mult=gold_mult,
        exp_mult=exp_mult,
        sources=sources,
        source_labels_ru=source_labels_ru,
        guild_bonus_lines=guild_lines,
    )


def _points_to_rewards(points: int, cfg: dict[str, str], br: ChatRewardBreakdown) -> tuple[int, int]:
    if points <= 0:
        return 0, 0
    gold_per = cfg_int(cfg, "chat_reward.gold_per_point", 2)
    exp_per = cfg_int(cfg, "chat_reward.exp_per_point", 3)
    gold = max(0, int(round(points * gold_per * br.gold_mult)))
    exp = max(0, int(round(points * exp_per * br.exp_mult)))
    return gold, exp


async def _redis_get_int(redis: Any, key: str) -> int:
    if not redis:
        return 0
    try:
        raw = await redis.get(key)
        return int(raw or 0)
    except Exception:
        return 0


async def _redis_hgetall_ints(redis: Any, key: str) -> dict[str, int]:
    if not redis:
        return {}
    try:
        raw = await redis.hgetall(key)
        if not raw:
            return {}
        out: dict[str, int] = {}
        for k, v in raw.items():
            try:
                out[str(k)] = int(v or 0)
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


async def _get_today_points(session: AsyncSession, redis: Any, player_id: int, day: date) -> int:
    row = (
        await session.execute(
            select(PlayerChatActivityDaily.points).where(
                PlayerChatActivityDaily.player_id == int(player_id),
                PlayerChatActivityDaily.day == day,
            )
        )
    ).scalar_one_or_none()
    db_pts = int(row or 0)
    redis_pts = await _redis_get_int(redis, _daily_pts_key(player_id, day))
    return db_pts + redis_pts


async def _record_unique_author(redis: Any, chat_id: int | None, player_id: int) -> int:
    if not redis or chat_id is None:
        return 0
    try:
        key = _authors_key(chat_id)
        await redis.sadd(key, str(int(player_id)))
        await redis.expire(key, AUTHORS_TTL_SECONDS)
        return int(await redis.scard(key) or 0)
    except Exception:
        return 0


async def buffer_chat_reward(
    redis: Any,
    player_id: int,
    *,
    gold: int,
    exp: int,
    points: int,
    day: date | None = None,
) -> None:
    if not redis or (gold <= 0 and exp <= 0 and points <= 0):
        return
    key = _buf_key(player_id)
    d = day or _today_utc()
    try:
        pipe = redis.pipeline()
        if gold > 0:
            pipe.hincrby(key, "gold", int(gold))
        if exp > 0:
            pipe.hincrby(key, "exp", int(exp))
        if points > 0:
            pipe.hincrby(key, "points", int(points))
            pipe.incrby(_daily_pts_key(player_id, d), int(points))
            pipe.expire(_daily_pts_key(player_id, d), BUF_TTL_SECONDS)
        pipe.hincrby(key, "messages", 1)
        pipe.expire(key, BUF_TTL_SECONDS)
        await pipe.execute()
    except Exception:
        logger.exception("buffer_chat_reward failed player_id=%s", player_id)


async def try_award_chat_message(
    session: AsyncSession,
    redis: Any,
    *,
    player_id: int,
    chat_id: int | None,
    media_type: MediaType,
    text_chars: int,
    cfg: dict[str, str],
) -> bool:
    """Award chat activity into Redis buffer. Returns True if message counted."""
    min_chars = cfg_int(cfg, "chat_reward.min_chars", 3)
    if media_type in (MediaType.TEXT, MediaType.LINK) and text_chars > 0 and text_chars < min_chars:
        return False
    if media_type in (MediaType.TEXT, MediaType.LINK) and text_chars == 0:
        return False

    cooldown_s = max(1, cfg_int(cfg, "chat_reward.min_seconds_between_msgs", 8))
    if redis:
        try:
            ok = await redis.set(_cd_key(player_id), "1", nx=True, ex=cooldown_s)
            if not ok:
                return False
        except Exception:
            logger.exception("chat reward cooldown check failed player_id=%s", player_id)

    day = _today_utc()
    daily_cap = cfg_int(cfg, "chat_reward.daily_points_cap", 600)
    today_pts = await _get_today_points(session, redis, player_id, day)
    if today_pts >= daily_cap:
        return False

    points = compute_chat_points(media_type, text_chars, cfg)
    if points <= 0:
        return False

    room = daily_cap - today_pts
    points = min(points, room)
    if points <= 0:
        return False

    unique_authors = await _record_unique_author(redis, chat_id, player_id)
    br = await resolve_multipliers(session, player_id, unique_authors_in_chat=unique_authors)
    gold, exp = _points_to_rewards(points, cfg, br)
    await buffer_chat_reward(redis, player_id, gold=gold, exp=exp, points=points, day=day)
    try:
        from waifu_bot.services.hidden_skills import increment_skill_counter

        await increment_skill_counter(session, player_id, "group_message", 1)
    except Exception:
        pass
    return True


async def _ensure_wallet(session: AsyncSession, player_id: int) -> PlayerChatRewardWallet:
    row = await session.get(PlayerChatRewardWallet, int(player_id))
    if row:
        return row
    row = PlayerChatRewardWallet(player_id=int(player_id))
    session.add(row)
    await session.flush()
    return row


async def _ensure_daily(session: AsyncSession, player_id: int, day: date) -> PlayerChatActivityDaily:
    row = (
        await session.execute(
            select(PlayerChatActivityDaily).where(
                PlayerChatActivityDaily.player_id == int(player_id),
                PlayerChatActivityDaily.day == day,
            )
        )
    ).scalar_one_or_none()
    if row:
        return row
    row = PlayerChatActivityDaily(player_id=int(player_id), day=day)
    session.add(row)
    await session.flush()
    return row


async def _ensure_total(session: AsyncSession, player_id: int) -> PlayerChatActivityTotal:
    row = await session.get(PlayerChatActivityTotal, int(player_id))
    if row:
        return row
    row = PlayerChatActivityTotal(player_id=int(player_id))
    session.add(row)
    await session.flush()
    return row


async def _flush_player_buffer(
    session: AsyncSession,
    redis: Any,
    player_id: int,
    cfg: dict[str, str],
) -> bool:
    if not redis:
        return False
    key = _buf_key(player_id)
    data = await _redis_hgetall_ints(redis, key)
    if not data or not any(data.get(k, 0) for k in ("gold", "exp", "points", "messages")):
        return False

    gold = int(data.get("gold", 0) or 0)
    exp = int(data.get("exp", 0) or 0)
    points = int(data.get("points", 0) or 0)
    messages = int(data.get("messages", 0) or 0)

    wallet = await _ensure_wallet(session, player_id)
    wallet.gold = int(wallet.gold or 0) + gold
    wallet.exp = int(wallet.exp or 0) + exp
    wallet.last_buffered_at = datetime.now(timezone.utc)

    day = _today_utc()
    daily = await _ensure_daily(session, player_id, day)
    daily.points = int(daily.points or 0) + points
    daily.gold_earned = int(daily.gold_earned or 0) + gold
    daily.exp_earned = int(daily.exp_earned or 0) + exp
    daily.messages = int(daily.messages or 0) + messages

    total = await _ensure_total(session, player_id)
    before = int(total.lifetime_points or 0)
    after = before + points
    total.lifetime_points = after

    step = max(1, cfg_int(cfg, "chat_reward.chest_milestone_step", 1000))
    new_chests = award_chest_milestones(before, after, step)
    if new_chests > 0:
        wallet.pending_chests = int(wallet.pending_chests or 0) + new_chests
        total.chests_unlocked_count = int(total.chests_unlocked_count or 0) + new_chests
        total.last_chest_at = datetime.now(timezone.utc)
        daily.chests_granted = int(daily.chests_granted or 0) + new_chests

    try:
        await redis.delete(key)
        await redis.delete(_daily_pts_key(player_id, day))
    except Exception:
        logger.exception("flush: redis delete failed player_id=%s", player_id)
    return True


async def flush_buffer_to_db(session: AsyncSession, redis: Any) -> int:
    """Flush all pending Redis chat reward buffers into DB. Returns players flushed."""
    if not redis:
        return 0
    cfg = await get_game_config_map(session)
    flushed = 0
    try:
        async for key in redis.scan_iter(match=f"{BUF_PREFIX}*"):
            suffix = str(key)[len(BUF_PREFIX) :]
            try:
                player_id = int(suffix)
            except ValueError:
                continue
            if await _flush_player_buffer(session, redis, player_id, cfg):
                flushed += 1
    except Exception:
        logger.exception("flush_buffer_to_db scan failed")
    return flushed


async def flush_player_buffer(session: AsyncSession, redis: Any, player_id: int) -> None:
    cfg = await get_game_config_map(session)
    await _flush_player_buffer(session, redis, int(player_id), cfg)


@dataclass
class ClaimResult:
    ok: bool = True
    gold: int = 0
    exp: int = 0
    chests: int = 0
    level_before: int = 1
    level_after: int = 1
    items: list[dict[str, Any]] = field(default_factory=list)
    guild_bonus_lines: list[str] = field(default_factory=list)
    error: str | None = None


async def claim_wallet(session: AsyncSession, redis: Any, player_id: int) -> ClaimResult:
    """Claim accumulated chat rewards (flush buffer first, then wallet)."""
    await flush_player_buffer(session, redis, player_id)

    wallet = (
        await session.execute(
            select(PlayerChatRewardWallet)
            .where(PlayerChatRewardWallet.player_id == int(player_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not wallet:
        return ClaimResult(ok=True, gold=0, exp=0, chests=0)

    gold = int(wallet.gold or 0)
    exp_amt = int(wallet.exp or 0)
    chests = int(wallet.pending_chests or 0)
    if gold <= 0 and exp_amt <= 0 and chests <= 0:
        return ClaimResult(ok=True, gold=0, exp=0, chests=0)

    player = await session.get(Player, int(player_id))
    waifu = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if not player or not waifu:
        return ClaimResult(ok=False, error="no_waifu")

    level_before = int(waifu.level or 1)
    items_out: list[dict[str, Any]] = []
    br = await resolve_multipliers(session, player_id)

    if gold > 0:
        player.gold = int(player.gold or 0) + gold
    if exp_amt > 0:
        waifu.experience = int(waifu.experience or 0) + exp_amt
        from waifu_bot.services.combat import apply_main_waifu_levelups

        await apply_main_waifu_levelups(session, waifu)

    if chests > 0:
        from waifu_bot.services.item_service import ItemService

        cfg = await get_game_config_map(session)
        svc = ItemService()
        act = max(1, int(getattr(player, "current_act", 1) or 1))
        ilvl_offset = cfg_int(cfg, "chat_reward.chest_min_item_level_offset", -2)
        item_level = max(1, level_before + ilvl_offset)
        total_row = await _ensure_total(session, player_id)
        base_chest_idx = int(total_row.chests_unlocked_count or 0) - chests
        for i in range(chests):
            rarity = chest_rarity_for_unlock_index(base_chest_idx + i + 1)
            try:
                inv = await svc.generate_inventory_item(
                    session,
                    player_id=int(player_id),
                    act=act,
                    rarity=rarity,
                    level=item_level,
                )
                affix_count = len(getattr(inv, "affixes", None) or [])
                if int(rarity) >= 2 and affix_count == 0:
                    logger.warning(
                        "claim_wallet: chest item has no affixes player_id=%s rarity=%s "
                        "level=%s act=%s inv_id=%s name=%r",
                        player_id,
                        rarity,
                        item_level,
                        act,
                        getattr(inv, "id", None),
                        getattr(getattr(inv, "item", None), "name", None),
                    )
                item_name = "Предмет"
                if inv.item:
                    item_name = inv.item.name
                else:
                    await session.refresh(inv, ["item"])
                    if inv.item:
                        item_name = inv.item.name
                items_out.append(
                    {
                        "inventory_item_id": int(inv.id),
                        "name": item_name,
                        "rarity": rarity,
                    }
                )
            except Exception:
                logger.exception("claim_wallet: chest item gen failed player_id=%s", player_id)

    wallet.gold = 0
    wallet.exp = 0
    wallet.pending_chests = 0
    wallet.last_claimed_at = datetime.now(timezone.utc)

    level_after = int(waifu.level or 1)
    return ClaimResult(
        ok=True,
        gold=gold,
        exp=exp_amt,
        chests=chests,
        level_before=level_before,
        level_after=level_after,
        items=items_out,
        guild_bonus_lines=list(br.guild_bonus_lines),
    )


async def get_status(session: AsyncSession, redis: Any, player_id: int) -> dict[str, Any]:
    """Wallet + today stats + lifetime progress for UI."""
    cfg = await get_game_config_map(session)
    day = _today_utc()
    step = max(1, cfg_int(cfg, "chat_reward.chest_milestone_step", 1000))
    daily_cap = cfg_int(cfg, "chat_reward.daily_points_cap", 600)

    wallet = await session.get(PlayerChatRewardWallet, int(player_id))
    daily = (
        await session.execute(
            select(PlayerChatActivityDaily).where(
                PlayerChatActivityDaily.player_id == int(player_id),
                PlayerChatActivityDaily.day == day,
            )
        )
    ).scalar_one_or_none()
    total = await session.get(PlayerChatActivityTotal, int(player_id))

    buf = await _redis_hgetall_ints(redis, _buf_key(player_id)) if redis else {}
    redis_daily = await _redis_get_int(redis, _daily_pts_key(player_id, day)) if redis else 0

    wallet_gold = int(wallet.gold or 0 if wallet else 0) + int(buf.get("gold", 0) or 0)
    wallet_exp = int(wallet.exp or 0 if wallet else 0) + int(buf.get("exp", 0) or 0)
    pending_chests = int(wallet.pending_chests or 0 if wallet else 0)

    today_points = int(daily.points or 0 if daily else 0) + redis_daily
    lifetime = int(total.lifetime_points or 0 if total else 0) + int(buf.get("points", 0) or 0)
    progress_in_step = lifetime % step
    next_chest_at = step - progress_in_step if progress_in_step > 0 else step

    br = await resolve_multipliers(session, player_id)
    return {
        "wallet": {
            "gold": wallet_gold,
            "exp": wallet_exp,
            "pending_chests": pending_chests,
        },
        "today": {
            "points": today_points,
            "cap": daily_cap,
            "messages": int(daily.messages or 0 if daily else 0) + int(buf.get("messages", 0) or 0),
            "gold": int(daily.gold_earned or 0 if daily else 0) + int(buf.get("gold", 0) or 0),
            "exp": int(daily.exp_earned or 0 if daily else 0) + int(buf.get("exp", 0) or 0),
        },
        "lifetime_points": lifetime,
        "next_chest_in_points": next_chest_at,
        "chest_milestone_step": step,
        "multipliers": {
            "gold_mult": round(br.gold_mult, 4),
            "exp_mult": round(br.exp_mult, 4),
            "sources": {k: round(v, 4) for k, v in br.sources.items()},
            "source_labels_ru": br.source_labels_ru,
        },
        "guild_bonus_lines": br.guild_bonus_lines,
        "claimable": wallet_gold > 0 or wallet_exp > 0 or pending_chests > 0,
    }
