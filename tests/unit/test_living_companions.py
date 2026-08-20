"""Living companions: catalog, digest, ledger teeth stay off the faucet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from waifu_bot.db.models.companion_card import CompanionCard
from waifu_bot.game.delve_catalog import SHAFT_BIOMES, STANCES, TEMPERS
from waifu_bot.services.chronicle import (
    BEAT_SEC,
    CATALOG_SHA256_PREFIX,
    MAX_CATCHUP,
    apply_outcome,
    assemble_line,
    assert_catalog_pin,
    bond_sentence,
    catalog_hash,
    digest_lines,
    load_catalog,
    refresh_event_line,
    _biome_ok,
)
from waifu_bot.services.delve import grant_tap
from waifu_bot.services.companion_living import look_card_for


def _ev(**kw):
    base = dict(
        id=1,
        ts=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
        severity="mundane",
        kind="beat",
        line_ru="тишина",
        depth=4,
        card_id=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_catalog_pin_and_size():
    pack = load_catalog()
    assert len(pack["templates"]) == 40
    assert catalog_hash() == CATALOG_SHA256_PREFIX
    assert_catalog_pin()
    ids = [t["id"] for t in pack["templates"]]
    assert len(ids) == len(set(ids))
    for tpl in pack["templates"]:
        assert "{who}" in str(tpl.get("line") or "")


def test_assemble_uses_line_and_place_not_nominative_biome():
    tpl = {"line": "{who} трогает метку {place}."}
    a = assemble_line(who="Данилка", place="в пепле", tpl=tpl)
    b = assemble_line(who="Данилка", place="в пепле", wound="Бережёт руку.", tpl=tpl)
    assert a == "Данилка трогает метку в пепле."
    assert a != b
    assert "в Пепел" not in a
    ash = next(t for t in load_catalog()["templates"] if t["id"] == "ash_cough")
    spit = assemble_line(who="Данилка", place="в угольной пыли", tpl=ash)
    assert spit.startswith("Данилка сплёвывает пепел")
    assert "в угольной" not in spit
    for biome in SHAFT_BIOMES:
        for t in load_catalog()["templates"]:
            line = assemble_line(who="Данилка", place=str(biome["place_ru"]), tpl=t, other="Сера")
            assert f"в {biome['label']}" not in line


def test_bond_line_uses_name_not_shield_role():
    tpl = next(t for t in load_catalog()["templates"] if t["id"] == "bond_look_away")
    bond = bond_sentence(delta=-1, other="Сера", tpl=tpl)
    assert bond == "Сера не смотрит."
    line = assemble_line(who="Данилка", place="среди грибов", wound="", bond=bond, tpl=tpl, other="Сера")
    assert line == "Данилка отводит глаза. Сера не смотрит."
    assert "Щит" not in line
    share = next(t for t in load_catalog()["templates"] if t["id"] == "bond_share_cloak")
    shared = assemble_line(who="Данилка", tpl=share, other="Сера")
    assert shared == "Данилка кидает плащ на плечи Сера."
    assert "Щит" not in shared


def test_biome_lock_keeps_ash_off_ice():
    ash = next(t for t in load_catalog()["templates"] if t["id"] == "ash_cough")
    ice = next(t for t in load_catalog()["templates"] if t["id"] == "ice_breath")
    assert _biome_ok(ash, "ash")
    assert not _biome_ok(ash, "ice")
    assert _biome_ok(ice, "ice")
    assert not _biome_ok(ice, "ash")
    generic = next(t for t in load_catalog()["templates"] if t["id"] == "lamp_hiss")
    assert _biome_ok(generic, "crystal")


def test_refresh_rewrites_old_glue_unless_spiced():
    ev = SimpleNamespace(
        line_ru="Данилка трогает метку в Пепел.",
        template_id="landmark_touch",
        depth=50,
        payload={},
    )
    fresh = refresh_event_line(ev, who="Данилка")
    assert "в Пепел" not in fresh
    assert "в пепле" in fresh
    spiced = SimpleNamespace(
        line_ru="Данилка трогает метку в Пепел.",
        template_id="landmark_touch",
        depth=50,
        payload={"spiced": True},
    )
    assert refresh_event_line(spiced, who="Данилка") == "Данилка трогает метку в Пепел."
    bond_ev = SimpleNamespace(
        line_ru="Данилка отводит глаза. Щит не смотрит.",
        template_id="bond_look_away",
        depth=20,
        payload={"bond": {"2": -1}, "other_name": "Сера", "bond_delta": -1},
    )
    bonded = refresh_event_line(bond_ev, who="Данилка")
    assert "Щит" not in bonded
    assert "Сера не смотрит" in bonded


def test_dismiss_card_has_no_age_or_beat_lock():
    from inspect import getsource

    from waifu_bot.services.companion_living import dismiss_card

    src = Path("src/waifu_bot/services/companion_living.py").read_text(encoding="utf-8")
    body = getsource(dismiss_card)
    assert "too_young" not in body
    assert "too_young" not in src
    assert STANCES["shield"]["label"] == "Со щитом"
    assert TEMPERS["temper"]["label"] == "Вспыльчивость"
    hall_js = Path("src/waifu_bot/webapp/pages/tavern_hall.js").read_text(encoding="utf-8")
    assert "Плоть" not in hall_js
    assert "living-dismiss-btn" in hall_js
    assert "disabled" not in hall_js.split("living-dismiss-btn")[1][:80]
    assert 'data-kind="hire"' in hall_js
    assert "living-log-btn" in hall_js
    assert "confirm_hire" not in hall_js
    assert "hireCostLabel" in hall_js
    assert "can-rename" in hall_js
    assert "/tavern/living/cards/" in hall_js and "rename" in hall_js
    living = Path("src/waifu_bot/services/companion_living.py").read_text(encoding="utf-8")
    assert '"kind": "hire"' in living
    assert "compute_living_hire_price" in living
    assert "spend_gold" in living
    css = Path("src/waifu_bot/webapp/pages/tavern-living.css").read_text(encoding="utf-8")
    modal_css = css.split(".living-modal {", 1)[1].split("}", 1)[0]
    assert "align-items: center" in modal_css
    assert "flex-end" not in modal_css
    art = Path("src/waifu_bot/services/companion_art.py").read_text(encoding="utf-8")
    assert "schedule_pending_art" in art
    assert "extra_visual" in art
    assert "image_url" in art
    assert "race_ru" in art
    from waifu_bot.services.companion_living import hire_generated

    hire_src = getsource(hire_generated)
    assert "too_young" not in hire_src
    assert "party_full" in hire_src
    assert "not_enough_gold" in hire_src


def test_living_chat_knows_main_waifu():
    chat = Path("src/waifu_bot/services/companion_chat.py").read_text(encoding="utf-8")
    assert "patron_name" in chat
    assert "путницей" in chat
    assert "наняла" in chat
    art = Path("src/waifu_bot/services/companion_art.py").read_text(encoding="utf-8")
    assert "hired_by" in art
    assert "наняла" in art
    living = Path("src/waifu_bot/services/companion_living.py").read_text(encoding="utf-8")
    assert "hired_by" in living
    look = look_card_for(name="Мира", stance="scout", cloak="ash", traits=["тихая"], seed=1, hired_by="Вася")
    assert look["hired_by"] == "Вася"
    assert look["race_id"] in range(1, 8)
    assert look["class_id"] in range(1, 8)
    assert look["race_ru"]
    assert look["class_ru"]


def test_rename_once_and_name_rules():
    from inspect import getsource

    from waifu_bot.services.companion_living import normalize_companion_name, rename_card
    from waifu_bot.services.delve import DelveError

    assert normalize_companion_name("Юна") == "Юна"
    try:
        normalize_companion_name("x")
        raise AssertionError("expected bad_name")
    except DelveError as e:
        assert e.code == "bad_name"
    src = getsource(rename_card)
    assert "name_locked" in src
    assert "renamed" in src


def test_apply_outcome_gold_xp_always_zero():
    card = CompanionCard(
        player_id=1,
        name="Мира",
        stance="scout",
        temper="stay",
        flesh=[],
        psyche=[],
        adventure_tags=[],
        relations={},
        look_card={},
    )
    for outcome in (
        {"outcome": "injury", "part": "рука"},
        {"outcome": "trauma", "trauma": "страх"},
        {"outcome": "heal"},
        {"outcome": "bond", "bond": -1},
        {"outcome": "leave_column"},
        {"outcome": "death"},
        {"outcome": "unlock_dismiss"},
    ):
        payload = apply_outcome(card, outcome, [card])
        assert payload["gold_delta"] == 0
        assert payload["xp_delta"] == 0
    assert card.scar_frame is True
    assert (card.look_card or {}).get("silhouette_dirty") is True


def test_digest_keeps_all_severe_then_mundane_and_legend():
    leave = _ev(id=1, severity="leave_column", kind="leave_column", line_ru="ушла")
    death = _ev(id=2, severity="death", kind="death", line_ru="не встаёт")
    maim = _ev(id=3, severity="maim", kind="injury", line_ru="рука")
    legend = _ev(id=4, severity="legend", kind="legend", line_ru="череп")
    mundanes = [
        _ev(id=10 + i, severity="mundane", kind="beat", line_ru=f"быт {i}") for i in range(8)
    ]
    lines = digest_lines([leave, death, maim, legend, *mundanes], seen_at=None)
    kinds = [x["kind"] for x in lines]
    assert "leave_column" in kinds
    assert "death" in kinds
    assert kinds.count("injury") == 1
    assert "legend" in kinds
    assert sum(1 for x in lines if x["severity"] == "mundane") == 3
    assert len(lines) == 3 + 1 + 3  # severe + legend + 3 mundane


def test_digest_does_not_clip_severe_to_three_total():
    severe = [
        _ev(id=i, severity="leave_column", kind="leave_column", line_ru=f"уход {i}")
        for i in range(1, 6)
    ]
    mundanes = [_ev(id=20 + i, line_ru=f"быт {i}") for i in range(5)]
    lines = digest_lines(severe + mundanes, seen_at=None)
    assert sum(1 for x in lines if x["kind"] == "leave_column") == 5
    assert len(lines) == 8


def test_catchup_cap_is_48_beats():
    five_days = 5 * 86400
    due = int(five_days // BEAT_SEC)
    assert due > MAX_CATCHUP
    assert min(due, MAX_CATCHUP) == 48
    assert BEAT_SEC == 7200


def test_chronicle_and_delve_stay_llm_free():
    chronicle = Path("src/waifu_bot/services/chronicle.py").read_text(encoding="utf-8")
    delve = Path("src/waifu_bot/services/delve.py").read_text(encoding="utf-8")
    assert "llm_client" not in chronicle
    assert "post_chat" not in chronicle
    assert "delve_line" not in delve
    assert "llm_client" not in delve


def test_grant_tap_source_has_no_party_mult():
    src = Path("src/waifu_bot/services/delve.py").read_text(encoding="utf-8")
    grant_src = __import__("inspect").getsource(grant_tap)
    assert "party_mult" not in grant_src
    assert "party_mult" not in src
