"""Daily GD: message/damage aggregation, MVP scoring, chat-wide percentages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import calculate_message_damage

MSG_TYPE_KEYS = (
    "text",
    "photo",
    "sticker",
    "animation",
    "video",
    "voice",
    "audio",
    "document",
    "link",
    "other",
)


def empty_day_stats() -> dict[str, Any]:
    return {
        "msg_total": 0,
        "by_type": {k: 0 for k in MSG_TYPE_KEYS},
        "damage_total": 0,
        "text_chars": 0,
        "last_message_at": None,
    }


def media_type_to_day_key(media_type: MediaType | str | None) -> str:
    if media_type is None:
        return "other"
    if isinstance(media_type, MediaType):
        mapping = {
            MediaType.TEXT: "text",
            MediaType.LINK: "link",
            MediaType.STICKER: "sticker",
            MediaType.PHOTO: "photo",
            MediaType.GIF: "animation",
            MediaType.AUDIO: "audio",
            MediaType.VIDEO: "video",
            MediaType.VOICE: "voice",
        }
        return mapping.get(media_type, "other")
    raw = str(media_type).strip().lower()
    aliases = {
        "gif": "animation",
        "animation": "animation",
        "document": "document",
        "text": "text",
        "photo": "photo",
        "sticker": "sticker",
        "video": "video",
        "voice": "voice",
        "audio": "audio",
        "link": "link",
    }
    return aliases.get(raw, "other" if raw not in MSG_TYPE_KEYS else raw)


def normalize_day_stats(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = empty_day_stats()
    if not raw:
        return base
    by_type = dict(base["by_type"])
    src = raw.get("by_type") or {}
    if isinstance(src, dict):
        for k in MSG_TYPE_KEYS:
            by_type[k] = max(0, int(src.get(k) or 0))
    base["by_type"] = by_type
    base["msg_total"] = max(0, int(raw.get("msg_total") or sum(by_type.values())))
    base["damage_total"] = max(0, int(raw.get("damage_total") or 0))
    base["text_chars"] = max(0, int(raw.get("text_chars") or 0))
    base["last_message_at"] = raw.get("last_message_at")
    return base


def apply_message_to_day_stats(
    stats: dict[str, Any] | None,
    *,
    msg_key: str,
    damage: int = 0,
    text_chars_delta: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    out = normalize_day_stats(stats)
    key = msg_key if msg_key in out["by_type"] else "other"
    out["by_type"][key] = int(out["by_type"].get(key) or 0) + 1
    out["msg_total"] = int(out["msg_total"] or 0) + 1
    out["damage_total"] = int(out["damage_total"] or 0) + max(0, int(damage))
    out["text_chars"] = int(out["text_chars"] or 0) + max(0, int(text_chars_delta or 0))
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    out["last_message_at"] = ts.isoformat()
    return out


def sort_rows_by_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Most active first: msg_total, then damage_total, then stable user_id."""
    return sorted(
        rows,
        key=lambda r: (
            -int(r.get("msg_total") or 0),
            -int(r.get("damage_total") or 0),
            int(r.get("user_id") or 0),
        ),
    )


def format_top_words_line_ru(row: dict[str, Any]) -> str:
    """Human-readable top-words line for finale HTML."""
    if row.get("words_unavailable"):
        return "топ слов недоступен"
    if row.get("no_word_repeated"):
        return "нет повторов слов"
    words = row.get("top_words") or []
    if not isinstance(words, list) or not words:
        if int(row.get("msg_total") or 0) <= 0 and int(row.get("text_chars") or 0) <= 0:
            return "—"
        return "топ слов недоступен"
    parts: list[str] = []
    for item in words[:5]:
        if isinstance(item, dict):
            w = str(item.get("word") or "").strip()
            c = int(item.get("count") or 0)
            if w:
                parts.append(f"{w} ({c})" if c > 0 else w)
        else:
            w = str(item).strip()
            if w:
                parts.append(w)
    return ", ".join(parts) if parts else "топ слов недоступен"


def calc_snapshot_message_damage(
    snapshot: dict[str, Any] | None,
    media_type: MediaType,
    *,
    message_length: int = 0,
) -> int:
    """Calc-only outgoing damage from frozen waifu snapshot (no solo battle required)."""
    snap = snapshot or {}
    strength = int(snap.get("strength") or 10)
    agility = int(snap.get("agility") or 10)
    intelligence = int(snap.get("intelligence") or 10)
    weapon_damage = snap.get("weapon_damage")
    wd = int(weapon_damage) if weapon_damage is not None else None
    attack_type = str(snap.get("attack_type") or "melee")
    return max(
        0,
        int(
            calculate_message_damage(
                media_type,
                strength=strength,
                agility=agility,
                intelligence=intelligence,
                attack_type=attack_type,
                message_length=max(0, int(message_length or 0)),
                weapon_damage=wd,
            )
        ),
    )


def chat_message_share_pct(player_msgs: int, chat_total: int) -> float:
    if chat_total <= 0:
        return 0.0
    return round(100.0 * max(0, int(player_msgs)) / float(chat_total), 2)


def composite_activity_score(*, msg_total: int, damage_total: int, chat_share_pct: float) -> float:
    """MVP score: message volume + damage + chat share."""
    return float(msg_total) * 10.0 + float(damage_total) * 0.01 + float(chat_share_pct) * 5.0


def pick_mvp_and_least(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Pick MVP (max composite) and least-active among participants who sent ≥1 message.

    Silent participants (0 messages) are excluded from least-active; caller may mention them separately.
    """
    if not rows:
        return None, None
    ranked = sorted(rows, key=lambda r: float(r.get("score") or 0.0), reverse=True)
    mvp = ranked[0]
    active = [r for r in ranked if int(r.get("msg_total") or 0) > 0]
    least = active[-1] if active else ranked[-1]
    if mvp is least and len(ranked) > 1 and active:
        # Prefer a different least when possible
        if len(active) > 1:
            least = active[-1]
    return mvp, least


def build_player_summary_rows(
    registrations: list[Any],
    *,
    chat_msg_total: int,
) -> list[dict[str, Any]]:
    """Build per-player summary dicts from GDRegistration-like objects."""
    rows: list[dict[str, Any]] = []
    for reg in registrations:
        snap = dict(getattr(reg, "waifu_snapshot", None) or {})
        stats = normalize_day_stats(getattr(reg, "day_stats_json", None))
        uid = int(getattr(reg, "user_id"))
        username = (snap.get("username") or "").strip().lstrip("@") or None
        share = chat_message_share_pct(int(stats["msg_total"]), chat_msg_total)
        score = composite_activity_score(
            msg_total=int(stats["msg_total"]),
            damage_total=int(stats["damage_total"]),
            chat_share_pct=share,
        )
        rows.append(
            {
                "user_id": uid,
                "username": username,
                "name": snap.get("name") or f"Игрок {uid}",
                "level": int(snap.get("level") or 1),
                "perfection_level": int(snap.get("perfection_level") or 0),
                "gear_score": int(snap.get("gear_score") or 0),
                "msg_total": int(stats["msg_total"]),
                "by_type": dict(stats["by_type"]),
                "damage_total": int(stats["damage_total"]),
                "text_chars": int(stats["text_chars"]),
                "chat_share_pct": share,
                "score": score,
            }
        )
    return rows


def format_type_breakdown_ru(by_type: dict[str, int]) -> str:
    labels = {
        "text": "текст",
        "photo": "фото",
        "sticker": "стикеры",
        "animation": "GIF",
        "video": "видео",
        "voice": "войс",
        "audio": "аудио",
        "document": "дока",
        "link": "ссылки",
        "other": "прочее",
    }
    parts = []
    for k in MSG_TYPE_KEYS:
        n = int(by_type.get(k) or 0)
        if n > 0:
            parts.append(f"{labels.get(k, k)} {n}")
    return ", ".join(parts) if parts else "—"


def format_mention(username: str | None, user_id: int) -> str:
    if username:
        return f"@{username.lstrip('@')}"
    return f'<a href="tg://user?id={int(user_id)}">id{int(user_id)}</a>'
