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
    assert "can_dismiss" in hall_js
    assert "Завтра" in hall_js
    assert "loyalty-tick" in hall_js
    assert "living-bio-btn" in hall_js
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
    assert "_rewrite_delve_flavor_name" in src


def test_enforce_squad_names_replaces_pool_and_keeps_living():
    from waifu_bot.game.delve_catalog import enforce_squad_names, replace_companion_name
    from waifu_bot.services.delve import overlay_flavor_phrase
    from waifu_bot.services.delve_line import _sanitize_line, flavor_cache_key

    assert enforce_squad_names("Милана рубит споры.", ["Васянка"]) == "Васянка рубит споры."
    assert enforce_squad_names("Васянка идёт дальше.", ["Васянка"]) == "Васянка идёт дальше."
    assert replace_companion_name("Юна считает шаги.", "Юна", "Данилка") == "Данилка считает шаги."
    assert enforce_squad_names("Юна считает шаги.", ["Данилка"]) == "Данилка считает шаги."
    two = enforce_squad_names("Милана кивает Эльза.", ["Васянка", "Сера"])
    assert two == "Васянка кивает Сера."
    kept = enforce_squad_names("Данилка трогает метку в Пепел.", ["Данилка"])
    assert kept == "Данилка трогает метку в Пепел."
    sanitized = _sanitize_line(' "Милана молчит и идёт." ', names=["Васянка"], face="Васянка")
    assert sanitized == "Васянка молчит и идёт."
    key_a = flavor_cache_key(d=4, node="TRAVERSE", palette_id="wet", names=["Васянка"])
    key_b = flavor_cache_key(d=4, node="TRAVERSE", palette_id="wet", names=["Данилка"])
    assert key_a != key_b
    assert flavor_cache_key(d=4, node="TRAVERSE", palette_id="wet", names=["Васянка"]) == key_a
    state = SimpleNamespace(flavor_text="Милана знает камень.")
    frame = {"phrase": "шаблон"}
    overlay_flavor_phrase(state, frame, [SimpleNamespace(name="Васянка")])
    assert frame["phrase"] == "Васянка знает камень."
    assert state.flavor_text == "Васянка знает камень."


def test_spiced_line_picks_up_rename():
    spiced = SimpleNamespace(
        line_ru="Юна трогает метку в Пепел.",
        template_id="landmark_touch",
        depth=50,
        payload={"spiced": True, "who": "Юна"},
    )
    assert refresh_event_line(spiced, who="Данилка") == "Данилка трогает метку в Пепел."


def test_companion_name_pool_is_wide():
    from waifu_bot.game.delve_catalog import COMPANION_NAME_POOL, pick_companion_name
    from waifu_bot.services.companion_living import _spawn_rain
    from inspect import getsource

    assert len(COMPANION_NAME_POOL) >= 80
    assert len(set(COMPANION_NAME_POOL)) == len(COMPANION_NAME_POOL)
    names = {pick_companion_name(305174198, 1, salt=i) for i in range(60)}
    assert len(names) >= 20
    src = getsource(_spawn_rain)
    assert "salt=" in src


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
    assert "loyalty_mult" in grant_src
    from waifu_bot.services.delve import loyalty_faucet_mult

    assert loyalty_faucet_mult([]) == 1.0
    assert loyalty_faucet_mult([50, 50, 50]) == 1.0
    assert abs(loyalty_faucet_mult([100]) - 1.15) < 1e-9
    assert abs(loyalty_faucet_mult([100, 100, 100]) - 1.35) < 1e-9
    assert loyalty_faucet_mult([0, 0, 0]) == 1.0
    assert loyalty_faucet_mult([100, 100, 100, 100]) <= 1.40


def test_class_to_stance_and_spawn_dedupes_class():
    from inspect import getsource

    from waifu_bot.services.companion_living import CLASS_NAMES_RU, CLASS_TO_STANCE, _spawn_rain, look_card_for

    assert set(CLASS_TO_STANCE) == set(CLASS_NAMES_RU)
    assert CLASS_TO_STANCE[1] == CLASS_TO_STANCE[2] == "shield"
    assert CLASS_TO_STANCE[3] == CLASS_TO_STANCE[5] == "scout"
    assert CLASS_TO_STANCE[4] == "guide"
    src = getsource(_spawn_rain)
    assert "used_c" in src
    assert "CLASS_TO_STANCE" in src
    look = look_card_for(name="Мира", stance="scout", cloak="ash", traits=["тихая"], seed=1, class_id=3, race_id=2)
    assert look["class_id"] == 3
    assert look["loyalty"] == 50


def test_dismiss_cap_and_loyalty_leave_are_separate():
    from inspect import getsource

    from waifu_bot.services.companion_living import dismiss_card, leave_loyalty

    dismiss_src = getsource(dismiss_card)
    leave_src = getsource(leave_loyalty)
    assert "dismiss_day_cap" in dismiss_src
    assert 'template_id="dismiss"' in dismiss_src
    assert "was_living" in dismiss_src
    assert "start_mourning" not in leave_src
    assert "loyalty_leave" in leave_src
    assert "leave_column" in leave_src
    assert "dismiss_day_cap" not in leave_src
    living = Path("src/waifu_bot/services/companion_living.py").read_text(encoding="utf-8")
    assert "dismiss_left" in living
    assert "is_admin" in living
    hall = Path("src/waifu_bot/webapp/pages/tavern_hall.js").read_text(encoding="utf-8")
    assert "isAdminUiEnabled" not in hall


def test_bio_prompt_long_and_not_grotesque():
    from inspect import getsource

    from waifu_bot.game.constants import AI_NARRATIVE_GROTESQUE_HUMOR_RU
    from waifu_bot.services.companion_art import fill_identity
    from waifu_bot.services.expedition_events_ai import generate_hire_waifu_image

    src = getsource(fill_identity)
    assert AI_NARRATIVE_GROTESQUE_HUMOR_RU not in src
    assert "5–8" in src or "5-8" in src
    assert "max_tokens" in src
    assert "grotesk" in src.lower() or "гротеск" in src
    art = Path("src/waifu_bot/services/companion_art.py").read_text(encoding="utf-8")
    assert 'tone="living"' in art
    hire = getsource(generate_hire_waifu_image)
    assert "tone" in hire
    assert "absurd comedy" in hire
    assert "no comedy" in hire


def test_strip_stage_directions_keeps_emphasis():
    from waifu_bot.services.companion_chat import strip_stage_directions

    assert strip_stage_directions("*поправила щит* Сижу.") == "Сижу."
    assert strip_stage_directions("Это *важно* знать.") == "Это *важно* знать."
    assert "поправила" not in strip_stage_directions("*поправила щит*\nНу. Говори.")
    chat = Path("src/waifu_bot/services/companion_chat.py").read_text(encoding="utf-8")
    assert "msk_today" in chat
    assert "loyalty_tick_msk" in chat
    assert "Био: {card.bio or ''}" in chat


def test_catch_up_midday_cap_and_card_gold():
    from datetime import datetime, timezone

    from waifu_bot.game.delve_catalog import gold_rate_per_sec, split_weighted
    from waifu_bot.services.delve import attribute_party_grant, catch_up_midday_cap_increase

    last = datetime(2026, 1, 1, 17, 0, tzinfo=timezone.utc)  # 20:00 MSK
    minted, today = catch_up_midday_cap_increase(
        0,
        275,
        last=last,
        now=last,
        cap=330,
        rate=gold_rate_per_sec(330),
        granted_before=250,
    )
    assert minted == 25
    assert today == 275
    zero, _ = catch_up_midday_cap_increase(
        10, 10, last=last, now=last, cap=330, rate=gold_rate_per_sec(330), granted_before=0
    )
    assert zero == 10
    parts = split_weighted(10, [50, 50, 100])
    assert sum(parts) == 10
    delve_rows = [
        SimpleNamespace(slot=1, gold_earned=0, xp_earned=0),
        SimpleNamespace(slot=2, gold_earned=0, xp_earned=0),
        SimpleNamespace(slot=3, gold_earned=0, xp_earned=0),
    ]
    cards = [
        SimpleNamespace(slot=1, look_card={"loyalty": 50}, gold_earned=0, xp_earned=0),
        SimpleNamespace(slot=2, look_card={"loyalty": 50}, gold_earned=0, xp_earned=0),
        SimpleNamespace(slot=3, look_card={"loyalty": 100}, gold_earned=0, xp_earned=0),
    ]
    attribute_party_grant(delve_rows, 9, 9, cards=cards)
    assert sum(r.gold_earned for r in delve_rows) == 9
    assert sum(c.gold_earned for c in cards) == 9
    assert cards[2].gold_earned >= cards[0].gold_earned


def test_modal_css_and_cache_v108():
    css = Path("src/waifu_bot/webapp/pages/tavern-living.css").read_text(encoding="utf-8")
    html = Path("src/waifu_bot/webapp/tavern.html").read_text(encoding="utf-8")
    hall = Path("src/waifu_bot/webapp/pages/tavern_hall.js").read_text(encoding="utf-8")
    assert "max-height: 92vh" in css
    assert "132px" in css
    assert "v110" in hall
    assert "waifu-webapp-v110" in html
    docs = Path("docs/TAVERN_LIVING_COMPANIONS.md").read_text(encoding="utf-8")
    assert "1 раз в сутки" in docs
    assert "Без замка по суткам" not in docs


def test_loyalty_hearts_on_hall():
    from waifu_bot.services.companion_living import loyalty_heart_key, loyalty_heart_url

    assert loyalty_heart_key(0) == loyalty_heart_key(5) == "broken"
    assert loyalty_heart_key(6) == loyalty_heart_key(30) == "dim"
    assert loyalty_heart_key(31) == loyalty_heart_key(69) == "pink"
    assert loyalty_heart_key(70) == loyalty_heart_key(99) == "red"
    assert loyalty_heart_key(100) == "gold"
    root = Path("static/game/delve/portraits")
    for key in ("broken", "dim", "pink", "red", "gold"):
        path = root / f"loyalty_heart_{key}.webp"
        assert path.is_file() and path.stat().st_size > 80
        assert loyalty_heart_url({"broken": 0, "dim": 6, "pink": 50, "red": 80, "gold": 100}[key]).endswith(
            f"loyalty_heart_{key}.webp"
        )
    hall = Path("src/waifu_bot/webapp/pages/tavern_hall.js").read_text(encoding="utf-8")
    assert "living-hood-row" in hall
    assert "loyaltyHeart" in hall
    css = Path("src/waifu_bot/webapp/pages/tavern-living.css").read_text(encoding="utf-8")
    assert "living-loyalty" in css

