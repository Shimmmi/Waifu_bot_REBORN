"""Совпадение детализации базового урона сообщения с calculate_message_damage."""

from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import (
    apply_equipment_damage_flats,
    build_message_damage_base_trace_ru,
    calculate_message_damage,
)


def test_base_trace_matches_calculate_message_damage_grid():
    for mt in MediaType:
        for atk in ("melee", "ranged", "magic"):
            for weapon in (None, 7, 22):
                for msg_len in (0, 3, 80, 200):
                    exp = calculate_message_damage(
                        mt,
                        12,
                        11,
                        14,
                        atk,
                        message_length=msg_len,
                        weapon_damage=weapon,
                    )
                    got, steps = build_message_damage_base_trace_ru(
                        mt,
                        12,
                        11,
                        14,
                        atk,
                        msg_len,
                        weapon,
                    )
                    assert got == exp, (mt, atk, weapon, msg_len, got, exp)
                    assert len(steps) >= 2


def test_base_trace_steps_contain_media_and_stat_labels():
    _, steps = build_message_damage_base_trace_ru(
        MediaType.STICKER,
        10,
        10,
        15,
        "melee",
        0,
        15,
    )
    labels = " ".join(s.get("label_ru", "") for s in steps)
    assert "стикер" in labels.lower() or "Стикер" in labels
    assert "ИНТ к медиа" in labels
    assert "СИЛ" not in labels


def test_base_trace_weapon_breakdown_label():
    # Dual-wield components surface as "= {base} ({mh}MH+{oh}OH)".
    _, steps = build_message_damage_base_trace_ru(
        MediaType.TEXT,
        10,
        10,
        10,
        "melee",
        0,
        20,
        weapon_main=15,
        weapon_offhand=5,
    )
    base_label = next(s["label_ru"] for s in steps if s.get("source") == "message_base")
    assert base_label == "База: урон оружия = 20 (15MH+5OH)"


def test_base_trace_weapon_breakdown_mainhand_only():
    _, steps = build_message_damage_base_trace_ru(
        MediaType.TEXT,
        10,
        10,
        10,
        "melee",
        0,
        20,
        weapon_main=20,
        weapon_offhand=0,
    )
    base_label = next(s["label_ru"] for s in steps if s.get("source") == "message_base")
    assert base_label == "База: урон оружия = 20 (20MH)"


def test_text_length_step_when_long():
    _, steps = build_message_damage_base_trace_ru(
        MediaType.TEXT,
        5,
        5,
        10,
        "ranged",
        100,
        None,
    )
    kinds = [s["kind"] for s in steps]
    assert "mult" in kinds
    labels = " ".join(s.get("label_ru", "") for s in steps)
    assert "Длина" in labels or "длина" in labels.lower()


def test_apply_equipment_damage_flats_magic_text():
    base = 50
    got, steps = apply_equipment_damage_flats(
        base,
        attack_type="magic",
        media_type=MediaType.TEXT,
        bonuses={"magic_damage_flat": 8, "damage_flat": 3},
    )
    assert got == base + 8 + 3
    assert len(steps) == 2
    assert all(s["source"] == "affix_attack_damage_flat" for s in steps)
    assert any("магией" in s["label_ru"] for s in steps)


def test_apply_equipment_damage_flats_ranged_text():
    base = 40
    got, steps = apply_equipment_damage_flats(
        base,
        attack_type="ranged",
        media_type=MediaType.TEXT,
        bonuses={"ranged_damage_flat": 12, "magic_damage_flat": 99},
    )
    assert got == base + 12
    assert len(steps) == 1
    assert "дальнем" in steps[0]["label_ru"]


def test_apply_equipment_damage_flats_magic_on_sticker_with_ranged_weapon():
    base = 30
    got, steps = apply_equipment_damage_flats(
        base,
        attack_type="ranged",
        media_type=MediaType.STICKER,
        bonuses={"magic_damage_flat": 15, "ranged_damage_flat": 20},
    )
    assert got == base + 15
    assert len(steps) == 1
    assert "магией" in steps[0]["label_ru"]


def test_apply_equipment_damage_flats_damage_percent():
    base = 100
    got, steps = apply_equipment_damage_flats(
        base,
        attack_type="melee",
        media_type=MediaType.TEXT,
        bonuses={"damage_flat": 10, "damage_percent": 20},
    )
    assert got == int((base + 10) * 1.2)
    assert steps[-1]["kind"] == "mult"
    assert steps[-1]["source"] == "affix_attack_damage_percent"
