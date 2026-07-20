import base64
from io import BytesIO

from PIL import Image

from waifu_bot.services.expedition_events_ai import (
    _PAPERDOLL_IDENTITY_IMAGE_CAPTION,
    _build_main_waifu_paperdoll_prompt,
    _crop_portrait_identity_reference_for_paperdoll,
    _is_portrait_image_b64,
    _paperdoll_race_constraint_en,
)


def _png_b64(width: int, height: int) -> str:
    img = Image.new("RGB", (width, height), color=(120, 80, 160))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_identity_crop_produces_portrait_orientation():
    raw_b64 = _png_b64(848, 1264)
    result = _crop_portrait_identity_reference_for_paperdoll(raw_b64)
    assert result is not None
    cropped_b64, mime = result
    assert mime == "image/png"

    raw = base64.b64decode(cropped_b64)
    img = Image.open(BytesIO(raw))
    w, h = img.size
    assert h > w
    assert abs((w / h) - 0.75) < 0.02
    assert h == 480
    assert w == 360


def test_is_portrait_image_b64():
    portrait_b64 = _png_b64(360, 480)
    landscape_b64 = _png_b64(1376, 768)

    assert _is_portrait_image_b64(portrait_b64) is True
    assert _is_portrait_image_b64(landscape_b64) is False
    assert _is_portrait_image_b64("") is False
    assert _is_portrait_image_b64("not-valid-base64") is False


def test_paperdoll_prompt_rejects_heterochromia_and_unconditional_horns():
    prompt = _build_main_waifu_paperdoll_prompt(
        race_id=4,
        class_id=1,
        pose_en="standing facing viewer, arms relaxed at sides",
        identity_cropped=True,
    )
    assert "including heterochromia" not in prompt.lower()
    assert "do not invent heterochromia" in prompt.lower()
    assert "previous full-body paperdoll" in prompt.lower()
    assert "copy face, hair, horns" not in prompt.lower()
    assert "skin tone, horns, ears" not in prompt.lower()
    assert "no demon horns" in prompt.lower()
    assert "Copy face, hair, horns, ears, eye colors" not in _PAPERDOLL_IDENTITY_IMAGE_CAPTION
    assert "only racial features visible" in _PAPERDOLL_IDENTITY_IMAGE_CAPTION.lower()


def test_paperdoll_race_constraint_angel_vs_default():
    assert "no demon horns" in _paperdoll_race_constraint_en(4).lower()
    assert "invent horns" in _paperdoll_race_constraint_en(1).lower()
    # Demon keeps horns via race flavor; constraint must not forbid them.
    assert "no demon horns" not in _paperdoll_race_constraint_en(6).lower()
