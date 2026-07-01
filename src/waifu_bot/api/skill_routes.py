from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.game.constants import PASSIVE_QA_ADMIN_TELEGRAM_ID
from waifu_bot.services.hidden_skills import list_hidden_skills_payload
from waifu_bot.services.passive_skills import (
    admin_max_all_passive_nodes,
    get_passive_skill_tree,
    learn_passive_node,
    reset_passive_branch,
)
from waifu_bot.services.skills import SkillService

router = APIRouter()

skill_service = SkillService()


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


@router.get("/skills/available", tags=["skills"])
async def available_skills(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    skills = await skill_service.get_available_skills(session, player_id, act)
    return schemas.SkillsListResponse(skills=[_to_skill(s) for s in skills])


@router.get("/skills/hidden", response_model=schemas.HiddenSkillsResponse, tags=["skills"])
async def hidden_skills(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    raw = await list_hidden_skills_payload(session, player_id)
    return schemas.HiddenSkillsResponse(
        skills=[
            schemas.HiddenSkillOut(
                id=x["id"],
                name=x["name"],
                icon=x.get("icon"),
                category=x.get("category"),
                description=x.get("description"),
                unlock_hint=x.get("unlock_hint"),
                counter_type=x["counter_type"],
                level=int(x.get("level") or 0),
                counter=int(x.get("counter") or 0),
                next_threshold=x.get("next_threshold"),
                max_level=int(x.get("max_level") or 5),
                revealed=bool(x.get("revealed")),
                effect_types=list(x.get("effect_types") or []),
                effect_values=list(x.get("effect_values") or []),
                current_effects=dict(x.get("current_effects") or {}),
                next_effects=x.get("next_effects"),
                image_url=x.get("image_url"),
                current_effects_labeled=[
                    schemas.HiddenEffectLabeledOut(**row)
                    for row in (x.get("current_effects_labeled") or [])
                ],
                next_effects_labeled=[
                    schemas.HiddenEffectLabeledOut(**row)
                    for row in (x.get("next_effects_labeled") or [])
                ],
                bonus_summary=x.get("bonus_summary"),
                next_bonus_summary=x.get("next_bonus_summary"),
            )
            for x in raw
        ]
    )


@router.get("/skills/passive/tree", response_model=schemas.PassiveSkillTreeResponse, tags=["skills"])
async def passive_skill_tree(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    raw = await get_passive_skill_tree(session, player_id)
    return schemas.PassiveSkillTreeResponse(**raw)


@router.post("/skills/passive/learn", response_model=schemas.PassiveLearnResponse, tags=["skills"])
async def passive_skill_learn(
    body: schemas.PassiveLearnRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    out = await learn_passive_node(session, player_id, body.node_id.strip())
    return schemas.PassiveLearnResponse(**out)


@router.post("/skills/passive/reset/{branch}", response_model=schemas.PassiveResetResponse, tags=["skills"])
async def passive_skill_reset_branch(
    branch: str,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    out = await reset_passive_branch(session, player_id, branch)
    return schemas.PassiveResetResponse(**out)


@router.post("/skills/passive/admin-max-all", response_model=schemas.PassiveAdminMaxAllResponse, tags=["skills"])
async def passive_skill_admin_max_all(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """QA-only: max all passive nodes. Telegram user id must match PASSIVE_QA_ADMIN_TELEGRAM_ID."""
    if int(player_id) != int(PASSIVE_QA_ADMIN_TELEGRAM_ID):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    out = await admin_max_all_passive_nodes(session, player_id)
    return schemas.PassiveAdminMaxAllResponse(**out)


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
