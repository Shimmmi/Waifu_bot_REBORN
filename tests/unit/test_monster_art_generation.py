"""Monster art prompt building."""

from waifu_bot.services.monster_art_generation import build_monster_anime_prompt


def test_build_monster_anime_prompt_contains_name_stats_anime_bg() -> None:
    p = build_monster_anime_prompt(
        display_name="Гоблин-разведчик",
        family_en="feral beast or predator creature",
        tier=2,
        level=7,
        max_hp=120,
        damage=14,
        is_boss=False,
        is_elite=True,
        affix_names=["Крепкий"],
        template_trait_ru="опасен быстрым ростом урона",
        tags_hint="cave, forest",
    )
    assert "Гоблин-разведчик" in p
    assert "anime" in p.lower()
    assert "#1a1025" in p
    assert "level 7" in p
    assert "120" in p
    assert "14" in p
    assert "Elite" in p
    assert "Крепкий" in p
    assert "3:2" in p
