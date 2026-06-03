#!/usr/bin/env python3
"""Fallback flavor_ru without API (template pools). For production lore use generate_item_flavor_llm.py."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.item_base_catalog import load_item_base_catalog  # noqa: E402

ROOT = SCRIPTS_DIR.parent
OUT_PATH = ROOT / "scripts" / "data" / "item_base_flavor_ru.json"

_SLOT_MOOD: dict[str, list[str]] = {
    "weapon": [
        "В руках опытного бойца ощущается как продолжение воли.",
        "Кузнец оставил на стали едва заметную руну — будто предмет помнит первый удар.",
        "Говорят, такое оружие не любит пустых угроз: оно ждёт дела.",
    ],
    "armor": [
        "Ткань и металл сшиты так, будто доспех дышит вместе с владельцем.",
        "На подкладке выцветшая метка гильдии — знак, что вещь видела не одну осаду.",
        "Носят его не ради блеска: каждая царапина на латах — чужая история.",
    ],
    "ring": [
        "Камень в оправе тускнеет, пока кольцо не найдёт своего хозяина.",
        "Кольцо холодит палец — словно напоминает о долге, который ещё не назван.",
        "Внутри оправы спрятан волосок серебряной нити; старики шепчут о защите от сглаза.",
    ],
    "amulet": [
        "Амулет тихо звенит у груди, когда рядом туман сгущается.",
        "На обороте выгравирован символ, который понимают только те, кто уже видел Грань.",
        "Носитель чувствует лёгкое тепло — будто кто-то невидимый кивает в знак согласия.",
    ],
}

_TIER_TONE: dict[int, str] = {
    1: "Скромная вещь для первых дорог.",
    2: "Уже не игрушка — проверена на мелких стычках.",
    3: "Мастера на базарах узнают подобные по почерку ковки.",
    4: "Такие носят те, кто перестал считать удачу случайностью.",
    5: "В караванах за неё торгуются всерьёз.",
    6: "Редкость для отрядов, что не возвращаются с пустыми руками.",
    7: "Слухи о подобных доходят до стен Каменного пояса раньше самих вещей.",
    8: "Кузнецы молчат о технологии — будто боятся испортить заказ.",
    9: "Пепельные степи помнят имена тех, кто умирал, не снимая это с плеч.",
    10: "Граница миров тонка; такие предметы кажутся сшитыми из двух реальностей.",
}

_NAME_HOOKS: dict[str, str] = {
    "экскалибур": "Свет стекает по лезвию, когда рядом нет лжи.",
    "теневое жало": "Клинок поглощает отблеск факелов — удобно для ночных троп.",
    "звёздный лук": "Тетива поёт тихо, будто натянута на невидимую созвездие.",
    "топор бури": "Воздух вокруг рукояти вибрирует, как перед грозой.",
    "рунный": "Руны теплеют только под чужой кровью — или так утверждают снайперы.",
}


def _pick(pool: list[str], key: str) -> str:
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return pool[h % len(pool)]


def _flavor_for(name: str, item_type: str, subtype: str, tier: int, idx: int) -> str:
    low = name.lower()
    hook = ""
    for k, v in _NAME_HOOKS.items():
        if k in low:
            hook = v
            break
    mood = _pick(_SLOT_MOOD.get(item_type, _SLOT_MOOD["weapon"]), f"{name}:{item_type}:{idx}")
    tone = _TIER_TONE.get(tier, _TIER_TONE[10])
    if hook:
        return f"{hook} {tone} {mood}"
    return f"«{name}» — {tone} {mood}"


def main() -> None:
    items = load_item_base_catalog()
    out: dict[str, str] = {}
    seen_text: set[str] = set()
    for it in items:
        text = _flavor_for(it["name"], it["item_type"], it["subtype"], it["tier"], it["id"])
        n = 1
        base = text
        while text in seen_text:
            n += 1
            text = f"{base} (вариант {n})"
        seen_text.add(text)
        out[str(it["id"])] = text
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} flavors to {OUT_PATH}")


if __name__ == "__main__":
    main()
