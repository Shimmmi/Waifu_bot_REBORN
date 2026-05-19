"""Expedition affixes table + slot naming (base_location, affix_ids, biome_tag). cursor_plan_6.

Revision ID: 0026_exp_affixes_naming
Revises: 0025_exp_outcome_hired_exp
Create Date: 2026-03-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_exp_affixes_naming"
down_revision: Union[str, None] = "0025_exp_outcome_hired_exp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expedition_affixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),  # 'prefix' | 'suffix'
        sa.Column("category", sa.String(32), nullable=False),  # elemental, enemy, hazard, cursed, blessed
        sa.Column("difficulty_add", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("damage_mult", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("reward_mult", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("paired_perks", sa.JSON(), nullable=True),
        sa.Column("allowed_biomes", sa.JSON(), nullable=True),
        sa.Column("forbidden_biomes", sa.JSON(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("description_hint", sa.String(128), nullable=True),
    )

    affixes_data = [
        # 10 prefixes
        {"name": "Огненная", "type": "prefix", "category": "elemental", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["magic_ward", "spirit_ward"], "weight": 100},
        {"name": "Ледяная", "type": "prefix", "category": "elemental", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["nature_weather", "def_fortress"], "weight": 100},
        {"name": "Ядовитая", "type": "prefix", "category": "elemental", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["heal_antidote", "nature_poison"], "weight": 100},
        {"name": "Проклятая", "type": "prefix", "category": "cursed", "difficulty_add": 2, "damage_mult": 1.4, "reward_mult": 1.3, "paired_perks": ["spirit_curse", "spirit_ward"], "weight": 100},
        {"name": "Тёмная", "type": "prefix", "category": "cursed", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["spirit_anchor", "stealth_shadow"], "weight": 100},
        {"name": "Заброшенная", "type": "prefix", "category": "hazard", "difficulty_add": 0, "damage_mult": 0.9, "reward_mult": 0.9, "paired_perks": ["trap_detect", "know_history"], "weight": 100},
        {"name": "Древняя", "type": "prefix", "category": "blessed", "difficulty_add": 0, "damage_mult": 1.0, "reward_mult": 1.3, "paired_perks": ["know_history", "know_language"], "weight": 100},
        {"name": "Туманная", "type": "prefix", "category": "hazard", "difficulty_add": 1, "damage_mult": 1.1, "reward_mult": 1.0, "paired_perks": ["stealth_shadow", "nature_pathfind"], "weight": 100},
        {"name": "Затопленная", "type": "prefix", "category": "elemental", "difficulty_add": 2, "damage_mult": 1.3, "reward_mult": 1.2, "paired_perks": ["nature_pathfind", "social_charm"], "weight": 100},
        {"name": "Горящая", "type": "prefix", "category": "elemental", "difficulty_add": 2, "damage_mult": 1.5, "reward_mult": 1.4, "paired_perks": ["magic_ward", "heal_antidote"], "weight": 100},
        # 12 suffixes
        {"name": "с гоблинами", "type": "suffix", "category": "enemy", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["combat_strike", "social_intimidate"], "weight": 100},
        {"name": "с разбойниками", "type": "suffix", "category": "enemy", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.2, "paired_perks": ["combat_tactics", "stealth_shadow"], "weight": 100},
        {"name": "с пауками", "type": "suffix", "category": "enemy", "difficulty_add": 1, "damage_mult": 1.3, "reward_mult": 1.1, "paired_perks": ["trap_detect", "nature_poison"], "weight": 100},
        {"name": "со змеями", "type": "suffix", "category": "enemy", "difficulty_add": 1, "damage_mult": 1.2, "reward_mult": 1.1, "paired_perks": ["heal_antidote", "nature_beast"], "weight": 100},
        {"name": "с нежитью", "type": "suffix", "category": "enemy", "difficulty_add": 2, "damage_mult": 1.4, "reward_mult": 1.3, "paired_perks": ["spirit_ward", "spirit_drain"], "weight": 100},
        {"name": "с демонами", "type": "suffix", "category": "enemy", "difficulty_add": 2, "damage_mult": 1.5, "reward_mult": 1.4, "paired_perks": ["spirit_ward", "magic_ward"], "weight": 100},
        {"name": "с ловушками", "type": "suffix", "category": "hazard", "difficulty_add": 1, "damage_mult": 1.3, "reward_mult": 1.1, "paired_perks": ["trap_detect", "trap_disarm"], "weight": 100},
        {"name": "с огненными реками", "type": "suffix", "category": "hazard", "difficulty_add": 2, "damage_mult": 1.4, "reward_mult": 1.3, "paired_perks": ["magic_ward", "def_fortress"], "weight": 100},
        {"name": "с призраками", "type": "suffix", "category": "enemy", "difficulty_add": 1, "damage_mult": 1.3, "reward_mult": 1.2, "paired_perks": ["spirit_commune", "spirit_anchor"], "weight": 100},
        {"name": "с охраной", "type": "suffix", "category": "enemy", "difficulty_add": 2, "damage_mult": 1.4, "reward_mult": 1.3, "paired_perks": ["stealth_disguise", "social_bribe"], "weight": 100},
        {"name": "с головоломками", "type": "suffix", "category": "hazard", "difficulty_add": 0, "damage_mult": 0.8, "reward_mult": 1.4, "paired_perks": ["know_language", "magic_identify"], "weight": 100},
        {"name": "с сокровищами", "type": "suffix", "category": "blessed", "difficulty_add": 0, "damage_mult": 1.0, "reward_mult": 1.8, "paired_perks": ["luck_finder", "trade_fence"], "weight": 100},
    ]
    from sqlalchemy import table, column
    t = table("expedition_affixes",
        column("name", sa.String(64)),
        column("type", sa.String(16)),
        column("category", sa.String(32)),
        column("difficulty_add", sa.Integer()),
        column("damage_mult", sa.Float()),
        column("reward_mult", sa.Float()),
        column("paired_perks", sa.JSON()),
        column("weight", sa.Integer()),
    )
    op.bulk_insert(t, [{"name": d["name"], "type": d["type"], "category": d["category"], "difficulty_add": d["difficulty_add"], "damage_mult": d["damage_mult"], "reward_mult": d["reward_mult"], "paired_perks": d["paired_perks"], "weight": d["weight"]} for d in affixes_data])

    op.add_column("expedition_slots", sa.Column("base_location", sa.String(64), nullable=True))
    op.add_column("expedition_slots", sa.Column("affix_ids", sa.JSON(), nullable=True))
    op.add_column("expedition_slots", sa.Column("computed_name", sa.String(256), nullable=True))
    op.add_column("expedition_slots", sa.Column("biome_tag", sa.String(32), nullable=True))
    op.add_column("expedition_slots", sa.Column("difficulty", sa.Integer(), nullable=True))
    op.add_column("expedition_slots", sa.Column("damage_mult", sa.Float(), nullable=True))
    op.add_column("expedition_slots", sa.Column("reward_mult", sa.Float(), nullable=True))
    op.add_column("expedition_slots", sa.Column("paired_perks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("expedition_slots", "paired_perks")
    op.drop_column("expedition_slots", "reward_mult")
    op.drop_column("expedition_slots", "damage_mult")
    op.drop_column("expedition_slots", "difficulty")
    op.drop_column("expedition_slots", "biome_tag")
    op.drop_column("expedition_slots", "computed_name")
    op.drop_column("expedition_slots", "affix_ids")
    op.drop_column("expedition_slots", "base_location")
    op.drop_table("expedition_affixes")
