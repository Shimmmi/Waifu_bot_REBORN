"""Пошаговая трассировка расчёта урона в соло-бою (для BattleLog и WebApp)."""

from __future__ import annotations

from typing import Any

from waifu_bot.game.constants import MediaType


MAX_STEPS = 48
MAX_CONTRIB_STEPS = 40
MAX_LABEL_LEN = 220
TOTAL_REDUCE_CAP = 0.90


class DamageTrace:
    """Накапливает шаги без изменения математики — только наблюдение."""

    __slots__ = ("steps",)

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def _append(self, row: dict[str, Any]) -> None:
        if len(self.steps) >= MAX_STEPS:
            return
        self.steps.append(row)

    def base(self, source: str, label_ru: str, value: int) -> None:
        v = int(value)
        self._append(
            {
                "kind": "base",
                "source": source,
                "label_ru": label_ru[:MAX_LABEL_LEN],
                "value_before": 0,
                "value_after": v,
            }
        )

    def mult(
        self,
        source: str,
        label_ru: str,
        before: int,
        after: int,
        *,
        factor: float | None = None,
    ) -> int:
        b, a = int(before), int(after)
        row: dict[str, Any] = {
            "kind": "mult",
            "source": source,
            "label_ru": label_ru[:MAX_LABEL_LEN],
            "value_before": b,
            "value_after": a,
        }
        if factor is not None:
            row["factor"] = round(float(factor), 6)
        self._append(row)
        return a

    def add(
        self,
        source: str,
        label_ru: str,
        before: int,
        after: int,
        *,
        delta: int | None = None,
    ) -> int:
        b, a = int(before), int(after)
        row: dict[str, Any] = {
            "kind": "add",
            "source": source,
            "label_ru": label_ru[:MAX_LABEL_LEN],
            "value_before": b,
            "value_after": a,
        }
        if delta is not None:
            row["delta"] = int(delta)
        self._append(row)
        return a

    def result(self, source: str, label_ru: str, before: int, after: int) -> int:
        """Финальный итог / уклон / особый случай."""
        b, a = int(before), int(after)
        self._append(
            {
                "kind": "result",
                "source": source,
                "label_ru": label_ru[:MAX_LABEL_LEN],
                "value_before": b,
                "value_after": a,
            }
        )
        return a

    def contrib(
        self,
        source: str,
        label_ru: str,
        *,
        pct_add: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Вклад в аддитивный пул (не меняет урон до apply)."""
        n_contrib = sum(1 for s in self.steps if s.get("kind") == "contrib")
        if n_contrib >= MAX_CONTRIB_STEPS:
            return
        row: dict[str, Any] = {
            "kind": "contrib",
            "source": source,
            "label_ru": label_ru[:MAX_LABEL_LEN],
        }
        if pct_add is not None:
            row["pct_add"] = round(float(pct_add), 6)
        if meta:
            row["meta"] = meta
        self.steps.append(row)

    def cap_step(self, source: str, label_ru: str, *, meta: dict[str, Any] | None = None) -> None:
        row: dict[str, Any] = {
            "kind": "cap",
            "source": source,
            "label_ru": label_ru[:MAX_LABEL_LEN],
        }
        if meta:
            row["meta"] = meta
        self.steps.append(row)

    def extend_steps(self, rows: list[dict[str, Any]]) -> None:
        """Добавить готовые шаги (например базу урона из formulas)."""
        for row in rows:
            if len(self.steps) >= MAX_STEPS:
                return
            out = dict(row)
            if "label_ru" in out and isinstance(out["label_ru"], str):
                out["label_ru"] = out["label_ru"][:MAX_LABEL_LEN]
            self.steps.append(out)

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.steps)


LOG_MEDIA_LABEL_RU: dict[str, str] = {
    "text": "Текст",
    "link": "Ссылки",
    "sticker": "Стикеры",
    "photo": "Фото",
    "gif": "GIF",
    "audio": "Аудио",
    "video": "Видео",
    "voice": "Голосовые",
    "other": "Прочее",
}


def media_type_to_log_media_key(media_type: MediaType | None) -> str:
    """Стабильный ключ для группировки записей журнала (UI)."""
    if media_type is None:
        return "text"
    m: dict[int, str] = {
        int(MediaType.TEXT): "text",
        int(MediaType.LINK): "link",
        int(MediaType.STICKER): "sticker",
        int(MediaType.PHOTO): "photo",
        int(MediaType.GIF): "gif",
        int(MediaType.AUDIO): "audio",
        int(MediaType.VIDEO): "video",
        int(MediaType.VOICE): "voice",
    }
    return m.get(int(media_type), "other")


def append_passive_pool_trace(
    trace: DamageTrace,
    passive_rows: list[dict[str, Any]],
    effect_type: str,
    pool_label: str,
    combined_source: str,
    damage: int,
) -> int:
    """Каждый узел пассива — contrib; итоговый множитель — один mult (математика как сумма долей)."""
    matching = [r for r in passive_rows if str(r.get("effect_type") or "") == effect_type]
    if not matching:
        return damage
    total = sum(float(r.get("value") or 0) for r in matching)
    if total <= 0:
        return damage
    for r in matching:
        v = float(r.get("value") or 0)
        if v <= 0:
            continue
        nid = str(r.get("node_id") or "")
        name = str(r.get("name") or nid)
        lvl = int(r.get("level") or 0)
        trace.contrib(
            f"passive:{nid}:{effect_type}",
            f"Пассив «{name}» (ур. {lvl}): +{v * 100:.1f}% к {pool_label}",
            pct_add=v,
            meta={"node_id": nid, "level": lvl},
        )
    nb = int(damage)
    fac = 1.0 + total
    out = int(nb * fac)
    trace.mult(
        combined_source,
        f"Итого {pool_label}: +{total * 100:.1f}% (×{fac:.3f})",
        nb,
        out,
        factor=fac,
    )
    return out


def log_media_label_ru(log_media_key: str | None) -> str:
    k = (log_media_key or "other").strip() or "other"
    return LOG_MEDIA_LABEL_RU.get(k, LOG_MEDIA_LABEL_RU["other"])


def build_incoming_damage_breakdown_ru(
    *,
    raw_monster_damage: int,
    armor_total: int,
    armor_dr: float,
    waifu_level: int,
    total_reduce: float,
    damage_after_mitigation: int,
    final_armor_pct: float,
    damage_after_final_armor: int,
    low_hp_reduce_pct: float = 0.0,
    damage_after_low_hp_reduce: int | None = None,
    secondary_evade_triggered: bool,
    full_evade_triggered: bool,
    final_damage_taken: int,
    dmg_reduce_contribs: list[dict[str, Any]] | None = None,
    armor_slot_contribs: list[dict[str, Any]] | None = None,
    passive_armor_flat_contribs: list[dict[str, Any]] | None = None,
    passive_armor_pct_contribs: list[dict[str, Any]] | None = None,
    evade_contribs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Шаги ответного удара монстра (реторс при убийстве) — тот же формат, что damage_breakdown."""
    steps: list[dict[str, Any]] = []
    raw = int(raw_monster_damage)
    arm = int(armor_total)
    adr = float(armor_dr or 0.0)
    lvl = int(waifu_level or 1)
    dam = int(damage_after_mitigation)
    daf = int(damage_after_final_armor)
    dalhr = int(damage_after_low_hp_reduce if damage_after_low_hp_reduce is not None else daf)
    tr = float(total_reduce)
    fap = float(final_armor_pct or 0.0)
    lhrp = float(low_hp_reduce_pct or 0.0)

    steps.append(
        {
            "kind": "base",
            "source": "monster_retaliation",
            "label_ru": "Урон монстра (до снижения)",
            "value_before": 0,
            "value_after": raw,
        }
    )
    if armor_slot_contribs:
        for c in armor_slot_contribs:
            if c.get("kind") == "contrib":
                steps.append(dict(c))
    if passive_armor_flat_contribs:
        for c in passive_armor_flat_contribs:
            if c.get("kind") == "contrib":
                steps.append(dict(c))
    if passive_armor_pct_contribs:
        for c in passive_armor_pct_contribs:
            if c.get("kind") == "contrib":
                steps.append(dict(c))
    if arm > 0 or adr > 0:
        steps.append(
            {
                "kind": "contrib",
                "source": "armor_dr",
                "label_ru": f"Броня вайфу {arm} при ур.{lvl}: −{adr * 100:.1f}% (A/(A+K))",
                "pct_add": adr,
            }
        )
    dr_steps: list[dict[str, Any]] = []
    if dmg_reduce_contribs:
        dr_steps = [dict(c) for c in dmg_reduce_contribs if c.get("kind") == "contrib"]
        steps.extend(dr_steps)
    raw_sum = adr + sum(float(c.get("pct_add") or 0) for c in dr_steps)
    if raw_sum > tr + 1e-9:
        steps.append(
            {
                "kind": "cap",
                "source": "cap:total_reduce_90",
                "label_ru": (
                    f"Потолок снижения {TOTAL_REDUCE_CAP * 100:.0f}%: "
                    f"сумма источников {raw_sum * 100:.1f}%, учтено {tr * 100:.1f}%, "
                    f"отброшено {(raw_sum - tr) * 100:.1f}%"
                ),
                "meta": {"raw_sum": raw_sum, "applied": tr},
            }
        )
    fac_mit = max(0.0, min(1.0, 1.0 - tr))
    steps.append(
        {
            "kind": "mult",
            "source": "mitigation_apply",
            "label_ru": f"Применение пула снижения: −{tr * 100:.1f}% урона",
            "value_before": raw,
            "value_after": dam,
            "factor": round(fac_mit, 6),
        }
    )
    if fap > 0:
        fac_fa = max(0.0, min(1.0, 1.0 - fap / 100.0))
        steps.append(
            {
                "kind": "mult",
                "source": "hidden_final_armor",
                "label_ru": f"Скрытая финальная броня: −{fap:.0f}%",
                "value_before": dam,
                "value_after": daf,
                "factor": round(fac_fa, 6),
            }
        )
    before_ev = daf
    if lhrp > 0 and dalhr != daf:
        fac_lhr = max(0.0, min(1.0, 1.0 - lhrp / 100.0))
        steps.append(
            {
                "kind": "mult",
                "source": "hidden_low_hp_reduce",
                "label_ru": f"Скрытый «Выживший»: снижение урона при низком HP −{lhrp:.0f}%",
                "value_before": daf,
                "value_after": dalhr,
                "factor": round(fac_lhr, 6),
            }
        )
        before_ev = dalhr
    elif lhrp > 0 and dalhr == daf and daf != dam:
        before_ev = dalhr
    if evade_contribs and (secondary_evade_triggered or full_evade_triggered):
        for c in evade_contribs:
            if c.get("kind") == "contrib":
                steps.append(dict(c))
    if secondary_evade_triggered:
        steps.append(
            {
                "kind": "result",
                "source": "secondary_evade",
                "label_ru": "Сработало уклонение (ЛОВ, экипировка, пассивы)",
                "value_before": before_ev,
                "value_after": 0,
            }
        )
    elif full_evade_triggered:
        steps.append(
            {
                "kind": "result",
                "source": "full_evade",
                "label_ru": "Полное уклонение (пассив)",
                "value_before": before_ev,
                "value_after": 0,
            }
        )
    else:
        fd = int(final_damage_taken)
        steps.append(
            {
                "kind": "result",
                "source": "hp_loss",
                "label_ru": "Списано с HP вайфу",
                "value_before": before_ev,
                "value_after": fd,
            }
        )
    return steps


def build_incoming_damage_summary_ru(*, damage_taken: int, monster_name: str | None = None) -> str:
    name = (monster_name or "").strip() or "Монстр"
    d = int(damage_taken)
    if d <= 0:
        return f"{name}: ответный удар, урон по вайфу 0."
    return f"{name}: ответный удар, {d} урона по вайфу."


def build_damage_summary_ru(
    *,
    damage: int,
    is_crit: bool,
    monster_dodged: bool,
    monster_media_immune: bool = False,
    monster_name: str | None = None,
) -> str:
    """Одна строка для компактного UI."""
    name = (monster_name or "").strip() or "цель"
    if monster_dodged:
        return f"{name}: уклонение монстра (аффикс), урон 0."
    if monster_media_immune:
        return f"{name}: иммунитет к типу сообщения, урон 0."
    if damage <= 0:
        return f"{name}: урон 0."
    crit_s = ", критический удар" if is_crit else ""
    return f"{name}: {damage} урона{crit_s}."

