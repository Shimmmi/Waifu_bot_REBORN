"""Парсинг изображений из ответа OpenRouter image API (наёмницы, портрет ОВ)."""

import unittest

from waifu_bot.services.expedition_events_ai import (
    _extract_openrouter_image_b64_sync,
    _openrouter_image_part_url,
)

# 1×1 PNG, минимальный валидный base64
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestOpenrouterImageExtract(unittest.TestCase):
    def test_openrouter_image_part_url_string_and_dict(self):
        self.assertEqual(_openrouter_image_part_url(""), "")
        self.assertEqual(_openrouter_image_part_url("  https://x/y  "), "https://x/y")
        u = "data:image/png;base64," + _TINY_PNG_B64
        self.assertEqual(_openrouter_image_part_url(u), u)
        self.assertEqual(_openrouter_image_part_url({"url": u}), u)

    def test_extract_sync_images_array_imageurl_string(self):
        """SDK-стиль: imageUrl как строка data:, не вложенный объект."""
        data_url = "data:image/png;base64," + _TINY_PNG_B64
        msg = {
            "role": "assistant",
            "content": "",
            "images": [{"type": "image_url", "imageUrl": data_url}],
        }
        self.assertEqual(_extract_openrouter_image_b64_sync(msg), _TINY_PNG_B64)

    def test_extract_sync_images_array_image_url_nested(self):
        msg = {
            "images": [
                {"image_url": {"url": "data:image/png;base64," + _TINY_PNG_B64}},
            ]
        }
        self.assertEqual(_extract_openrouter_image_b64_sync(msg), _TINY_PNG_B64)

    def test_extract_sync_content_block_imageurl_string(self):
        data_url = "data:image/png;base64," + _TINY_PNG_B64
        msg = {
            "content": [
                {"type": "image_url", "image_url": data_url},
            ]
        }
        self.assertEqual(_extract_openrouter_image_b64_sync(msg), _TINY_PNG_B64)


if __name__ == "__main__":
    unittest.main()
