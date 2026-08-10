"""Admin hired-waifu portrait regenerate API."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.api import admin_routes as ar


def test_admin_generate_hired_waifu_art_success() -> None:
    async def _run() -> None:
        session = AsyncMock()
        waifu = MagicMock()
        waifu.id = 406
        waifu.name = "Зубодробилка"
        waifu.bio = "bio"
        waifu.perks = ["strong_spirit"]
        waifu.race = 7
        waifu.class_ = 6
        waifu.level = 11
        session.get = AsyncMock(return_value=waifu)

        with (
            patch(
                "waifu_bot.services.llm_client.has_image_llm_configured",
                return_value=True,
            ),
            patch(
                "waifu_bot.services.expedition_events_ai.generate_hire_waifu_image",
                new_callable=AsyncMock,
                return_value="YmFzZTY0",
            ) as gen,
            patch.object(
                ar.tavern_service,
                "_waifu_bio_inputs",
                return_value=("Зубодробилка", "фея", "целительница", 11, ["Дух"]),
            ),
        ):
            resp = await ar.admin_generate_hired_waifu_art(
                waifu_id=406, _admin=1, session=session
            )

        gen.assert_awaited_once()
        assert resp["success"] is True
        assert resp["waifu_id"] == 406
        assert "/api/tavern/hired-waifus/406/portrait" in resp["image_url"]
        assert waifu.image_data == "YmFzZTY0"
        assert waifu.image_mime == "image/webp"
        assert waifu.image_generated_at is not None
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_admin_generate_hired_waifu_art_not_found() -> None:
    from fastapi import HTTPException

    async def _run() -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        try:
            await ar.admin_generate_hired_waifu_art(waifu_id=999, _admin=1, session=session)
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == "waifu_not_found"

    asyncio.run(_run())


def test_admin_generate_hired_waifu_art_generation_failed() -> None:
    from fastapi import HTTPException

    async def _run() -> None:
        session = AsyncMock()
        waifu = MagicMock()
        waifu.id = 1
        waifu.name = "X"
        waifu.bio = ""
        waifu.perks = []
        session.get = AsyncMock(return_value=waifu)

        with (
            patch(
                "waifu_bot.services.llm_client.has_image_llm_configured",
                return_value=True,
            ),
            patch(
                "waifu_bot.services.expedition_events_ai.generate_hire_waifu_image",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ar.tavern_service,
                "_waifu_bio_inputs",
                return_value=("X", "человек", "маг", 1, []),
            ),
        ):
            try:
                await ar.admin_generate_hired_waifu_art(waifu_id=1, _admin=1, session=session)
                raise AssertionError("expected 503")
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == "hired_waifu_art_generation_failed"

    asyncio.run(_run())
