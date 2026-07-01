"""Affix display name LLM batch: prompts, parsing, validation, legacy copy."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from passive_node_labels import passive_node_genitive_ru, passive_node_label_ru

# Import after sys.path includes src in generate script
PREFIX_MAX_LEN = 24
SUFFIX_MAX_LEN = 40
_NAME_RE = re.compile(r"^[\u0400-\u04FF\u0450-\u045F\-]+$")
_LATIN_RE = re.compile(r"[A-Za-z_]")
_PORTMANTEAU_RE = re.compile(
    r"^[А-Яа-яЁё]{4,12}(?:остр|зач|руб|дроб|мист|ярост|удач|очар|дух|лун|сур|кров|рубя|зача|дробз|очарз|удачр)",
    re.IGNORECASE,
)
_EFFECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.IGNORECASE)
_FAMILY_ID_RE = re.compile(r"^(p|s)_[a-z0-9_]+$", re.IGNORECASE)

# Never overwrite via LLM/synthesize — legacy maps are authoritative.
ALWAYS_LEGACY_FAMILIES: frozenset[str] = frozenset(
    {
        "p_merchant_cut",
        "s_merchant_cut",
        "s_dmg_magic",
        "s_dmg_melee",
        "s_dmg_ranged",
        "s_media_audio",
        "s_media_gif",
        "s_media_link",
        "s_media_photo",
        "s_media_sticker",
        "s_media_text",
        "s_media_video",
        "s_media_voice",
        "p_dmg_magic",
        "p_media_link",
    }
)

BROKEN_LEGACY_FAMILIES: tuple[str, ...] = tuple(sorted(ALWAYS_LEGACY_FAMILIES))

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


def _expanded_prefix_adjective_pool(*, include_portmanteau: bool = False) -> list[str]:
    """Base adjective pool; portmanteau stems disabled by default (garbage names)."""
    pool: list[str] = list(_PREFIX_ADJECTIVES)
    seen = {x.lower() for x in pool}
    if not include_portmanteau:
        return pool
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
    fams: list[dict],
    tiers_by_family: dict[str, list[int]],
    *,
    skip_passive: bool = False,
    only_families: set[str] | frozenset[str] | None = None,
) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fam in fams:
        fid = str(fam.get("family_id") or "")
        if not fid:
            continue
        if only_families is not None and fid not in only_families:
            continue
        kind = str(fam.get("kind") or "").lower()
        ek = str(fam.get("effect_key") or "")
        if skip_passive and _is_passive_family_id(fid, ek):
            continue
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
    """Fallback genitive; prefer passive_node_genitive_ru()."""
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


def _is_passive_family_id(family_id: str, effect_key: str = "") -> bool:
    fid = str(family_id or "")
    ek = str(effect_key or "").lower()
    return "passive" in fid or ek.startswith("passive_")


def strip_family_names(
    names: dict[str, dict[str, str]], family_ids: set[str]
) -> dict[str, dict[str, str]]:
    return {k: v for k, v in names.items() if k not in family_ids}


def passive_family_ids(fams: list[dict]) -> set[str]:
    return {
        str(f.get("family_id") or "")
        for f in fams
        if _is_passive_family_id(str(f.get("family_id") or ""), str(f.get("effect_key") or ""))
    }


def synthesize_passive_unique_names(
    fams: list[dict],
    tiers_by_family: dict[str, list[int]],
    *,
    existing: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Deterministic unique passive names (no LLM) when API unavailable — no portmanteau."""
    import warnings

    warnings.warn(
        "synthesize_passive_unique_names: offline fallback only; use expert LLM for production",
        stacklevel=2,
    )
    existing = existing or {}
    out: dict[str, dict[str, str]] = {}
    passive_fams = sorted(
        [
            f
            for f in fams
            if _is_passive_family_id(str(f.get("family_id") or ""), str(f.get("effect_key") or ""))
        ],
        key=lambda f: str(f.get("family_id") or ""),
    )
    adj_pool = _expanded_prefix_adjective_pool(include_portmanteau=False)
    t1_used = collect_passive_t1_prefix_names(existing)
    for fam in passive_fams:
        fid = str(fam.get("family_id") or "")
        if is_always_legacy_family(fid):
            continue
        kind = str(fam.get("kind") or "").lower()
        ek = str(fam.get("effect_key") or "")
        gen = passive_node_genitive_ru(fid, ek) or _label_genitive_word(passive_node_label_ru(fid, ek) or fid)
        tier_list = tiers_by_family.get(fid) or []
        per: dict[str, str] = {}
        base_i = _family_hash(fid) % max(len(adj_pool), 1)
        for t_idx, t in enumerate(tier_list):
            if kind == "suffix":
                ep = _SUFFIX_TIER_EPITHETS[min(int(t) - 1, 9)]
                name = f"{ep} {gen}".strip()
            else:
                name = ""
                for off in range(len(adj_pool)):
                    cand = adj_pool[(base_i + t_idx + off) % len(adj_pool)]
                    low = cand.lower()
                    if int(t) == 1 and fid.startswith("p_passive") and low in t1_used:
                        continue
                    name = cand
                    break
                if not name:
                    name = f"Рун{t}"
            if kind != "suffix" and fid.startswith("p_passive") and str(t) == "1":
                t1_used.add(name.lower())
            per[str(t)] = name
        if per:
            out[fid] = per
    return out


def build_system_prompt(forbidden_sample: list[str]) -> str:
    banned = ", ".join(forbidden_sample[:40]) if forbidden_sample else "—"
    return (
        "Ты — нейминг-редактор Diablo-like RPG (Waifu Bot). Пиши на русском.\n"
        "Для каждого семейства аффиксов и каждого tier (1–10) задай ОДНО короткое имя.\n"
        "Префикс (kind=prefix): одно существующее русское прилагательное в мужском роде, "
        "именительный падеж (пример: «Меткий», «Закалённый», «Теневой»). Без пробелов.\n"
        "Суффикс (kind=suffix): фраза в родительном падеже после названия предмета "
        "(пример: «ученика удара», «мастера шага тени»). 2–5 слов, только кириллица.\n"
        "Для пассивных навыков: префикс отражает суть node_label_ru; суффикс — "
        "«{эпитет} {навыка в род.п.}», используй node_genitive_ru если задан.\n"
        "Запрещено: портманто и склеенные слоги, латиница, family_id, аббревиатуры "
        "(«кров.», «маг.», «трансценд.»), клише «Наставнический».\n"
        "Тон: тёмное фэнтези. Tier 1–3 — проще; 7–10 — эпичнее.\n"
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
            "node_genitive_ru": it.get("node_genitive_ru"),
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


def is_always_legacy_family(family_id: str) -> bool:
    return str(family_id or "") in ALWAYS_LEGACY_FAMILIES


def is_raw_affix_display_name(name: str, *, effect_key: str | None = None, family_id: str | None = None) -> bool:
    """True when stored/cached name is an untranslated effect_key or family_id placeholder."""
    s = str(name or "").strip()
    if not s:
        return False
    if family_id and s == family_id:
        return True
    if effect_key and s.lower() == str(effect_key).lower():
        return True
    if _FAMILY_ID_RE.match(s):
        return True
    if _EFFECT_KEY_RE.match(s):
        return True
    if _LATIN_RE.search(s) and "_" in s:
        return True
    return False


def validate_name(
    name: str, *, kind: str, effect_key: str | None = None, family_id: str | None = None
) -> str | None:
    s = str(name or "").strip()
    if not s:
        return "empty"
    if _LATIN_RE.search(s):
        return "latin"
    if len(s) > (PREFIX_MAX_LEN if kind == "prefix" else SUFFIX_MAX_LEN):
        return "too_long"
    if kind == "suffix":
        parts = s.split()
        if len(parts) < 1 or len(parts) > 5:
            return "suffix_word_count"
        if not parts or not all(_NAME_RE.match(p) for p in parts):
            return "invalid_chars"
        if ".а" in s.lower() or re.search(r"\.\s*[а-яё]", s.lower()):
            return "abbrev"
    elif not _NAME_RE.match(s):
        return "invalid_chars"
    if kind == "prefix" and " " in s:
        return "prefix_has_space"
    if s.lower() in FORBIDDEN_CLICHES:
        return "cliche"
    if _PORTMANTEAU_RE.match(s):
        return "portmanteau"
    if is_raw_affix_display_name(s, effect_key=effect_key, family_id=family_id):
        return "raw_key"
    return None


def parse_names_response(
    raw: str,
    expected_family_ids: list[str],
    *,
    used_names: set[str],
    name_owners: dict[str, str] | None = None,
    passive_t1_prefix_used: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    owners = dict(name_owners or {})
    t1_used = passive_t1_prefix_used if passive_t1_prefix_used is not None else None
    batch_seen: dict[str, str] = {}
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
            err = validate_name(val, kind=kind, family_id=fid)
            if err:
                raise ValueError(f"{fid} tier {tier}: {err}")
            low = val.lower()
            batch_owner = batch_seen.get(low)
            if batch_owner is not None and batch_owner != fid:
                raise ValueError(f"duplicate name: {val}")
            if t1_used is not None and kind == "prefix" and fid.startswith("p_passive") and tier == "1":
                if low in t1_used:
                    raise ValueError(f"duplicate name: {val}")
            elif t1_used is None:
                owner = owners.get(low)
                if owner is not None and owner != fid:
                    raise ValueError(f"duplicate name: {val}")
            batch_seen[low] = fid
            owners[low] = fid
            used_names.add(low)
            if t1_used is not None and kind == "prefix" and fid.startswith("p_passive") and tier == "1":
                t1_used.add(low)
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
        if is_always_legacy_family(fid) and fid in merged:
            continue
        merged[fid] = dict(tiers)
    return merged


def collect_passive_t1_prefix_names(names: dict[str, dict[str, str]]) -> set[str]:
    used: set[str] = set()
    for fid, per in names.items():
        if not str(fid).startswith("p_passive"):
            continue
        v = per.get("1")
        if v:
            used.add(str(v).lower())
    return used


def collect_used_names(
    names: dict[str, dict[str, str]], *, family_prefix: str | None = None
) -> set[str]:
    used: set[str] = set()
    for fid, per in names.items():
        if family_prefix and not str(fid).startswith(family_prefix):
            continue
        for v in per.values():
            used.add(str(v).lower())
    return used


def _name_owner_map(names: dict[str, dict[str, str]]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for fid, per in names.items():
        for v in per.values():
            low = str(v).lower()
            if low and low not in owners:
                owners[low] = str(fid)
    return owners


def families_for_llm(
    fams: list[dict],
    tiers_by_family: dict[str, list[int]],
    *,
    only_passive: bool = False,
    only_family: str | None = None,
    existing: dict[str, dict[str, str]] | None = None,
    force_regen: bool = False,
) -> list[dict]:
    existing = existing or {}
    rows: list[dict] = []
    for fam in fams:
        fid = str(fam.get("family_id") or "")
        if not fid or (fid in existing and not force_regen):
            continue
        if only_family and fid != only_family:
            continue
        if is_always_legacy_family(fid):
            continue
        ek = str(fam.get("effect_key") or "")
        is_passive = _is_passive_family_id(fid, ek)
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
                "node_genitive_ru": passive_node_genitive_ru(fid, ek),
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
