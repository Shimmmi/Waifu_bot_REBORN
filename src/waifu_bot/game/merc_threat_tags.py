"""Universal threat tags for Operations + Arena (no creature-specific counters)."""
from __future__ import annotations

THREAT_TAGS: tuple[str, ...] = (
    "pressure",
    "burst",
    "sustain",
    "barrier",
    "attrition",
    "ambush",
    "control",
    "cleanse_need",
    "tempo",
    "pierce",
    "antiheal",
    "focus_fire",
)

THREAT_TAG_LABELS_RU: dict[str, str] = {
    "pressure": "Натиск",
    "burst": "Взрыв",
    "sustain": "Стойкость",
    "barrier": "Барьер",
    "attrition": "Истощение",
    "ambush": "Засада",
    "control": "Контроль",
    "cleanse_need": "Проклятие",
    "tempo": "Темп",
    "pierce": "Пробитие",
    "antiheal": "Антихил",
    "focus_fire": "Фокус",
}

# Cap resist vs one tag from all perks on a unit
TAG_RESIST_CAP = 0.55
