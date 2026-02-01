#!/usr/bin/env python3
"""Seed GD dungeon templates and event templates."""
import asyncio
import sys
from pathlib import Path

# Add project root so waifu_bot is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select

from waifu_bot.db.session import get_session, init_engine
from waifu_bot.db.models.group_dungeon import GDDungeonTemplate, GDEventTemplate

# WaifuClass: KNIGHT=1, WARRIOR=2, ARCHER=3, MAGE=4, ASSASSIN=5, HEALER=6, MERCHANT=7
GD_DUNGEON_TEMPLATES = [
    {
        "name": "Воздушная крепость",
        "description": "Летающая крепость в облаках. Лучники наносят повышенный урон.",
        "hp_multiplier": 8.5,
        "thematic_bonus_description": "Лучники +25% урона",
        "thematic_bonus_class_ids": [3],  # ARCHER
        "unique_event_key": "whirlwind",
    },
    {
        "name": "Глубинный риф",
        "description": "Подводный риф. Лекари усиливают исцеление.",
        "hp_multiplier": 7.0,
        "thematic_bonus_description": "Лекари +40% к исцелению",
        "thematic_bonus_class_ids": [6],  # HEALER
        "unique_event_key": "tide",
    },
    {
        "name": "Пустыня забвения",
        "description": "Бескрайние пески. Торговцы получают больше монет.",
        "hp_multiplier": 9.0,
        "thematic_bonus_description": "Торговцы +20% монет",
        "thematic_bonus_class_ids": [7],  # MERCHANT
        "unique_event_key": "oasis",
    },
    {
        "name": "Лабиринт зеркал",
        "description": "Зеркальные коридоры. Воины усиливают щит.",
        "hp_multiplier": 8.0,
        "thematic_bonus_description": "Воины +15% к щиту",
        "thematic_bonus_class_ids": [2],  # WARRIOR
        "unique_event_key": "reflection",
    },
    {
        "name": "Часовня времени",
        "description": "Застывшее время. Маги наносят повышенный урон.",
        "hp_multiplier": 10.0,
        "thematic_bonus_description": "Маги +20% к урону",
        "thematic_bonus_class_ids": [4],  # MAGE
        "unique_event_key": "slowdown",
    },
]

GD_EVENT_TEMPLATES = [
    # 50% HP events
    {"trigger_type": "hp_50", "target_type": "tank", "content_type": "sticker_or_emoji", "emoji_filter": "shield",
     "effect_type": "shield_30_90", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Щит"},
    {"trigger_type": "hp_50", "target_type": "healer", "content_type": "text_or_emoji", "emoji_filter": "heal",
     "effect_type": "heal_20", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Исцеление"},
    {"trigger_type": "hp_50", "target_type": "all", "content_type": "text_emoji", "emoji_filter": "fire",
     "effect_type": "damage_buff_60", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Финальный рывок"},
    # 10% HP events (same pool, lower trigger)
    {"trigger_type": "hp_10", "target_type": "tank", "content_type": "sticker_or_emoji", "emoji_filter": "shield",
     "effect_type": "shield_30_90", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Щит"},
    {"trigger_type": "hp_10", "target_type": "healer", "content_type": "text_or_emoji", "emoji_filter": "heal",
     "effect_type": "heal_20", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Исцеление"},
    {"trigger_type": "hp_10", "target_type": "all", "content_type": "text_emoji", "emoji_filter": "fire",
     "effect_type": "damage_buff_60", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Финальный рывок"},
    # Engage chain (manual)
    {"trigger_type": "engage", "target_type": "any", "content_type": "chain_3",
     "effect_type": "instant_hp_35", "min_players_required": 2, "duration_seconds": 60, "weight": 100,
     "name": "Цепочка заданий"},
    # Boss unique events (by dungeon_event_key)
    {"trigger_type": "boss_unique", "dungeon_event_key": "whirlwind",
     "content_type": "emoji_count", "emoji_filter": "wind", "min_players_required": 5, "duration_seconds": 45,
     "effect_type": "instant_hp_25", "name": "Вихрь"},
    {"trigger_type": "boss_unique", "dungeon_event_key": "tide",
     "content_type": "emoji_count", "emoji_filter": "water", "min_players_required": 8, "duration_seconds": 45,
     "effect_type": "instant_hp_25", "name": "Прилив"},
    {"trigger_type": "boss_unique", "dungeon_event_key": "oasis",
     "content_type": "healer_plus_emoji", "emoji_filter": "sun", "min_players_required": 3, "duration_seconds": 45,
     "effect_type": "damage_buff_rest_of_boss", "name": "Оазис"},
    {"trigger_type": "boss_unique", "dungeon_event_key": "reflection",
     "content_type": "chain_3_classes", "emoji_filter": "mirror", "min_players_required": 3, "duration_seconds": 45,
     "effect_type": "instant_hp_20_shield_120", "name": "Отражение"},
    {"trigger_type": "boss_unique", "dungeon_event_key": "slowdown",
     "content_type": "voice_count", "min_players_required": 4, "duration_seconds": 60,
     "effect_type": "damage_buff_rest_of_boss", "name": "Замедление"},
    # Adaptive (low activity)
    {"trigger_type": "adaptive", "target_type": "all", "content_type": "text_emoji", "emoji_filter": "fire",
     "effect_type": "damage_buff_60", "min_players_required": 1, "duration_seconds": 45, "weight": 100,
     "name": "Финальный рывок"},
]


async def seed_gd_templates(session):
    """Upsert GD dungeon templates by name."""
    for data in GD_DUNGEON_TEMPLATES:
        existing = await session.scalar(
            select(GDDungeonTemplate).where(GDDungeonTemplate.name == data["name"])
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            session.add(GDDungeonTemplate(**data))
    await session.flush()


async def seed_event_templates(session):
    """Insert GD event templates (skip if same trigger_type + name + dungeon_event_key exists)."""
    for data in GD_EVENT_TEMPLATES:
        key = data.get("dungeon_event_key")
        q = select(GDEventTemplate).where(
            GDEventTemplate.trigger_type == data["trigger_type"],
            GDEventTemplate.name == data.get("name"),
        )
        if key:
            q = q.where(GDEventTemplate.dungeon_event_key == key)
        else:
            q = q.where(GDEventTemplate.dungeon_event_key.is_(None))
        existing = await session.scalar(q)
        if not existing:
            session.add(GDEventTemplate(**data))
    await session.flush()


async def main():
    init_engine()
    async for session in get_session():
        try:
            await seed_gd_templates(session)
            await seed_event_templates(session)
            await session.commit()
            print("GD dungeon templates and event templates seeded.")
        except Exception as e:
            await session.rollback()
            print("Error:", e)
            raise
        break


if __name__ == "__main__":
    asyncio.run(main())
