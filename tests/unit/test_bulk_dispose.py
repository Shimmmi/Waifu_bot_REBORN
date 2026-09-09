"""Bulk sell / dismantle rarity thresholds and totals."""

from types import SimpleNamespace

from waifu_bot.services.dismantle import (
    bulk_item_rarity,
    calculate_dismantle_dust,
    is_bulk_candidate,
    select_bulk_items,
    summarize_bulk_cells,
)

_DEFAULT_CFG = {
    "dismantle.dust_base": "5",
    "dismantle.rarity_mult_1": "1.0",
    "dismantle.rarity_mult_2": "1.78",
    "dismantle.rarity_mult_3": "3.16",
    "dismantle.rarity_mult_4": "5.62",
    "dismantle.rarity_mult_5": "10.0",
    "dismantle.tier_mult": "1.20",
}


def _inv(
    inv_id: int,
    rarity: int | None,
    *,
    equipped: int | None = None,
    tier: int = 1,
    item_rarity: int | None = None,
    item_tier: int | None = None,
) -> SimpleNamespace:
    item = None
    if item_rarity is not None or item_tier is not None:
        item = SimpleNamespace(rarity=item_rarity, tier=item_tier, base_value=None)
    return SimpleNamespace(
        id=inv_id,
        rarity=rarity,
        tier=tier,
        equipment_slot=equipped,
        item=item,
    )


def test_epic_threshold_skips_legendary() -> None:
    items = [_inv(1, 4), _inv(2, 5)]
    got = select_bulk_items(items, 4)
    assert [i.id for i in got] == [1]


def test_legendary_only_at_max_rarity_five() -> None:
    legend = _inv(2, 5)
    assert is_bulk_candidate(legend, 4) is False
    assert is_bulk_candidate(legend, 5) is True
    assert [i.id for i in select_bulk_items([legend], 5)] == [2]


def test_equipped_and_raid_skipped() -> None:
    bag = [
        _inv(1, 1, equipped=3),
        _inv(2, 6),
        _inv(3, 1),
    ]
    got = select_bulk_items(bag, 5)
    assert [i.id for i in got] == [3]


def test_rarity_falls_back_to_item_catalog() -> None:
    inv = _inv(1, None, item_rarity=3)
    assert bulk_item_rarity(inv) == 3
    assert is_bulk_candidate(inv, 3) is True
    assert is_bulk_candidate(inv, 2) is False


def test_matrix_legendary_count_zero_below_five() -> None:
    items = [_inv(1, 1), _inv(2, 5)]
    cells = summarize_bulk_cells(
        items,
        shop_ids=set(),
        price_fn=lambda inv: 10,
        cfg=_DEFAULT_CFG,
    )
    for r in range(1, 5):
        assert cells[str(r)]["legendary_count"] == 0
        assert cells[str(r)]["dismantle_legendary_count"] == 0
    assert cells["5"]["legendary_count"] == 1
    assert cells["4"]["count"] == 1
    assert cells["5"]["count"] == 2


def test_sell_gold_sum_matches_per_item() -> None:
    items = [_inv(1, 1), _inv(2, 2), _inv(3, 4)]
    prices = {1: 11, 2: 25, 3: 90}

    def price_fn(inv: SimpleNamespace) -> int:
        return prices[int(inv.id)]

    cells = summarize_bulk_cells(items, shop_ids=set(), price_fn=price_fn, cfg=_DEFAULT_CFG)
    assert cells["1"]["gold_total"] == 11
    assert cells["2"]["gold_total"] == 11 + 25
    assert cells["4"]["gold_total"] == 11 + 25 + 90
    assert cells["4"]["count"] == 3


def test_dismantle_dust_sum_matches_per_item() -> None:
    items = [_inv(1, 1, tier=1), _inv(2, 3, tier=2), _inv(3, 5, tier=1)]
    expected_all = sum(
        calculate_dismantle_dust(rarity=bulk_item_rarity(i), tier=int(i.tier), cfg=_DEFAULT_CFG)
        for i in items
    )
    expected_epic = sum(
        calculate_dismantle_dust(rarity=bulk_item_rarity(i), tier=int(i.tier), cfg=_DEFAULT_CFG)
        for i in items
        if bulk_item_rarity(i) <= 4
    )
    cells = summarize_bulk_cells(
        items,
        shop_ids=set(),
        price_fn=lambda _inv: 1,
        cfg=_DEFAULT_CFG,
    )
    assert cells["5"]["dust_total"] == expected_all
    assert cells["4"]["dust_total"] == expected_epic
    assert cells["5"]["dismantle_count"] == 3


def test_dismantle_skips_active_shop_offer() -> None:
    items = [_inv(1, 1), _inv(2, 1)]
    cells = summarize_bulk_cells(
        items,
        shop_ids={2},
        price_fn=lambda _inv: 7,
        cfg=_DEFAULT_CFG,
    )
    assert cells["1"]["count"] == 2
    assert cells["1"]["gold_total"] == 14
    assert cells["1"]["dismantle_count"] == 1
    assert cells["1"]["dust_total"] == calculate_dismantle_dust(rarity=1, tier=1, cfg=_DEFAULT_CFG)
    dust_only = select_bulk_items(items, 1, shop_ids={2}, skip_shop=True)
    assert [i.id for i in dust_only] == [1]
