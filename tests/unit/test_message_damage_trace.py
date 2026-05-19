"""Совпадение детализации базового урона сообщения с calculate_message_damage."""

from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import build_message_damage_base_trace_ru, calculate_message_damage


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
