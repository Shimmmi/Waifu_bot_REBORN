"""Dual portraits for a living card. Failures do not block hire."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.paths import static_game_directory

logger = logging.getLogger(__name__)

SILHOUETTE_PARTS = frozenset({"рука", "нога", "лицо", "глаз"})

_HAIR_EN = {
    "ash": "ash-gray hair",
    "ink": "black hair",
    "wine": "wine-red hair",
    "straw": "straw-blonde hair",
    "copper": "copper-red hair",
}
_EYES_EN = {
    "grey": "grey eyes",
    "amber": "amber eyes",
    "green": "green eyes",
    "dark": "dark brown eyes",
}
_MARK_EN = {
    "brow_scar": "thin scar through the eyebrow",
    "freckles": "light freckles",
    "chipped_fang": "a tiny chipped fang",
    "mole": "a small mole near the lip",
}
_STANCE_EN = {
    "scout": "scout leathers, hood, short blade",
    "shield": "round shield and mail, sturdy stance",
    "guide": "lantern or map, travel cloak",
}

_player_jobs: set[int] = set()


def _anime_rel(player_id: int, card_id: int) -> str:
    return f"game/delve/portraits/{int(player_id)}_card_{int(card_id)}_23.webp"


def _pixel_rel(player_id: int, card_id: int) -> str:
    return f"game/delve/portraits/{int(player_id)}_card_{int(card_id)}_11.webp"


def _dest(rel: str) -> Path:
    game = static_game_directory()
    return game.parent / rel


def _b64_to_webp(b64: str, size: tuple[int, int] | None = None) -> bytes | None:
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None
    try:
        img = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=82, method=4, lossless=False)
    return buf.getvalue()


def _silhouette_note(card: m.CompanionCard) -> str:
    bits = []
    for row in card.flesh or []:
        if isinstance(row, dict) and row.get("part") in SILHOUETTE_PARTS:
            bits.append(str(row["part"]))
    if not bits:
        return ""
    return "silhouette changed: " + ", ".join(bits)


def mark_silhouette_dirty(card: m.CompanionCard, part: str) -> None:
    if part not in SILHOUETTE_PARTS:
        return
    look = dict(card.look_card or {})
    look["silhouette_dirty"] = True
    card.look_card = look


def _needs_art(card: m.CompanionCard) -> bool:
    look = card.look_card or {}
    if look.get("silhouette_dirty"):
        return True
    if not card.portrait_pixel_path:
        return True
    if not card.portrait_anime_path:
        return True
    return False


async def fill_identity(session: AsyncSession, card: m.CompanionCard) -> None:
    """One fast JSON for bio/voice. Does not rewrite a shown name or a frozen bio."""
    from waifu_bot.services.companion_living import patron_name, stamp_look_lineage

    patron = await patron_name(session, int(card.player_id))
    look = stamp_look_lineage(card.look_card or {}, seed=int(card.id or 0), stance=card.stance)
    if patron and look.get("hired_by") != patron:
        look["hired_by"] = patron
    card.look_card = look
    if (card.bio or "").strip() and card.voice:
        return
    fallback_bio = f"Нанялась к {patron}. За столом уже своя."
    try:
        from waifu_bot.services.delve_line import _fast_model
        from waifu_bot.services.llm_client import has_text_llm_configured, post_chat_completions_routerai

        if not has_text_llm_configured():
            if not card.bio:
                card.bio = fallback_bio
            return
        traits = ", ".join(card.traits or [])
        race_ru = look.get("race_ru") or "человек"
        class_ru = look.get("class_ru") or "наёмница"
        prompt = (
            "Ответь строго JSON без markdown: {\"bio\":\"...\",\"voice\":\"...\"}.\n"
            f"Имя уже есть: {card.name}. Не меняй имя.\n"
            f"Раса: {race_ru}. Класс: {class_ru}. Стойка: {card.stance}. Нрав: {card.temper}. Черты: {traits}.\n"
            f"Её наняла {patron} — основная вайфу игрока. Они в одном отряде, знакомы.\n"
            f"Look: hair {look.get('hair')}, eyes {look.get('eyes')}, mark {look.get('mark')}.\n"
            "bio — 2 коротких предложения по-русски, без цифр, перков и редкости. "
            f"Можно коротко задеть, что идёт с {patron}, не «встретила путника».\n"
            f"voice — одно предложение, как она говорит с {patron} (на «ты», не с чужаком)."
        )
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await post_chat_completions_routerai(
                client,
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 180,
                    "temperature": 0.85,
                    "reasoning": {"exclude": True},
                },
                model=_fast_model(),
                caller="tavern living identity",
            )
            if r.status_code != 200:
                return
            data = r.json()
            choices = data.get("choices") or []
            msg = ""
            if choices:
                msg = str((choices[0].get("message") or {}).get("content") or "")
            text = msg.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            if not card.bio and parsed.get("bio"):
                card.bio = str(parsed["bio"])[:800]
            voice = dict(card.voice or {})
            if parsed.get("voice"):
                voice["line"] = str(parsed["voice"])[:240]
            card.voice = voice
    except Exception:
        logger.warning("living identity failed card=%s", getattr(card, "id", None), exc_info=True)
        if not card.bio:
            card.bio = fallback_bio
    await session.flush()


def _look_visual_en(look: dict) -> str:
    bits = [
        _HAIR_EN.get(str(look.get("hair") or ""), "brown hair"),
        _EYES_EN.get(str(look.get("eyes") or ""), "brown eyes"),
        _MARK_EN.get(str(look.get("mark") or ""), ""),
        _STANCE_EN.get(str(look.get("stance") or ""), "adventurer kit"),
    ]
    cloak = look.get("cloak") or ""
    if cloak:
        bits.append(f"cloak accent {cloak}")
    return ", ".join(b for b in bits if b)


async def _generate_pixel_from_identity(
    *,
    name: str,
    stance: str,
    temper: str,
    cloak: str | None,
    look: dict,
    reference_webp: bytes | None,
) -> bytes | None:
    from waifu_bot.services.delve_portraits import CLOAK_HEX, STANCE_PROMPT, TEMPERS, _image_bytes_to_webp96
    from waifu_bot.services.llm_client import IMAGE_MODALITY_ATTEMPTS, get_image_model, has_image_llm_configured, post_chat_completions
    from waifu_bot.services.llm_narrative import _extract_openrouter_image_b64

    if not has_image_llm_configured():
        return None
    stance_en = STANCE_PROMPT.get(stance, STANCE_PROMPT["guide"])
    temper_label = TEMPERS.get(temper, {}).get("label", temper)
    cloak_hex = CLOAK_HEX.get(cloak or "", "#4a4458")
    visual = _look_visual_en(look)
    prompt = (
        "Generate ONE isolated pixel-art character bust, square 1:1 crop, 128x128 game sprite.\n"
        "Style: 16-bit SNES JRPG (Final Fantasy VI / Suikoden), 6-color limited palette, "
        "hard pixels, NO photorealism, NO anime 2:3 portrait, NO rectangular poster, "
        "NO chibi full-body, NO 3D.\n"
        f"Subject: {stance_en}. Name flavor: {name}. Temper (flavor only): {temper_label}.\n"
        f"Same person as the identity reference if attached: {visual}. "
        "Copy face, hair color, eye color, race features (ears, horns, wings, fangs) from the reference.\n"
        "Framing: square bust, head and shoulders filling the frame, 3/4 view, facing slightly left. "
        f"Cloak / scarf accent color {cloak_hex}.\n"
        "Background: flat dark stone #12161c. No text, no UI, no watermark, SFW.\n"
        "Not the main heroine — a supporting companion, smaller presence."
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    if reference_webp:
        b64 = base64.standard_b64encode(reference_webp).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/webp;base64,{b64}"},
            }
        )
    model = get_image_model()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "modalities": list(modalities),
                    "image_config": {"aspect_ratio": "1:1", "image_size": "1K"},
                }
                r = await post_chat_completions(
                    client, body, caller="living pixel portrait", use_image_model=True
                )
                if not r.is_success:
                    logger.warning("living pixel HTTP %s", r.status_code)
                    return None
                data = r.json()
                choices = data.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    continue
                message = choices[0].get("message") or {}
                if not isinstance(message, dict):
                    continue
                b64_out = await _extract_openrouter_image_b64(message, client)
                if not b64_out:
                    continue
                try:
                    raw = base64.standard_b64decode(b64_out, validate=True)
                except Exception:
                    raw = base64.b64decode(b64_out)
                webp = _image_bytes_to_webp96(raw)
                if webp:
                    return webp
    except Exception:
        logger.exception("living pixel from identity failed name=%s", name)
    return None


async def enqueue_dual_portraits(session: AsyncSession, card_id: int) -> None:
    from waifu_bot.services.companion_living import stamp_look_lineage, sync_card_to_delve

    card = await session.get(m.CompanionCard, int(card_id))
    if card is None:
        return
    pid = int(card.player_id)
    dest_px = _dest(_pixel_rel(pid, card.id))
    dest_an = _dest(_anime_rel(pid, card.id))
    dest_px.parent.mkdir(parents=True, exist_ok=True)
    look = stamp_look_lineage(card.look_card or {}, seed=int(card.id or 0), stance=card.stance)
    dirty = bool(look.get("silhouette_dirty"))
    if look != dict(card.look_card or {}):
        card.look_card = look
    note = _silhouette_note(card)
    extra = _look_visual_en(look)
    if note:
        extra = f"{extra}, {note}"
    race_ru = str(look.get("race_ru") or "человек")
    class_ru = str(look.get("class_ru") or "маг")
    made_anime = False
    have_anime = bool(card.portrait_anime_path) and dest_an.is_file() and not dirty
    if not have_anime:
        try:
            from waifu_bot.services.expedition_events_ai import generate_hire_waifu_image

            b64 = await generate_hire_waifu_image(
                race_ru,
                class_ru,
                (card.bio or "")[:400],
                name=card.name,
                extra_visual=extra,
            )
            if b64:
                webp = _b64_to_webp(b64, size=(512, 768))
                if webp:
                    dest_an.write_bytes(webp)
                    card.portrait_anime_path = _anime_rel(pid, card.id)
                    have_anime = True
                    made_anime = True
                    await session.flush()
        except Exception:
            logger.warning("living anime portrait failed card=%s", card.id, exc_info=True)
    have_pixel = bool(card.portrait_pixel_path) and dest_px.is_file() and not dirty
    if have_anime and (not have_pixel or made_anime):
        try:
            ref = dest_an.read_bytes() if dest_an.is_file() else None
            blob = await _generate_pixel_from_identity(
                name=card.name,
                stance=card.stance,
                temper=card.temper,
                cloak=card.cloak_color,
                look=look,
                reference_webp=ref,
            )
            if blob:
                dest_px.write_bytes(blob)
                card.portrait_pixel_path = _pixel_rel(pid, card.id)
                have_pixel = True
        except Exception:
            logger.warning("living pixel portrait failed card=%s", card.id, exc_info=True)
    if dirty and have_anime and have_pixel:
        look["silhouette_dirty"] = False
        card.look_card = look
    if card.slot:
        await sync_card_to_delve(session, card)
    await session.flush()


async def enqueue_pending(session: AsyncSession, player_id: int, *, limit: int = 6) -> dict:
    rows = (
        await session.execute(
            select(m.CompanionCard).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.status == "living",
            )
        )
    ).scalars().all()
    done = 0
    for card in rows:
        if not _needs_art(card) and (card.bio or "").strip():
            continue
        if not (card.bio or "").strip() or not card.voice:
            await fill_identity(session, card)
        if _needs_art(card):
            await enqueue_dual_portraits(session, int(card.id))
        done += 1
        if done >= limit:
            break
    return {"ok": True, "n": done}


async def _run_pending_art(player_id: int) -> None:
    from waifu_bot.db.session import get_session, init_engine

    try:
        init_engine()
        async for session in get_session():
            try:
                await enqueue_pending(session, player_id, limit=6)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("living art job failed player=%s", player_id)
            break
    finally:
        _player_jobs.discard(int(player_id))


def schedule_pending_art(player_id: int) -> dict:
    pid = int(player_id)
    if pid in _player_jobs:
        return {"ok": True, "queued": True}
    _player_jobs.add(pid)
    asyncio.create_task(_run_pending_art(pid), name=f"living-art:{pid}")
    return {"ok": True, "queued": True}
