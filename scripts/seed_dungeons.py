#!/usr/bin/env python3
"""Seed script for dungeons and monsters."""
import asyncio
from pathlib import Path

from sqlalchemy import select

from waifu_bot.db.session import get_session, init_engine
from waifu_bot.db import models as m

DATA_DIR = Path(__file__).resolve().parent / "data"
DUNGEONS_FILE = DATA_DIR / "dungeons.json"


async def upsert_dungeons(session, dungeons_data: list[dict]):
    """Upsert dungeons and their monsters."""
    for dungeon_data in dungeons_data:
        monsters_data = dungeon_data.pop("monsters", [])

        # Upsert dungeon
        existing = await session.scalar(
            select(m.Dungeon).where(
                m.Dungeon.act == dungeon_data["act"],
                m.Dungeon.dungeon_number == dungeon_data["dungeon_number"]
            )
        )
        if existing:
            for k, v in dungeon_data.items():
                setattr(existing, k, v)
            dungeon = existing
        else:
            dungeon = m.Dungeon(**dungeon_data)
            session.add(dungeon)
            await session.flush()  # Get dungeon ID

        # Upsert monsters
        for monster_data in monsters_data:
            monster_data["dungeon_id"] = dungeon.id
            existing_monster = await session.scalar(
                select(m.Monster).where(
                    m.Monster.dungeon_id == dungeon.id,
                    m.Monster.position == monster_data["position"]
                )
            )
            if existing_monster:
                for k, v in monster_data.items():
                    setattr(existing_monster, k, v)
            else:
                session.add(m.Monster(**monster_data))


async def main():
    """Main seeding function."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Sample dungeon data
    dungeons_data = [
        {
            "name": "Пещера Теней",
            "description": "Темная пещера, полная опасных существ",
            "act": 1,
            "dungeon_number": 1,
            "dungeon_type": 1,  # SOLO
            "level": 1,
            "obstacle_count": 3,
            "base_experience": 150,
            "base_gold": 500,
            "monsters": [
                {
                    "name": "Летучая Мышь",
                    "level": 1,
                    "max_hp": 50,
                    "damage": 8,
                    "experience_reward": 50,
                    "monster_type": "пещера",
                    "position": 1,
                },
                {
                    "name": "Каменный Голем",
                    "level": 2,
                    "max_hp": 80,
                    "damage": 12,
                    "experience_reward": 70,
                    "monster_type": "пещера",
                    "position": 2,
                },
                {
                    "name": "Теневой Страж",
                    "level": 3,
                    "max_hp": 120,
                    "damage": 15,
                    "experience_reward": 100,
                    "monster_type": "пещера",
                    "position": 3,
                },
            ]
        },
        {
            "name": "Лесной Лабиринт",
            "description": "Запутанный лес с дикими зверями",
            "act": 1,
            "dungeon_number": 2,
            "dungeon_type": 1,  # SOLO
            "level": 3,
            "obstacle_count": 4,
            "base_experience": 300,
            "base_gold": 1000,
            "monsters": [
                {
                    "name": "Дикий Волк",
                    "level": 3,
                    "max_hp": 90,
                    "damage": 14,
                    "experience_reward": 80,
                    "monster_type": "лес",
                    "position": 1,
                },
                {
                    "name": "Гигантский Паук",
                    "level": 4,
                    "max_hp": 110,
                    "damage": 16,
                    "experience_reward": 100,
                    "monster_type": "лес",
                    "position": 2,
                },
                {
                    "name": "Лесной Дух",
                    "level": 5,
                    "max_hp": 140,
                    "damage": 18,
                    "experience_reward": 120,
                    "monster_type": "лес",
                    "position": 3,
                },
                {
                    "name": "Древний Деревочеловек",
                    "level": 6,
                    "max_hp": 180,
                    "damage": 22,
                    "experience_reward": 150,
                    "monster_type": "лес",
                    "position": 4,
                },
            ]
        },
        {
            "name": "Подземный Храм",
            "description": "Забытый храм с древними стражами",
            "act": 1,
            "dungeon_number": 3,
            "dungeon_type": 1,  # SOLO
            "level": 5,
            "obstacle_count": 5,
            "base_experience": 500,
            "base_gold": 1500,
            "monsters": [
                {
                    "name": "Скелет-Воин",
                    "level": 5,
                    "max_hp": 120,
                    "damage": 18,
                    "experience_reward": 100,
                    "monster_type": "храм",
                    "position": 1,
                },
                {
                    "name": "Мумия",
                    "level": 6,
                    "max_hp": 150,
                    "damage": 20,
                    "experience_reward": 120,
                    "monster_type": "храм",
                    "position": 2,
                },
                {
                    "name": "Призрачный Страж",
                    "level": 7,
                    "max_hp": 180,
                    "damage": 24,
                    "experience_reward": 150,
                    "monster_type": "храм",
                    "position": 3,
                },
                {
                    "name": "Жрец Тьмы",
                    "level": 8,
                    "max_hp": 220,
                    "damage": 28,
                    "experience_reward": 180,
                    "monster_type": "храм",
                    "position": 4,
                },
                {
                    "name": "Хранитель Храма",
                    "level": 9,
                    "max_hp": 280,
                    "damage": 32,
                    "experience_reward": 220,
                    "monster_type": "храм",
                    "position": 5,
                },
            ]
        },
        {
            "name": "Огненные Пещеры",
            "description": "Раскаленные пещеры с лавовыми существами",
            "act": 1,
            "dungeon_number": 4,
            "dungeon_type": 1,  # SOLO
            "level": 7,
            "obstacle_count": 4,
            "base_experience": 700,
            "base_gold": 2000,
            "monsters": [
                {
                    "name": "Огненный Элементаль",
                    "level": 7,
                    "max_hp": 200,
                    "damage": 25,
                    "experience_reward": 150,
                    "monster_type": "огонь",
                    "position": 1,
                },
                {
                    "name": "Лавовый Голем",
                    "level": 8,
                    "max_hp": 250,
                    "damage": 30,
                    "experience_reward": 180,
                    "monster_type": "огонь",
                    "position": 2,
                },
                {
                    "name": "Пепельный Дракон",
                    "level": 9,
                    "max_hp": 320,
                    "damage": 35,
                    "experience_reward": 220,
                    "monster_type": "огонь",
                    "position": 3,
                },
                {
                    "name": "Повелитель Огня",
                    "level": 10,
                    "max_hp": 400,
                    "damage": 40,
                    "experience_reward": 280,
                    "monster_type": "огонь",
                    "position": 4,
                },
            ]
        },
        {
            "name": "Крепость Тьмы",
            "description": "Мрачная крепость с армией нежити",
            "act": 1,
            "dungeon_number": 5,
            "dungeon_type": 1,  # SOLO
            "level": 9,
            "obstacle_count": 6,
            "base_experience": 1000,
            "base_gold": 3000,
            "monsters": [
                {
                    "name": "Скелет-Лучник",
                    "level": 9,
                    "max_hp": 180,
                    "damage": 22,
                    "experience_reward": 120,
                    "monster_type": "крепость",
                    "position": 1,
                },
                {
                    "name": "Зомби-Берсерк",
                    "level": 10,
                    "max_hp": 240,
                    "damage": 28,
                    "experience_reward": 150,
                    "monster_type": "крепость",
                    "position": 2,
                },
                {
                    "name": "Вампир-Воин",
                    "level": 11,
                    "max_hp": 300,
                    "damage": 32,
                    "experience_reward": 180,
                    "monster_type": "крепость",
                    "position": 3,
                },
                {
                    "name": "Призрачный Рыцарь",
                    "level": 12,
                    "max_hp": 380,
                    "damage": 38,
                    "experience_reward": 220,
                    "monster_type": "крепость",
                    "position": 4,
                },
                {
                    "name": "Лич-Маг",
                    "level": 13,
                    "max_hp": 450,
                    "damage": 45,
                    "experience_reward": 280,
                    "monster_type": "крепость",
                    "position": 5,
                },
                {
                    "name": "Властелин Тьмы",
                    "level": 15,
                    "max_hp": 600,
                    "damage": 55,
                    "experience_reward": 400,
                    "monster_type": "крепость",
                    "position": 6,
                },
            ]
        },
    ]

    init_engine()
    async for session in get_session():
        await upsert_dungeons(session, dungeons_data)
        await session.commit()
        break

    print(f"Seeded {len(dungeons_data)} dungeons")


if __name__ == "__main__":
    asyncio.run(main())
