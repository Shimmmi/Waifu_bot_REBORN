"""Affix display name LLM batch: prompts, parsing, validation, legacy copy."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from passive_node_labels import passive_node_label_ru

# Import after sys.path includes src in generate script
PREFIX_MAX_LEN = 24
SUFFIX_MAX_LEN = 40
_NAME_RE = re.compile(r"^[\u0400-\u04FF\u0450-\u045F\-]+$")

FORBIDDEN_CLICHES = frozenset(
    {
        "наставнический",
        "мастерский",
        "просветляющий",
        "трансцендентный",
    }
)

_PREFIX_ADJECTIVES = [
    "Мощный",
    "Грозный",
    "Сокрушительный",
    "Меткий",
    "Стремительный",
    "Мудрый",
    "Проницательный",
    "Крепкий",
    "Несокрушимый",
    "Очаровательный",
    "Удачливый",
    "Рубящий",
    "Дробящий",
    "Зачарованный",
    "Мистический",
    "Острый",
    "Яростный",
    "Усиленный",
    "Заострённый",
    "Проворный",
    "Кровный",
    "Богатый",
    "Искательный",
    "Болтливый",
    "Звучащий",
    "Разящий",
    "Карающий",
    "Безжалостный",
    "Неуловимый",
    "Эфирный",
    "Всеведущий",
    "Непокорный",
    "Великолепный",
    "Благословенный",
    "Снайперский",
    "Арканный",
    "Титанический",
    "Божественный",
    "Молниеносный",
    "Жестокий",
    "Убийственный",
    "Фантомный",
    "Реликтовый",
    "Сокровищный",
    "Вихревой",
    "Ледяной",
    "Пылающий",
    "Теневой",
    "Рунический",
    "Клинковый",
    "Штормовой",
    "Звёздный",
    "Пламенный",
    "Глубинный",
    "Высокий",
    "Древний",
    "Суровый",
    "Безумный",
    "Хитрый",
    "Свирепый",
    "Бесстрашный",
    "Мстительный",
    "Коварный",
    "Беспощадный",
    "Величественный",
    "Грозовой",
    "Мрачный",
    "Сияющий",
    "Кристальный",
    "Ядовитый",
    "Костяной",
    "Кровавый",
    "Пылающий",
    "Лунный",
    "Солнечный",
    "Бездонный",
    "Громовой",
    "Ледокол",
    "Стальной",
    "Медный",
    "Серебряный",
    "Золотой",
    "Бронзовый",
    "Гранитный",
    "Мраморный",
    "Обсидиановый",
    "Пепельный",
    "Угольный",
    "Багровый",
    "Лазурный",
    "Изумрудный",
    "Рубиновый",
]

_STEM_A = (
    "Тен", "Рун", "Клин", "Ост", "Гром", "Лед", "Пыл", "Жар", "Скал", "Вих",
    "Кров", "Дух", "Яр", "Сур", "Лун", "Сол", "Бур", "Штор", "Кост", "Яд",
)
_STEM_B = ("овый", "евый", "иный", "анный", "енный", "ский", "цкий", "чный", "рный", "тный")


def _expanded_prefix_adjective_pool() -> list[str]:
    pool: list[str] = list(_PREFIX_ADJECTIVES)
    seen = {x.lower() for x in pool}
    for a in _STEM_A:
        for b in _STEM_B:
            w = a + b
            if w.lower() not in seen and _NAME_RE.match(w):
                seen.add(w.lower())
                pool.append(w)
    for i, x in enumerate(list(_PREFIX_ADJECTIVES)):
        for y in _PREFIX_ADJECTIVES[i + 1 : i + 6]:
            w = (x[:4] + y[:5]).capitalize()
            if len(w) >= 7 and w.lower() not in seen and _NAME_RE.match(w):
                seen.add(w.lower())
                pool.append(w)
    return pool

_SUFFIX_TIER_EPITHETS = [
    "ученика",
    "подмастерья",
    "адепта",
    "знатока",
    "эксперта",
    "мастера",
    "наставника",
    "архимастера",
    "парадигмы",
    "бесконечности",
]


def load_affix_catalog(data_dir: Path) -> tuple[list[dict], dict[str, list[int]]]:
    fams = json.loads((data_dir / "diablo_affix_families.json").read_text(encoding="utf-8"))
    tiers = json.loads((data_dir / "diablo_affix_family_tiers.json").read_text(encoding="utf-8"))
    tiers_by_family: dict[str, list[int]] = defaultdict(list)
    for row in tiers:
        fid = str(row.get("family_id") or "")
        t = int(row.get("affix_tier") or 0)
        if fid and t > 0 and t not in tiers_by_family[fid]:
            tiers_by_family[fid].append(t)
    for fid in tiers_by_family:
        tiers_by_family[fid].sort()
    return fams, dict(tiers_by_family)


def _legacy_prefix(stat: str, tier: int) -> str:
    from waifu_bot.game.affix_display_names import _resolve_prefix_name_ru_legacy

    return _resolve_prefix_name_ru_legacy(stat, tier)


def _legacy_suffix(family_id: str, tier: int) -> str:
    from waifu_bot.game.affix_display_names import _resolve_suffix_name_ru_legacy

    return _resolve_suffix_name_ru_legacy(family_id, tier)


def copy_legacy_names(
    fams: list[dict], tiers_by_family: dict[str, list[int]]
) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fam in fams:
        fid = str(fam.get("family_id") or "")
        if not fid:
            continue
        kind = str(fam.get("kind") or "").lower()
        ek = str(fam.get("effect_key") or "")
        tier_list = tiers_by_family.get(fid) or []
        if not tier_list:
            continue
        per: dict[str, str] = {}
        for t in tier_list:
            if kind == "suffix":
                per[str(t)] = _legacy_suffix(fid, t)
            else:
                per[str(t)] = _legacy_prefix(ek, t)
        out[fid] = per
    return out


def _family_hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def _label_genitive_word(label: str) -> str:
    w = (label or "").strip().split()[0]
    if not w:
        return "навыка"
    low = w.lower()
    if low.endswith("ость") or low.endswith("ство"):
        return low
    if low.endswith("а") or low.endswith("я"):
        return low[:-1] + "и" if len(low) > 2 else low
    if low.endswith("ь"):
        return low[:-1] + "и"
    if low.endswith("й"):
        return low[:-1] + "я"
    return low + "а"


def synthesize_passive_unique_names(
    fams: list[dict], tiers_by_family: dict[str, list[int]]
) -> dict[str, dict[str, str]]:
    """Deterministic unique passive names (no LLM) when API unavailable."""
    out: dict[str, dict[str, str]] = {}
    used: set[str] = set()
    passive_fams = sorted(
        [
            f
            for f in fams
            if "passive" in str(f.get("family_id") or "")
            or str(f.get("effect_key") or "").lower().startswith("passive_")
        ],
        key=lambda f: str(f.get("family_id") or ""),
    )
    adj_pool = _expanded_prefix_adjective_pool()
    adj_i = 0
    for fam in passive_fams:
        fid = str(fam.get("family_id") or "")
        kind = str(fam.get("kind") or "").lower()
        ek = str(fam.get("effect_key") or "")
        node_label = passive_node_label_ru(fid, ek) or fid
        gen = _label_genitive_word(node_label)
        tier_list = tiers_by_family.get(fid) or []
        per: dict[str, str] = {}
        for t in tier_list:
            if kind == "suffix":
                ep = _SUFFIX_TIER_EPITHETS[min(t - 1, 9)]
                name = f"{ep} {gen}".strip()
            else:
                name = ""
                while adj_i < len(adj_pool):
                    cand = adj_pool[adj_i]
                    adj_i += 1
                    if cand.lower() not in used:
                        name = cand
                        break
                if not name:
                    name = f"Рун{t}"
            used.add(name.lower())
            per[str(t)] = name
        if per:
            out[fid] = per
    return out


def build_system_prompt(forbidden_sample: list[str]) -> str:
    banned = ", ".join(forbidden_sample[:40]) if forbidden_sample else "—"
    return (
        "Ты — нейминг-редактор Diablo-like RPG (Waifu Bot). Пиши на русском.\n"
        "Для каждого семейства аффиксов и каждого tier (1–10) задай ОДНО короткое имя.\n"
        "Префикс (kind=prefix): одно прилагательное в мужском роде, именительный падеж "
        "(пример: «Меткий», «Грозный»). Без пробелов.\n"
        "Суффикс (kind=suffix): фраза в родительном падеже после названия предмета "
        "(пример: «ученика удара», «убийцы нежити»). Можно 1–4 слова.\n"
        "Тон: тёмное фэнтези. Без юмора, без англицизмов, без цифр.\n"
        "Tier 1–3 — проще; 7–10 — эпичнее.\n"
        "Для пассивных навыков привязывай имя к node_label_ru, не пиши общее «Наставнический».\n"
        "Не повторяй строки внутри ответа. Избегай уже занятых имён: "
        f"{banned}.\n"
        "Ответ — только JSON-объект без markdown."
    )


def build_user_prompt(batch: list[dict]) -> str:
    payload = [
        {
            "family_id": it["family_id"],
            "kind": it["kind"],
            "effect_key": it["effect_key"],
            "node_label_ru": it.get("node_label_ru"),
            "tiers": it["tiers"],
        }
        for it in batch
    ]
    ids = [it["family_id"] for it in batch]
    return (
        "Сгенерируй display names для семейств аффиксов.\n"
        f"family_id в ответе: {', '.join(ids)}\n"
        "Формат ответа:\n"
        '{"p_passive_lvl_w_bash": {"1": "Разящий", "2": "...", "10": "..."}, ...}\n'
        "Ключи tier — строки \"1\"..\"10\".\n\n"
        f"Данные:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def validate_name(name: str, *, kind: str) -> str | None:
    s = str(name or "").strip()
    if not s:
        return "empty"
    if len(s) > (PREFIX_MAX_LEN if kind == "prefix" else SUFFIX_MAX_LEN):
        return "too_long"
    if kind == "suffix":
        parts = s.split()
        if not parts or not all(_NAME_RE.match(p) for p in parts):
            return "invalid_chars"
    elif not _NAME_RE.match(s):
        return "invalid_chars"
    if kind == "prefix" and " " in s:
        return "prefix_has_space"
    if s.lower() in FORBIDDEN_CLICHES:
        return "cliche"
    return None


def parse_names_response(
    raw: str,
    expected_family_ids: list[str],
    *,
    used_names: set[str],
) -> dict[str, dict[str, str]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    out: dict[str, dict[str, str]] = {}
    for fid in expected_family_ids:
        block = data.get(fid)
        if not isinstance(block, dict):
            raise ValueError(f"missing family_id {fid}")
        per: dict[str, str] = {}
        for k, v in block.items():
            tier = str(int(k))
            val = str(v or "").strip()
            if not val:
                continue
            kind = "suffix" if fid.startswith("s_") else "prefix"
            err = validate_name(val, kind=kind)
            if err:
                raise ValueError(f"{fid} tier {tier}: {err}")
            low = val.lower()
            if low in used_names:
                raise ValueError(f"duplicate name: {val}")
            used_names.add(low)
            per[tier] = val
        if not per:
            raise ValueError(f"empty tiers for {fid}")
        out[fid] = per
    return out


def merge_name_maps(
    base: dict[str, dict[str, str]], patch: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    merged = {k: dict(v) for k, v in base.items()}
    for fid, tiers in patch.items():
        merged[fid] = dict(tiers)
    return merged


def collect_used_names(names: dict[str, dict[str, str]]) -> set[str]:
    used: set[str] = set()
    for per in names.values():
        for v in per.values():
            used.add(str(v).lower())
    return used


def families_for_llm(
    fams: list[dict],
    tiers_by_family: dict[str, list[int]],
    *,
    only_passive: bool = False,
    only_family: str | None = None,
    existing: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    existing = existing or {}
    rows: list[dict] = []
    for fam in fams:
        fid = str(fam.get("family_id") or "")
        if not fid or fid in existing:
            continue
        if only_family and fid != only_family:
            continue
        ek = str(fam.get("effect_key") or "")
        is_passive = "passive" in fid or ek.lower().startswith("passive_")
        if only_passive and not is_passive:
            continue
        tiers = tiers_by_family.get(fid) or []
        if not tiers:
            continue
        rows.append(
            {
                "family_id": fid,
                "kind": str(fam.get("kind") or ""),
                "effect_key": ek,
                "node_label_ru": passive_node_label_ru(fid, ek),
                "tiers": tiers,
            }
        )
    return rows


def save_names_out(
    path: Path,
    names: dict[str, dict[str, str]],
    *,
    model: str = "",
    provider: str = "",
) -> None:
    from datetime import datetime, timezone

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "provider": provider,
        "names": {fid: dict(sorted(per.items(), key=lambda x: int(x[0]))) for fid, per in sorted(names.items())},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_names_out(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    names = raw.get("names") if isinstance(raw, dict) else raw
    if not isinstance(names, dict):
        return {}
    return {
        str(fid): {str(k): str(v) for k, v in per.items()}
        for fid, per in names.items()
        if isinstance(per, dict)
    }
