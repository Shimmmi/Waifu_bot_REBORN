"""Пассивное дерево навыков: дерево, изучение, сброс ветки."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.db.models import MainWaifu, PassiveSkillNode, Player, PlayerPassiveSkill
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map
from waifu_bot.services.waifu_hp import sync_waifu_max_hp

logger = logging.getLogger(__name__)

BRANCHES = ("warrior", "shadow", "sage")

# Эффекты, для которых значения за пределами таблицы не растут (баланс / шансы).
_PASSIVE_EFFECT_CAP_AT_TABLE_MAX: frozenset[str] = frozenset(
    {
        "instakill_chance",
        "revive_chance",
        "survive_chance",
        "full_evade_chance",
    }
)

_SESSION_PASSIVE_EXTRA_CACHE_KEY = "_cached_passive_node_level_extra"

_STAT_PASSIVE_NODE_LEVEL_ADD = "passive_node_level_add:"
_STAT_PASSIVE_BRANCH_LEVEL_ADD = "passive_branch_level_add:"
_STAT_PASSIVE_ALL_NODES = "passive_all_nodes_level_add"


def normalize_passive_level_affix_value(stat: str | None, raw: Any) -> int:
    """
    Целое значение аффикса «+N уровней» к пассивам.

    В тирах `p_/s_passive_branch_*` и `p_/s_passive_all` ошибочно стояли value_min/max
    как у урона (десятки–сотни). Чиним отображение и суммирование для уже выкинутых предметов.
    """
    s = str(stat or "").strip().lower()
    try:
        add = int(float(raw))
    except (TypeError, ValueError):
        return 0
    if add <= 0:
        return 0
    if not (
        s.startswith(_STAT_PASSIVE_NODE_LEVEL_ADD)
        or s.startswith(_STAT_PASSIVE_BRANCH_LEVEL_ADD)
        or s == _STAT_PASSIVE_ALL_NODES
    ):
        return add
    if add <= 8:
        return add
    if add < 25:
        return 1
    if add < 45:
        return 2
    if add < 75:
        return 3
    return 4


@dataclass
class PassiveEquipmentLevelBonuses:
    """Бонусы уровней пассивов с экипировки (целые уровни к эффективному уровню узла)."""

    nodes: dict[str, int] = field(default_factory=dict)
    branches: dict[str, int] = field(default_factory=dict)
    all_nodes: int = 0

    @classmethod
    def empty(cls) -> PassiveEquipmentLevelBonuses:
        return cls(nodes={}, branches={b: 0 for b in BRANCHES}, all_nodes=0)

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "branches": {b: int(self.branches.get(b, 0) or 0) for b in BRANCHES},
            "all_nodes": int(self.all_nodes or 0),
        }


def _coerce_equipment_bundle(data: Any) -> PassiveEquipmentLevelBonuses:
    """Кэш: новый формат или legacy (только словарь node_id -> add)."""
    if data is None:
        return PassiveEquipmentLevelBonuses.empty()
    if isinstance(data, PassiveEquipmentLevelBonuses):
        return data
    if not isinstance(data, dict):
        return PassiveEquipmentLevelBonuses.empty()
    if "nodes" in data or "branches" in data or "all_nodes" in data:
        nodes: dict[str, int] = {}
        for k, v in (data.get("nodes") or {}).items():
            nk = str(k).strip().lower()
            if not nk:
                continue
            try:
                nodes[nk] = nodes.get(nk, 0) + int(float(v))
            except (TypeError, ValueError):
                continue
        br_in = data.get("branches") or {}
        branches = {b: int(br_in.get(b, 0) or 0) for b in BRANCHES}
        return PassiveEquipmentLevelBonuses(
            nodes=nodes,
            branches=branches,
            all_nodes=int(data.get("all_nodes") or 0),
        )
    nodes_legacy: dict[str, int] = {}
    for k, v in data.items():
        nk = str(k).strip().lower()
        if not nk:
            continue
        try:
            nodes_legacy[nk] = nodes_legacy.get(nk, 0) + int(float(v))
        except (TypeError, ValueError):
            continue
    return PassiveEquipmentLevelBonuses(
        nodes=nodes_legacy,
        branches={b: 0 for b in BRANCHES},
        all_nodes=0,
    )


async def _waifu_level(session: AsyncSession, player_id: int) -> int:
    lv = await session.scalar(select(MainWaifu.level).where(MainWaifu.player_id == int(player_id)))
    return max(1, int(lv or 1))


async def _branch_points(session: AsyncSession, player_id: int) -> dict[str, int]:
    q = (
        select(PlayerPassiveSkill.level, PassiveSkillNode.branch)
        .join(PassiveSkillNode, PassiveSkillNode.id == PlayerPassiveSkill.node_id)
        .where(PlayerPassiveSkill.player_id == int(player_id))
    )
    rows = (await session.execute(q)).all()
    bp = {b: 0 for b in BRANCHES}
    for lvl, br in rows:
        if br in bp:
            bp[br] += int(lvl or 0)
    return bp


def _coerce_passive_effect_values(raw: Any) -> list[Any]:
    """JSONB / ORM иногда отдают строку или не-list; для extrapolate нужен список чисел."""
    if raw is None:
        return []
    data: Any = raw
    if isinstance(data, str):
        s = data.strip()
        if not s:
            return []
        try:
            data = json.loads(s)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    out: list[Any] = []
    for x in data:
        if x is None:
            continue
        if isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            out.append(x)
            continue
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            continue
    return out


def extrapolate_passive_effect_value(
    effect_values: list[Any] | None,
    level: int,
    effect_type: str,
) -> float | int | None:
    """
    Значение эффекта узла на уровне ``level`` (1-based).

    - Уровни 1..len(table) — из ``effect_values``.
    - Выше таблицы — линейная экстраполяция по шагу последних двух точек
      (пример: +5% / +10% / +15% → шаг +5% на уровень дальше).
    - Для типов из ``_PASSIVE_EFFECT_CAP_AT_TABLE_MAX`` — не выше последней
      ячейки таблицы (даже если снаряжение даёт «виртуальные» уровни).
    """
    if level <= 0:
        return None
    vals = _coerce_passive_effect_values(effect_values)
    if not vals:
        return None
    et = str(effect_type or "")
    n = len(vals)
    if et in _PASSIVE_EFFECT_CAP_AT_TABLE_MAX:
        idx = min(level, n) - 1
        if idx < 0:
            return None
        try:
            return vals[idx]
        except (IndexError, TypeError):
            return None

    if level <= n:
        try:
            return vals[level - 1]
        except (IndexError, TypeError):
            return None

    if n == 1:
        return vals[0]

    try:
        v_prev = float(vals[-2])
        v_last = float(vals[-1])
    except (TypeError, ValueError):
        return vals[-1]
    step = v_last - v_prev
    over = level - n
    out = v_last + step * float(over)

    if et in ("trade_flat", "nth_hit_crit", "main_stats_flat", "armor_flat"):
        if et == "nth_hit_crit":
            return max(1, int(round(out)))
        return int(round(out))
    return out


def _effect_value_at(node: PassiveSkillNode, current_level: int) -> float | int | None:
    """Только уровни внутри таблицы (для UI дерева без бонусов предметов)."""
    if current_level <= 0:
        return None
    return extrapolate_passive_effect_value(node.effect_values, current_level, str(node.effect_type or ""))


async def collect_passive_node_level_bonus_from_session(
    session: AsyncSession, player_id: int
) -> PassiveEquipmentLevelBonuses:
    """
    Суммарные «виртуальные уровни» с экипировки:

    - ``passive_node_level_add:<node_id>`` — к конкретному узлу;
    - ``passive_branch_level_add:<warrior|shadow|sage>`` — ко всем изученным узлам ветки;
    - ``passive_all_nodes_level_add`` — ко всем изученным узлам.

    Значения аффиксов — целые уровни (+1, +2, …).
    Вторичка из ``item_base_templates`` суммируется с заточкой (``+ enchant_sec_step * enchant_level``),
    как ``secondary_bonus_effective`` у предмета в инвентаре.
    """
    stmt = (
        select(m.InventoryAffix.stat, m.InventoryAffix.value)
        .join(m.InventoryItem, m.InventoryItem.id == m.InventoryAffix.inventory_item_id)
        .where(
            m.InventoryItem.player_id == int(player_id),
            m.InventoryItem.equipment_slot.isnot(None),
        )
    )
    nodes: dict[str, int] = {}
    branches: dict[str, int] = {b: 0 for b in BRANCHES}
    all_nodes = 0
    try:
        rows = (await session.execute(stmt)).all()
    except Exception:
        logger.exception("collect_passive_node_level_bonus: affix query failed player_id=%s", player_id)
        rows = []
    p_node = _STAT_PASSIVE_NODE_LEVEL_ADD
    p_branch = _STAT_PASSIVE_BRANCH_LEVEL_ADD
    for stat, val in rows:
        s = str(stat or "").strip().lower()
        add = normalize_passive_level_affix_value(stat, val)
        if add == 0:
            continue
        if s == _STAT_PASSIVE_ALL_NODES:
            all_nodes += add
        elif s.startswith(p_branch):
            br = s[len(p_branch) :].strip().lower()
            if br in branches:
                branches[br] = branches.get(br, 0) + add
        elif s.startswith(p_node):
            nid = s[len(p_node) :].strip().lower()
            if nid:
                nodes[nid] = nodes.get(nid, 0) + add

    # Passive secondaries from instance snapshot + affixes (fraction handled in combat query).
    try:
        tpl_rows = (
            await session.execute(
                text(
                    """
                    SELECT ii.secondary_bonus_type,
                           ii.secondary_bonus_value,
                           ibt.secondary_bonus_type AS template_secondary_type,
                           ibt.secondary_bonus_value AS template_secondary_value
                    FROM inventory_items ii
                    JOIN items i ON i.id = ii.item_id
                    LEFT JOIN item_base_templates ibt
                      ON btrim(ibt.name) = btrim(i.name)
                     AND ibt.tier = COALESCE(NULLIF(ii.tier, 0), i.tier)
                    WHERE ii.player_id = :pid
                      AND ii.equipment_slot IS NOT NULL
                    """
                ),
                {"pid": int(player_id)},
            )
        ).all()
    except Exception:
        tpl_rows = []

    from waifu_bot.game.item_secondary import is_passive_secondary_type

    for row in tpl_rows:
        sec_type = row[0] or row[2]
        sec_val = row[1] if row[0] is not None else row[3]
        if not sec_type or not is_passive_secondary_type(sec_type):
            continue
        try:
            base_sec = float(sec_val or 0.0)
        except (TypeError, ValueError):
            continue
        eff_sec = base_sec
        try:
            raw_add = int(round(eff_sec))
        except (TypeError, ValueError):
            continue
        s = str(sec_type or "").strip().lower()
        add = normalize_passive_level_affix_value(sec_type, raw_add)
        if add == 0:
            continue
        if s == _STAT_PASSIVE_ALL_NODES:
            all_nodes += add
        elif s.startswith(p_branch):
            br = s[len(p_branch) :].strip().lower()
            if br in branches:
                branches[br] = branches.get(br, 0) + add
        elif s.startswith(p_node):
            nid = s[len(p_node) :].strip().lower()
            if nid:
                nodes[nid] = nodes.get(nid, 0) + add

    return PassiveEquipmentLevelBonuses(nodes=nodes, branches=branches, all_nodes=all_nodes)


async def get_passive_skill_bonuses(
    session: AsyncSession,
    player_id: int,
    *,
    extra_node_levels: dict[str, int] | None = None,
    extra_branch_levels: dict[str, int] | None = None,
    extra_all_nodes_level: int | None = None,
    _skip_equipment_passive_levels: bool = False,
) -> dict[str, float]:
    """Суммарные эффекты пассивного дерева (значения из effect_values на текущем уровне узла).

    Доли (0.15 = +15%) складываются по одинаковому effect_type.
    ``armor_and_reduce`` даёт и броню, и снижение урона одним и тем же значением уровня.

    Бонусы уровней с экипировки (если не переданы явные overrides и не
    ``_skip_equipment_passive_levels``): ``passive_node_level_add:*``,
    ``passive_branch_level_add:*``, ``passive_all_nodes_level_add`` — кэшируются на сессии.

    Явные ``extra_node_levels`` / ``extra_branch_levels`` / ``extra_all_nodes_level``:
    если хотя бы один аргумент не ``None``, экипировка не читается; непереданные части
    считаются нулевыми.

    Для уровней выше длины ``effect_values`` применяется линейная экстраполяция (кроме
    шансов «воскрешения / выжить / инстакилл» — там потолок по последней ячейке таблицы).
    """
    explicit_override = (
        extra_node_levels is not None
        or extra_branch_levels is not None
        or extra_all_nodes_level is not None
    )
    bundle: PassiveEquipmentLevelBonuses
    if _skip_equipment_passive_levels:
        bundle = PassiveEquipmentLevelBonuses.empty()
    elif not explicit_override:
        cached = session.info.get(_SESSION_PASSIVE_EXTRA_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("player_id") == int(player_id):
            bundle = _coerce_equipment_bundle(cached.get("data"))
        else:
            bundle = await collect_passive_node_level_bonus_from_session(session, player_id)
            session.info[_SESSION_PASSIVE_EXTRA_CACHE_KEY] = {
                "player_id": int(player_id),
                "data": bundle.to_cache_dict(),
            }
    else:
        eb = extra_branch_levels or {}
        bundle = PassiveEquipmentLevelBonuses(
            nodes=dict(extra_node_levels or {}),
            branches={b: int(eb.get(b, 0) or 0) for b in BRANCHES},
            all_nodes=0 if extra_all_nodes_level is None else int(extra_all_nodes_level),
        )

    learned_rows = (
        await session.execute(select(PlayerPassiveSkill).where(PlayerPassiveSkill.player_id == int(player_id)))
    ).scalars().all()
    learned_map = {str(r.node_id).strip().lower(): int(r.level or 0) for r in learned_rows}

    all_skill_nodes = (await session.execute(select(PassiveSkillNode))).scalars().all()
    bonuses: dict[str, float] = {}
    for node in all_skill_nodes:
        cur = int(learned_map.get(str(node.id).strip().lower(), 0) or 0)
        br = str(node.branch or "")
        add_lv = (
            int(bundle.nodes.get(str(node.id).strip().lower(), 0) or 0)
            + int(bundle.branches.get(br, 0) or 0)
            + int(bundle.all_nodes or 0)
        )
        eff_lv = cur + max(0, add_lv)
        if eff_lv < 1:
            continue
        raw = extrapolate_passive_effect_value(node.effect_values, eff_lv, str(node.effect_type or ""))
        if raw is None:
            continue
        v = float(raw)
        et = str(node.effect_type or "")
        if et == "armor_and_reduce":
            bonuses["armor_pct"] = bonuses.get("armor_pct", 0.0) + v
            bonuses["dmg_reduce_pct"] = bonuses.get("dmg_reduce_pct", 0.0) + v
        else:
            bonuses[et] = bonuses.get(et, 0.0) + v
    return bonuses


async def get_passive_contributions_for_log(
    session: AsyncSession,
    player_id: int,
    *,
    extra_node_levels: dict[str, int] | None = None,
    extra_branch_levels: dict[str, int] | None = None,
    extra_all_nodes_level: int | None = None,
    _skip_equipment_passive_levels: bool = False,
) -> list[dict[str, Any]]:
    """По одной записи на узел пассивного дерева (для журнала боя / баланса).

    ``armor_and_reduce`` даёт две записи: ``armor_pct`` и ``dmg_reduce_pct`` с одним node_id.
    """
    explicit_override = (
        extra_node_levels is not None
        or extra_branch_levels is not None
        or extra_all_nodes_level is not None
    )
    bundle: PassiveEquipmentLevelBonuses
    if _skip_equipment_passive_levels:
        bundle = PassiveEquipmentLevelBonuses.empty()
    elif not explicit_override:
        cached = session.info.get(_SESSION_PASSIVE_EXTRA_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("player_id") == int(player_id):
            bundle = _coerce_equipment_bundle(cached.get("data"))
        else:
            bundle = await collect_passive_node_level_bonus_from_session(session, player_id)
            session.info[_SESSION_PASSIVE_EXTRA_CACHE_KEY] = {
                "player_id": int(player_id),
                "data": bundle.to_cache_dict(),
            }
    else:
        eb = extra_branch_levels or {}
        bundle = PassiveEquipmentLevelBonuses(
            nodes=dict(extra_node_levels or {}),
            branches={b: int(eb.get(b, 0) or 0) for b in BRANCHES},
            all_nodes=0 if extra_all_nodes_level is None else int(extra_all_nodes_level),
        )

    learned_rows = (
        await session.execute(select(PlayerPassiveSkill).where(PlayerPassiveSkill.player_id == int(player_id)))
    ).scalars().all()
    learned_map = {str(r.node_id).strip().lower(): int(r.level or 0) for r in learned_rows}

    all_skill_nodes = (await session.execute(select(PassiveSkillNode))).scalars().all()
    out: list[dict[str, Any]] = []
    for node in all_skill_nodes:
        nid = str(node.id).strip().lower()
        cur = int(learned_map.get(nid, 0) or 0)
        br = str(node.branch or "")
        add_lv = (
            int(bundle.nodes.get(nid, 0) or 0)
            + int(bundle.branches.get(br, 0) or 0)
            + int(bundle.all_nodes or 0)
        )
        eff_lv = cur + max(0, add_lv)
        if eff_lv < 1:
            continue
        et = str(node.effect_type or "")
        raw = extrapolate_passive_effect_value(node.effect_values, eff_lv, et)
        if raw is None:
            continue
        v = float(raw)
        name = str(node.name or nid)
        base = {
            "node_id": nid,
            "name": name,
            "branch": br,
            "level": eff_lv,
            "value": v,
        }
        if et == "armor_and_reduce":
            out.append({**base, "effect_type": "armor_pct"})
            out.append({**base, "effect_type": "dmg_reduce_pct"})
        else:
            out.append({**base, "effect_type": et})
    return out


def compute_passive_buy_price_from_bonuses(
    price: int,
    ps: dict[str, float],
    hs: dict[str, float] | None = None,
) -> int:
    """Цена после скидки и торгового бонуса (без запросов к БД)."""
    sd = float(ps.get("shop_discount_pct", 0) or 0)
    if hs:
        sd += float(hs.get("shop_discount_pct", 0) or 0) / 100.0
    p = max(1, int(round(int(price) * (1.0 - min(0.85, max(0.0, sd))))))
    tf = int(ps.get("trade_flat", 0) or 0)
    if tf > 0:
        p = max(1, p - tf)
    return p


async def apply_passive_buy_price(session: AsyncSession, player_id: int, price: int) -> int:
    """Цена покупки в магазине / казино после скидки и торгового бонуса."""
    try:
        ps = await get_passive_skill_bonuses(session, player_id)
    except Exception:
        return max(1, int(price))
    hs: dict[str, float] | None = None
    try:
        from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses

        hs = await get_hidden_skill_bonuses(session, player_id)
    except Exception:
        pass
    return compute_passive_buy_price_from_bonuses(int(price), ps, hs)


async def apply_passive_hire_cost(session: AsyncSession, player_id: int, base_cost: int) -> int:
    """Стоимость найма в таверне (скидка + торговый flat)."""
    return await apply_passive_buy_price(session, player_id, base_cost)


async def effective_main_waifu_charm(session: AsyncSession, player_id: int) -> int:
    """ОБА основной вайфу + бонусы с экипировки (как в /shop/inventory)."""
    waifu = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if not waifu:
        return 0
    rows = (
        await session.execute(
            select(m.InventoryItem)
            .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
            .where(
                m.InventoryItem.player_id == int(player_id),
                m.InventoryItem.equipment_slot.isnot(None),
            )
        )
    ).scalars().all()
    # Ленивый импорт: routes тянет passive_skills на уровне модуля.
    from waifu_bot.api.routes import calculate_item_bonuses

    total = 0
    for inv in rows or []:
        b = calculate_item_bonuses(inv)
        total += int(b.get("charm", 0) or 0)
    return int(getattr(waifu, "charm", 0) or 0) + total


async def merchant_discount_pct_for_player(session: AsyncSession, player_id: int) -> float:
    """Скидка у торговца (%) — как в блоке профиля: эффективный ОБА × coeff + flat/percent с экипировки."""
    from waifu_bot.game.constants import CHM_MERCHANT_DISCOUNT_COEFF

    waifu = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if not waifu:
        return 0.0
    rows = (
        await session.execute(
            select(m.InventoryItem)
            .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
            .where(
                m.InventoryItem.player_id == int(player_id),
                m.InventoryItem.equipment_slot.isnot(None),
            )
        )
    ).scalars().all()
    from waifu_bot.api.routes import calculate_item_bonuses

    charm = int(getattr(waifu, "charm", 0) or 0)
    md_flat = 0.0
    md_pct = 0.0
    for inv in rows or []:
        b = calculate_item_bonuses(inv)
        charm += int(b.get("charm", 0) or 0)
        md_flat += float(b.get("merchant_discount_flat", 0) or 0)
        md_pct += float(b.get("merchant_discount_percent", 0) or 0)
    base_disc = min(50.0, max(0.0, float(charm) * float(CHM_MERCHANT_DISCOUNT_COEFF) * 100.0))
    merchant_disc = base_disc + md_flat
    if md_pct > 0:
        merchant_disc = merchant_disc * (1.0 + md_pct / 100.0)
    return min(50.0, max(0.0, merchant_disc))


def _charm_discount_fraction(charm: int, coeff: float) -> float:
    return min(0.5, max(0.0, float(charm) * float(coeff)))


def apply_charm_hire_discount(cost: int, charm: int) -> int:
    from waifu_bot.game.constants import CHM_HIRE_DISCOUNT_COEFF

    f = _charm_discount_fraction(charm, CHM_HIRE_DISCOUNT_COEFF)
    return max(1, int(round(int(cost) * (1.0 - f))))


def apply_charm_training_discount(cost: int, charm: int) -> int:
    from waifu_bot.game.constants import CHM_TRAINING_DISCOUNT_COEFF

    f = _charm_discount_fraction(charm, CHM_TRAINING_DISCOUNT_COEFF)
    return max(1, int(round(int(cost) * (1.0 - f))))


def compute_passive_learn_cost_from_bonuses(
    base_cost: int,
    ps: dict[str, float],
    hs: dict[str, float] | None,
    charm: int,
) -> int:
    """Золото за уровень пассивки: торговля + скидка тренировок от ОБА (без БД)."""
    after_passive = compute_passive_buy_price_from_bonuses(int(base_cost), ps, hs)
    return apply_charm_training_discount(after_passive, charm)


async def compute_tavern_hire_price(session: AsyncSession, player_id: int, base_cost: int) -> int:
    """Пассивки (торговля) + скидка найма от ОБА — как в профиле."""
    after_passive = await apply_passive_hire_cost(session, player_id, int(base_cost))
    ch = await effective_main_waifu_charm(session, player_id)
    return apply_charm_hire_discount(after_passive, ch)


async def effective_passive_learn_cost(session: AsyncSession, player_id: int, base_cost: int) -> int:
    """Золото за уровень пассивки: пассивки торговли + скидка тренировок от ОБА."""
    after_passive = await apply_passive_buy_price(session, player_id, int(base_cost))
    ch = await effective_main_waifu_charm(session, player_id)
    return apply_charm_training_discount(after_passive, ch)


def expedition_reward_multiplier(ps: dict[str, float], hs: dict[str, float] | None = None) -> float:
    """Множитель золота/опыта экспедиции."""
    mult = 1.0 + float(ps.get("expedition_bonus_pct", 0) or 0)
    if hs:
        mult += float(hs.get("expedition_reward_pct", 0) or 0) / 100.0
    return mult


def expedition_success_probability_boost(
    ps: dict[str, float], hs: dict[str, float] | None = None
) -> float:
    """Добавка к вероятности успеха (0..1) при первом claim."""
    eb = float(ps.get("expedition_bonus_pct", 0) or 0)
    boost = min(0.4, eb * 0.65)
    if hs:
        boost += float(hs.get("loyal_unit_success_pct", 0) or 0) / 100.0
    return min(0.5, boost)


def merge_passive_into_profile_details(
    details: dict[str, Any],
    ps: dict[str, float],
    *,
    skip_all_stats_pct_on_damage: bool = False,
) -> dict[str, Any]:
    """Дополняет словарь из _compute_details бонусами пассивок (для UI профиля).

    Если основные статы в _compute_details уже учитывают all_stats_pct (как в соло-бое),
    передайте skip_all_stats_pct_on_damage=True, чтобы не умножать урон второй раз.
    """
    out = dict(details)
    af = int(ps.get("armor_flat", 0) or 0)
    if af > 0:
        out["armor"] = int(out.get("armor", 0) or 0) + af
    ap = float(ps.get("armor_pct", 0) or 0)
    if ap > 0:
        out["armor"] = int(round(int(out.get("armor", 0) or 0) * (1.0 + ap)))
    hp = float(ps.get("hp_max_pct", 0) or 0)
    if hp > 0:
        out["hp_max"] = int(round(int(out.get("hp_max", 0) or 0) * (1.0 + hp)))

    md = int(out.get("melee_damage", 0) or 0)
    rd = int(out.get("ranged_damage", 0) or 0)
    mgd = int(out.get("magic_damage", 0) or 0)
    md_min = out.get("melee_damage_min")
    md_max = out.get("melee_damage_max")
    rd_min = out.get("ranged_damage_min")
    rd_max = out.get("ranged_damage_max")
    mgd_min = out.get("magic_damage_min")
    mgd_max = out.get("magic_damage_max")
    has_melee_bounds = md_min is not None and md_max is not None
    has_ranged_bounds = rd_min is not None and rd_max is not None
    has_magic_bounds = mgd_min is not None and mgd_max is not None

    def _apply_dmg_mult(val: int, mult: float) -> int:
        return int(round(val * mult))

    mm = float(ps.get("melee_dmg_pct", 0) or 0)
    if mm > 0:
        m = 1.0 + mm
        md = _apply_dmg_mult(md, m)
        if has_melee_bounds:
            md_min = _apply_dmg_mult(int(md_min), m)
            md_max = _apply_dmg_mult(int(md_max), m)
    pr = float(ps.get("ranged_dmg_pct", 0) or 0)
    if pr > 0:
        m = 1.0 + pr
        rd = _apply_dmg_mult(rd, m)
        if has_ranged_bounds:
            rd_min = _apply_dmg_mult(int(rd_min), m)
            rd_max = _apply_dmg_mult(int(rd_max), m)
    mg = float(ps.get("magic_dmg_pct", 0) or 0)
    if mg > 0:
        m = 1.0 + mg
        mgd = _apply_dmg_mult(mgd, m)
        if has_magic_bounds:
            mgd_min = _apply_dmg_mult(int(mgd_min), m)
            mgd_max = _apply_dmg_mult(int(mgd_max), m)
    if not skip_all_stats_pct_on_damage:
        asp = float(ps.get("all_stats_pct", 0) or 0)
        if asp > 0:
            m = 1.0 + asp
            md, rd, mgd = _apply_dmg_mult(md, m), _apply_dmg_mult(rd, m), _apply_dmg_mult(mgd, m)
            if has_melee_bounds:
                md_min, md_max = _apply_dmg_mult(int(md_min), m), _apply_dmg_mult(int(md_max), m)
            if has_ranged_bounds:
                rd_min, rd_max = _apply_dmg_mult(int(rd_min), m), _apply_dmg_mult(int(rd_max), m)
            if has_magic_bounds:
                mgd_min, mgd_max = _apply_dmg_mult(int(mgd_min), m), _apply_dmg_mult(int(mgd_max), m)
    act = float(ps.get("active_skill_dmg_pct", 0) or 0)
    if act > 0:
        m = 1.0 + act
        md, rd, mgd = _apply_dmg_mult(md, m), _apply_dmg_mult(rd, m), _apply_dmg_mult(mgd, m)
        if has_melee_bounds:
            md_min, md_max = _apply_dmg_mult(int(md_min), m), _apply_dmg_mult(int(md_max), m)
        if has_ranged_bounds:
            rd_min, rd_max = _apply_dmg_mult(int(rd_min), m), _apply_dmg_mult(int(rd_max), m)
        if has_magic_bounds:
            mgd_min, mgd_max = _apply_dmg_mult(int(mgd_min), m), _apply_dmg_mult(int(mgd_max), m)
    out["melee_damage"], out["ranged_damage"], out["magic_damage"] = md, rd, mgd
    if has_melee_bounds:
        out["melee_damage_min"], out["melee_damage_max"] = md_min, md_max
    if has_ranged_bounds:
        out["ranged_damage_min"], out["ranged_damage_max"] = rd_min, rd_max
    if has_magic_bounds:
        out["magic_damage_min"], out["magic_damage_max"] = mgd_min, mgd_max

    cc = float(ps.get("crit_chance_pct", 0) or 0)
    if cc > 0:
        out["crit_chance"] = round(float(out.get("crit_chance", 0) or 0) + cc * 100.0, 2)
    ev = float(ps.get("evade_pct", 0) or 0)
    if ev > 0:
        out["dodge_chance"] = round(float(out.get("dodge_chance", 0) or 0) + ev * 100.0, 2)
    fe = float(ps.get("full_evade_chance", 0) or 0)
    if fe > 0:
        out["full_evade_chance"] = round(fe * 100.0, 2)
    dr = float(ps.get("dmg_reduce_pct", 0) or 0)
    if dr > 0:
        out["damage_reduction"] = round(float(out.get("damage_reduction", 0) or 0) + dr * 100.0, 2)
    idr = float(ps.get("int_dmg_reduce", 0) or 0)
    if idr > 0:
        out["damage_reduction"] = round(float(out.get("damage_reduction", 0) or 0) + idr * 100.0, 2)
    ex = float(ps.get("exp_bonus_pct", 0) or 0)
    if ex > 0:
        out["exp_bonus"] = round(float(out.get("exp_bonus", 0) or 0) + ex * 100.0, 2)
    tf = float(ps.get("trade_flat", 0) or 0)
    if tf > 0:
        out["merchant_discount"] = round(float(out.get("merchant_discount", 0) or 0) + min(10.0, tf * 0.15), 2)
    sd = float(ps.get("shop_discount_pct", 0) or 0)
    if sd > 0:
        out["merchant_discount"] = round(float(out.get("merchant_discount", 0) or 0) + sd * 100.0 * 0.25, 2)
    return out


def _max_effect_display(node: PassiveSkillNode) -> str:
    vals = _coerce_passive_effect_values(node.effect_values)
    if not vals:
        return "—"
    mx = max(float(x) for x in vals if x is not None)
    # доли 0..2 → проценты; большие числа (trade_flat, nth_hit) — как есть
    if node.effect_type in ("trade_flat", "nth_hit_crit", "main_stats_flat", "armor_flat"):
        return str(int(mx)) if mx == int(mx) else f"{mx:g}"
    return f"+{round(mx * 100)}%"


def passive_learn_block_reason(
    *,
    waifu_level: int,
    branch_spent: int,
    waifu_level_req: int,
    branch_points_req: int,
    current_level: int,
    max_level: int,
    skill_points: int,
    gold: int,
    cost_gold: int,
) -> str | None:
    """Причина, почему узел нельзя прокачать; None — можно (при прочих условиях API)."""
    if waifu_level < int(waifu_level_req):
        return "locked_waifu_level"
    if branch_spent < int(branch_points_req):
        return "locked_branch_points"
    if current_level >= int(max_level):
        return "skill_maxed"
    if int(skill_points) < 1:
        return "no_skill_points"
    if int(gold) < int(cost_gold):
        return "insufficient_gold"
    return None


async def get_passive_skill_tree(session: AsyncSession, player_id: int) -> dict[str, Any]:
    nodes = (
        (await session.execute(select(PassiveSkillNode).order_by(PassiveSkillNode.branch, PassiveSkillNode.tier, PassiveSkillNode.position)))
        .scalars()
        .all()
    )
    learned_rows = (
        await session.execute(select(PlayerPassiveSkill).where(PlayerPassiveSkill.player_id == int(player_id)))
    ).scalars().all()
    learned_map = {str(r.node_id).strip().lower(): int(r.level or 0) for r in learned_rows}

    player = await session.get(Player, int(player_id))
    if not player:
        return {
            "branches": {},
            "skill_points": 0,
            "branch_points": {},
            "waifu_level": 1,
            "gold": 0,
            "reset_cost_per_point": 500.0,
        }

    waifu_lv = await _waifu_level(session, player_id)
    bp = await _branch_points(session, player_id)
    sp = int(getattr(player, "skill_points", 0) or 0)
    gold = int(player.gold or 0)
    cfg = await get_game_config_map(session)
    reset_cost_per_point = float(cfg_float(cfg, "skill.reset_cost_per_point", 500.0))

    bundle = await collect_passive_node_level_bonus_from_session(session, player_id)

    try:
        ps_bonuses = await get_passive_skill_bonuses(session, player_id)
    except Exception:
        ps_bonuses = {}
    hs_bonuses: dict[str, float] | None = None
    try:
        from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses

        hs_bonuses = await get_hidden_skill_bonuses(session, player_id)
    except Exception:
        pass
    charm = await effective_main_waifu_charm(session, player_id)

    branches: dict[str, list[dict[str, Any]]] = {b: [] for b in BRANCHES}

    for n in nodes:
        cur = learned_map.get(str(n.id).strip().lower(), 0)
        b = n.branch
        if b not in branches:
            continue
        spent = bp.get(b, 0)
        cost_gold_eff = compute_passive_learn_cost_from_bonuses(
            int(n.cost_gold or 0), ps_bonuses, hs_bonuses, charm
        )
        block = passive_learn_block_reason(
            waifu_level=waifu_lv,
            branch_spent=spent,
            waifu_level_req=int(n.waifu_level_req),
            branch_points_req=int(n.branch_points_req),
            current_level=cur,
            max_level=int(n.max_level),
            skill_points=sp,
            gold=gold,
            cost_gold=cost_gold_eff,
        )
        locked = block in ("locked_waifu_level", "locked_branch_points")
        can_learn = block is None
        add_lv = (
            int(bundle.nodes.get(str(n.id).strip().lower(), 0) or 0)
            + int(bundle.branches.get(str(n.branch), 0) or 0)
            + int(bundle.all_nodes or 0)
        )
        eff_lv = cur + max(0, add_lv)
        ev_cur = _effect_value_at(n, cur)
        et = str(n.effect_type or "")
        ev_eff = (
            extrapolate_passive_effect_value(n.effect_values, eff_lv, et)
            if eff_lv >= 1
            else None
        )
        next_lv = eff_lv + 1
        ev_next = extrapolate_passive_effect_value(n.effect_values, next_lv, et) if next_lv >= 1 else None
        max_lv = int(n.max_level)
        if (
            ev_next is not None
            and cur >= max_lv
            and add_lv <= 0
            and next_lv > max_lv
        ):
            ev_next = None
        branches[b].append(
            {
                "id": n.id,
                "branch": n.branch,
                "tier": int(n.tier),
                "position": int(n.position),
                "name": n.name,
                "max_level": int(n.max_level),
                "current_level": cur,
                "waifu_level_req": int(n.waifu_level_req),
                "branch_points_req": int(n.branch_points_req),
                "effect_type": n.effect_type,
                "effect_values": _coerce_passive_effect_values(n.effect_values),
                "current_effect_value": ev_cur,
                "equipment_level_bonus": int(add_lv) if add_lv > 0 else 0,
                "effective_level": int(eff_lv) if eff_lv >= 1 else 0,
                "effective_effect_value": ev_eff,
                "next_effective_effect_value": ev_next,
                "max_effect_label": _max_effect_display(n),
                "cost_gold": cost_gold_eff,
                "description": n.description,
                "can_learn": can_learn,
                "is_locked": locked,
                "learn_block_reason": block,
            }
        )

    total_learned = sum(int(v) for v in learned_map.values())
    per_level = int(cfg_float(cfg, "skill.points_per_level", 1.0))
    expected_free = max(0, (waifu_lv - 1) * per_level - total_learned)
    if abs(sp - expected_free) > 0:
        logger.warning(
            "passive skill_points mismatch player_id=%s sp=%s expected_free=%s learned_sum=%s waifu_lv=%s",
            player_id,
            sp,
            expected_free,
            total_learned,
            waifu_lv,
        )

    return {
        "branches": branches,
        "skill_points": sp,
        "branch_points": bp,
        "waifu_level": waifu_lv,
        "gold": gold,
        "reset_cost_per_point": reset_cost_per_point,
    }


async def learn_passive_node(session: AsyncSession, player_id: int, node_id: str) -> dict[str, Any]:
    node = await session.get(PassiveSkillNode, node_id)
    if not node:
        return {"ok": False, "error": "node_not_found"}

    player = await session.get(Player, int(player_id))
    if not player:
        return {"ok": False, "error": "player_not_found"}

    waifu_lv = await _waifu_level(session, player_id)
    bp = await _branch_points(session, player_id)
    b = node.branch
    spent = bp.get(b, 0)
    if waifu_lv < int(node.waifu_level_req):
        return {"ok": False, "error": "insufficient_waifu_level"}
    if spent < int(node.branch_points_req):
        return {"ok": False, "error": "insufficient_branch_points"}

    row = await session.get(PlayerPassiveSkill, (int(player_id), node_id))
    cur = int(row.level) if row else 0
    if cur >= int(node.max_level):
        return {"ok": False, "error": "skill_maxed"}

    if int(getattr(player, "skill_points", 0) or 0) < 1:
        return {"ok": False, "error": "no_skill_points"}

    cost = await effective_passive_learn_cost(session, player_id, int(node.cost_gold or 0))
    if int(player.gold or 0) < cost:
        return {"ok": False, "error": "insufficient_gold", "required": cost, "have": int(player.gold or 0)}

    new_lvl = cur + 1
    player.skill_points = int(getattr(player, "skill_points", 0) or 0) - 1
    player.gold = int(player.gold or 0) - cost

    if row:
        row.level = new_lvl
    else:
        session.add(PlayerPassiveSkill(player_id=int(player_id), node_id=node_id, level=new_lvl))

    mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if mw:
        await sync_waifu_max_hp(session, int(player_id), mw)

    await session.commit()
    return {
        "ok": True,
        "new_level": new_lvl,
        "skill_points_left": int(player.skill_points or 0),
        "gold_remaining": int(player.gold or 0),
    }


async def reset_passive_branch(session: AsyncSession, player_id: int, branch: str) -> dict[str, Any]:
    br = str(branch).lower().strip()
    if br not in BRANCHES:
        return {"ok": False, "error": "invalid_branch"}

    q = (
        select(PlayerPassiveSkill, PassiveSkillNode)
        .join(PassiveSkillNode, PassiveSkillNode.id == PlayerPassiveSkill.node_id)
        .where(PlayerPassiveSkill.player_id == int(player_id), PassiveSkillNode.branch == br)
    )
    rows = (await session.execute(q)).all()
    total_points = sum(int(ps.level or 0) for ps, _n in rows)
    if total_points <= 0:
        return {"ok": False, "error": "nothing_to_reset"}

    cfg = await get_game_config_map(session)
    per_pt = cfg_float(cfg, "skill.reset_cost_per_point", 500.0)
    reset_cost = max(0, int(round(total_points * float(per_pt))))

    player = await session.get(Player, int(player_id))
    if not player:
        return {"ok": False, "error": "player_not_found"}
    if int(player.gold or 0) < reset_cost:
        return {"ok": False, "error": "insufficient_gold", "required": reset_cost, "have": int(player.gold or 0)}

    nid_rows = (
        await session.execute(select(PassiveSkillNode.id).where(PassiveSkillNode.branch == br))
    ).scalars().all()
    nids = [str(x) for x in nid_rows]
    if nids:
        await session.execute(
            delete(PlayerPassiveSkill).where(
                PlayerPassiveSkill.player_id == int(player_id),
                PlayerPassiveSkill.node_id.in_(nids),
            )
        )

    player.skill_points = int(getattr(player, "skill_points", 0) or 0) + total_points
    player.gold = int(player.gold or 0) - reset_cost

    mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    if mw:
        await sync_waifu_max_hp(session, int(player_id), mw)

    await session.commit()
    return {
        "ok": True,
        "points_refunded": total_points,
        "gold_spent": reset_cost,
        "skill_points": int(player.skill_points or 0),
        "gold_remaining": int(player.gold or 0),
    }


async def admin_max_all_passive_nodes(session: AsyncSession, player_id: int) -> dict[str, Any]:
    """Set every passive node to max level for QA. Does not spend gold or skill points."""
    pid = int(player_id)
    nodes = (await session.execute(select(PassiveSkillNode))).scalars().all()
    rows_changed = 0
    for n in nodes:
        mx = max(1, int(n.max_level or 0))
        nid = str(n.id).strip()
        row = await session.get(PlayerPassiveSkill, (pid, nid))
        if row:
            if int(row.level or 0) != mx:
                row.level = mx
                rows_changed += 1
        else:
            session.add(PlayerPassiveSkill(player_id=pid, node_id=nid, level=mx))
            rows_changed += 1
    mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == pid))
    if mw:
        await sync_waifu_max_hp(session, pid, mw)
    await session.commit()
    return {
        "ok": True,
        "total_nodes": len(nodes),
        "rows_changed": rows_changed,
    }


async def grant_skill_points_on_waifu_levelup(session: AsyncSession, player_id: int, levels_gained: int) -> None:
    """Выдать очки навыков за левелап ОВ (из game_config skill.points_per_level)."""
    if levels_gained <= 0:
        return
    player = await session.get(Player, int(player_id))
    if not player:
        return
    cfg = await get_game_config_map(session)
    per = int(cfg_float(cfg, "skill.points_per_level", 1.0))
    add = int(levels_gained * per)
    player.skill_points = int(getattr(player, "skill_points", 0) or 0) + add
