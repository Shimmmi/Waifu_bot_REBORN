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
        damage_after_armor=70,
        total_reduce=0.25,
        damage_after_mitigation=53,
        final_armor_pct=10.0,
        damage_after_final_armor=48,
        secondary_evade_triggered=False,
        full_evade_triggered=False,
        final_damage_taken=48,
    )
    kinds = [s["kind"] for s in steps]
    assert kinds == ["base", "add", "mult", "mult", "result"]
    assert steps[0]["value_after"] == 100
    assert steps[1]["value_before"] == 100 and steps[1]["value_after"] == 70
    assert steps[2]["source"] == "mitigation_apply"
    assert steps[2]["value_before"] == 70 and steps[2]["value_after"] == 53
    assert steps[3]["label_ru"].startswith("Скрытая финальная броня")
    assert steps[4]["kind"] == "result" and steps[4]["value_after"] == 48


def test_incoming_breakdown_secondary_evade():
    steps = build_incoming_damage_breakdown_ru(
        raw_monster_damage=50,
        armor_total=0,
        damage_after_armor=50,
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
        damage_after_armor=30,
        total_reduce=0.0,
        damage_after_mitigation=30,
        final_armor_pct=0.0,
        damage_after_final_armor=30,
        secondary_evade_triggered=False,
        full_evade_triggered=True,
        final_damage_taken=0,
    )
    assert steps[-1]["source"] == "full_evade"
