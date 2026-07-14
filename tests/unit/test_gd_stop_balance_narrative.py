"""GD stop / idle / 2p balance / folding chronicle helpers."""
from __future__ import annotations

from waifu_bot.services.gd_narrative_ai import build_gd_folding_chronicle


def test_folding_chronicle_truncates_and_includes_facts():
    long = "А" * 400
    text = build_gd_folding_chronicle(
        [long, "<b>Второй</b> раунд был коротким."],
        wave="trash",
        round_num=3,
        wipe_count=1,
        last_outcome="ongoing",
        fallen_names=["Алиса"],
        max_chars_each=280,
    )
    assert "ХРОНИКА ПОХОДА" in text
    assert "волна=trash" in text
    assert "нокауты_отряда=1" in text
    assert "Алиса" in text
    assert "<b>" not in text
    assert "…" in text


def test_monster_dmg_party_scale_formula():
    """n<=4: clamp(ref/n, min, 1); n=2 with ref=1.3 → 0.65."""
    ref, min_m = 1.3, 0.55
    for n, expected in ((2, 0.65), (1, 1.0), (4, 0.55), (10, 1.0)):
        if n <= 4:
            scale = max(min_m, min(1.0, ref / float(n)))
        else:
            scale = 1.0
        assert abs(scale - expected) < 1e-9


def test_trash_mons_count_2p_vs_large():
    def n_mons(n_players: int) -> int:
        return 1 if n_players <= 2 else 1 + n_players // 2

    assert n_mons(1) == 1
    assert n_mons(2) == 1
    assert n_mons(4) == 3
    assert n_mons(10) == 6
