"""Dungeon+ monster template picker and story boss art paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.monster_art_generation import (
    MonsterArtGenerationResult,
    generate_story_boss_art_webp,
)


def _tmpl(
    tid: int,
    *,
    act_min: int,
    act_max: int,
    boss_allowed: bool = False,
    base_difficulty: int = 5,
    weight: int = 1,
) -> MagicMock:
    t = MagicMock()
    t.id = tid
    t.act_min = act_min
    t.act_max = act_max
    t.boss_allowed = boss_allowed
    t.base_difficulty = base_difficulty
    t.weight = weight
    return t


def _mock_session(templates: list[MagicMock]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = templates
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_plus_cross_act_pool_includes_other_acts() -> None:
    svc = DungeonService()
    templates = [
        _tmpl(10, act_min=1, act_max=1),
        _tmpl(20, act_min=3, act_max=3),
        _tmpl(30, act_min=5, act_max=5),
    ]
    session = _mock_session(templates)

    cand = await svc._get_plus_cross_act_candidates(
        session,
        is_boss=False,
        target_diff=5,
        used_template_ids=set(),
    )
    ids = {int(t.id) for t, _ in cand}
    assert ids == {10, 20, 30}


@pytest.mark.asyncio
async def test_plus_cross_act_dedupes_used_templates() -> None:
    svc = DungeonService()
    templates = [_tmpl(i, act_min=1, act_max=5) for i in range(1, 17)]
    session = _mock_session(templates)
    used = set(range(1, 16))

    cand = await svc._get_plus_cross_act_candidates(
        session,
        is_boss=False,
        target_diff=5,
        used_template_ids=used,
    )
    ids = [int(t.id) for t, _ in cand]
    assert ids == [16]


@pytest.mark.asyncio
async def test_plus_cross_act_boss_filter() -> None:
    svc = DungeonService()
    # DB applies boss_allowed filter; mock returns post-filter rows only.
    templates = [_tmpl(2, act_min=1, act_max=5, boss_allowed=True)]
    session = _mock_session(templates)

    cand = await svc._get_plus_cross_act_candidates(
        session,
        is_boss=True,
        target_diff=5,
        used_template_ids=set(),
    )
    ids = {int(t.id) for t, _ in cand}
    assert ids == {2}


@pytest.mark.asyncio
async def test_plus_cross_act_allows_reuse_when_exhausted() -> None:
    svc = DungeonService()
    templates = [_tmpl(1, act_min=1, act_max=5)]
    session = _mock_session(templates)

    cand = await svc._get_plus_cross_act_candidates(
        session,
        is_boss=False,
        target_diff=5,
        used_template_ids={1},
    )
    assert len(cand) == 1
    assert int(cand[0][0].id) == 1


@pytest.mark.asyncio
async def test_generate_story_boss_art_webp_path() -> None:
    sbd = MagicMock()
    sbd.id = 7
    sbd.slug = "act2_p10"
    sbd.name = "Караул колокола"
    sbd.short_lore = "Страж руин."
    sbd.monster_template_id = 99

    tmpl = MagicMock()
    tmpl.family = "undead"
    tmpl.tier = 4
    tmpl.level_min = 40
    tmpl.hp_base = 100
    tmpl.hp_per_level = 10
    tmpl.dmg_base = 20
    tmpl.dmg_per_level = 2
    tmpl.tags = None

    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, pk: sbd if pk == 7 else tmpl)

    fake_webp = b"RIFFfake"
    with patch(
        "waifu_bot.services.monster_art_generation._openrouter_generate_webp",
        new=AsyncMock(return_value=fake_webp),
    ):
        result = await generate_story_boss_art_webp(session, 7)

    assert isinstance(result, MonsterArtGenerationResult)
    assert result.relative_path == "bosses/webp/act2_p10.webp"
    assert result.slug == "act2_p10"
    assert result.webp_bytes == fake_webp
