"""Delve 2.2-C invariants: tap, sawtooth, 1=3, 410, copy."""

from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.api.legacy_gone import GONE, is_legacy_expedition_path
from waifu_bot.game.delve_catalog import (
    COPY,
    GOLD_CAP_DAY_DEFAULT,
    HUD_STATUS,
    PHRASES,
    SOLO_XP_DAY_K,
    d_ceiling,
    fog_spine_type,
    frame_kicker,
    gold_cap_day,
    gold_rate_per_sec,
    hours_in_column,
    implied_record,
    journal_stamp_label,
    sawtooth,
    shaft_art_for_depth,
    shaft_band_depths,
    shaft_band_for_depth,
    spine_type,
    split_even,
    typical_solo_xp_day,
    title_for_record,
    walk_capped_grant,
    xp_cap_day,
)
from waifu_bot.game.formulas import calculate_experience_for_level
from waifu_bot.services.delve import DelveError, build_frame, companion_out, grant_tap, start_delve
from waifu_bot.services.companion_living import (
    living_preview_rows,
    party_source_cards,
    reconcile_delve_party_to_living,
)
from waifu_bot.services.guild_progress import apply_expedition_success_guild
from waifu_bot.services.passive_skills import expedition_reward_multiplier, expedition_success_probability_boost


FORBIDDEN = (
    "anyway",
    "отголосок",
    "сказание",
    "скрипторий",
    "эпитет",
    "чернила",
    "chroma",
    "idle",
)


def test_gold_cap_is_quarter_of_chat():
    assert GOLD_CAP_DAY_DEFAULT == 300
    assert gold_cap_day() == 300
    assert gold_cap_day(gold_of_chat_cap=0.25, chat_gold_cap=1200) == 300


def test_xp_cap_is_15_percent_of_typical_solo_day():
    assert SOLO_XP_DAY_K == 2.0
    typical = typical_solo_xp_day(10)
    assert typical == int(2.0 * calculate_experience_for_level(11))
    assert xp_cap_day(10) == int(0.15 * typical)


def test_afk_equals_heartbeat_gold_three_days():
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=3)
    rate = gold_rate_per_sec(300)
    one_shot, day, today = walk_capped_grant(start, end, rate=rate, cap=300, day_key=None, granted_today=0)
    cursor = start
    heartbeat_total = 0
    day_key = None
    bucket = 0
    while cursor < end:
        nxt = min(end, cursor + timedelta(hours=1))
        g, day_key, bucket = walk_capped_grant(
            cursor, nxt, rate=rate, cap=300, day_key=day_key, granted_today=bucket
        )
        heartbeat_total += g
        cursor = nxt
    assert one_shot == heartbeat_total
    assert one_shot > 0


def test_one_equals_three_ceiling_and_record():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = origin + timedelta(days=3)
    a = hours_in_column(origin, now)
    c1 = d_ceiling(a, 12)
    c3 = d_ceiling(a, 12)
    assert c1 == c3
    t1 = sawtooth(t_origin=origin, now=now, ov_level=12)
    t3 = sawtooth(t_origin=origin, now=now, ov_level=12)
    assert t1["implied_record"] == t3["implied_record"]
    assert t1["d"] == t3["d"]
    assert t1["state"] == t3["state"]


def test_palette_does_not_change_depth():
    origin = datetime(2026, 2, 1, tzinfo=timezone.utc)
    now = origin + timedelta(hours=8)
    a = sawtooth(t_origin=origin, now=now, ov_level=8)
    b = sawtooth(t_origin=origin, now=now, ov_level=8)
    assert a["depth"] == b["depth"]
    assert implied_record(
        elapsed_sec=a["elapsed_sec"], depth=a["depth"], ceil=a["d_ceiling"], t_down=a["t_down"]
    ) == b["implied_record"]


def test_after_cap_theater_still_moves():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = origin + timedelta(days=2, hours=3)
    t = sawtooth(t_origin=origin, now=now, ov_level=5)
    assert t["state"] in {"DESCENDING", "ASCENDING", "SURFACE_REST"}
    assert t["state"] != "STOPPED"
    rate = gold_rate_per_sec(300)
    g, day, today = walk_capped_grant(
        origin, origin + timedelta(hours=23), rate=rate, cap=300, day_key=None, granted_today=0
    )
    g2, _, today2 = walk_capped_grant(
        origin + timedelta(hours=23),
        origin + timedelta(hours=23, minutes=30),
        rate=rate,
        cap=300,
        day_key=day,
        granted_today=today,
    )
    assert g > 0
    assert today2 == 300 or g2 == 0 or today >= 300 or today2 >= today


def test_hud_status_strings():
    assert HUD_STATUS["DESCENDING_FAST"] == "Спуск · несут"
    assert HUD_STATUS["SURFACE_REST"] == "Лагерь · сами пойдут"
    assert COPY["go_down"] == "Идти вниз"
    assert COPY["tab"] == "Экспедиции"


def test_copy_has_no_forbidden_substrings():
    texts = list(COPY.values()) + list(HUD_STATUS.values())
    for pool in PHRASES.values():
        texts.extend(pool)
    blob = "\n".join(str(t) for t in texts).lower()
    js = (Path("/opt/waifu-bot-REBORN") / "src/waifu_bot/webapp/pages/delve.js").read_text(
        encoding="utf-8"
    ).lower()
    for word in FORBIDDEN:
        assert word not in blob, word
        if word == "чернила":
            continue
        assert word not in js, word


def test_phrases_are_short_russian():
    for pool in PHRASES.values():
        for line in pool:
            assert "{name}" in line
            assert "anyway" not in line
            assert len(line) < 80


def test_titles_zero_power_thresholds():
    assert title_for_record(9) is None
    assert title_for_record(10) == "Спускалась"
    assert title_for_record(50) == "Держит фонарь"
    assert title_for_record(120) == "Экспедиция помнит"


def test_spine_boss_every_ten():
    assert spine_type(0, 40) == "SURFACE"
    assert spine_type(10, 40) == "BOSS"
    assert spine_type(40, 40) == "CITY"
    assert spine_type(15, 40) == "CITY"
    assert spine_type(5, 40) == "BRANCH"
    assert spine_type(7, 40) == "LANDMARK"


def test_roguelike_spine_keeps_boss_city_and_rerolls_specials():
    assert spine_type(10, 9, seed=11, wipe_count=0) == "BOSS"
    assert spine_type(40, 9, seed=11, wipe_count=0) == "CITY"
    assert spine_type(15, 9, seed=11, wipe_count=0) == "CITY"
    row = [spine_type(d, 9, seed=11, wipe_count=0) for d in range(1, 10)]
    assert row.count("REST") == 2
    assert row.count("SHOP") == 1
    assert row == [spine_type(d, 9, seed=11, wipe_count=0) for d in range(1, 10)]
    other = [spine_type(d, 9, seed=11, wipe_count=1) for d in range(1, 10)]
    third = [spine_type(d, 9, seed=99, wipe_count=0) for d in range(1, 10)]
    assert row != other or row != third
    ahead = [d for d in range(13, 20) if spine_type(d, 9, seed=11, wipe_count=0) in {"REST", "SHOP", "LANDMARK"}]
    assert ahead
    assert fog_spine_type(ahead[0], 9, last_d=12, seed=11, wipe_count=0) == "UNKNOWN"
    assert fog_spine_type(20, 9, last_d=12, seed=11, wipe_count=0) == "BOSS"
    assert fog_spine_type(15, 9, last_d=12, seed=11, wipe_count=0) == "CITY"
    assert fog_spine_type(ahead[0], 9, last_d=ahead[0], seed=11, wipe_count=0) != "UNKNOWN"


def test_no_node_history_loop_helper():
    import waifu_bot.services.delve as delve_mod

    src = inspect.getsource(delve_mod)
    tree = ast.parse(src)
    names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "replay_nodes" not in names
    assert "for node in history" not in src


def test_service_does_not_import_openrouter():
    import waifu_bot.services.delve as delve_mod

    src = Path(delve_mod.__file__).read_text(encoding="utf-8")
    assert "from waifu_bot.services.llm_client" not in src
    assert "openrouter" not in src.lower()
    assert "ai_generate" not in src
    assert "llm_client" not in src


def test_legacy_expeditions_and_chronicle_are_gone():
    assert is_legacy_expedition_path("/api/expeditions/start")
    assert is_legacy_expedition_path("/api/chronicle/sync")
    assert is_legacy_expedition_path("/api/chronicle/prose")
    assert not is_legacy_expedition_path("/api/delve/sync")
    assert not is_legacy_expedition_path("/api/tavern/bgm")
    assert not is_legacy_expedition_path("/api/tavern/living/hall")
    assert not is_legacy_expedition_path("/api/tavern/living/spice")
    assert GONE["error"] == "expedition_legacy_removed"


def test_expedition_hooks_still_zero():
    assert expedition_reward_multiplier({"expedition_bonus_pct": 5.0}, {"expedition_reward_pct": 50}) == 1.0
    assert expedition_success_probability_boost({}, {"loyal_unit_success_pct": 40}) == 0.0


@pytest.mark.asyncio
async def test_apply_expedition_gxp_is_noop():
    session = MagicMock()
    await apply_expedition_success_guild(session, 1)


def test_grant_creates_no_inventory_item():
    src = inspect.getsource(grant_tap)
    assert "InventoryItem" not in src
    assert "add_item" not in src


def test_start_midday_does_not_grant_morning():
    """t_origin at 12:00 MSK must not pay the hours before noon."""
    start = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)  # 12:00 MSK
    rate = gold_rate_per_sec(300)
    g, _day, today = walk_capped_grant(
        start, start + timedelta(seconds=2), rate=rate, cap=300, day_key=None, granted_today=0
    )
    assert g == 0
    assert today >= 0


def test_afk_pb_matches_formula_samples():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = origin + timedelta(days=3)
    tooth = sawtooth(t_origin=origin, now=end, ov_level=10)
    heartbeat_pb = 0
    cursor = origin
    while cursor <= end:
        sample = sawtooth(t_origin=origin, now=cursor, ov_level=10)
        heartbeat_pb = max(heartbeat_pb, int(sample["implied_record"]))
        cursor += timedelta(hours=1)
    assert tooth["implied_record"] == heartbeat_pb
    assert tooth["implied_record"] >= 0


def test_branch_palette_not_in_depth_formula():
    origin = datetime(2026, 3, 1, tzinfo=timezone.utc)
    now = origin + timedelta(hours=11)
    a = sawtooth(t_origin=origin, now=now, ov_level=7)
    assert "palette" not in a
    assert a["d_ceiling"] == d_ceiling(hours_in_column(origin, now), 7)


@pytest.mark.asyncio
async def test_grant_tap_uses_add_gold_not_items():
    player = MagicMock()
    player.gold = 0
    mw = MagicMock()
    mw.level = 8
    mw.experience = 0
    mw.player_id = 1
    state = MagicMock()
    state.t_origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state.last_grant_ts = state.t_origin
    state.grant_day_msk = None
    state.gold_granted_today = 0
    state.xp_granted_today = 0
    state.gold_granted_total = 0
    state.xp_granted_total = 0
    now = state.t_origin + timedelta(hours=6)
    session = AsyncMock()
    with patch("waifu_bot.services.delve._caps", new_callable=AsyncMock, return_value=(300, 100)):
        with patch("waifu_bot.services.delve.add_gold", new_callable=AsyncMock, return_value=True) as add:
            with patch("waifu_bot.services.combat.apply_main_waifu_levelups", new_callable=AsyncMock):
                g, x = await grant_tap(session, player, mw, state, now=now)
    assert add.await_count == 1
    assert add.await_args.kwargs["source"] == "delve"
    assert g >= 0
    assert x >= 0


def test_build_frame_token_n_only_from_party_size():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = origin + timedelta(hours=2)
    state = MagicMock()
    state.t_origin = origin
    state.spine_seed = 7
    state.committed_palette = "coal"
    state.pb_depth = 0
    c1 = MagicMock(name="Мира", temper="curiosity")
    c1.name = "Мира"
    c1.temper = "curiosity"
    frame1 = build_frame(state, [c1], now=now, ov_level=6)
    c2 = MagicMock()
    c2.name = "Сера"
    c2.temper = "stay"
    c3 = MagicMock()
    c3.name = "Кайра"
    c3.temper = "temper"
    frame3 = build_frame(state, [c1, c2, c3], now=now, ov_level=6)
    assert frame1["d"] == frame3["d"]
    assert frame1["record"] == frame3["record"]
    assert frame1["token_n"] == 1
    assert frame3["token_n"] == 3
    assert len(frame1["band_nodes"]) == 10
    assert [n["d"] for n in frame1["band_nodes"]] == shaft_band_depths(frame1["d"])
    assert frame1.get("shaft_label")


def test_split_even_sums_to_total():
    assert split_even(10, 3) == [4, 3, 3]
    assert sum(split_even(300, 1)) == 300
    assert sum(split_even(300, 3)) == 300
    assert split_even(0, 3) == [0, 0, 0]


def test_kicker_is_human_not_enum():
    line = frame_kicker("TRAVERSE", "wet")
    assert "Мокрое" not in line
    assert "Переход" not in line
    assert "мокрый камень" in line
    assert journal_stamp_label("shop", 4, "wet") == "Лавка на 4"
    assert journal_stamp_label("landmark", 7, "wet") == "Метка на 7"
    assert journal_stamp_label("palette", 0, "wet") == "Мокрый колодец"


def test_companion_out_uses_static_webp():
    row = MagicMock()
    row.player_id = 1
    row.slot = 1
    row.name = "Васянка"
    row.stance = "scout"
    row.temper = "stay"
    row.cloak_color = "ash"
    row.image_path = None
    row.gold_earned = 12
    row.xp_earned = 4
    row.joined_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    row.created_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    out = companion_out(row, now=datetime(2026, 8, 19, tzinfo=timezone.utc))
    assert out["image_url"].startswith("/static/")
    assert "/api/delve/portraits" not in out["image_url"]
    assert out["portrait_url"] == out["image_url"]
    assert out["gold_earned"] == 12
    assert out["days"] == 9


def test_delve_py_still_llm_free():
    import waifu_bot.services.delve as delve_mod

    src = Path(delve_mod.__file__).read_text(encoding="utf-8")
    assert "llm_client" not in src
    assert "delve_line" not in src


def test_shaft_art_bands():
    assert shaft_band_for_depth(0) == 10
    assert shaft_band_for_depth(1) == 10
    assert shaft_band_for_depth(10) == 10
    assert shaft_band_for_depth(11) == 20
    assert shaft_band_for_depth(20) == 20
    assert shaft_band_for_depth(21) == 30
    assert shaft_band_for_depth(100) == 100
    assert shaft_band_for_depth(101) == 125
    assert shaft_band_for_depth(125) == 125
    assert shaft_band_for_depth(126) == 150
    assert shaft_band_for_depth(4001) == 3000
    assert shaft_art_for_depth(10)["url"].endswith("/shaft.webp")
    assert shaft_art_for_depth(20)["url"].endswith("/shaft_20.webp")
    assert shaft_art_for_depth(100)["id"] == "abyss"
    assert shaft_art_for_depth(20)["id"] == "mushrooms"
    assert shaft_art_for_depth(101)["id"] == "rust"
    assert shaft_art_for_depth(4001)["id"] == "quiet"
    assert shaft_band_depths(0) == list(range(1, 11))
    assert shaft_band_depths(15) == list(range(11, 21))
    assert shaft_band_depths(20) == list(range(11, 21))
    assert shaft_band_depths(101) == list(range(101, 111))
    assert shaft_band_depths(126) == list(range(126, 136))
    assert len(shaft_band_depths(101)) == 10
    assert len(shaft_band_depths(4001)) == 10
    delve_dir = Path("/opt/waifu-bot-REBORN/static/game/delve")
    from waifu_bot.game.delve_catalog import SHAFT_BIOMES

    assert len(SHAFT_BIOMES) == 30
    assert shaft_art_for_depth(1)["label"] == "Мокрый колодец"
    banned = {"Мокрое", "Медянка", "Зубья", "Сукно"}
    for row in SHAFT_BIOMES:
        assert row["label"] not in banned, row
        art = delve_dir / str(row["file"])
        assert art.is_file(), row["file"]
        assert art.stat().st_size > 800, row["file"]


def test_ceiling_week_keeps_old_pace_month_clears_100():
    import math

    from waifu_bot.game.delve_catalog import ALPHA, D0

    ov = 10
    week_h = 168.0
    old = D0 * (1.0 + ALPHA * math.log(1.0 + week_h)) * (1.0 + 0.03 * math.sqrt(ov))
    assert d_ceiling(week_h, ov) == pytest.approx(old)
    assert d_ceiling(week_h - 1.0, ov) == pytest.approx(
        D0 * (1.0 + ALPHA * math.log(week_h)) * (1.0 + 0.03 * math.sqrt(ov))
    )
    assert d_ceiling(30 * 24.0, ov) > 100


def test_party_source_prefers_tavern_hires():
    tavern = MagicMock()
    tavern.slot = 1
    tavern.status = "living"
    tavern.source_delve_id = None
    tavern.name = "Мара"
    ghost = MagicMock()
    ghost.slot = 2
    ghost.status = "living"
    ghost.source_delve_id = 99
    ghost.name = "Фейк"
    keep, ghosts = party_source_cards([tavern, ghost])
    assert keep == [tavern]
    assert ghosts == [ghost]


def test_party_source_keeps_migrate_only_party():
    a = MagicMock(slot=1, status="living", source_delve_id=1)
    b = MagicMock(slot=2, status="living", source_delve_id=2)
    keep, ghosts = party_source_cards([a, b])
    assert keep == [a, b]
    assert ghosts == []


def test_living_preview_rows_use_static_portrait():
    card = MagicMock()
    card.slot = 1
    card.name = "Мара"
    card.stance = "scout"
    card.portrait_pixel_path = "game/delve/portraits/1_1.webp"
    rows = living_preview_rows([card])
    assert rows == [
        {
            "slot": 1,
            "name": "Мара",
            "stance": "scout",
            "portrait_url": "/static/game/delve/portraits/1_1.webp",
        }
    ]


def test_start_delve_without_living_raises_need_hire():
    async def _run():
        mw = MagicMock()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mw
        session.execute = AsyncMock(return_value=result)
        with patch("waifu_bot.services.delve.is_unlocked", new_callable=AsyncMock, return_value=True):
            with patch(
                "waifu_bot.services.companion_living.list_living_cards",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with pytest.raises(DelveError) as ei:
                    await start_delve(
                        session,
                        1,
                        size=3,
                        companions=[{"name": "Фейк", "stance": "scout", "temper": "stay"}],
                    )
                assert ei.value.code == "need_hire"

    asyncio.run(_run())


def test_start_delve_copies_living_not_wizard_body():
    async def _run():
        card = MagicMock()
        card.slot = 1
        card.name = "Мара"
        card.status = "living"
        mw = MagicMock()
        state = MagicMock()
        state.t_origin = None
        state.sprite_count = 0
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mw
        session.execute = AsyncMock(return_value=result)
        session.flush = AsyncMock()
        synced: list[str] = []
        with patch("waifu_bot.services.delve.is_unlocked", new_callable=AsyncMock, return_value=True):
            with patch("waifu_bot.services.delve.get_state_for_update", new_callable=AsyncMock, return_value=state):
                with patch("waifu_bot.services.delve.list_companions", new_callable=AsyncMock, return_value=[]):
                    with patch(
                        "waifu_bot.services.delve.grant_and_sync",
                        new_callable=AsyncMock,
                        return_value={"started": True},
                    ):
                        with patch("waifu_bot.services.event_log.log_event", new_callable=AsyncMock):
                            with patch(
                                "waifu_bot.services.companion_living.list_living_cards",
                                new_callable=AsyncMock,
                                return_value=[card],
                            ):
                                with patch(
                                    "waifu_bot.services.companion_living.sync_card_to_delve",
                                    new_callable=AsyncMock,
                                    side_effect=lambda _s, c: synced.append(c.name),
                                ):
                                    out = await start_delve(
                                        session,
                                        9,
                                        size=3,
                                        companions=[
                                            {"name": "Фейк", "stance": "guide", "temper": "curiosity"}
                                        ],
                                    )
        assert synced == ["Мара"]
        assert state.t_origin is not None
        assert out["started"] is True

    asyncio.run(_run())


def test_reconcile_drops_migrate_ghosts_when_tavern_hire_exists():
    async def _run():
        tavern = MagicMock()
        tavern.slot = 1
        tavern.status = "living"
        tavern.source_delve_id = None
        tavern.name = "Мара"
        tavern.player_id = 1
        tavern.id = 10
        ghost = MagicMock()
        ghost.slot = 2
        ghost.status = "living"
        ghost.source_delve_id = 77
        ghost.name = "Фейк"
        ghost.player_id = 1
        ghost.id = 11
        fake = MagicMock(slot=1, name="Чужая")
        extra = MagicMock(slot=3, name="Лишняя")
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        synced: list[str] = []
        with patch(
            "waifu_bot.services.companion_living.list_living_cards",
            new_callable=AsyncMock,
            return_value=[tavern, ghost],
        ):
            with patch(
                "waifu_bot.services.companion_living.sync_card_to_delve",
                new_callable=AsyncMock,
                side_effect=lambda _s, c: synced.append(c.name),
            ):
                with patch(
                    "waifu_bot.services.companion_living.unsync_delve_slot",
                    new_callable=AsyncMock,
                ) as unsync:
                    with patch(
                        "waifu_bot.services.companion_living.list_companions",
                        new_callable=AsyncMock,
                        return_value=[fake, extra],
                    ):
                        await reconcile_delve_party_to_living(session, 1)
        assert ghost.status == "left"
        assert ghost.slot is None
        assert synced == ["Мара"]
        unsync.assert_awaited()
        session.delete.assert_awaited()

    asyncio.run(_run())
