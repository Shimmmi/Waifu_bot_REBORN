"""Skills service for skill management."""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from waifu_bot.db.models import (
    Player,
    MainWaifu,
    Skill,
    WaifuSkill,
    GuildSkill,
    Guild,
)


class SkillService:
    """Service for skill operations."""

    async def get_available_skills(
        self, session: AsyncSession, player_id: int, act: int
    ) -> List[Skill]:
        """Get available skills for training hall."""
        # Get all passive skills
        stmt = select(Skill).where(Skill.skill_type == 2)  # Passive
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def upgrade_skill(
        self, session: AsyncSession, player_id: int, skill_id: int, cost: int
    ) -> dict:
        """Upgrade waifu skill."""
        # Get player and waifu
        player = await session.get(Player, player_id)
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not player or not waifu:
            return {"error": "not_found"}

        # Get skill
        skill = await session.get(Skill, skill_id)
        if not skill:
            return {"error": "skill_not_found"}

        # Check gold
        if player.gold < cost:
            return {"error": "insufficient_gold"}

        # Get current skill level
        stmt = (
            select(WaifuSkill)
            .where(WaifuSkill.waifu_id == waifu.id)
            .where(WaifuSkill.skill_id == skill_id)
        )
        waifu_skill = (await session.execute(stmt)).scalar_one_or_none()

        # Get max level for current act
        max_level = self._get_max_level_for_act(skill, player.current_act)

        current_level = waifu_skill.level if waifu_skill else 0

        if current_level >= max_level:
            return {"error": "max_level_reached", "max_level": max_level}

        # Check requirements
        if skill.required_level and waifu.level < skill.required_level:
            return {"error": "level_requirement_not_met"}

        # Deduct gold
        player.gold -= cost

        # Upgrade skill
        if waifu_skill:
            waifu_skill.level += 1
        else:
            waifu_skill = WaifuSkill(waifu_id=waifu.id, skill_id=skill_id, level=1)
            session.add(waifu_skill)

        await session.commit()

        return {
            "success": True,
            "skill_id": skill_id,
            "new_level": waifu_skill.level,
            "gold_remaining": player.gold,
        }

    async def get_waifu_skills(
        self, session: AsyncSession, player_id: int
    ) -> List[dict]:
        """Get all skills for waifu."""
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not waifu:
            return []

        stmt = (
            select(WaifuSkill, Skill)
            .join(Skill, WaifuSkill.skill_id == Skill.id)
            .where(WaifuSkill.waifu_id == waifu.id)
        )
        result = await session.execute(stmt)
        skills = []

        for waifu_skill, skill in result.all():
            skills.append({
                "skill_id": skill.id,
                "skill_name": skill.name,
                "level": waifu_skill.level,
                "max_level": 15,  # TODO: Get from act
            })

        return skills

    def _get_max_level_for_act(self, skill: Skill, act: int) -> int:
        """Get max level for skill in given act."""
        max_levels = {
            1: skill.max_level_act_1,
            2: skill.max_level_act_2,
            3: skill.max_level_act_3,
            4: skill.max_level_act_4,
            5: skill.max_level_act_5,
        }
        return max_levels.get(act, skill.max_level_act_1)

