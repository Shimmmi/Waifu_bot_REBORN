from waifu_bot.game.solo_hp_apply import merge_solo_hp


def test_never_raise_hp_same_dungeon_and_position():
    prev = {
        "dungeon_id": 12,
        "position": 2,
        "monster_hp": 80,
        "monster_max_hp": 100,
        "waifu_current_hp": 50,
        "waifu_max_hp": 50,
    }
    stale = {
        "dungeon_id": 12,
        "position": 2,
        "monster_hp": 90,
        "monster_max_hp": 100,
        "waifu_current_hp": 50,
        "waifu_max_hp": 50,
    }
    assert merge_solo_hp(prev, stale) is None


def test_accept_lower_hp_and_new_monster():
    prev = {"dungeon_id": 12, "position": 2, "monster_hp": 80, "monster_max_hp": 100}
    hit = {"dungeon_id": 12, "monster_position": 2, "monster_current_hp": 40, "monster_max_hp": 100}
    out = merge_solo_hp(prev, hit)
    assert out is not None
    assert out["monster_hp"] == 40

    nxt = {"dungeon_id": 12, "position": 3, "monster_hp": 200, "monster_max_hp": 200}
    out2 = merge_solo_hp(out, nxt)
    assert out2 is not None
    assert out2["monster_hp"] == 200
    assert out2["position"] == 3


def test_dungeons_js_hit_path_does_not_refresh_active():
    from pathlib import Path

    src = Path("/opt/waifu-bot-REBORN/src/waifu_bot/webapp/pages/dungeons.js").read_text(
        encoding="utf-8"
    )
    # The live battle branch must patch only; full include_log refresh is defeat/complete.
    assert "if (!applied) scheduleSoloHpRefetch();" in src
    assert "refreshSoloActive({ includeLog: true })" in src
    # Successful hit must not debounce a full /dungeons/active refetch.
    assert "payload.damage_breakdown?.length || payload.summary_ru" not in src
    on_sse = src.split("window.WaifuApp.onSseEvent = (evt) => {", 1)[1]
    on_sse = on_sse.split("const tabParamRaw", 1)[0]
    # After a normal apply, no refreshSoloActive except the defeat/complete block already returned.
    normal_tail = on_sse.rsplit("if (payload.dungeon_completed || payload.monster_defeated)", 1)[-1]
    assert "refreshSoloActive" not in normal_tail.split("if (!applied)", 1)[-1]
