"""Tagged memory shelves on a living companion card. O(1) lookup, tiny LLM context."""

from __future__ import annotations

from typing import Any, Iterable

SHELVES = ("origin", "people", "prefs", "notes")
LEARNED_SHELVES = frozenset({"people", "prefs", "notes"})
MAX_KEYS = 12
MAX_KEY = 24
MAX_VAL = 80


def _blank() -> dict[str, Any]:
    return {"v": 1, "origin": {"moments": {}}, "people": {}, "prefs": {}, "notes": {}}


def _key(raw: Any) -> str:
    text = "".join(ch if str(ch).isalnum() or ch in "_-" else "_" for ch in str(raw or "").strip())
    return text.strip("_")[:MAX_KEY]


def _val(raw: Any) -> str:
    return str(raw or "").strip()[:MAX_VAL]


def memory_of(card: Any) -> dict[str, Any]:
    raw = card.memory if isinstance(getattr(card, "memory", None), dict) else {}
    out = _blank()
    try:
        out["v"] = int(raw.get("v") or 1)
    except (TypeError, ValueError):
        out["v"] = 1
    origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
    moments = origin.get("moments") if isinstance(origin.get("moments"), dict) else {}
    out["origin"]["moments"] = {_key(k): _val(v) for k, v in moments.items() if _key(k) and _val(v)}
    for tag in ("people", "prefs", "notes"):
        src = raw.get(tag) if isinstance(raw.get(tag), dict) else {}
        out[tag] = {_key(k): _val(v) for k, v in src.items() if _key(k) and _val(v)}
    return out


def _shelf(mem: dict[str, Any], tag: str) -> dict[str, str]:
    if tag == "origin":
        moments = mem.setdefault("origin", {}).setdefault("moments", {})
        if not isinstance(moments, dict):
            mem["origin"]["moments"] = {}
            return mem["origin"]["moments"]
        return moments
    slot = mem.setdefault(tag, {})
    if not isinstance(slot, dict):
        mem[tag] = {}
        return mem[tag]
    return slot


def memory_get(card: Any, tag: str, key: str | None = None) -> Any:
    mem = memory_of(card)
    shelf = dict(_shelf(mem, tag))
    if key is None:
        return shelf
    return shelf.get(_key(key))


def memory_put(card: Any, tag: str, key: str, value: str, *, overwrite: bool = True) -> None:
    if tag not in SHELVES:
        return
    k = _key(key)
    v = _val(value)
    if not k or not v:
        return
    mem = memory_of(card)
    shelf = _shelf(mem, tag)
    if not overwrite and k in shelf:
        return
    if k not in shelf and len(shelf) >= MAX_KEYS:
        first = next(iter(shelf), None)
        if first is not None:
            shelf.pop(first, None)
    shelf[k] = v
    card.memory = mem


def memory_seed_party(card: Any, patron: str, party: Iterable[Any]) -> None:
    name = str(patron or "").strip()
    if name:
        memory_put(card, "people", "patron", name, overwrite=False)
    for mate in party or []:
        mid = getattr(mate, "id", None)
        mname = str(getattr(mate, "name", "") or "").strip()
        if mid is None or not mname:
            continue
        if int(getattr(card, "id", 0) or 0) and int(mid) == int(card.id):
            continue
        memory_put(card, "people", str(int(mid)), mname, overwrite=False)


def memory_apply_facts(card: Any, facts: list[dict[str, Any]] | None) -> None:
    for row in facts or []:
        if not isinstance(row, dict):
            continue
        tag = str(row.get("tag") or "").strip()
        if tag not in LEARNED_SHELVES:
            continue
        memory_put(card, tag, str(row.get("key") or ""), str(row.get("value") or ""), overwrite=True)


def memory_prompt(card: Any, tags: tuple[str, ...] = ("people", "prefs", "origin")) -> str:
    parts: list[str] = []
    for tag in tags:
        shelf = memory_get(card, tag)
        if not shelf:
            continue
        bits = [f"{k}={v}" for k, v in list(shelf.items())[:MAX_KEYS]]
        parts.append(f"{tag}: " + "; ".join(bits))
    if not parts:
        return ""
    return "Карточка:\n" + "\n".join(parts)
