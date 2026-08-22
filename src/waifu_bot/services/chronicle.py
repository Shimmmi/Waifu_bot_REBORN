"""Column chronicle: table-driven beats. GET /delve/sync stays LLM-free."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_catalog import (
    NODE_BOSS,
    NODE_BRANCH,
    NODE_LANDMARK,
    NODE_REST,
    NODE_SHOP,
    NODE_SURFACE,
    shaft_art_for_depth,
    spine_type,
    sawtooth,
)

BEAT_SEC = 7200
MAX_CATCHUP = 48
SPECIAL_NODES = frozenset({NODE_BOSS, NODE_BRANCH, NODE_LANDMARK, NODE_REST, NODE_SHOP, NODE_SURFACE})
SEVERE = frozenset({"death", "leave_column", "maim", "psyche", "crime", "bond_break"})
CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "delve_events.v1.json"
# First 16 of sha256(data/delve_events.v1.json). Bump when the pack changes.
CATALOG_SHA256_PREFIX = "9d4dc79e4fcdd580"
MOURNING = timedelta(days=3)
SILHOUETTE_PARTS = frozenset({"рука", "нога", "лицо", "глаз"})

_CATALOG: dict[str, Any] | None = None
_CATALOG_HASH = ""


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def load_catalog() -> dict[str, Any]:
    global _CATALOG, _CATALOG_HASH
    if _CATALOG is None:
        raw = CATALOG_PATH.read_bytes()
        _CATALOG_HASH = hashlib.sha256(raw).hexdigest()[:16]
        _CATALOG = json.loads(raw.decode("utf-8"))
    return _CATALOG


def catalog_hash() -> str:
    load_catalog()
    return _CATALOG_HASH


def assert_catalog_pin() -> None:
    if catalog_hash() != CATALOG_SHA256_PREFIX:
        raise RuntimeError(
            f"delve_events.v1.json hash {catalog_hash()} != pin {CATALOG_SHA256_PREFIX}"
        )


def _templates() -> list[dict[str, Any]]:
    return list(load_catalog().get("templates") or [])


def _rng(spine_seed: int, beat_index: int, extra: str = "") -> random.Random:
    digest = hashlib.sha256(f"chronicle:{spine_seed}:{beat_index}:{extra}".encode()).hexdigest()[:16]
    return random.Random(int(digest, 16))


def assemble_line(
    *,
    who: str,
    place: str = "",
    wound: str = "",
    bond: str = "",
    tpl: dict[str, Any] | None = None,
    verb: str = "",
    other: str = "",
    biome: str = "",
) -> str:
    tpl = tpl or {}
    pattern = str(tpl.get("line") or "")
    if not pattern:
        v = str(tpl.get("verb") or verb or "идёт")
        loc = place or biome
        pattern = f"{{who}} {v} {loc}." if loc else f"{{who}} {v}."
    text = (
        pattern.replace("{who}", who)
        .replace("{place}", place or biome)
        .replace("{other}", other or "спутница")
        .replace("{verb}", str(tpl.get("verb") or verb or "идёт"))
    )
    text = " ".join(text.split())
    if text and text[-1] not in ".!?":
        text += "."
    bits = [text]
    if wound:
        bits.append(wound if str(wound).endswith(".") else f"{wound}.")
    if bond:
        bits.append(bond if str(bond).endswith(".") else f"{bond}.")
    return " ".join(bits)[:280]


BIOME_LOCK_TAGS = {
    "вода": "wet",
    "грибы": "mushrooms",
    "лёд": "ice",
    "пепел": "ash",
    "кости": "bone",
    "бездна": "abyss",
}


def _biome_ok(tpl: dict[str, Any], biome_id: str) -> bool:
    tags = [str(t) for t in (tpl.get("tags") or [])]
    locked = {BIOME_LOCK_TAGS[t] for t in tags if t in BIOME_LOCK_TAGS}
    if not locked:
        return True
    return biome_id in locked


def template_by_id(tid: str) -> dict[str, Any] | None:
    for tpl in _templates():
        if str(tpl.get("id")) == str(tid):
            return tpl
    return None


def bond_sentence(*, delta: int, other: str, tpl: dict[str, Any]) -> str:
    name = (other or "").strip()
    if not name:
        return ""
    if delta > 0 and "{other}" in str(tpl.get("line") or ""):
        return ""
    if delta < 0:
        return f"{name} не смотрит."
    return ""


def refresh_event_line(event: m.CompanionEvent, *, who: str, other: str = "") -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    if payload.get("spiced"):
        from waifu_bot.game.delve_catalog import enforce_squad_names, replace_companion_name

        text = event.line_ru or ""
        old_who = str(payload.get("who") or "").strip()
        if who and old_who and old_who != who:
            text = replace_companion_name(text, old_who, who)
        names = [n for n in (who, other) if n]
        return enforce_squad_names(text, names, face=who or None)
    tpl = template_by_id(str(event.template_id or ""))
    if tpl is None:
        return event.line_ru
    art = shaft_art_for_depth(int(event.depth or 0))
    place = str(art.get("place_ru") or "")
    wound = ""
    if payload.get("injury"):
        wound = f"Бережёт {payload['injury']}."
    other_name = str(payload.get("other_name") or other or "")
    bond = ""
    if payload.get("bond") is not None:
        delta = int(payload.get("bond_delta") or 0)
        if not delta and isinstance(payload.get("bond"), dict):
            vals = list(payload["bond"].values())
            delta = int(vals[0]) if vals else 0
        bond = bond_sentence(delta=delta, other=other_name, tpl=tpl)
    return assemble_line(who=who or "Она", place=place, wound=wound, bond=bond, tpl=tpl, other=other_name)


def serve_line(event: m.CompanionEvent, *, who: str, other: str = "") -> str:
    fresh = refresh_event_line(event, who=who, other=other)
    payload = event.payload if isinstance(event.payload, dict) else {}
    if fresh != event.line_ru:
        event.line_ru = fresh
    if who and payload.get("spiced") and payload.get("who") != who:
        payload = dict(payload)
        payload["who"] = who
        event.payload = payload
    return fresh


def _card_tags(card: m.CompanionCard) -> set[str]:
    out = set()
    for t in card.traits or []:
        out.add(str(t))
    for t in card.adventure_tags or []:
        out.add(str(t))
    for row in card.psyche or []:
        if isinstance(row, dict) and row.get("facet"):
            out.add(str(row["facet"]))
    return out


def _has_arm(card: m.CompanionCard) -> bool:
    for row in card.flesh or []:
        if isinstance(row, dict) and row.get("part") == "рука" and row.get("permanent"):
            return False
    return True


def _has_wound(card: m.CompanionCard) -> bool:
    return bool(card.flesh) or bool(card.psyche)


def _eligible(tpl: dict[str, Any], cards: list[m.CompanionCard], node: str) -> list[m.CompanionCard]:
    living = [c for c in cards if c.status == "living" and c.slot]
    if len(living) < int(tpl.get("min_living") or 1):
        return []
    when = str(tpl.get("when") or "any")
    if when not in ("any", node):
        return []
    need = tpl.get("need_tag")
    out: list[m.CompanionCard] = []
    for c in living:
        if tpl.get("need_arm") and not _has_arm(c):
            continue
        if tpl.get("need_wound") and not _has_wound(c):
            continue
        if need and need not in _card_tags(c):
            continue
        out.append(c)
    return out


def pick_template(
    *,
    rng: random.Random,
    node: str,
    cards: list[m.CompanionCard],
    biome_id: str = "",
) -> tuple[dict[str, Any], m.CompanionCard | None]:
    scored: list[tuple[float, dict[str, Any], list[m.CompanionCard]]] = []
    for tpl in _templates():
        if biome_id and not _biome_ok(tpl, biome_id):
            continue
        actors = _eligible(tpl, cards, node)
        if not actors:
            continue
        w = float(tpl.get("weight") or 1)
        if str(tpl.get("when")) == node:
            w *= 1.4
        prefer_t = tpl.get("prefer_temper")
        if prefer_t and any(a.temper == prefer_t for a in actors):
            w *= 1.25
        outcome = str(tpl.get("outcome") or "")
        if outcome == "leave_column" and any(_has_wound(a) for a in actors):
            w *= 1.7
        if str(tpl.get("severity") or "") == "bond_break":
            if any(
                int(v) < 0
                for a in actors
                for v in (a.relations or {}).values()
                if str(v).lstrip("-").isdigit()
            ):
                w *= 1.4
        scored.append((w, tpl, actors))
    if not scored:
        living = [c for c in cards if c.status == "living" and c.slot]
        generics = [
            t
            for t in _templates()
            if _biome_ok(t, biome_id) and str(t.get("when") or "any") in ("any", node)
        ]
        fallback = generics[0] if generics else _templates()[0]
        return fallback, (living[0] if living else None)
    total = sum(s[0] for s in scored)
    roll = rng.random() * total
    acc = 0.0
    for w, tpl, actors in scored:
        acc += w
        if roll <= acc:
            prefer = tpl.get("prefer_stance")
            pool = [a for a in actors if a.stance == prefer] if prefer else actors
            actor = rng.choice(pool or actors)
            return tpl, actor
    tpl, actors = scored[-1][1], scored[-1][2]
    return tpl, rng.choice(actors)


def _append_slot(rows: list | None, item: dict[str, Any], cap: int = 3) -> list[dict[str, Any]]:
    cur = [x for x in (rows or []) if isinstance(x, dict)]
    key = item.get("part") or item.get("facet")
    for i, old in enumerate(cur):
        if (old.get("part") or old.get("facet")) == key:
            sev = {"царапина": 1, "рана": 2, "увечье": 3}
            if sev.get(item.get("severity"), 1) > sev.get(old.get("severity"), 1):
                cur[i] = item
            return cur
    if len(cur) >= cap:
        cur[0] = item
        return cur
    cur.append(item)
    return cur


def apply_outcome(
    card: m.CompanionCard | None,
    tpl: dict[str, Any],
    cards: list[m.CompanionCard],
    *,
    node: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"gold_delta": 0, "xp_delta": 0}
    if card is None:
        return payload
    outcome = str(tpl.get("outcome") or "")
    tags = list(card.adventure_tags or [])
    if outcome in {"leave_column", "death"} and node not in (None, NODE_SURFACE):
        payload["deferred"] = outcome
        return payload
    if outcome == "injury":
        from waifu_bot.game.delve_pq_layer import TEMPLATE_STATUS, apply_status

        status_id = str(tpl.get("status_id") or TEMPLATE_STATUS.get(str(tpl.get("id") or ""), "") or "")
        if status_id:
            mercish = type("M", (), {"flesh": list(card.flesh or []), "psyche": list(card.psyche or [])})()
            row = apply_status(mercish, status_id)
            card.flesh = list(getattr(mercish, "flesh", None) or [])
            card.psyche = list(getattr(mercish, "psyche", None) or [])
            part = str((row or {}).get("part") or tpl.get("part") or "рука")
        else:
            part = str(tpl.get("part") or "рука")
            card.flesh = _append_slot(card.flesh, {"part": part, "severity": "рана", "permanent": False})
        card.scar_frame = True
        payload["injury"] = part
        if part in SILHOUETTE_PARTS:
            look = dict(card.look_card or {})
            look["silhouette_dirty"] = True
            card.look_card = look
    elif outcome == "trauma":
        from waifu_bot.game.delve_pq_layer import TEMPLATE_STATUS, apply_status

        status_id = str(tpl.get("status_id") or TEMPLATE_STATUS.get(str(tpl.get("id") or ""), "") or "")
        facet = str(tpl.get("trauma") or "страх")
        if status_id:
            mercish = type("M", (), {"flesh": list(card.flesh or []), "psyche": list(card.psyche or [])})()
            apply_status(mercish, status_id)
            card.flesh = list(getattr(mercish, "flesh", None) or [])
            card.psyche = list(getattr(mercish, "psyche", None) or [])
        else:
            card.psyche = _append_slot(card.psyche, {"facet": facet, "severity": "рана", "permanent": False})
        if facet not in tags:
            tags.append(facet)
        payload["trauma"] = facet
    elif outcome == "heal":
        flesh = [x for x in (card.flesh or []) if isinstance(x, dict)]
        if flesh:
            row = flesh[-1]
            if row.get("severity") == "царапина" and not row.get("permanent"):
                flesh.pop()
            elif not row.get("permanent"):
                row["severity"] = "царапина"
            card.flesh = flesh
        payload["heal"] = True
    elif outcome == "heal_psyche":
        psyche = [x for x in (card.psyche or []) if isinstance(x, dict)]
        if psyche and not psyche[-1].get("permanent"):
            psyche.pop()
            card.psyche = psyche
        payload["heal_psyche"] = True
    elif outcome == "bond":
        others = [c for c in cards if c.id != card.id and c.status == "living" and c.slot]
        if others:
            other = others[0]
            rel = dict(card.relations or {})
            key = str(other.id)
            rel[key] = int(rel.get(key) or 0) + int(tpl.get("bond") or 0)
            card.relations = rel
            payload["bond"] = {key: rel[key]}
            payload["other_name"] = other.name
            payload["bond_delta"] = int(tpl.get("bond") or 0)
    elif outcome == "ask_leave":
        card.asked_to_leave = True
        payload["asked_to_leave"] = True
    elif outcome == "unlock_dismiss":
        payload["unlock_dismiss"] = True
    elif outcome == "leave_column":
        payload["leave_column"] = True
    elif outcome == "death":
        payload["death"] = True
    card.adventure_tags = tags
    return payload


async def _seated_cards(session: AsyncSession, player_id: int) -> list[m.CompanionCard]:
    rows = (
        await session.execute(
            select(m.CompanionCard)
            .where(m.CompanionCard.player_id == int(player_id), m.CompanionCard.slot.is_not(None))
            .order_by(m.CompanionCard.slot)
        )
    ).scalars().all()
    return list(rows)


async def resolve_chronicle(
    session: AsyncSession,
    state: m.DelveState,
    *,
    now: datetime,
    ov_level: int,
) -> list[m.CompanionEvent]:
    if not state.t_origin:
        return []
    load_catalog()
    origin = _aware(state.t_origin)
    now = _aware(now)
    elapsed = max(0.0, (now - origin).total_seconds())
    due_index = int(elapsed // BEAT_SEC)
    last = int(state.last_beat_index or 0)
    n = min(MAX_CATCHUP, max(0, due_index - last))
    if n <= 0:
        return []
    cards = await _seated_cards(session, int(state.player_id))
    created: list[m.CompanionEvent] = []
    prev_node = state.last_beat_node or ""
    for step in range(1, n + 1):
        beat_index = last + step
        t = origin + timedelta(seconds=beat_index * BEAT_SEC)
        if t > now:
            break
        tooth = sawtooth(t_origin=origin, now=t, ov_level=ov_level)
        node = spine_type(int(tooth["d"]), float(tooth["d_ceiling"]))
        fire = node != prev_node or node in SPECIAL_NODES
        prev_node = node
        state.last_beat_index = beat_index
        state.last_beat_node = node
        if not fire or not cards:
            continue
        rng = _rng(int(state.spine_seed or 0), beat_index)
        art = shaft_art_for_depth(int(tooth["d"]))
        tpl, actor = pick_template(rng=rng, node=node, cards=cards, biome_id=str(art.get("id") or ""))
        payload = apply_outcome(actor, tpl, cards, node=node)
        if payload.get("death") and actor is not None:
            living_n = sum(1 for c in cards if c.status == "living" and c.slot)
            if living_n <= 1:
                payload.pop("death", None)
        who = actor.name if actor else "Они"
        wound_bit = ""
        if payload.get("injury"):
            wound_bit = f"Бережёт {payload['injury']}."
        other_name = str(payload.get("other_name") or "")
        bond_bit = ""
        if payload.get("bond") is not None:
            bond_bit = bond_sentence(
                delta=int(payload.get("bond_delta") or 0),
                other=other_name,
                tpl=tpl,
            )
        line = assemble_line(
            who=who,
            place=str(art.get("place_ru") or ""),
            wound=wound_bit,
            bond=bond_bit,
            tpl=tpl,
            other=other_name,
        )
        special = node in SPECIAL_NODES and rng.random() < 0.18
        row = m.CompanionEvent(
            player_id=int(state.player_id),
            card_id=actor.id if actor else None,
            beat_index=beat_index,
            ts=t,
            depth=int(tooth["d"]),
            node=node,
            template_id=str(tpl["id"]),
            severity=str(tpl.get("severity") or "mundane"),
            kind=str(tpl.get("kind") or "beat"),
            line_ru=line,
            payload={**payload, "title": tpl.get("title_ru")},
            discovered=True,
            needs_prose=bool(special),
            gold_delta=0,
            xp_delta=0,
        )
        session.add(row)
        await session.flush()
        if payload.get("unlock_dismiss") and actor is not None:
            actor.can_dismiss_beat_id = int(row.id)
        created.append(row)
        if payload.get("leave_column") and actor is not None:
            await _leave_column(session, actor)
            cards = [c for c in cards if c.id != actor.id]
        elif payload.get("death") and actor is not None:
            await _die(session, actor)
            cards = [c for c in cards if c.id != actor.id]
    return created


async def _leave_column(session: AsyncSession, card: m.CompanionCard) -> None:
    from waifu_bot.services.companion_living import start_mourning, unsync_delve_slot

    card.status = "left"
    slot = card.slot
    card.slot = None
    await unsync_delve_slot(session, int(card.player_id), int(slot or 0))
    await start_mourning(session, int(card.player_id))


async def _die(session: AsyncSession, card: m.CompanionCard) -> None:
    from waifu_bot.services.companion_living import start_mourning, unsync_delve_slot

    card.status = "fallen"
    slot = card.slot
    card.slot = None
    await unsync_delve_slot(session, int(card.player_id), int(slot or 0))
    await start_mourning(session, int(card.player_id))


def digest_lines(events: list[m.CompanionEvent], *, seen_at: datetime | None) -> list[dict[str, Any]]:
    if seen_at:
        fresh = [e for e in events if _aware(e.ts) > _aware(seen_at)]
    else:
        fresh = list(events)
    severe = [e for e in fresh if e.severity in SEVERE or e.kind in ("death", "leave_column", "crime")]
    legends = [e for e in fresh if e.severity == "legend" and e not in severe]
    mundane = [e for e in fresh if e not in severe and e not in legends]
    chosen = severe + legends + mundane[:3]
    return [
        {
            "id": e.id,
            "line": e.line_ru,
            "severity": e.severity,
            "kind": e.kind,
            "depth": e.depth,
            "name": None,
        }
        for e in chosen
    ]
