"""Аффиксы элит: иммунитет к типам медиа."""

from waifu_bot.game.constants import MediaType
from waifu_bot.game.monster_affix_behavior import media_type_matches_immune


def test_media_immune_audio_includes_voice() -> None:
    assert media_type_matches_immune("audio", MediaType.AUDIO) is True
    assert media_type_matches_immune("audio", MediaType.VOICE) is True
    assert media_type_matches_immune("audio", MediaType.TEXT) is False


def test_media_immune_url_maps_to_link() -> None:
    assert media_type_matches_immune("url", MediaType.LINK) is True
    assert media_type_matches_immune("url", MediaType.TEXT) is False


def test_media_immune_video_photo_sticker() -> None:
    assert media_type_matches_immune("video", MediaType.VIDEO) is True
    assert media_type_matches_immune("photo", MediaType.PHOTO) is True
    assert media_type_matches_immune("sticker", MediaType.STICKER) is True


def test_unknown_param_false() -> None:
    assert media_type_matches_immune("gif", MediaType.GIF) is False
    assert media_type_matches_immune("", MediaType.AUDIO) is False
