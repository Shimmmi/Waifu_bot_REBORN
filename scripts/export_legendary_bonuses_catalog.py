#!/usr/bin/env python3
"""Export legendary_bonuses pool (316) to info/legendary_bonuses_catalog.md."""

from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _legacy_rows() -> list[tuple]:
    m = _load_module(ROOT / "alembic/versions/0091_legendary_bonuses_core.py", "m0091")
    return [(k, n, d, g, c, p, True, "legacy") for k, n, d, g, c, p in m._bonus_rows()]


def _pool_rows() -> list[tuple]:
    m105 = _load_module(ROOT / "alembic/versions/0105_legendary_bonus_pool.py", "m0105")
    m106 = _load_module(
        ROOT / "alembic/versions/0106_activate_text_content_bonuses.py", "m0106"
    )
    activated = set(m106._TEXT_CONTENT_KEYS)
    return [
        (
            k,
            n,
            d,
            g,
            c,
            p,
            active or k in activated,
            str((p or {}).get("handler") or "generic"),
        )
        for k, n, d, g, c, p, active in m105._bonus_rows()
    ]


FAMILY_LABELS = {
    "media_type": "1. Тип сообщения",
    "time_calendar": "2. Время суток / календарь",
    "tempo": "3. Темп и паузы",
    "text_content": "4. Контент текста",
    "combo_counter": "5. Комбо, серии и счётчики",
    "crit": "6. Крит-механики",
    "hp_state": "7. HP-состояния",
    "reactive": "8. Реактивные / защитные",
    "dungeon_progress": "9. Прогресс боя / данжа",
    "economy": "10. Экономика / лут",
    "meta_inventory": "11. Мета / инвентарь",
    "exotic": "12. Экзотика / жёсткие условия",
    "legacy": "0. Legacy (0091, bespoke handlers)",
}


def main() -> None:
    rows = _legacy_rows() + _pool_rows()
    assert len(rows) == 316, f"expected 316 rows, got {len(rows)}"
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys)), "duplicate bonus_key"

    by_group: dict[str, list] = defaultdict(list)
    for row in rows:
        by_group[row[3]].append(row)

    out = ROOT / "info/legendary_bonuses_catalog.md"
    lines: list[str] = [
        "# Каталог легендарных бонусов (пул 316)",
        "",
        "Бонусы привязаны к шаблонам через `legendary_bonus_ids` (миграция `0107`, матрица `legendary_bonus_distribution.md`).",
        "",
        "**Источники:** `0091_legendary_bonuses_core.py` (46 legacy), `0105_legendary_bonus_pool.py` (+270 generic).",
        "**Handlers:** legacy → `BONUS_HANDLERS[bonus_key]`; pool → `GENERIC_HANDLERS[params.handler]` в `generic.py`.",
        "",
        f"**Всего:** {len(rows)} бонусов · **активных:** {sum(1 for r in rows if r[6])} · **неактивных:** {sum(1 for r in rows if not r[6])}",
        "",
        "## Сводка по семействам",
        "",
        "| trigger_group | шт. | handler |",
        "|---------------|-----|---------|",
    ]

    order = ["legacy"] + [
        "media_type",
        "time_calendar",
        "tempo",
        "text_content",
        "combo_counter",
        "crit",
        "hp_state",
        "reactive",
        "dungeon_progress",
        "economy",
        "meta_inventory",
        "exotic",
    ]
    for grp in order:
        if grp not in by_group:
            continue
        items = by_group[grp]
        handler = items[0][7] if grp == "legacy" else "generic primitives"
        lines.append(f"| {grp} | {len(items)} | {handler} |")

    lines.extend(["", "---", ""])

    for grp in order:
        if grp not in by_group:
            continue
        label = FAMILY_LABELS.get(grp, grp)
        lines.append(f"## {label} (`{grp}`)")
        lines.append("")
        lines.append("| bonus_key | name | complexity | active | handler | description |")
        lines.append("|-----------|------|------------|--------|---------|-------------|")
        for k, n, d, _g, c, p, active, handler in sorted(by_group[grp], key=lambda r: r[0]):
            act = "yes" if active else "no"
            desc = d.replace("|", "\\|")
            lines.append(f"| {k} | {n} | {c} | {act} | {handler} | {desc} |")
        lines.append("")
        lines.append("<details><summary>params JSON</summary>")
        lines.append("")
        lines.append("```json")
        payload = {
            r[0]: {"handler": r[7], "params": r[5], "active": r[6]}
            for r in sorted(by_group[grp], key=lambda r: r[0])
        }
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(rows)} bonuses)")


if __name__ == "__main__":
    main()
