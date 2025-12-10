import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.core.config import settings
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from waifu_bot.services.combat import CombatService
from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.guild import GuildService
from waifu_bot.services.shop import ShopService
from waifu_bot.services.skills import SkillService
from waifu_bot.services.tavern import TavernService
from waifu_bot.services.webhook import process_update

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_webhook_secret(x_webhook_secret: str = Header(..., alias="X-Webhook-Secret")) -> None:
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret")


@router.post("/webhook", tags=["telegram"])
async def telegram_webhook(request: Request, _: None = Depends(verify_webhook_secret)) -> dict:
    body = await request.json()
    await process_update(body)
    return {"ok": True}


@router.get("/sse/ping", tags=["sse"])
async def sse_ping() -> dict:
    return {"pong": True}


# --- Shop endpoints ---
shop_service = ShopService()


@router.get("/shop/inventory", tags=["shop"])
async def get_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    session: AsyncSession = Depends(get_db),
):
    items = await shop_service.get_shop_inventory(session, act)
    return schemas.ShopInventoryResponse(items=[_to_item(item) for item in items], count=len(items))


@router.post("/shop/buy", tags=["shop"])
async def buy_item(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.buy_item(session, player_id, item_id)
    if result.get("item_id"):
        item = await session.get(m.Item, result["item_id"])
        if item:
            result["item"] = _to_item(item)
    return schemas.BuySellResponse(**result)


@router.post("/shop/sell", tags=["shop"])
async def sell_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.sell_item(session, player_id, inventory_item_id)
    if result.get("item_id"):
        item = await session.get(m.Item, result["item_id"])
        if item:
            result["item"] = _to_item(item)
    return schemas.BuySellResponse(**result)


@router.post("/shop/gamble", tags=["shop"])
async def gamble(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.gamble(session, player_id, act)
    if result.get("item_id"):
        item = await session.get(m.Item, result["item_id"])
        if item:
            result["item"] = _to_item(item)
    return schemas.GambleResponse(**result)


# --- Tavern endpoints ---
tavern_service = TavernService()


@router.get("/tavern/available", tags=["tavern"])
async def tavern_available(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    waifus = await tavern_service.get_available_waifus(session, player_id)
    return schemas.TavernListResponse(waifus=[_to_hired_waifu(w) for w in waifus], count=len(waifus))


@router.post("/tavern/hire", tags=["tavern"])
async def tavern_hire(
    waifu_id: Optional[int] = Query(None),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.hire_waifu(session, player_id, waifu_id)
    if result.get("waifu_id"):
        waifu = await session.get(m.HiredWaifu, result["waifu_id"])
        if waifu:
            result["waifu_name"] = waifu.name
            result["waifu_rarity"] = waifu.rarity
    return schemas.TavernActionResponse(**result)


@router.get("/tavern/squad", tags=["tavern"])
async def tavern_squad(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    squad = await tavern_service.get_squad(session, player_id)
    return {"squad": [_to_hired_waifu(w) for w in squad]}


@router.get("/tavern/reserve", tags=["tavern"])
async def tavern_reserve(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    reserve = await tavern_service.get_reserve(session, player_id)
    return {"reserve": [_to_hired_waifu(w) for w in reserve]}


@router.post("/tavern/squad/add", tags=["tavern"])
async def tavern_squad_add(
    waifu_id: int,
    slot: Optional[int] = Query(None, ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.add_to_squad(session, player_id, waifu_id, slot)
    return schemas.TavernActionResponse(**result)


@router.post("/tavern/squad/remove", tags=["tavern"])
async def tavern_squad_remove(
    waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.remove_from_squad(session, player_id, waifu_id)
    return schemas.TavernActionResponse(**result)


# --- Dungeon endpoints ---
dungeon_service = DungeonService()
combat_service = CombatService(redis_client=get_redis())


@router.get("/dungeons", tags=["dungeon"])
async def list_dungeons(
    act: int = Query(..., ge=1, le=5),
    session: AsyncSession = Depends(get_db),
):
    dungeons = await dungeon_service.get_dungeons_for_act(session, act)
    return schemas.DungeonListResponse(dungeons=[_to_dungeon(d) for d in dungeons])


@router.post("/dungeons/{dungeon_id}/start", tags=["dungeon"])
async def start_dungeon(
    dungeon_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.DungeonStartResponse(**await dungeon_service.start_dungeon(session, player_id, dungeon_id))


@router.get("/dungeons/active", tags=["dungeon"])
async def active_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    data = await dungeon_service.get_active_dungeon(session, player_id)
    return data if data is None else schemas.DungeonActiveResponse(**data)


@router.post("/battle/message", tags=["battle"])
async def battle_message(
    media_type: int = Query(..., ge=1, le=8),
    message_text: Optional[str] = None,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.game.constants import MediaType

    return schemas.BattleMessageResponse(
        **await combat_service.process_message_damage(
            session, player_id, MediaType(media_type), message_text=message_text
        )
    )


# --- Guild endpoints ---
guild_service = GuildService()


@router.post("/guilds", tags=["guild"])
async def create_guild(
    name: str,
    tag: str,
    description: Optional[str] = None,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildCreateResponse(
        **await guild_service.create_guild(session, player_id, name, tag, description)
    )


@router.get("/guilds/search", tags=["guild"])
async def search_guilds(
    q: Optional[str] = Query(None, alias="query"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
):
    guilds = await guild_service.search_guilds(session, q, limit)
    return schemas.GuildSearchResponse(guilds=[_to_guild(g) for g in guilds])


@router.post("/guilds/{guild_id}/join", tags=["guild"])
async def join_guild(
    guild_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(**await guild_service.join_guild(session, player_id, guild_id))


@router.post("/guilds/leave", tags=["guild"])
async def leave_guild(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(**await guild_service.leave_guild(session, player_id))


@router.post("/guilds/deposit/gold", tags=["guild"])
async def deposit_guild_gold(
    amount: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.deposit_gold(session, player_id, amount)
    )


@router.post("/guilds/withdraw/gold", tags=["guild"])
async def withdraw_guild_gold(
    amount: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.withdraw_gold(session, player_id, amount)
    )


@router.post("/guilds/deposit/item", tags=["guild"])
async def deposit_guild_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.deposit_item(session, player_id, inventory_item_id)
    )


@router.post("/guilds/withdraw/item", tags=["guild"])
async def withdraw_guild_item(
    bank_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.withdraw_item(session, player_id, bank_item_id)
    )


# --- Skills endpoints ---
skill_service = SkillService()


@router.get("/skills/available", tags=["skills"])
async def available_skills(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    skills = await skill_service.get_available_skills(session, player_id, act)
    return schemas.SkillsListResponse(skills=[_to_skill(s) for s in skills])


@router.post("/skills/{skill_id}/upgrade", tags=["skills"])
async def upgrade_skill(
    skill_id: int,
    cost: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.SkillUpgradeResponse(
        **await skill_service.upgrade_skill(session, player_id, skill_id, cost)
    )


# --- Serialization helpers ---
def _to_item(item: m.Item) -> schemas.ItemOut:
    return schemas.ItemOut(
        id=item.id,
        name=item.name,
        rarity=item.rarity,
        tier=item.tier,
        level=item.level,
        item_type=item.item_type,
        damage=item.damage,
        attack_speed=item.attack_speed,
        weapon_type=item.weapon_type,
        attack_type=item.attack_type,
        base_value=item.base_value,
        is_legendary=item.is_legendary,
        affixes=item.affixes,
    )


def _to_hired_waifu(w: m.HiredWaifu) -> schemas.HiredWaifuOut:
    return schemas.HiredWaifuOut(
        id=w.id,
        name=w.name,
        race=w.race,
        class_=w.class_,
        rarity=w.rarity,
        level=w.level,
        experience=w.experience,
        strength=w.strength,
        agility=w.agility,
        intelligence=w.intelligence,
        endurance=w.endurance,
        charm=w.charm,
        luck=w.luck,
        squad_position=w.squad_position,
    )


def _to_dungeon(d: m.Dungeon) -> schemas.DungeonOut:
    return schemas.DungeonOut(
        id=d.id,
        name=d.name,
        act=d.act,
        dungeon_number=d.dungeon_number,
        dungeon_type=d.dungeon_type,
        level=d.level,
        obstacle_count=d.obstacle_count,
    )


def _to_guild(g: m.Guild) -> schemas.GuildOut:
    return schemas.GuildOut(
        id=g.id,
        name=g.name,
        tag=g.tag,
        level=g.level,
        experience=g.experience,
        is_recruiting=g.is_recruiting,
    )


def _to_skill(s: m.Skill) -> schemas.SkillOut:
    return schemas.SkillOut(
        id=s.id,
        name=s.name,
        description=s.description,
        skill_type=s.skill_type,
        tier=s.tier,
        energy_cost=s.energy_cost,
        cooldown=s.cooldown,
        stat_bonus=s.stat_bonus,
        bonus_value=s.bonus_value,
        max_level_act_1=s.max_level_act_1,
        max_level_act_2=s.max_level_act_2,
        max_level_act_3=s.max_level_act_3,
        max_level_act_4=s.max_level_act_4,
        max_level_act_5=s.max_level_act_5,
    )

