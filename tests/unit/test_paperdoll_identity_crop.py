import base64
from io import BytesIO

from PIL import Image

from waifu_bot.services.expedition_events_ai import (
    _crop_portrait_identity_reference_for_paperdoll,
    _is_portrait_image_b64,
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
