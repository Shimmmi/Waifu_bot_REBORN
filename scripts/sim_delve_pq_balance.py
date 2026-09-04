#!/usr/bin/env python3
"""Balance harness for Delve PQ: week record, HP at 80, shop mix.

Pure simulate_pq, no DB. Trio roster matches unit pace tests.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from waifu_bot.game.delve_pq import (
    MercState,
    PqParty,
    compute_power,
    d_max_of,
    party_power,
    refresh_derived,
    simulate_pq,
)


ROSTER = (("Мира", "guide", 4), ("Сера", "shield", 1), ("Кайра", "scout", 3))


@dataclass
class WatchParty(PqParty):
    pb: int = 0
    hp_at_80: list[float] = field(default_factory=list)
    shop_kinds: Counter = field(default_factory=Counter)

    def __setattr__(self, name, value):
        if name == "last_d":
            cur = int(value or 0)
            if cur > int(getattr(self, "pb", 0) or 0):
                object.__setattr__(self, "pb", cur)
            if cur == 80 and getattr(self, "mercs", None):
                living = [m for m in self.mercs if m.living()]
                if living:
                    frac = sum(m.hp_current / max(1, m.hp_max) for m in living) / len(living)
                    rows = list(getattr(self, "hp_at_80", []) or [])
                    rows.append(frac)
                    object.__setattr__(self, "hp_at_80", rows)
        super().__setattr__(name, value)


def _merc(card_id: int, slot: int, name: str, stance: str, class_id: int) -> MercState:
    merc = MercState(
        card_id=card_id,
        slot=slot,
        name=name,
        loyalty=50,
        level=1,
        gold_wallet=0,
        power=1,
        hp_current=48,
        hp_max=48,
        class_id=class_id,
        stance=stance,
        temper="stay",
    )
    refresh_derived(merc, fill_if_full=True)
    return merc


def run_days(days: float, *, seed: int = 11, step_h: int = 2, n: int = 3) -> WatchParty:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    party = WatchParty(
        seed=seed,
        run_origin=origin,
        last_ts=origin,
        mercs=[_merc(i + 1, i + 1, *ROSTER[i]) for i in range(n)],
        layer=2,
        t_node=30,
        pb=0,
    )
    now = origin
    end = origin + timedelta(hours=int(days * 24))
    while now < end:
        now += timedelta(hours=step_h)
        simulate_pq(party, now, pb_depth=max(int(party.pb), 1))
        for row in party.shop_log:
            kind = str(row.get("kind") or "")
            if kind:
                party.shop_kinds[kind] += 1
        party.shop_log.clear()
    return party


def _print_party(party: WatchParty, days: float) -> None:
    power = party_power(party.mercs)
    hp_rows = list(party.hp_at_80 or [])
    hp_mean = sum(hp_rows) / len(hp_rows) if hp_rows else None
    potions = sum(int(m.bag.get("potion_hp", 0) or 0) for m in party.mercs)
    wipes = [int(w.get("d") or 0) for w in (party.wipe_log or [])]
    med_wipe = sorted(wipes)[len(wipes) // 2] if wipes else None
    print(f"days={days:g}")
    print(f"  pb_depth={party.pb}  d_max={d_max_of(power)}  party_power={power}")
    print(f"  levels={[m.level for m in party.mercs]}  powers={[compute_power(m) for m in party.mercs]}")
    print(f"  wipes={party.wipe_count}  median_wipe_d={med_wipe}")
    print(f"  shop={dict(party.shop_kinds)}  potions_in_bags={potions}")
    if hp_mean is not None:
        print(f"  mean_hp_frac_at_d80={hp_mean:.3f}  samples={len(hp_rows)}")
    else:
        print("  mean_hp_frac_at_d80=n/a")


def main() -> None:
    for days in (1.0, 7.0, 30.0):
        party = run_days(days)
        _print_party(party, days)
        if days >= 7:
            assert party.pb > 137, f"week record {party.pb} still on the 137 wall"
        if party.hp_at_80:
            mean = sum(party.hp_at_80) / len(party.hp_at_80)
            if party_power(party.mercs) >= 350:
                assert mean >= 0.85, f"depth 80 HP {mean:.3f} with power {party_power(party.mercs)}"


if __name__ == "__main__":
    main()
