"""Tavern hall: living cards, rain hire, dismiss. No arena."""

from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_catalog import (
    CLOAK_COLORS,
    STANCES,
    TEMPERS,
    days_in_party,
    pick_companion_name,
    template_portrait_url,
)
from waifu_bot.services.chronicle import MOURNING, digest_lines, resolve_chronicle, serve_line
from waifu_bot.services.delve import DelveError, list_companions

TRAIT_POOL = (
    "тихая",
    "вспыльчивая",
    "суеверная",
    "циничная",
    "верная",
    "одиночка",
    "осторожная",
    "бесстрашная",
    "жадная",
    "боится_тьмы",
    "певунья",
    "молчунья",
    "хвастунья",
    "добрая",
    "упрямая",
    "насмешливая",
)

RACE_NAMES_RU = {
    1: "человек",
    2: "эльфийка",
    3: "зверолюдка",
    4: "ангел",
    5: "вампирша",
    6: "демоница",
    7: "фея",
}
CLASS_NAMES_RU = {
    1: "рыцарь",
    2: "воин",
    3: "лучник",
    4: "маг",
    5: "ассасин",
    6: "целительница",
    7: "торговка",
}
CLASS_TO_STANCE = {
    1: "shield",
    2: "shield",
    3: "scout",
    4: "guide",
    5: "scout",
    6: "guide",
    7: "guide",
}

_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-]{0,22}[A-Za-zА-Яа-яЁё]$")

TRAIT_ANTONYM = {
    "тихая": "хвастунья",
    "хвастунья": "тихая",
    "добрая": "циничная",
    "циничная": "добрая",
    "осторожная": "бесстрашная",
    "бесстрашная": "осторожная",
    "верная": "одиночка",
    "одиночка": "верная",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def patron_name(session: AsyncSession, player_id: int) -> str:
    row = (
        await session.execute(select(m.MainWaifu.name).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    name = str(row or "").strip()
    return name or "хозяйка"


def _rng(*parts: object) -> random.Random:
    digest = hashlib.sha256((":".join(str(p) for p in parts)).encode()).hexdigest()[:16]
    return random.Random(int(digest, 16))


def roll_traits(rng: random.Random) -> list[str]:
    pool = list(TRAIT_POOL)
    rng.shuffle(pool)
    a = pool[0]
    b = next((x for x in pool[1:] if TRAIT_ANTONYM.get(a) != x), pool[1])
    return [a, b]


def stamp_look_lineage(look: dict[str, Any] | None, *, seed: int, stance: str) -> dict[str, Any]:
    out = dict(look or {})
    try:
        rid = int(out.get("race_id") or 0)
    except (TypeError, ValueError):
        rid = 0
    try:
        cid = int(out.get("class_id") or 0)
    except (TypeError, ValueError):
        cid = 0
    if rid not in RACE_NAMES_RU or cid not in CLASS_NAMES_RU:
        rng = _rng("lineage", seed, stance, out.get("hair"), out.get("eyes"))
        rid = rng.randint(1, 7)
        cid = rng.randint(1, 7)
        out["race_id"] = rid
        out["class_id"] = cid
    out["race_ru"] = RACE_NAMES_RU.get(int(out["race_id"]), "человек")
    out["class_ru"] = CLASS_NAMES_RU.get(int(out["class_id"]), "маг")
    if "loyalty" not in out:
        out["loyalty"] = 50
    return out


def card_loyalty(card: m.CompanionCard | None) -> int:
    if card is None:
        return 50
    look = card.look_card or {}
    try:
        value = int(look.get("loyalty", 50))
    except (TypeError, ValueError):
        value = 50
    return max(0, min(100, value))


LOYALTY_HEART_DIR = "/static/game/delve/portraits"


def loyalty_heart_key(loyalty: int) -> str:
    n = max(0, min(100, int(loyalty)))
    if n <= 5:
        return "broken"
    if n <= 30:
        return "dim"
    if n <= 69:
        return "pink"
    if n <= 99:
        return "red"
    return "gold"


def loyalty_heart_url(loyalty: int) -> str:
    return f"{LOYALTY_HEART_DIR}/loyalty_heart_{loyalty_heart_key(loyalty)}.webp"


def card_class_id(card: m.CompanionCard) -> int:
    look = card.look_card or {}
    try:
        cid = int(look.get("class_id") or 0)
    except (TypeError, ValueError):
        cid = 0
    return cid if cid in CLASS_NAMES_RU else 0


def look_card_for(
    *,
    name: str,
    stance: str,
    cloak: str,
    traits: list[str],
    seed: int,
    hired_by: str = "",
    race_id: int | None = None,
    class_id: int | None = None,
) -> dict[str, Any]:
    rng = _rng("look", name, stance, cloak, seed)
    hair = rng.choice(["ash", "ink", "wine", "straw", "copper"])
    eyes = rng.choice(["grey", "amber", "green", "dark"])
    mark = rng.choice(["brow_scar", "freckles", "chipped_fang", "mole"])
    out: dict[str, Any] = {
        "hair": hair,
        "eyes": eyes,
        "mark": mark,
        "stance": stance,
        "cloak": cloak,
        "traits": traits,
        "marks": [],
        "loyalty": 50,
    }
    if hired_by:
        out["hired_by"] = hired_by
    if race_id in RACE_NAMES_RU:
        out["race_id"] = int(race_id)
    if class_id in CLASS_NAMES_RU:
        out["class_id"] = int(class_id)
    return stamp_look_lineage(out, seed=seed, stance=stance)


async def has_living_hire_history(session: AsyncSession, player_id: int) -> bool:
    n = (
        await session.execute(
            select(func.count())
            .select_from(m.CompanionCard)
            .where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.status.in_(("living", "dismissed", "left", "fallen")),
            )
        )
    ).scalar_one()
    return int(n or 0) > 0


async def compute_living_hire_price(session: AsyncSession, player_id: int) -> int:
    """Base 10000, then ОБА / passives / guild tavern-hire discounts. First seat can be free."""
    from waifu_bot.game.constants import TAVERN_HIRE_COST
    from waifu_bot.services.tavern import compute_effective_tavern_hire_price, compute_tavern_hire_price

    if not await has_living_hire_history(session, player_id):
        return int(await compute_effective_tavern_hire_price(session, player_id))
    cost = await compute_tavern_hire_price(session, player_id, TAVERN_HIRE_COST)
    try:
        from waifu_bot.services.guild_skill_effects import apply_price_discount_pct, guild_skill_contributions

        contribs = await guild_skill_contributions(
            session, player_id, params={"tavern_hire_discount_pct"}
        )
        discount_pct = sum(float(c.value) for c in contribs)
        cost = apply_price_discount_pct(cost, discount_pct)
    except Exception:
        pass
    return int(cost)


def normalize_companion_name(raw: str) -> str:
    name = " ".join(str(raw or "").split())
    if len(name) < 2 or len(name) > 24 or not _NAME_RE.fullmatch(name):
        raise DelveError("bad_name", 400)
    return name


async def get_hall_row(session: AsyncSession, player_id: int) -> m.CompanionHall:
    row = await session.get(m.CompanionHall, int(player_id))
    if row is None:
        row = m.CompanionHall(player_id=int(player_id))
        session.add(row)
        await session.flush()
    return row


async def start_mourning(session: AsyncSession, player_id: int, *, now: datetime | None = None) -> None:
    hall = await get_hall_row(session, player_id)
    hall.mourning_until = (now or _now()) + MOURNING
    hall.rain_card_id = None


async def unsync_delve_slot(session: AsyncSession, player_id: int, slot: int) -> None:
    if slot < 1:
        return
    row = (
        await session.execute(
            select(m.DelveCompanion).where(
                m.DelveCompanion.player_id == int(player_id),
                m.DelveCompanion.slot == int(slot),
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.flush()


async def sync_card_to_delve(session: AsyncSession, card: m.CompanionCard) -> None:
    if not card.slot or card.status != "living":
        return
    existing = (
        await session.execute(
            select(m.DelveCompanion).where(
                m.DelveCompanion.player_id == int(card.player_id),
                m.DelveCompanion.slot == int(card.slot),
            )
        )
    ).scalar_one_or_none()
    pixel = card.portrait_pixel_path or ""
    if existing is None:
        session.add(
            m.DelveCompanion(
                player_id=int(card.player_id),
                slot=int(card.slot),
                name=card.name,
                stance=card.stance,
                temper=card.temper,
                cloak_color=card.cloak_color,
                image_path=pixel or None,
                gold_earned=int(card.gold_earned or 0),
                xp_earned=int(card.xp_earned or 0),
                joined_at=card.joined_at,
            )
        )
    else:
        existing.name = card.name
        existing.stance = card.stance
        existing.temper = card.temper
        existing.cloak_color = card.cloak_color
        if pixel:
            existing.image_path = pixel
        existing.gold_earned = max(int(existing.gold_earned or 0), int(card.gold_earned or 0))
        existing.xp_earned = max(int(existing.xp_earned or 0), int(card.xp_earned or 0))


async def migrate_delve_to_cards(session: AsyncSession, player_id: int, *, now: datetime | None = None) -> None:
    now = now or _now()
    companions = await list_companions(session, player_id)
    existing = (
        await session.execute(select(m.CompanionCard).where(m.CompanionCard.player_id == int(player_id)))
    ).scalars().all()
    by_source = {int(c.source_delve_id): c for c in existing if c.source_delve_id}
    by_slot = {int(c.slot): c for c in existing if c.slot}
    taken_names = [c.name for c in existing]
    for row in companions:
        if row.id in by_source or int(row.slot) in by_slot:
            continue
        rng = _rng("migrate", player_id, row.slot, row.name)
        traits = roll_traits(rng)
        cloak = row.cloak_color or "ash"
        patron = await patron_name(session, player_id)
        card = m.CompanionCard(
            player_id=int(player_id),
            slot=int(row.slot),
            status="living",
            name=row.name,
            stance=row.stance,
            temper=row.temper,
            cloak_color=cloak,
            traits=traits,
            look_card=look_card_for(
                name=row.name,
                stance=row.stance,
                cloak=cloak,
                traits=traits,
                seed=rng.randrange(10**9),
                hired_by=patron,
            ),
            bio=f"Шли вместе с {patron} до таверны.",
            portrait_pixel_path=row.image_path,
            flesh=[],
            psyche=[],
            adventure_tags=[],
            relations={},
            gold_earned=int(row.gold_earned or 0),
            xp_earned=int(row.xp_earned or 0),
            joined_at=row.joined_at or row.created_at or now,
            source_delve_id=int(row.id),
        )
        session.add(card)
        await session.flush()
        taken_names.append(row.name)
        session.add(
            m.CompanionEvent(
                player_id=int(player_id),
                card_id=card.id,
                beat_index=0,
                ts=now,
                depth=0,
                node="SURFACE",
                template_id="migrate",
                severity="mundane",
                kind="hire",
                line_ru=f"{row.name} уже шла в колонне.",
                payload={"migrated": True},
                discovered=True,
                gold_delta=0,
                xp_delta=0,
            )
        )
    await session.flush()


def _tone(n: int) -> str:
    if n <= 0:
        return "ok"
    if n == 1:
        return "warn"
    return "bad"


def _qual_body(card: m.CompanionCard) -> str:
    n = len(card.flesh or [])
    if n <= 0:
        return "в форме"
    if n == 1:
        return "побита"
    return "еле держится"


def _qual_mind(card: m.CompanionCard) -> str:
    n = len(card.psyche or [])
    if n <= 0:
        return "ясна"
    if n == 1:
        return "тень"
    return "пустой взгляд"


def _consequence(card: m.CompanionCard, party: list[m.CompanionCard] | None = None) -> list[str]:
    out: list[str] = []
    rel = card.relations or {}
    if any(int(v) < 0 for v in rel.values() if str(v).lstrip("-").isdigit() or isinstance(v, int)):
        other_name = ""
        for pid, val in rel.items():
            try:
                if int(val) >= 0:
                    continue
            except (TypeError, ValueError):
                continue
            if party:
                mate = next((c for c in party if str(c.id) == str(pid)), None)
                if mate:
                    other_name = mate.name
                    break
        out.append(f"{other_name} не смотрит." if other_name else "Не смотрит на спутницу.")
    for row in card.flesh or []:
        if isinstance(row, dict) and row.get("part"):
            out.append(f"Бережёт {row['part']}.")
    for row in card.psyche or []:
        if isinstance(row, dict) and row.get("facet"):
            out.append(str(row["facet"]).replace("_", " "))
    for t in (card.adventure_tags or [])[:3]:
        if t not in ("боится_тьмы",):
            continue
        out.append("Просит не гасить.")
    return out[:6]


def can_dismiss_now(card: m.CompanionCard, *, dismiss_left: int, is_admin: bool) -> bool:
    if card.status == "left":
        return True
    if card.status != "living":
        return False
    return int(dismiss_left) > 0 or bool(is_admin)


def _dismiss_reason(
    card: m.CompanionCard,
    *,
    now: datetime,
    dismiss_left: int = 1,
    is_admin: bool = False,
) -> str | None:
    if card.status == "left":
        return None
    if card.status != "living":
        return "cannot_dismiss"
    if can_dismiss_now(card, dismiss_left=dismiss_left, is_admin=is_admin):
        return None
    return "dismiss_day_cap"


async def count_dismisses_today(session: AsyncSession, player_id: int, *, now: datetime) -> int:
    from waifu_bot.game.delve_catalog import msk_day_start

    start = msk_day_start(now)
    n = await session.scalar(
        select(func.count())
        .select_from(m.CompanionEvent)
        .where(
            m.CompanionEvent.player_id == int(player_id),
            m.CompanionEvent.kind == "dismiss",
            m.CompanionEvent.template_id == "dismiss",
            m.CompanionEvent.ts >= start,
        )
    )
    return int(n or 0)


async def list_living_cards(session: AsyncSession, player_id: int) -> list[m.CompanionCard]:
    rows = (
        await session.execute(
            select(m.CompanionCard)
            .where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.status == "living",
                m.CompanionCard.slot.is_not(None),
            )
            .order_by(m.CompanionCard.slot.asc())
        )
    ).scalars().all()
    return list(rows)


def card_public(
    card: m.CompanionCard,
    *,
    now: datetime,
    party: list[m.CompanionCard] | None = None,
    dismiss_left: int = 1,
    is_admin: bool = False,
) -> dict[str, Any]:
    stance = STANCES.get(card.stance, {})
    temper = TEMPERS.get(str(card.temper), {})
    reason = _dismiss_reason(card, now=now, dismiss_left=dismiss_left, is_admin=is_admin)
    from waifu_bot.services.companion_chat import chat_left

    look = dict(card.look_card or {})
    race_ru = str(look.get("race_ru") or "")
    class_ru = str(look.get("class_ru") or "")
    lineage = " · ".join(p for p in (race_ru, class_ru) if p)
    bio = str(card.bio or "")
    try:
        bio_version = int(look.get("bio_version") or 0)
    except (TypeError, ValueError):
        bio_version = 0
    return {
        "id": card.id,
        "slot": card.slot,
        "status": card.status,
        "name": card.name,
        "stance": card.stance,
        "stance_label": stance.get("label", card.stance),
        "temper": card.temper,
        "temper_label": temper.get("label", card.temper),
        "cloak_color": card.cloak_color,
        "traits": list(card.traits or []),
        "bio": card.bio,
        "portrait_anime": f"/static/{card.portrait_anime_path}" if card.portrait_anime_path else "",
        "portrait_pixel": f"/static/{card.portrait_pixel_path}" if card.portrait_pixel_path else template_portrait_url(card.stance),
        "body": _qual_body(card),
        "mind": _qual_mind(card),
        "body_tone": _tone(len(card.flesh or [])),
        "mind_tone": _tone(len(card.psyche or [])),
        "wounds": [
            {"part": r.get("part"), "label": r.get("part"), "severity": r.get("severity")}
            for r in (card.flesh or [])
            if isinstance(r, dict)
        ],
        "psyche": [
            {"facet": r.get("facet"), "label": str(r.get("facet") or "").replace("_", " "), "severity": r.get("severity")}
            for r in (card.psyche or [])
            if isinstance(r, dict)
        ],
        "consequences": _consequence(card, party),
        "scar_frame": bool(card.scar_frame),
        "days": days_in_party(card.joined_at, now),
        "gold_earned": int(card.gold_earned or 0),
        "xp_earned": int(card.xp_earned or 0),
        "can_dismiss": can_dismiss_now(card, dismiss_left=dismiss_left, is_admin=is_admin),
        "dismiss_reason": reason,
        "dismiss_left": 1 if is_admin else max(0, min(1, int(dismiss_left))),
        "asked_to_leave": bool(card.asked_to_leave),
        "chat_left": chat_left(card, now=now),
        "joined_at": card.joined_at.isoformat() if card.joined_at else None,
        "can_rename": card.status == "living" and not bool(look.get("renamed")),
        "race_ru": race_ru,
        "class_ru": class_ru,
        "lineage": lineage,
        "loyalty": card_loyalty(card),
        "loyalty_heart": loyalty_heart_url(card_loyalty(card)),
        "bio_expandable": card.status == "living" and bio_version < 2 and 0 < len(bio.strip()) < 200,
    }


async def _spawn_rain(session: AsyncSession, player_id: int, *, now: datetime) -> m.CompanionCard:
    seated = (
        await session.execute(
            select(m.CompanionCard).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.slot.is_not(None),
            )
        )
    ).scalars().all()
    names = [c.name for c in seated]
    rng = _rng("rain", player_id, int(now.timestamp() * 1000), len(names))
    name = pick_companion_name(
        player_id,
        1,
        exclude=names,
        salt=f"{int(now.timestamp() * 1000)}:{len(names)}:{rng.randrange(10**9)}",
    )
    tempers = list(TEMPERS.keys())
    used_t = {c.temper for c in seated}
    temper = rng.choice([t for t in tempers if t not in used_t] or tempers)
    used_c = {card_class_id(c) for c in seated if card_class_id(c)}
    class_pool = [cid for cid in CLASS_NAMES_RU if cid not in used_c] or list(CLASS_NAMES_RU)
    class_id = rng.choice(class_pool)
    race_id = rng.randint(1, 7)
    stance = CLASS_TO_STANCE.get(class_id, rng.choice(list(STANCES.keys())))
    cloak = rng.choice(list(CLOAK_COLORS))
    traits = roll_traits(rng)
    # pity = weirder person: extra odd trait
    if rng.random() < 0.35:
        extra = rng.choice([t for t in TRAIT_POOL if t not in traits])
        traits = (traits + [extra])[:3]
    patron = await patron_name(session, player_id)
    card = m.CompanionCard(
        player_id=int(player_id),
        slot=None,
        status="rain",
        name=name,
        stance=stance,
        temper=temper,
        cloak_color=cloak,
        traits=traits,
        look_card=look_card_for(
            name=name,
            stance=stance,
            cloak=cloak,
            traits=traits,
            seed=rng.randrange(10**9),
            hired_by=patron,
            race_id=race_id,
            class_id=class_id,
        ),
        bio="",
        flesh=[],
        psyche=[],
        adventure_tags=[],
        relations={},
        joined_at=now,
    )
    session.add(card)
    await session.flush()
    return card


async def ensure_rain(session: AsyncSession, player_id: int, *, now: datetime) -> m.CompanionCard | None:
    hall = await get_hall_row(session, player_id)
    seated = (
        await session.execute(
            select(m.CompanionCard).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.status == "living",
                m.CompanionCard.slot.is_not(None),
            )
        )
    ).scalars().all()
    if len(seated) >= 3:
        return None
    if hall.mourning_until and _aware(hall.mourning_until) > now:
        return None
    if hall.rain_card_id:
        rain = await session.get(m.CompanionCard, int(hall.rain_card_id))
        if rain and rain.status == "rain":
            return rain
    rain = await _spawn_rain(session, player_id, now=now)
    hall.rain_card_id = rain.id
    hall.mourning_until = None
    return rain


async def build_hall(
    session: AsyncSession,
    player_id: int,
    *,
    now: datetime | None = None,
    mark_seen: bool = False,
) -> dict[str, Any]:
    now = now or _now()
    await migrate_delve_to_cards(session, player_id, now=now)
    hall = await get_hall_row(session, player_id)
    state = await session.get(m.DelveState, int(player_id))
    mw = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))).scalar_one_or_none()
    if state and state.t_origin:
        await resolve_chronicle(session, state, now=now, ov_level=int(mw.level or 1) if mw else 1)
    rain = await ensure_rain(session, player_id, now=now)
    rain_card = rain
    dismiss_left, is_admin = await hall_dismiss_flags(session, player_id, now=now)
    seated = (
        await session.execute(
            select(m.CompanionCard)
            .where(m.CompanionCard.player_id == int(player_id), m.CompanionCard.slot.is_not(None))
            .order_by(m.CompanionCard.slot)
        )
    ).scalars().all()
    by_slot = {int(c.slot): c for c in seated if c.slot}
    mourning = bool(hall.mourning_until and _aware(hall.mourning_until) > now)
    columns = []
    for slot in (1, 2, 3):
        card = by_slot.get(slot)
        if card:
            columns.append(
                {
                    "slot": slot,
                    "kind": "living",
                    "card": card_public(
                        card, now=now, party=seated, dismiss_left=dismiss_left, is_admin=is_admin
                    ),
                }
            )
            continue
        if rain and not any(c.get("kind") == "rain" for c in columns):
            columns.append(
                {
                    "slot": slot,
                    "kind": "rain",
                    "card": card_public(
                        rain, now=now, party=seated, dismiss_left=dismiss_left, is_admin=is_admin
                    ),
                    "mourning": False,
                }
            )
            rain = None
            continue
        columns.append(
            {
                "slot": slot,
                "kind": "hire",
                "card": None,
                "mourning": mourning,
                "mourning_until": hall.mourning_until.isoformat() if hall.mourning_until else None,
            }
        )
    events = (
        await session.execute(
            select(m.CompanionEvent)
            .where(m.CompanionEvent.player_id == int(player_id))
            .order_by(m.CompanionEvent.id.desc())
            .limit(80)
        )
    ).scalars().all()
    events_asc = list(reversed(list(events)))
    name_ids = {int(e.card_id) for e in events_asc if e.card_id}
    for ev in events_asc:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        bond = payload.get("bond")
        if isinstance(bond, dict):
            for key in bond:
                try:
                    name_ids.add(int(key))
                except (TypeError, ValueError):
                    pass
    names: dict[int, str] = {}
    if name_ids:
        for cid, nm in (
            await session.execute(
                select(m.CompanionCard.id, m.CompanionCard.name).where(m.CompanionCard.id.in_(name_ids))
            )
        ).all():
            names[int(cid)] = str(nm)
    for ev in events_asc:
        who = names.get(int(ev.card_id), "Она") if ev.card_id else "Они"
        other = ""
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        bond = payload.get("bond")
        if isinstance(bond, dict):
            for key in bond:
                try:
                    other = names.get(int(key), "") or other
                except (TypeError, ValueError):
                    continue
        if not other:
            other = str(payload.get("other_name") or "")
        serve_line(ev, who=who, other=other)
    chalkboard = digest_lines(events_asc, seen_at=hall.digest_seen_at)
    for row in chalkboard:
        ev = next((e for e in events_asc if e.id == row["id"]), None)
        if ev and ev.card_id:
            row["name"] = names.get(int(ev.card_id))
        if ev:
            row["line"] = ev.line_ru
    if mark_seen:
        hall.digest_seen_at = now
    living_n = sum(1 for c in columns if c["kind"] == "living")
    needs_art = []
    for col in columns:
        card_row = col.get("card")
        if not card_row:
            continue
        cid = int(card_row["id"])
        raw = by_slot.get(int(col["slot"])) if col.get("kind") == "living" else None
        if col.get("kind") == "rain":
            raw = rain_card
        look = (raw.look_card if raw else None) or {}
        if raw and (not raw.portrait_anime_path or look.get("silhouette_dirty") or not (raw.bio or "").strip()):
            needs_art.append(cid)
    return {
        "copy": {
            "title": "Таверна",
            "sub": f"За столом {living_n} из 3",
            "empty": "Пустой стул",
            "hire": "Нанять",
            "rain": "Вошла с дождя",
            "confirm_rain": "Снять капюшон и посадить за стол?",
            "dismiss": "Уволить",
            "chat_ph": "Сказать ей…",
            "history_empty": "Пока тишина.",
            "board": "Вчера",
        },
        "columns": columns,
        "chalkboard": chalkboard,
        "mourning": mourning,
        "living": living_n,
        "needs_art": needs_art,
        "hire_cost": await compute_living_hire_price(session, player_id),
        "dismiss_left": dismiss_left,
        "is_admin": is_admin,
    }


async def accept_rain(session: AsyncSession, player_id: int, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    hall = await get_hall_row(session, player_id)
    if not hall.rain_card_id:
        raise DelveError("no_rain", 400)
    card = await session.get(m.CompanionCard, int(hall.rain_card_id))
    if card is None or card.status != "rain":
        raise DelveError("no_rain", 400)
    used = {
        int(c.slot)
        for c in (
            await session.execute(
                select(m.CompanionCard).where(
                    m.CompanionCard.player_id == int(player_id),
                    m.CompanionCard.slot.is_not(None),
                )
            )
        ).scalars().all()
        if c.slot
    }
    slot = next((s for s in (1, 2, 3) if s not in used), None)
    if slot is None:
        raise DelveError("party_full", 400)
    card.slot = slot
    card.status = "living"
    card.joined_at = now
    hall.rain_card_id = None
    hall.mourning_until = None
    await sync_card_to_delve(session, card)
    session.add(
        m.CompanionEvent(
            player_id=int(player_id),
            card_id=card.id,
            beat_index=0,
            ts=now,
            depth=0,
            node="SURFACE",
            template_id="rain_accept",
            severity="mundane",
            kind="hire",
            line_ru=f"{card.name} села за стол.",
            payload={},
            discovered=True,
            gold_delta=0,
            xp_delta=0,
        )
    )
    await session.flush()
    return card_public(card, now=now)


async def _taken_slots(session: AsyncSession, player_id: int) -> set[int]:
    rows = (
        await session.execute(
            select(m.CompanionCard.slot).where(
                m.CompanionCard.player_id == int(player_id),
                m.CompanionCard.slot.is_not(None),
            )
        )
    ).all()
    return {int(s) for (s,) in rows if s}


async def hire_generated(
    session: AsyncSession,
    player_id: int,
    *,
    slot: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Seat a generated card into an empty chair. Paid hire; rain stays on the door CTA."""
    now = now or _now()
    taken = await _taken_slots(session, player_id)
    free = [s for s in (1, 2, 3) if s not in taken]
    if not free:
        raise DelveError("party_full", 400)
    want = int(slot) if slot else None
    target = want if want in free else free[0]
    price = await compute_living_hire_price(session, player_id)
    player = await session.get(m.Player, int(player_id))
    if player is None:
        raise DelveError("player_not_found", 404)
    from waifu_bot.services import merc_systems as merc_sys

    state = await merc_sys.get_or_create_tavern_state(session, player_id)
    pay_with_contract = price > 0 and int(getattr(state, "merc_contracts", 0) or 0) > 0
    if not pay_with_contract and price > 0 and int(player.gold or 0) < int(price):
        raise DelveError("not_enough_gold", 400)
    card = await _spawn_rain(session, player_id, now=now)
    card.slot = target
    card.status = "living"
    card.joined_at = now
    await sync_card_to_delve(session, card)
    paid = 0
    if pay_with_contract:
        state.merc_contracts = max(0, int(state.merc_contracts or 0) - 1)
    elif price > 0:
        from waifu_bot.services import wallet as wallet_svc
        from waifu_bot.services.wallet import InsufficientCurrency

        try:
            await wallet_svc.spend_gold(
                session,
                player,
                int(price),
                source="tavern_hire",
                ref_type="companion_card",
                ref_id=int(card.id),
            )
            paid = int(price)
        except InsufficientCurrency:
            raise DelveError("not_enough_gold", 400) from None
    session.add(
        m.CompanionEvent(
            player_id=int(player_id),
            card_id=card.id,
            beat_index=0,
            ts=now,
            depth=0,
            node="SURFACE",
            template_id="hire",
            severity="mundane",
            kind="hire",
            line_ru=f"{card.name} села за стол.",
            payload={"hire_cost": paid, "paid_with_contract": pay_with_contract},
            discovered=True,
            gold_delta=0,
            xp_delta=0,
        )
    )
    await session.flush()
    return card_public(card, now=now)


async def _rewrite_delve_flavor_name(
    session: AsyncSession, player_id: int, old: str, new: str
) -> None:
    from waifu_bot.game.delve_catalog import enforce_squad_names, replace_companion_name
    from waifu_bot.services.delve import get_state

    state = await get_state(session, int(player_id))
    cached = (getattr(state, "flavor_text", None) or "").strip() if state is not None else ""
    if state is None or not cached:
        return
    living = await list_living_cards(session, int(player_id))
    names = [str(c.name).strip() for c in living if c.name]
    text = replace_companion_name(cached, old, new)
    face = names[0] if names else new
    state.flavor_text = enforce_squad_names(text, names, face=face)[:280]
    state.flavor_key = None


async def rename_card(
    session: AsyncSession,
    player_id: int,
    card_id: int,
    raw_name: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or _now()
    card = await session.get(m.CompanionCard, int(card_id))
    if card is None or int(card.player_id) != int(player_id) or card.status != "living":
        raise DelveError("not_found", 404)
    look = dict(card.look_card or {})
    if look.get("renamed"):
        raise DelveError("name_locked", 400)
    new = normalize_companion_name(raw_name)
    old = card.name
    if new != old:
        taken = (
            await session.execute(
                select(m.CompanionCard.name).where(
                    m.CompanionCard.player_id == int(player_id),
                    m.CompanionCard.id != int(card.id),
                    m.CompanionCard.status.in_(("living", "rain", "left")),
                )
            )
        ).scalars().all()
        if any(str(n).strip().casefold() == new.casefold() for n in taken):
            raise DelveError("name_taken", 400)
        card.name = new
    look["renamed"] = True
    card.look_card = look
    await sync_card_to_delve(session, card)
    if new != old:
        await _rewrite_delve_flavor_name(session, player_id, old, new)
    await session.flush()
    return card_public(card, now=now)


async def refuse_rain(session: AsyncSession, player_id: int, *, now: datetime | None = None) -> None:
    now = now or _now()
    hall = await get_hall_row(session, player_id)
    if hall.rain_card_id:
        card = await session.get(m.CompanionCard, int(hall.rain_card_id))
        if card is not None and card.status == "rain":
            card.status = "refused"
            card.slot = None
    hall.rain_card_id = None
    hall.mourning_until = now + MOURNING


async def hall_dismiss_flags(
    session: AsyncSession, player_id: int, *, now: datetime | None = None
) -> tuple[int, bool]:
    now = now or _now()
    from waifu_bot.core.config import settings

    is_admin = bool(settings.is_admin(int(player_id)))
    used = await count_dismisses_today(session, player_id, now=now)
    dismiss_left = 1 if is_admin or used < 1 else 0
    return dismiss_left, is_admin


async def dismiss_card(session: AsyncSession, player_id: int, card_id: int, *, now: datetime | None = None) -> None:
    now = now or _now()
    card = await session.get(m.CompanionCard, int(card_id))
    if card is None or int(card.player_id) != int(player_id):
        raise DelveError("not_found", 404)
    if card.status not in ("living", "left"):
        raise DelveError("cannot_dismiss", 400)
    was_living = card.status == "living"
    if was_living:
        from waifu_bot.core.config import settings

        if not settings.is_admin(int(player_id)):
            used = await count_dismisses_today(session, player_id, now=now)
            if used >= 1:
                raise DelveError("dismiss_day_cap", 429)
    slot = card.slot
    card.status = "dismissed"
    card.slot = None
    if slot:
        await unsync_delve_slot(session, player_id, int(slot))
    if was_living:
        await start_mourning(session, player_id, now=now)
        session.add(
            m.CompanionEvent(
                player_id=int(player_id),
                card_id=card.id,
                beat_index=0,
                ts=now,
                depth=0,
                node="SURFACE",
                template_id="dismiss",
                severity="mundane",
                kind="dismiss",
                line_ru=f"{card.name} ушла со стола.",
                payload={"beat_id": card.can_dismiss_beat_id},
                discovered=True,
                gold_delta=0,
                xp_delta=0,
            )
        )


async def leave_loyalty(session: AsyncSession, player_id: int, card_id: int, *, now: datetime | None = None) -> None:
    """Self-leave at loyalty 0. Does not consume dismiss slot or start mourning."""
    now = now or _now()
    card = await session.get(m.CompanionCard, int(card_id))
    if card is None or int(card.player_id) != int(player_id):
        raise DelveError("not_found", 404)
    if card.status != "living":
        return
    slot = card.slot
    card.status = "left"
    card.slot = None
    if slot:
        await unsync_delve_slot(session, player_id, int(slot))
    session.add(
        m.CompanionEvent(
            player_id=int(player_id),
            card_id=card.id,
            beat_index=0,
            ts=now,
            depth=0,
            node="SURFACE",
            template_id="loyalty_leave",
            severity="leave_column",
            kind="leave_column",
            line_ru=f"{card.name} ушла сама.",
            payload={"loyalty": 0},
            discovered=True,
            gold_delta=0,
            xp_delta=0,
        )
    )
    await session.flush()


async def card_history(session: AsyncSession, player_id: int, card_id: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(m.CompanionEvent)
            .where(
                m.CompanionEvent.player_id == int(player_id),
                m.CompanionEvent.card_id == int(card_id),
                m.CompanionEvent.discovered.is_(True),
            )
            .order_by(m.CompanionEvent.id.desc())
            .limit(40)
        )
    ).scalars().all()
    card = await session.get(m.CompanionCard, int(card_id))
    who = card.name if card else "Она"
    return [
        {
            "id": r.id,
            "line": serve_line(r, who=who),
            "depth": r.depth,
            "kind": r.kind,
        }
        for r in rows
    ]
