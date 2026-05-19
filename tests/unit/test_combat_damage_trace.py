"""Регрессия: DamageTrace и сводка урона (services/combat_damage_trace.py)."""

from waifu_bot.services.combat_damage_trace import DamageTrace, build_damage_summary_ru


def test_damage_trace_mult_and_add() -> None:
    t = DamageTrace()
    t.base("x", "База", 100)
    t.mult("m", "×1.5", 100, 150, factor=1.5)
    t.add("a", "+10", 150, 160, delta=10)
    steps = t.as_list()
    assert len(steps) == 3
    assert steps[0]["kind"] == "base"
    assert steps[0]["value_after"] == 100
    assert steps[1]["value_after"] == 150
    assert steps[2]["value_after"] == 160


def test_build_damage_summary_ru() -> None:
    s = build_damage_summary_ru(damage=42, is_crit=True, monster_dodged=False, monster_name="Гуль")
    assert "42" in s and "Гуль" in s and "крит" in s
    s2 = build_damage_summary_ru(damage=0, is_crit=False, monster_dodged=True, monster_name="Босс")
    assert "уклон" in s2.lower()
    s3 = build_damage_summary_ru(
        damage=0,
        is_crit=False,
        monster_dodged=False,
        monster_media_immune=True,
        monster_name="Хранитель",
    )
    assert "иммунитет" in s3.lower()
