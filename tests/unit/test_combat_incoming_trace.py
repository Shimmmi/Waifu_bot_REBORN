"""Тесты разбора входящего урона (реторс) и ключа log_media_key."""

from waifu_bot.game.constants import MediaType
from waifu_bot.services.combat_damage_trace import (
    build_incoming_damage_breakdown_ru,
    media_type_to_log_media_key,
)


def test_media_type_to_log_media_key_maps_all_types():
    assert media_type_to_log_media_key(None) == "text"
    assert media_type_to_log_media_key(MediaType.TEXT) == "text"
    assert media_type_to_log_media_key(MediaType.LINK) == "link"
    assert media_type_to_log_media_key(MediaType.STICKER) == "sticker"
    assert media_type_to_log_media_key(MediaType.PHOTO) == "photo"
    assert media_type_to_log_media_key(MediaType.GIF) == "gif"
    assert media_type_to_log_media_key(MediaType.AUDIO) == "audio"
    assert media_type_to_log_media_key(MediaType.VIDEO) == "video"
    assert media_type_to_log_media_key(MediaType.VOICE) == "voice"


def test_incoming_breakdown_no_evade_fixed_numbers():
    steps = build_incoming_damage_breakdown_ru(
        raw_monster_damage=100,
        armor_total=30,
        armor_dr=0.25,
        waifu_level=10,
        total_reduce=0.25,
        damage_after_mitigation=75,
        final_armor_pct=10.0,
        damage_after_final_armor=68,
        secondary_evade_triggered=False,
        full_evade_triggered=False,
        final_damage_taken=68,
    )
    kinds = [s["kind"] for s in steps]
    assert kinds == ["base", "contrib", "mult", "mult", "result"]
    assert steps[0]["value_after"] == 100
    assert steps[1]["source"] == "armor_dr"
    assert steps[2]["source"] == "mitigation_apply"
    assert steps[2]["value_before"] == 100 and steps[2]["value_after"] == 75
    assert steps[3]["label_ru"].startswith("Скрытая финальная броня")
    assert steps[4]["kind"] == "result" and steps[4]["value_after"] == 68


def test_incoming_breakdown_secondary_evade():
    steps = build_incoming_damage_breakdown_ru(
        raw_monster_damage=50,
        armor_total=0,
        armor_dr=0.0,
        waifu_level=20,
        total_reduce=0.0,
        damage_after_mitigation=50,
        final_armor_pct=0.0,
        damage_after_final_armor=50,
        secondary_evade_triggered=True,
        full_evade_triggered=False,
        final_damage_taken=0,
    )
    assert steps[-1]["source"] == "secondary_evade"
    assert steps[-1]["value_after"] == 0


def test_incoming_breakdown_full_evade_only():
    steps = build_incoming_damage_breakdown_ru(
        raw_monster_damage=40,
        armor_total=10,
        armor_dr=0.05,
        waifu_level=15,
        total_reduce=0.05,
        damage_after_mitigation=38,
        final_armor_pct=0.0,
        damage_after_final_armor=38,
        secondary_evade_triggered=False,
        full_evade_triggered=True,
        final_damage_taken=0,
    )
    assert steps[-1]["source"] == "full_evade"
