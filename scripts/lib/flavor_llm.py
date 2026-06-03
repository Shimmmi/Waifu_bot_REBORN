"""LLM flavor batch parsing and prompt helpers (scripts only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from waifu_bot.game.constants import AI_NARRATIVE_GROTESQUE_HUMOR_RU

FORBIDDEN_FLAVOR_FRAGMENTS: tuple[str, ...] = (
    "скромная вещь для первых дорог",
    "уже не игрушка — проверена на мелких стычках",
    "мастера на базарах узнают подобные",
    "такие носят те, кто перестал считать удачу",
    "в караванах за неё торгуются",
    "редкость для отрядов, что не возвращаются",
    "граница миров тонка",
)

MIN_FLAVOR_LEN = 40
MAX_FLAVOR_LEN = 320


def load_world_blurb(narrative_path: Path) -> str:
    if not narrative_path.is_file():
        return ""
    try:
        data = json.loads(narrative_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts: list[str] = []
    global_block = data.get("global") or {}
    if isinstance(global_block, dict) and global_block.get("summary"):
        parts.append(str(global_block["summary"]).strip())
    regions = data.get("regions") or {}
    if isinstance(regions, dict):
        for key in ("1", "5"):
            reg = regions.get(key)
            if isinstance(reg, dict):
                name = reg.get("name_ru") or ""
                mood = reg.get("mood") or ""
                if name or mood:
                    parts.append(f"{name}: {mood}".strip(": "))
    return " ".join(parts).strip()


def build_system_prompt(world_blurb: str) -> str:
    world = world_blurb or "Империя пала; по миру рассеяно эхо силы у Грани."
    return (
        "Ты — сценарист кодекса предметов RPG Waifu Bot. "
        "Пиши на русском. Тон: тёмное фэнтези, империя и разлом у Грани. "
        f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU} "
        "Для каждого предмета — 1–2 коротких предложения: смешно, образно, уникально под имя и тип. "
        "Не повторяй шаблоны про «скромная вещь для первых дорог», «уже не игрушка» и прочие клише тира. "
        "Не начинай с «—» и не оборачивай имя в кавычки, если это не каламбур. "
        "Без markdown, без списков, без пояснений.\n\n"
        f"Мир: {world}"
    )


def build_user_prompt(batch: list[dict]) -> str:
    payload = [
        {
            "id": it["id"],
            "name": it["name"],
            "item_type": it["item_type"],
            "subtype": it["subtype"],
            "tier": it["tier"],
            "level_min": it.get("level_min"),
            "level_max": it.get("level_max"),
        }
        for it in batch
    ]
    ids = [str(it["id"]) for it in batch]
    return (
        "Сгенерируй художественные описания для библиотеки предметов.\n"
        f"Нужны ровно id: {', '.join(ids)}.\n"
        "Ответь СТРОГО JSON без markdown:\n"
        '{"flavors": {"1": "текст...", "2": "..."}}\n\n'
        f"Предметы: {json.dumps(payload, ensure_ascii=False)}"
    )


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def parse_flavors_response(raw: str, expected_ids: list[int]) -> dict[int, str]:
    """Parse model JSON; raises ValueError on invalid or incomplete batch."""
    text = _strip_json_fence(raw)
    if not text:
        raise ValueError("empty response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e

    flavors_raw: Any = None
    if isinstance(data, dict):
        if "flavors" in data and isinstance(data["flavors"], dict):
            flavors_raw = data["flavors"]
        else:
            flavors_raw = data
    if not isinstance(flavors_raw, dict):
        raise ValueError("missing flavors object")

    out: dict[int, str] = {}
    for eid in expected_ids:
        key = str(eid)
        if key not in flavors_raw:
            raise ValueError(f"missing id {eid}")
        val = str(flavors_raw[key] or "").strip()
        if len(val) < MIN_FLAVOR_LEN:
            raise ValueError(f"id {eid}: too short ({len(val)})")
        if len(val) > MAX_FLAVOR_LEN:
            val = val[: MAX_FLAVOR_LEN - 1].rstrip() + "…"
        low = val.lower()
        if any(frag in low for frag in FORBIDDEN_FLAVOR_FRAGMENTS):
            raise ValueError(f"id {eid}: forbidden template fragment")
        out[eid] = val
    return out


def merge_flavor_maps(base: dict[str, str], batch: dict[int, str]) -> dict[str, str]:
    merged = dict(base)
    for eid, text in batch.items():
        merged[str(eid)] = text
    return merged
