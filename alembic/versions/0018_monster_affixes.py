"""Add monster affixes system: elite_chance/max_affixes on templates, monster_affixes table, elite fields on run monsters.

Revision ID: 0018_monster_affixes
Revises: 0017_item_art
Create Date: 2026-03-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0018_monster_affixes"
down_revision: str | None = "0017_item_art"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- monster_templates: add elite fields ---
    op.add_column(
        "monster_templates",
        sa.Column(
            "elite_chance",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.06"),
        ),
    )
    op.add_column(
        "monster_templates",
        sa.Column(
            "max_affixes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("4"),
        ),
    )

    # --- dungeon_run_monsters: add elite state fields ---
    op.add_column(
        "dungeon_run_monsters",
        sa.Column("is_elite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "dungeon_run_monsters",
        sa.Column("elite_color", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "dungeon_run_monsters",
        sa.Column("applied_affix_ids", sa.JSON(), nullable=True),
    )

    # --- monster_affixes: master affix definitions ---
    op.create_table(
        "monster_affixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("affix_group", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),       # prefix / suffix
        sa.Column("category", sa.String(length=32), nullable=False),   # stat / behavior / reward / debuff
        sa.Column("level_add", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("hp_mult", sa.Float(), nullable=True),
        sa.Column("dmg_mult", sa.Float(), nullable=True),
        sa.Column("defense_add", sa.Integer(), nullable=True),         # % damage reduction
        sa.Column("evade_add", sa.Integer(), nullable=True),           # % evasion chance
        sa.Column("gold_mult", sa.Float(), nullable=True),
        sa.Column("exp_mult", sa.Float(), nullable=True),
        sa.Column("drop_chance_mult", sa.Float(), nullable=True),
        sa.Column("drop_rarity_bonus", sa.Integer(), nullable=True),
        sa.Column("behavior_flag", sa.String(length=32), nullable=True),
        sa.Column("behavior_params", sa.JSON(), nullable=True),
        sa.Column("incompatible_with", sa.JSON(), nullable=True),      # list of affix_group names
        sa.Column("allowed_families", sa.JSON(), nullable=True),       # null = all families
        sa.Column("forbidden_families", sa.JSON(), nullable=True),
        sa.Column(
            "max_per_monster",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # ---------------------------------------------------------------
    # Seed data — 48 affix rows
    # ---------------------------------------------------------------
    def row(
        name: str,
        affix_group: str,
        tier: int | None,
        type_: str,
        category: str,
        level_add: int,
        *,
        hp_mult: float | None = None,
        dmg_mult: float | None = None,
        defense_add: int | None = None,
        evade_add: int | None = None,
        gold_mult: float | None = None,
        exp_mult: float | None = None,
        drop_chance_mult: float | None = None,
        drop_rarity_bonus: int | None = None,
        behavior_flag: str | None = None,
        behavior_params: dict | None = None,
        incompatible_with: list[str] | None = None,
        allowed_families: list[str] | None = None,
        forbidden_families: list[str] | None = None,
        max_per_monster: int = 1,
    ) -> dict:
        return {
            "name": name,
            "affix_group": affix_group,
            "tier": tier,
            "type": type_,
            "category": category,
            "level_add": level_add,
            "hp_mult": hp_mult,
            "dmg_mult": dmg_mult,
            "defense_add": defense_add,
            "evade_add": evade_add,
            "gold_mult": gold_mult,
            "exp_mult": exp_mult,
            "drop_chance_mult": drop_chance_mult,
            "drop_rarity_bonus": drop_rarity_bonus,
            "behavior_flag": behavior_flag,
            "behavior_params": behavior_params,
            "incompatible_with": incompatible_with,
            "allowed_families": allowed_families,
            "forbidden_families": forbidden_families,
            "max_per_monster": max_per_monster,
        }

    rows: list[dict] = [
        # ============================================================
        # PREFIXES — stat modifiers
        # ============================================================

        # hp_bulk — HP increase
        row("Толстый",        "hp_bulk", 1, "prefix", "stat", 1, hp_mult=1.5),
        row("Жирнючий",       "hp_bulk", 2, "prefix", "stat", 2, hp_mult=2.0),
        row("Мегакабанистый", "hp_bulk", 3, "prefix", "stat", 3, hp_mult=2.5),

        # dmg_power — damage multiplier
        row("Могучий",        "dmg_power", 1, "prefix", "stat", 1, dmg_mult=1.4),
        row("Сокрушительный", "dmg_power", 2, "prefix", "stat", 2, dmg_mult=1.8),
        row("Опустошительный","dmg_power", 3, "prefix", "stat", 3, dmg_mult=2.3),

        # defense — incoming damage reduction
        row("Бронированный",  "defense", 1, "prefix", "stat", 1,
            defense_add=10, incompatible_with=["stone_skin"]),
        row("Закалённый",     "defense", 2, "prefix", "stat", 2,
            defense_add=20, incompatible_with=["stone_skin"]),
        row("Неприступный",   "defense", 3, "prefix", "stat", 3,
            defense_add=30, incompatible_with=["stone_skin"]),

        # evade — monster evasion chance
        row("Удачливый",  "evade", 1, "prefix", "stat", 1, evade_add=10),
        row("Увёртливый", "evade", 2, "prefix", "stat", 2, evade_add=20),
        row("Неуловимый", "evade", 3, "prefix", "stat", 3, evade_add=30),

        # stone_skin — phased armor: reduction scales linearly with remaining HP
        # Formula: reduction = max_reduction * (current_hp / max_hp)
        row("Каменный",  "stone_skin", 1, "prefix", "stat", 3,
            behavior_flag="STONE_SKIN",
            behavior_params={"max_reduction": 0.50},
            incompatible_with=["defense"],
            allowed_families=["construct", "beast"]),
        row("Гранитный", "stone_skin", 2, "prefix", "stat", 4,
            behavior_flag="STONE_SKIN",
            behavior_params={"max_reduction": 0.70},
            incompatible_with=["defense"],
            allowed_families=["construct", "beast"]),

        # ancient — bonus rewards, no combat effect
        row("Древний",    "ancient", 1, "prefix", "reward", 1,
            exp_mult=2.0, gold_mult=2.0,
            incompatible_with=["miser"]),
        row("Реликтовый", "ancient", 2, "prefix", "reward", 2,
            exp_mult=3.0, gold_mult=3.0, drop_rarity_bonus=1,
            incompatible_with=["miser"]),

        # ============================================================
        # SUFFIXES — behavioral modifiers
        # ============================================================

        # berserk — extra attack when HP drops below threshold (once per fight)
        row("-берсерк",    "berserk", 1, "suffix", "behavior", 2,
            behavior_flag="BERSERK",
            behavior_params={"threshold": 0.40, "dmg_bonus": 1.5},
            incompatible_with=["buff_next"]),
        row("-неистовый",  "berserk", 2, "suffix", "behavior", 3,
            behavior_flag="BERSERK",
            behavior_params={"threshold": 0.60, "dmg_bonus": 1.8},
            incompatible_with=["buff_next"]),
        row("-одержимый",  "berserk", 3, "suffix", "behavior", 4,
            behavior_flag="BERSERK",
            behavior_params={"threshold": 0.75, "dmg_bonus": 2.2},
            incompatible_with=["buff_next"]),

        # regen — HP regeneration every N messages
        row("-регенератор", "regen", 1, "suffix", "behavior", 2,
            behavior_flag="REGEN",
            behavior_params={"regen_pct": 3, "every_n": 5},
            incompatible_with=["undying"]),
        row("-живучий",     "regen", 2, "suffix", "behavior", 3,
            behavior_flag="REGEN",
            behavior_params={"regen_pct": 6, "every_n": 4},
            incompatible_with=["undying"]),
        row("-бессмертный", "regen", 3, "suffix", "behavior", 4,
            behavior_flag="REGEN",
            behavior_params={"regen_pct": 10, "every_n": 3},
            incompatible_with=["undying"]),

        # reflect — reflects a portion of damage back to the player
        row("-отражатель", "reflect", 1, "suffix", "behavior", 2,
            behavior_flag="REFLECT",
            behavior_params={"chance": 0.15, "reflect_pct": 0.20}),
        row("-зеркальный", "reflect", 2, "suffix", "behavior", 3,
            behavior_flag="REFLECT",
            behavior_params={"chance": 0.25, "reflect_pct": 0.35}),

        # split — splits into copies on death (copies deal damage on their death, no loot)
        row("-делитель", "split", 1, "suffix", "behavior", 3,
            behavior_flag="SPLIT",
            behavior_params={"copies": 2, "hp_pct": 0.40, "dmg_pct": 0.40},
            incompatible_with=["undying"]),
        row("-роевой",   "split", 2, "suffix", "behavior", 4,
            behavior_flag="SPLIT",
            behavior_params={"copies": 3, "hp_pct": 0.50, "dmg_pct": 0.50},
            incompatible_with=["undying"]),

        # undying — revives once after death (only undead, demon)
        row("-нежить",  "undying", 1, "suffix", "behavior", 3,
            behavior_flag="UNDYING",
            behavior_params={"revive_hp_pct": 0.10},
            incompatible_with=["split", "regen"],
            allowed_families=["undead", "demon"]),
        row("-феникс",  "undying", 2, "suffix", "behavior", 4,
            behavior_flag="UNDYING",
            behavior_params={"revive_hp_pct": 0.20},
            incompatible_with=["split", "regen"],
            allowed_families=["undead", "demon"]),
        row("-вечный",  "undying", 3, "suffix", "behavior", 5,
            behavior_flag="UNDYING",
            behavior_params={"revive_hp_pct": 0.30},
            incompatible_with=["split", "regen"],
            allowed_families=["undead", "demon"]),

        # media_block — blocks every N-th media message from dealing damage
        row("-поглотитель", "media_block", 1, "suffix", "behavior", 2,
            behavior_flag="MEDIA_BLOCK",
            behavior_params={"every_n": 3},
            incompatible_with=["text_immune"],
            forbidden_families=["construct"]),
        row("-пожиратель",  "media_block", 2, "suffix", "behavior", 3,
            behavior_flag="MEDIA_BLOCK",
            behavior_params={"every_n": 2},
            incompatible_with=["text_immune"],
            forbidden_families=["construct"]),
        row("-аннигилятор", "media_block", 3, "suffix", "behavior", 4,
            behavior_flag="MEDIA_BLOCK",
            behavior_params={"every_n": 1},
            incompatible_with=["text_immune"],
            forbidden_families=["construct"]),

        # media_immune — full immunity to one media type (not tiers, one random is assigned)
        # dmg_coeff reflects how much damage this media type normally deals (for balance reference)
        row("-игнорирующий аудио",    "media_immune_audio",   None, "suffix", "behavior", 1,
            behavior_flag="MEDIA_IMMUNE",
            behavior_params={"media_type": "audio", "dmg_coeff": 2.0}),
        row("-игнорирующий ссылки",   "media_immune_url",     None, "suffix", "behavior", 2,
            behavior_flag="MEDIA_IMMUNE",
            behavior_params={"media_type": "url", "dmg_coeff": 1.5}),
        row("-игнорирующий видео",    "media_immune_video",   None, "suffix", "behavior", 2,
            behavior_flag="MEDIA_IMMUNE",
            behavior_params={"media_type": "video", "dmg_coeff": 2.5}),
        row("-игнорирующий фото",     "media_immune_photo",   None, "suffix", "behavior", 3,
            behavior_flag="MEDIA_IMMUNE",
            behavior_params={"media_type": "photo", "dmg_coeff": 1.2}),
        row("-игнорирующий стикеры",  "media_immune_sticker", None, "suffix", "behavior", 4,
            behavior_flag="MEDIA_IMMUNE",
            behavior_params={"media_type": "sticker", "dmg_coeff": 0.9}),

        # text_immune — immune to text messages (only undead, elemental, demon)
        row("-неосязаемый", "text_immune", None, "suffix", "behavior", 5,
            behavior_flag="TEXT_IMMUNE",
            behavior_params={},
            incompatible_with=["media_block"],
            allowed_families=["undead", "elemental", "demon"]),

        # curse — debuffs player damage for the rest of the fight
        row("-проклинатель", "curse", 1, "suffix", "debuff", 2,
            behavior_flag="CURSE",
            behavior_params={"dmg_reduction": 0.15}),
        row("-порченый",     "curse", 2, "suffix", "debuff", 3,
            behavior_flag="CURSE",
            behavior_params={"dmg_reduction": 0.25}),
        row("-осквернитель", "curse", 3, "suffix", "debuff", 4,
            behavior_flag="CURSE",
            behavior_params={"dmg_reduction": 0.40}),

        # anti_crit — reduces player crit chance for the fight
        row("-скользкий", "anti_crit", 1, "suffix", "debuff", 1,
            behavior_flag="ANTI_CRIT",
            behavior_params={"crit_reduction": 0.15}),
        row("-туманный",  "anti_crit", 2, "suffix", "debuff", 2,
            behavior_flag="ANTI_CRIT",
            behavior_params={"crit_reduction": 0.30}),

        # miser — reduces rewards for killing this monster
        row("-жадина", "miser", 1, "suffix", "reward", 1,
            gold_mult=0.70, drop_chance_mult=0.70,
            behavior_flag="MISER",
            incompatible_with=["ancient"]),
        row("-скряга",  "miser", 2, "suffix", "reward", 2,
            gold_mult=0.50, exp_mult=0.80, drop_chance_mult=0.50,
            behavior_flag="MISER",
            incompatible_with=["ancient"]),

        # buff_next — buffs all following monsters in dungeon while alive
        # forbidden: slime (too weak for commander role)
        row("-воевода",    "buff_next", 1, "suffix", "behavior", 2,
            behavior_flag="BUFF_NEXT",
            behavior_params={"hp_mult": 1.20},
            incompatible_with=["berserk"],
            forbidden_families=["slime"]),
        row("-полководец", "buff_next", 2, "suffix", "behavior", 3,
            behavior_flag="BUFF_NEXT",
            behavior_params={"hp_mult": 1.20, "dmg_mult": 1.15},
            incompatible_with=["berserk"],
            forbidden_families=["slime"]),
        row("-повелитель", "buff_next", 3, "suffix", "behavior", 5,
            behavior_flag="BUFF_NEXT",
            behavior_params={"hp_mult": 1.30, "dmg_mult": 1.20, "player_dmg_mult": 0.90},
            incompatible_with=["berserk"],
            forbidden_families=["slime"]),
    ]

    affix_table = sa.table(
        "monster_affixes",
        sa.column("name", sa.String()),
        sa.column("affix_group", sa.String()),
        sa.column("tier", sa.Integer()),
        sa.column("type", sa.String()),
        sa.column("category", sa.String()),
        sa.column("level_add", sa.Integer()),
        sa.column("hp_mult", sa.Float()),
        sa.column("dmg_mult", sa.Float()),
        sa.column("defense_add", sa.Integer()),
        sa.column("evade_add", sa.Integer()),
        sa.column("gold_mult", sa.Float()),
        sa.column("exp_mult", sa.Float()),
        sa.column("drop_chance_mult", sa.Float()),
        sa.column("drop_rarity_bonus", sa.Integer()),
        sa.column("behavior_flag", sa.String()),
        sa.column("behavior_params", sa.JSON()),
        sa.column("incompatible_with", sa.JSON()),
        sa.column("allowed_families", sa.JSON()),
        sa.column("forbidden_families", sa.JSON()),
        sa.column("max_per_monster", sa.Integer()),
    )
    op.bulk_insert(affix_table, rows)


def downgrade() -> None:
    op.drop_table("monster_affixes")

    op.drop_column("dungeon_run_monsters", "applied_affix_ids")
    op.drop_column("dungeon_run_monsters", "elite_color")
    op.drop_column("dungeon_run_monsters", "is_elite")

    op.drop_column("monster_templates", "max_affixes")
    op.drop_column("monster_templates", "elite_chance")
