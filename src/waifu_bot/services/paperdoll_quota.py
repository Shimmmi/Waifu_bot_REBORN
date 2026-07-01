"""Paper-doll generation quota for main waifu (free first + admin-granted bonus)."""

from __future__ import annotations

from typing import Any


def _has_paperdoll_image(main: Any) -> bool:
    return bool((getattr(main, "paperdoll_image_data", None) or "").strip())


def paperdoll_generations_remaining(main: Any) -> int:
    bonus = int(getattr(main, "paperdoll_bonus_generations", 0) or 0)
    if not _has_paperdoll_image(main):
        return 1 + bonus
    return bonus


def consume_paperdoll_generation(main: Any, *, had_image_before: bool) -> None:
    """Spend one generation; first free use (no image before) does not debit bonus."""
    if had_image_before:
        bonus = int(getattr(main, "paperdoll_bonus_generations", 0) or 0)
        main.paperdoll_bonus_generations = max(0, bonus - 1)
