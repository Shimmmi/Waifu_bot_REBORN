"""Privacy edge for user chat messages.

Contract:
- Persist / log only MessageSignals (lengths, media meta, ids).
- EphemeralText may be passed into combat for legendary text_content bonuses
  and must never be written to DB, Redis, logs, or battle_state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import Message

from waifu_bot.game.constants import MediaType


# Keys that must never appear in persisted/serialized combat structures.
_FORBIDDEN_TEXT_KEYS = frozenset(
    {
        "text",
        "message_text",
        "text_preview",
        "caption",
        "body",
        "raw_text",
        "user_text",
    }
)


@dataclass(frozen=True, slots=True)
class MessageSignals:
    """Safe-to-persist metadata derived from a Telegram message."""

    length: int
    has_text: bool
    has_caption: bool
    media_type: MediaType


@dataclass(slots=True)
class EphemeralText:
    """In-memory user text for legendary bonuses; discard after the request."""

    value: str | None

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True, slots=True)
class PrivacyMessageView:
    signals: MessageSignals
    ephemeral: EphemeralText


def extract_from_telegram_message(
    message: Message,
    media_type: MediaType,
) -> PrivacyMessageView:
    """Boundary adapter: split signals (persistable) from ephemeral text."""
    text = message.text or None
    caption = message.caption or None
    body = text or caption
    length = len(body) if body else 0
    return PrivacyMessageView(
        signals=MessageSignals(
            length=length,
            has_text=bool(text),
            has_caption=bool(caption),
            media_type=media_type,
        ),
        ephemeral=EphemeralText(value=body),
    )


def signals_log_kwargs(signals: MessageSignals) -> dict[str, Any]:
    """Keyword args safe for logger.info / structured logs."""
    return {
        "text_len": signals.length,
        "has_text": signals.has_text,
        "has_caption": signals.has_caption,
        "media_type": int(signals.media_type),
    }


def assert_no_user_message_text(obj: Any, *, path: str = "root") -> None:
    """Raise AssertionError if a structure looks like it retained user chat text."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            key_s = str(key)
            child = f"{path}.{key_s}"
            if key_s in _FORBIDDEN_TEXT_KEYS and isinstance(val, str) and val.strip():
                raise AssertionError(f"user message text retained at {child}")
            assert_no_user_message_text(val, path=child)
    elif isinstance(obj, (list, tuple)):
        for i, val in enumerate(obj):
            assert_no_user_message_text(val, path=f"{path}[{i}]")


def strip_forbidden_text_keys(data: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow-cleaned copy without forbidden text keys (defense in depth)."""
    if not data:
        return {}
    out: dict[str, Any] = {}
    for key, val in data.items():
        if str(key) in _FORBIDDEN_TEXT_KEYS:
            continue
        if isinstance(val, dict):
            out[key] = strip_forbidden_text_keys(val)
        else:
            out[key] = val
    return out
