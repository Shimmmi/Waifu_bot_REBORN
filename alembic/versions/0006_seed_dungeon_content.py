"""seed dungeon content: monster templates + pools + dungeon params

Revision ID: 0006_seed_dungeon_content
Revises: 0005_dungeon_runs_and_pools
Create Date: 2026-01-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_seed_dungeon_content"
down_revision: Union[str, None] = "0005_dungeon_runs_and_pools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1) Update existing dungeons to have location + obstacle ranges + difficulty ---
    # Map dungeon_number 1..5 to location_type
    loc_by_num = {
        1: "cave",
        2: "forest",
        3: "ruins",
        4: "crypt",
        5: "abyss",
    }
    for num, loc in loc_by_num.items():
        op.execute(sa.text("UPDATE dungeons SET location_type = :loc WHERE dungeon_number = :num").bindparams(loc=loc, num=num))

    # Difficulty and monster count ranges by act/dungeon_number (simple baseline)
    # Feel free to tweak; this is just to get diversity immediately.
    for act in range(1, 6):
        for num in range(1, 6):
            diff = 80 + (act - 1) * 60 + (num - 1) * 20  # grows with act and within act
            omin = 5 + (act - 1) + (num - 1)  # 5..?
            omax = omin + 3
            op.execute(
                sa.text(
                    """
                    UPDATE dungeons
                    SET difficulty = :diff,
                        obstacle_min = :omin,
                        obstacle_max = :omax
                    WHERE act = :act AND dungeon_number = :num
                    """
                ).bindparams(diff=diff, omin=omin, omax=omax, act=act, num=num)
            )

    # --- 2) Seed monster templates ---
    monster_templates = sa.table(
        "monster_templates",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("emoji", sa.String()),
        sa.column("family", sa.String()),
        sa.column("tags", sa.JSON()),
        sa.column("act_min", sa.Integer()),
        sa.column("act_max", sa.Integer()),
        sa.column("level_min", sa.Integer()),
        sa.column("level_max", sa.Integer()),
        sa.column("weight", sa.Integer()),
        sa.column("base_difficulty", sa.Integer()),
        sa.column("hp_base", sa.Integer()),
        sa.column("hp_per_level", sa.Integer()),
        sa.column("dmg_base", sa.Integer()),
        sa.column("dmg_per_level", sa.Integer()),
        sa.column("exp_base", sa.Integer()),
        sa.column("exp_per_level", sa.Integer()),
        sa.column("gold_base", sa.Integer()),
        sa.column("gold_per_level", sa.Integer()),
        sa.column("boss_allowed", sa.Boolean()),
        sa.column("boss_hp_mult", sa.Float()),
        sa.column("boss_dmg_mult", sa.Float()),
        sa.column("boss_reward_mult", sa.Float()),
    )

    # Act level ranges (rough)
    act_level_ranges = {
        1: (1, 12),
        2: (10, 22),
        3: (20, 32),
        4: (30, 42),
        5: (40, 52),
    }

    # Archetypes: (base_name, emoji, family, locations, base_diff, hp_bias, dmg_bias)
    archetypes = [
        ("Скелет-воин", "💀", "undead", ["crypt", "ruins", "cave"], 12, 10, 2),
        ("Зомби", "🧟", "undead", ["crypt", "ruins"], 10, 16, 1),
        ("Призрак", "👻", "undead", ["crypt", "ruins"], 14, 6, 3),
        ("Летучая мышь", "🦇", "beast", ["cave", "crypt"], 8, 4, 1),
        ("Пещерный паук", "🕷️", "beast", ["cave"], 12, 8, 2),
        ("Гоблин", "👺", "humanoid", ["forest", "ruins", "cave"], 10, 6, 2),
        ("Бандит", "🗡️", "humanoid", ["forest", "ruins"], 11, 6, 3),
        ("Волк", "🐺", "beast", ["forest"], 10, 8, 2),
        ("Медведь", "🐻", "beast", ["forest"], 14, 18, 3),
        ("Слизь", "🟢", "slime", ["cave", "ruins"], 9, 12, 1),
        ("Огненный элементаль", "🔥", "elemental", ["abyss", "ruins"], 16, 10, 5),
        ("Ледяной элементаль", "❄️", "elemental", ["cave", "abyss"], 16, 10, 5),
        ("Демон-пехотинец", "😈", "demon", ["abyss", "crypt"], 18, 12, 6),
        ("Теневой охотник", "🌑", "demon", ["abyss", "ruins"], 20, 8, 7),
        ("Живой доспех", "🛡️", "construct", ["ruins", "crypt"], 15, 14, 4),
        ("Древний голем", "🗿", "construct", ["ruins", "abyss"], 22, 22, 5),
        ("Культист", "🕯️", "humanoid", ["crypt", "abyss"], 12, 6, 4),
        ("Гигантский червь", "🪱", "beast", ["cave", "abyss"], 18, 18, 4),
        ("Проклятый рыцарь", "⚔️", "undead", ["crypt"], 20, 14, 6),
        ("Дракончик", "🐉", "dragon", ["abyss", "cave"], 24, 20, 8),
    ]

    rows = []
    next_id = 1
    for act in range(1, 6):
        lvl_min, lvl_max = act_level_ranges[act]
        # scale per act
        hp_base_act = 24 + act * 10
        dmg_base_act = 3 + act * 2
        exp_base_act = 8 + act * 4
        gold_base_act = 6 + act * 4

        # For variety: generate 3 variants per archetype per act (60 templates per act => 300 total)
        for (base_name, emoji, family, locs, base_diff, hp_bias, dmg_bias) in archetypes:
            for v in range(1, 4):
                name = f"{base_name} {v}"
                tags = {"tags": list(dict.fromkeys(locs + [family, f"act{act}"]))}

                base_difficulty = base_diff + (act - 1) * 4 + (v - 1)
                hp_base = hp_base_act + hp_bias + (v - 1) * 6
                hp_per_level = 8 + act
                dmg_base = dmg_base_act + dmg_bias + (v - 1)
                dmg_per_level = 2 + act // 2
                exp_base = exp_base_act + (v - 1) * 2
                exp_per_level = 3 + act // 2
                gold_base = gold_base_act + (v - 1) * 2
                gold_per_level = 2 + act // 2

                rows.append(
                    {
                        "id": next_id,
                        "name": name,
                        "emoji": emoji,
                        "family": family,
                        "tags": tags,
                        "act_min": act,
                        "act_max": act,
                        "level_min": lvl_min,
                        "level_max": lvl_max,
                        "weight": 100,
                        "base_difficulty": base_difficulty,
                        "hp_base": hp_base,
                        "hp_per_level": hp_per_level,
                        "dmg_base": dmg_base,
                        "dmg_per_level": dmg_per_level,
                        "exp_base": exp_base,
                        "exp_per_level": exp_per_level,
                        "gold_base": gold_base,
                        "gold_per_level": gold_per_level,
                        "boss_allowed": True,
                        "boss_hp_mult": 2.5,
                        "boss_dmg_mult": 1.8,
                        "boss_reward_mult": 2.0,
                    }
                )
                next_id += 1

    op.bulk_insert(monster_templates, rows)

    # --- 3) Seed dungeon pools for SOLO by act + location ---
    dungeon_pools = sa.table(
        "dungeon_pools",
        sa.column("id", sa.Integer()),
        sa.column("location_type", sa.String()),
        sa.column("act", sa.Integer()),
        sa.column("dungeon_type", sa.Integer()),
        sa.column("name", sa.String()),
    )
    dungeon_pool_entries = sa.table(
        "dungeon_pool_entries",
        sa.column("pool_id", sa.Integer()),
        sa.column("template_id", sa.Integer()),
        sa.column("weight", sa.Integer()),
        sa.column("min_difficulty", sa.Integer()),
        sa.column("max_difficulty", sa.Integer()),
        sa.column("boss_only", sa.Boolean()),
        sa.column("exclude_boss", sa.Boolean()),
    )

    # Build pools with deterministic IDs
    pool_rows = []
    entry_rows = []
    pool_id = 1

    # Helper: templates by act+location tag from deterministic ID ranges we inserted above
    # We inserted 20 archetypes * 3 variants = 60 templates per act.
    per_act = 20 * 3
    for act in range(1, 6):
        for loc in ["cave", "forest", "ruins", "crypt", "abyss"]:
            pool_rows.append(
                {
                    "id": pool_id,
                    "location_type": loc,
                    "act": act,
                    "dungeon_type": 1,  # SOLO
                    "name": f"Act {act} {loc} SOLO",
                }
            )

            # Add entries: include all templates for that act that have the location in their tags.
            start_id = (act - 1) * per_act + 1
            end_id = start_id + per_act - 1

            # We don't have SQL filtering on JSON tags here; use archetype location mapping deterministically:
            # map which archetypes include this location and include their 3 variants.
            for a_idx, (_, _, _, locs, _, _, _) in enumerate(archetypes, start=0):
                if loc not in locs:
                    continue
                # each archetype produces 3 sequential IDs within act block
                base = start_id + a_idx * 3
                for tid in [base, base + 1, base + 2]:
                    entry_rows.append(
                        {
                            "pool_id": pool_id,
                            "template_id": tid,
                            "weight": 100,
                            "min_difficulty": None,
                            "max_difficulty": None,
                            "boss_only": False,
                            "exclude_boss": False,
                        }
                    )

            pool_id += 1

    op.bulk_insert(dungeon_pools, pool_rows)
    op.bulk_insert(dungeon_pool_entries, entry_rows)

    # --- 4) Drop rules baseline (boss only) ---
    drop_rules = sa.table(
        "drop_rules",
        sa.column("id", sa.Integer()),
        sa.column("act", sa.Integer()),
        sa.column("boss_only", sa.Boolean()),
        sa.column("chance", sa.Float()),
        sa.column("rarity_weights", sa.JSON()),
    )
    op.bulk_insert(
        drop_rules,
        [
            {
                "id": 1,
                "act": 1,
                "boss_only": True,
                "chance": 0.03,
                "rarity_weights": {"1": 70, "2": 25, "3": 5},
            },
            {
                "id": 2,
                "act": 2,
                "boss_only": True,
                "chance": 0.05,
                "rarity_weights": {"1": 55, "2": 30, "3": 12, "4": 3},
            },
            {
                "id": 3,
                "act": 3,
                "boss_only": True,
                "chance": 0.07,
                "rarity_weights": {"1": 45, "2": 32, "3": 18, "4": 5},
            },
            {
                "id": 4,
                "act": 4,
                "boss_only": True,
                "chance": 0.10,
                "rarity_weights": {"1": 35, "2": 30, "3": 22, "4": 11, "5": 2},
            },
            {
                "id": 5,
                "act": 5,
                "boss_only": True,
                "chance": 0.12,
                "rarity_weights": {"1": 28, "2": 30, "3": 24, "4": 14, "5": 4},
            },
        ],
    )


def downgrade() -> None:
    # Best-effort cleanup (delete seeded rows). Keep dungeons param updates as-is.
    op.execute(sa.text("DELETE FROM dungeon_pool_entries"))
    op.execute(sa.text("DELETE FROM dungeon_pools"))
    op.execute(sa.text("DELETE FROM drop_rules"))
    op.execute(sa.text("DELETE FROM monster_templates"))

