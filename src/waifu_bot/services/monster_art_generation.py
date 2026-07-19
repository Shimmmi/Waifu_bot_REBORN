"""RouterAI image generation for monster portraits (anime WebP, 3:2)."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Optional

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.dungeon import DungeonRun, DungeonRunMonster, MonsterAffix, MonsterTemplate
from waifu_bot.db.models.story_boss import StoryBossDefinition
from waifu_bot.services.dungeon import _monster_slug_for_webp
from waifu_bot.services.expedition_events_ai import (
    _extract_openrouter_image_b64,
    monster_template_dominant_trait_ru,
)
from waifu_bot.services.llm_client import (
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)

logger = logging.getLogger(__name__)

_MONSTER_BG_HEX = "#1a1025"

_FAMILY_EN: dict[str, str] = {
    "undead": "undead / restless corpse or spirit themes",
    "beast": "feral beast or predator creature",
    "humanoid": "humanoid monster (goblin, bandit, human-like foe)",
    "demon": "demonic infernal creature",
    "elemental": "elemental being (fire, ice, lightning, etc.)",
    "construct": "animated construct, golem, or artificial guardian",
    "slime": "slime, ooze, or gelatinous creature",
    "dragon": "dragon, drake, or reptilian monster",
    "fae": "fae, spirit, or whimsical magical creature",
}


def _family_gloss(family: str) -> str:
    f = (family or "").strip().lower()
    return _FAMILY_EN.get(f, f.replace("_", " ") or "fantasy monster")


def _tags_summary(tags: Any) -> str | None:
    if tags is None:
        return None
    if isinstance(tags, list):
        parts = [str(x).strip() for x in tags if str(x).strip()]
        return ", ".join(parts[:12]) if parts else None
    if isinstance(tags, dict):
        return None
    return str(tags)[:200]


def build_monster_anime_prompt(
    *,
    display_name: str,
    family_en: str,
    tier: int,
    level: int,
    max_hp: int,
    damage: int,
    is_boss: bool,
    is_elite: bool,
    affix_names: list[str],
    template_trait_ru: str,
    tags_hint: str | None,
) -> str:
    tier_clamped = max(1, min(5, int(tier)))
    affix_line = ""
    if affix_names:
        safe = ", ".join(a.replace("\n", " ")[:80] for a in affix_names[:8])
        affix_line = f"\nSpecial modifiers (elite): {safe}."
    boss_line = " Boss encounter — larger, more imposing silhouette, dramatic presence." if is_boss else ""
    elite_line = " Elite enemy — visibly empowered or ornate details." if is_elite and not is_boss else ""
    tags_block = f"\nHabitat / theme tags: {tags_hint}." if tags_hint else ""
    trait_block = (
        f"\nDesign hint (RU, mood only): {template_trait_ru}"
        if template_trait_ru
        else ""
    )
    return (
        "Generate ONE full-body or three-quarter fantasy RPG monster illustration.\n"
        "Art style: Japanese anime / light novel illustration — clean line art, cel shading or soft shading, "
        "expressive silhouette, coherent anatomy for a monster or creature. "
        "Not pixel art, not photorealistic, not 3D render.\n"
        f"Creature name (in-game, keep recognizable vibe): «{display_name.replace(chr(10), ' ')[:120]}».\n"
        f"Monster family / type: {family_en}.\n"
        f"Tier (rough threat band 1–5): {tier_clamped}/5.\n"
        f"Combat stats (for scale and menace only): level {level}, HP ~{max_hp}, attack power ~{damage}."
        f"{affix_line}{boss_line}{elite_line}{tags_block}{trait_block}\n"
        f"Background: flat solid color only, exactly {_MONSTER_BG_HEX} — no gradient, no floor, no scenery, no props.\n"
        "Composition: single creature horizontally centered in a 3:2 landscape frame; "
        "keep the head and primary body mass fully inside the centered 1:1 safe square "
        "(do not place the head near the left/right edges — UI crops to that center square); "
        "full figure readable silhouette; limbs/weapons may extend slightly into side margins if needed.\n"
        "Rules: no text, no letters, no watermark, no UI frame, no health bars, SFW only.\n"
        "Output aspect: landscape 3:2."
    )


def _image_bytes_to_webp(raw: bytes) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(raw))
        if img.mode not in ("RGB", "RGBA", "P"):
            img = img.convert("RGBA")
        elif img.mode == "P":
            img = img.convert("RGBA")
        buf = BytesIO()
        img.save(buf, format="WEBP", quality=88, method=6)
        out = buf.getvalue()
        return out if out else None
    except Exception:
        logger.exception("[MONSTER ART] webp conversion failed")
        return None


async def _fetch_run_monster_context(
    session: AsyncSession,
    player_id: int,
    template_id: int,
) -> dict[str, Any] | None:
    run = (
        await session.execute(
            select(DungeonRun).where(
                DungeonRun.player_id == player_id,
                DungeonRun.status == "active",
            ).limit(1)
        )
    ).scalar_one_or_none()
    if not run:
        return None
    pos = int(run.current_position or 1)
    cur = (
        await session.execute(
            select(DungeonRunMonster).where(
                DungeonRunMonster.run_id == run.id,
                DungeonRunMonster.position == pos,
            )
        )
    ).scalar_one_or_none()
    if not cur or int(cur.template_id or 0) != int(template_id):
        return None
    affix_names: list[str] = []
    raw_ids = cur.applied_affix_ids
    if isinstance(raw_ids, list) and raw_ids:
        try:
            ids = [int(x) for x in raw_ids]
            rows = (
                await session.execute(select(MonsterAffix).where(MonsterAffix.id.in_(ids)))
            ).scalars().all()
            affix_names = [a.name for a in rows]
        except Exception:
            affix_names = []
    return {
        "instance_name": cur.name,
        "level": int(cur.level or 1),
        "max_hp": int(cur.max_hp or 0),
        "damage": int(cur.damage or 0),
        "is_boss": bool(cur.is_boss),
        "is_elite": bool(cur.is_elite),
        "affix_names": affix_names,
    }


def _template_reference_stats(tmpl: MonsterTemplate) -> tuple[int, int, int]:
    lv = max(1, int(tmpl.level_min or 1))
    hp = int(tmpl.hp_base or 0) + int(tmpl.hp_per_level or 0) * max(0, lv - 1)
    dmg = int(tmpl.dmg_base or 0) + int(tmpl.dmg_per_level or 0) * max(0, lv - 1)
    return lv, max(hp, 1), max(dmg, 1)


@dataclass(frozen=True)
class MonsterArtGenerationResult:
    webp_bytes: bytes
    family: str
    slug: str
    relative_path: str


async def generate_monster_art_webp(
    session: AsyncSession,
    template_id: int,
    *,
    admin_player_id: int | None = None,
) -> Optional[MonsterArtGenerationResult]:
    """Call RouterAI image model; returns WEBP bytes and path metadata or None."""
    if not has_image_llm_configured():
        logger.info("[MONSTER ART] Skip: no RouterAI API key")
        return None

    tmpl = await session.get(MonsterTemplate, int(template_id))
    if not tmpl:
        return None

    ctx = None
    if admin_player_id is not None:
        ctx = await _fetch_run_monster_context(session, int(admin_player_id), int(template_id))

    if ctx:
        display_name = (ctx["instance_name"] or tmpl.name or "Monster").strip()
        level = int(ctx["level"])
        max_hp = int(ctx["max_hp"])
        damage = int(ctx["damage"])
        is_boss = bool(ctx["is_boss"])
        is_elite = bool(ctx["is_elite"])
        affix_names = list(ctx["affix_names"])
    else:
        display_name = (tmpl.name or "Monster").strip()
        level, max_hp, damage = _template_reference_stats(tmpl)
        is_boss = bool(tmpl.boss_allowed)
        is_elite = False
        affix_names = []

    family_raw = (tmpl.family or "unknown").strip().lower() or "unknown"
    family_en = _family_gloss(family_raw)
    tier = int(tmpl.tier or 1)
    try:
        trait_ru = monster_template_dominant_trait_ru(tmpl)
    except Exception:
        trait_ru = ""
    tags_hint = _tags_summary(getattr(tmpl, "tags", None))

    prompt = build_monster_anime_prompt(
        display_name=display_name,
        family_en=family_en,
        tier=tier,
        level=level,
        max_hp=max_hp,
        damage=damage,
        is_boss=is_boss,
        is_elite=is_elite,
        affix_names=affix_names,
        template_trait_ru=trait_ru,
        tags_hint=tags_hint,
    )

    slug = _monster_slug_for_webp(tmpl, int(template_id), display_name)
    slug = re.sub(r"[^a-z0-9_]+", "_", slug.lower()).strip("_") or f"m{template_id}"
    if len(slug) > 128:
        slug = slug[:128].rstrip("_")

    model = get_image_model()
    logger.info(
        "[MONSTER ART] model=%s provider=routerai template_id=%s slug=%s family=%s",
        model,
        template_id,
        slug,
        family_raw,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = IMAGE_MODALITY_ATTEMPTS
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "3:2",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="monster art",
                    use_image_model=True,
                )
                if r.status_code == 401:
                    logger.error("[MONSTER ART] LLM %s", r.status_code)
                    return None
                if not r.is_success:
                    logger.error("[MONSTER ART] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[MONSTER ART] no choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    try:
                        raw_png = base64.standard_b64decode(b64_out, validate=True)
                    except Exception:
                        raw_png = base64.b64decode(b64_out)
                    webp = _image_bytes_to_webp(raw_png)
                    if webp:
                        rel = f"monsters/{family_raw}/{slug}.webp"
                        return MonsterArtGenerationResult(
                            webp_bytes=webp,
                            family=family_raw,
                            slug=slug,
                            relative_path=rel,
                        )
                    logger.warning("[MONSTER ART] webp conversion returned empty")
                    return None

            logger.warning(
                "[MONSTER ART] no image in response last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:500],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[MONSTER ART] timeout")
        return None
    except Exception:
        logger.exception("[MONSTER ART] request failed")
        return None


async def _openrouter_generate_webp(prompt: str, *, log_tag: str) -> Optional[bytes]:
    """Shared RouterAI image call → WEBP bytes."""
    if not has_image_llm_configured():
        logger.info("[%s] Skip: no RouterAI API key", log_tag)
        return None

    model = get_image_model()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = IMAGE_MODALITY_ATTEMPTS
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "3:2",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller=log_tag,
                    use_image_model=True,
                )
                if r.status_code == 401:
                    logger.error("[%s] LLM %s", log_tag, r.status_code)
                    return None
                if not r.is_success:
                    logger.error("[%s] HTTP %s %s", log_tag, r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[%s] no choices modalities=%s", log_tag, modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    try:
                        raw_png = base64.standard_b64decode(b64_out, validate=True)
                    except Exception:
                        raw_png = base64.b64decode(b64_out)
                    webp = _image_bytes_to_webp(raw_png)
                    if webp:
                        return webp
                    logger.warning("[%s] webp conversion returned empty", log_tag)
                    return None

            logger.warning(
                "[%s] no image in response last_message=%s",
                log_tag,
                json.dumps(last_message, ensure_ascii=False)[:500],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[%s] timeout", log_tag)
        return None
    except Exception:
        logger.exception("[%s] request failed", log_tag)
        return None


async def generate_story_boss_art_webp(
    session: AsyncSession,
    story_boss_definition_id: int,
) -> Optional[MonsterArtGenerationResult]:
    """Generate anime portrait for a story boss; save path bosses/webp/{slug}.webp."""
    sbd = await session.get(StoryBossDefinition, int(story_boss_definition_id))
    if not sbd:
        return None

    tmpl = await session.get(MonsterTemplate, int(sbd.monster_template_id))
    display_name = (sbd.name or "Story Boss").strip()
    lore = (sbd.short_lore or "").strip()
    if tmpl:
        level, max_hp, damage = _template_reference_stats(tmpl)
        family_raw = (tmpl.family or "unknown").strip().lower() or "unknown"
        tier = int(tmpl.tier or 5)
        try:
            trait_ru = monster_template_dominant_trait_ru(tmpl)
        except Exception:
            trait_ru = ""
        tags_hint = _tags_summary(getattr(tmpl, "tags", None))
    else:
        level, max_hp, damage = 50, 5000, 200
        family_raw = "unknown"
        tier = 5
        trait_ru = ""
        tags_hint = None

    lore_block = lore or trait_ru
    family_en = _family_gloss(family_raw)
    prompt = build_monster_anime_prompt(
        display_name=display_name,
        family_en=family_en,
        tier=tier,
        level=level,
        max_hp=max_hp,
        damage=damage,
        is_boss=True,
        is_elite=False,
        affix_names=[],
        template_trait_ru=lore_block,
        tags_hint=tags_hint,
    )

    slug = re.sub(r"[^a-z0-9_]+", "_", (sbd.slug or f"story_boss_{sbd.id}").lower()).strip("_")
    if len(slug) > 128:
        slug = slug[:128].rstrip("_")

    logger.info("[STORY BOSS ART] story_boss_definition_id=%s slug=%s", story_boss_definition_id, slug)
    webp = await _openrouter_generate_webp(prompt, log_tag="STORY BOSS ART")
    if not webp:
        return None

    rel = f"bosses/webp/{slug}.webp"
    return MonsterArtGenerationResult(
        webp_bytes=webp,
        family=family_raw,
        slug=slug,
        relative_path=rel,
    )
