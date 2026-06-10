"""Legendary item display name generation (LLM + validation)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

_NAME_RE = re.compile(r"^[\u0400-\u04FF\u0450-\u045F\s\-]+$")
_NAME_MIN = 3
_NAME_MAX = 48

FORBIDDEN_FRAGMENTS = frozenset(
    {
        "обычный",
        "необычный",
        "редкий",
        "эпический",
        "легендарный",
        "tier",
        "t1",
        "t10",
    }
)

CURATED_SKIP: frozenset[tuple[str, int]] = frozenset(
    {
        ("Экскалибур", 10),
        ("Теневое жало", 10),
        ("Звёздный лук", 10),
        ("Топор бури", 10),
        ("Рунный меч", 9),
        ("Серебряная дуга", 9),
        ("Мистерикл", 9),
        ("Кольцо вечности", 10),
        ("Медальон стражника", 5),
    }
)


def validate_name(name: str) -> str | None:
    n = re.sub(r"\s+", " ", str(name or "").strip())
    if len(n) < _NAME_MIN or len(n) > _NAME_MAX:
        return f"length {len(n)}"
    if not _NAME_RE.match(n):
        return "invalid chars"
    low = n.lower()
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in low:
            return f"forbidden {frag}"
    return None


def build_system_prompt(forbidden_names: list[str]) -> str:
    banned = ", ".join(forbidden_names[:40])
    return (
        "Ты неймер легендарных предметов dark fantasy / Diablo-like на русском. "
        "Имена 1–4 слова, без цифр и латиницы, без юмора. "
        "Имя отражает уникальный бонус и роль предмета (оружие/броня/кольцо). "
        "Не повторяй уже занятые имена. "
        f"Занятые имена (не использовать): {banned or '—'}. "
        'Ответ: JSON {"names": {"<template_id>": "Имя"}} без markdown.'
    )


def build_user_prompt(batch: list[dict[str, Any]]) -> str:
    payload = {
        "items": [
            {
                "template_id": it["template_id"],
                "base_name": it.get("name"),
                "tier": it.get("tier"),
                "item_type": it.get("item_type"),
                "subtype": it.get("subtype"),
                "attack_type": it.get("attack_type"),
                "stat1": it.get("stat1_type"),
                "unique_bonuses": it.get("unique_bonuses"),
            }
            for it in batch
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

_META_KEYS = frozenset({"version", "generated_at", "model", "source", "names"})


def extract_names_map(data: dict) -> dict[str, str]:
    if "names" in data and isinstance(data["names"], dict):
        src = data["names"]
    else:
        src = {k: v for k, v in data.items() if k not in _META_KEYS}
    return {str(k): str(v) for k, v in src.items() if str(v or "").strip()}


def filter_template_id_keys(names: dict[str, str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for tid, name in names.items():
        key = str(tid).strip()
        if not key.isdigit():
            continue
        norm = str(name).strip()
        if norm:
            out[int(key)] = norm
    return out


def parse_names_response(
    raw: str,
    expected_ids: list[int],
    used_names: set[str],
) -> dict[int, str]:
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    data = json.loads(text)
    if "names" in data and isinstance(data["names"], dict):
        names_raw = data["names"]
    else:
        names_raw = data
    out: dict[int, str] = {}
    for tid in expected_ids:
        key = str(tid)
        val = names_raw.get(key) or names_raw.get(tid)
        if not val:
            raise ValueError(f"missing name for {tid}")
        err = validate_name(str(val))
        if err:
            raise ValueError(f"bad name for {tid}: {err}")
        norm = str(val).strip()
        if norm.lower() in {u.lower() for u in used_names}:
            raise ValueError(f"duplicate name for {tid}: {norm}")
        used_names.add(norm)
        out[tid] = norm
    return out


def load_names_out(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return extract_names_map(data)


def save_names_out(path: Path, names: dict[str, str], meta: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"version": 1, "names": names}
    if meta:
        payload.update(meta)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_used_names(names: dict[str, str]) -> set[str]:
    return {str(v).strip() for v in names.values() if str(v or "").strip()}
