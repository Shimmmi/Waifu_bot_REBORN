"""Regression guards for affix characteristic labels in item modal UI."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "src" / "waifu_bot" / "webapp" / "app.js"


def _app_js_source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_resolve_affix_characteristic_label_helper_exists() -> None:
    src = _app_js_source()
    assert "function resolveAffixCharacteristicLabel(affix)" in src
    assert "const PRIMARY_STAT_KEYS = new Set([" in src


def test_characteristics_renderer_does_not_use_affix_name_as_label() -> None:
    """affix.name is for item title only; stats block must use description/statMeta."""
    src = _app_js_source()
    start = src.index("function renderItemModalV2CharacteristicsHtml")
    end = src.index("function ", start + 1)
    block = src[start:end]
    assert "resolveAffixCharacteristicLabel(a)" in block
    assert "a.name" not in block


def test_bonus_renderers_use_shared_label_resolver() -> None:
    src = _app_js_source()
    assert "resolveAffixCharacteristicLabel(a)" in src
    render_bonuses = src.index("function renderItemBonusesHtml")
    get_text = src.index("function getItemBonusesText")
    bonuses_block = src[render_bonuses:get_text]
    text_block = src[get_text : get_text + 800]
    assert "resolveAffixCharacteristicLabel(a)" in bonuses_block
    assert "resolveAffixCharacteristicLabel(a)" in text_block


def test_primary_stat_uses_short_code_not_long_description() -> None:
    """Charm affix description from backend is 'Бонус к обаянию'; UI should prefer ОБА."""
    src = _app_js_source()
    resolver_start = src.index("function resolveAffixCharacteristicLabel")
    resolver_end = src.index("function formatBonusValue", resolver_start)
    resolver = src[resolver_start:resolver_end]
    assert 'PRIMARY_STAT_KEYS.has(skl)' in resolver
    assert "return m.short" in resolver
    assert "affix?.name" not in resolver
    assert "affix.name" not in resolver


def test_effect_stat_description_ru_tavern_discount() -> None:
    from waifu_bot.game.affix_effect_ui import effect_stat_description_ru

    assert effect_stat_description_ru("tavern_discount_percent") == "Скидка в таверне"
