"""Legendary bonus pool v2: +270 unique bonuses (12 trigger families, total 316).

Bonuses are NOT bound to item templates here — distribution to the 316 base
templates is a separate later step (D2-style identity per item/tier).

Each row's params carry ``handler`` — the generic primitive in
``waifu_bot.game.legendary_bonuses.generic`` that executes it — plus an
``effects`` dict consumed by ``build_effects``. Rows whose primitive needs
pipeline data that is not fed yet (text content flags in extra_data) are
seeded with ``is_active = false``.

Revision ID: 0105_legendary_bonus_pool
Revises: 0104_player_bgm_playlists
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0105_legendary_bonus_pool"
down_revision: Union[str, None] = "0104_player_bgm_playlists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _f1_media_type() -> list[tuple]:
    """Family 1 — тип сообщения (36). trigger_group=media_type."""
    g = "media_type"
    return [
        # text (4)
        ("WORD_BLADE", "Словесный клинок", "Текстовые сообщения наносят ×1.4 урона.", g, "easy",
         {"handler": "media", "media_types": ["text"], "effects": {"damage_multiplier": 1.4}}, True),
        ("INK_CRIT", "Чернильный крит", "Текст: 20% шанс критического удара.", g, "easy",
         {"handler": "media", "media_types": ["text"], "effects": {"force_crit_chance": 0.20}}, True),
        ("GRAPHOMANIA_ECHO", "Эхо графомана", "Текст: 15% шанс дополнительного удара на 60% урона.", g, "easy",
         {"handler": "media", "media_types": ["text"], "effects": {"extra_hit_chance": 0.15, "extra_hit_pct": 0.60}}, True),
        ("PEN_VAMPIRISM", "Перо-вампир", "Текстовые удары лечат ОВ на 8% нанесённого урона.", g, "easy",
         {"handler": "media", "media_types": ["text"], "effects": {"heal_pct_of_damage": 0.08}}, True),
        # sticker (5)
        ("STICKER_TRIPLE", "Стикер-залп", "Стикеры наносят ×3 урона.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"damage_multiplier": 3.0}}, True),
        ("STICKER_CRIT", "Липкий крит", "Стикер: 30% шанс критического удара.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"force_crit_chance": 0.30}}, True),
        ("STICKER_PIERCE", "Острый стикер", "Стикеры игнорируют броню монстра.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"ignore_monster_armor": True, "damage_multiplier": 1.2}}, True),
        ("STICKER_LIFELINE", "Стикер-аптечка", "Каждый стикер лечит ОВ на 3% макс. HP.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"heal_pct_max_hp": 0.03}}, True),
        ("STICKER_DOUBLE_TAP", "Двойное касание", "Стикер: 25% шанс второго удара на 50% урона.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"extra_hit_chance": 0.25, "extra_hit_pct": 0.50}}, True),
        # photo (4)
        ("PHOTO_FLASH", "Вспышка", "Фотографии наносят ×2.5 урона.", g, "easy",
         {"handler": "media", "media_types": ["photo"], "effects": {"damage_multiplier": 2.5}}, True),
        ("PHOTO_FOCUS", "Резкость", "Фото: 25% шанс критического удара.", g, "easy",
         {"handler": "media", "media_types": ["photo"], "effects": {"force_crit_chance": 0.25}}, True),
        ("PHOTO_ALBUM", "Фотоальбом", "Фото: два дополнительных удара по 40% урона.", g, "easy",
         {"handler": "media", "media_types": ["photo"], "effects": {"extra_hits": [0.40, 0.40]}}, True),
        ("PHOTO_XRAY", "Рентген", "Фото игнорирует броню и уклонение монстра.", g, "easy",
         {"handler": "media", "media_types": ["photo"], "effects": {"ignore_monster_armor": True, "ignore_monster_dodge": True}}, True),
        # gif (4)
        ("GIF_LOOP", "Зацикленность", "Гифки наносят ×2.5 урона.", g, "easy",
         {"handler": "media", "media_types": ["gif"], "effects": {"damage_multiplier": 2.5}}, True),
        ("GIF_HYPNOSIS", "Гипноз", "Гифка: монстр заворожён и не контратакует.", g, "easy",
         {"handler": "media", "media_types": ["gif"], "effects": {"ignore_monster_death_damage": True, "damage_multiplier": 1.3}}, True),
        ("GIF_FRENZY", "Кадровая ярость", "Гифка: 30% шанс дополнительного удара на 70% урона.", g, "easy",
         {"handler": "media", "media_types": ["gif"], "effects": {"extra_hit_chance": 0.30, "extra_hit_pct": 0.70}}, True),
        ("GIF_GLITCH", "Глитч-кадр", "Гифка: 20% шанс крита, игнорирует уклонение.", g, "easy",
         {"handler": "media", "media_types": ["gif"], "effects": {"force_crit_chance": 0.20, "ignore_monster_dodge": True}}, True),
        # audio (3)
        ("AUDIO_BASSLINE", "Басовая волна", "Аудио наносит ×3 урона.", g, "easy",
         {"handler": "media", "media_types": ["audio"], "effects": {"damage_multiplier": 3.0}}, True),
        ("AUDIO_RESONANCE", "Резонанс", "Аудио игнорирует броню и лечит 10% нанесённого урона.", g, "easy",
         {"handler": "media", "media_types": ["audio"], "effects": {"ignore_monster_armor": True, "heal_pct_of_damage": 0.10}}, True),
        ("AUDIO_ENCORE", "Бис!", "Аудио: 25% шанс повторного удара на 80% урона.", g, "easy",
         {"handler": "media", "media_types": ["audio"], "effects": {"extra_hit_chance": 0.25, "extra_hit_pct": 0.80}}, True),
        # video (3)
        ("VIDEO_PREMIERE", "Премьера", "Видео наносит ×2.5 урона.", g, "easy",
         {"handler": "media", "media_types": ["video"], "effects": {"damage_multiplier": 2.5}}, True),
        ("VIDEO_MONTAGE", "Монтаж", "Видео: три склейки по 50% урона вместо одного удара.", g, "medium",
         {"handler": "media", "media_types": ["video"], "effects": {"replace_with_hits": [0.5, 0.5, 0.5]}}, True),
        ("VIDEO_BLOCKBUSTER", "Блокбастер", "Видео: 15% шанс крита, крит-урон ×2.5.", g, "easy",
         {"handler": "media", "media_types": ["video"], "effects": {"force_crit_chance": 0.15, "crit_damage_multiplier": 2.5}}, True),
        # voice (4)
        ("VOICE_THUNDER", "Громовой голос", "Голосовые сообщения наносят ×3 урона.", g, "easy",
         {"handler": "media", "media_types": ["voice"], "effects": {"damage_multiplier": 3.0}}, True),
        ("VOICE_COMMAND", "Командный тон", "Войс: 35% шанс критического удара.", g, "easy",
         {"handler": "media", "media_types": ["voice"], "effects": {"force_crit_chance": 0.35}}, True),
        ("VOICE_LULLABY", "Колыбельная", "Войс: монстр наносит себе 30% базового урона.", g, "medium",
         {"handler": "media", "media_types": ["voice"], "effects": {"monster_self_damage_pct_base": 0.30}}, True),
        ("VOICE_SIREN", "Сирена", "Войс: ×1.5 урона, игнорирует уклонение.", g, "easy",
         {"handler": "media", "media_types": ["voice"], "effects": {"damage_multiplier": 1.5, "ignore_monster_dodge": True}}, True),
        # link (3)
        ("LINK_VIRUS", "Вирусная ссылка", "Ссылки наносят ×4 урона.", g, "easy",
         {"handler": "media", "media_types": ["link"], "effects": {"damage_multiplier": 4.0}}, True),
        ("LINK_PHISHING", "Фишинг", "Ссылка игнорирует броню и аффиксы монстра.", g, "easy",
         {"handler": "media", "media_types": ["link"], "effects": {"ignore_monster_armor": True, "ignore_monster_affixes": True, "damage_multiplier": 1.3}}, True),
        ("LINK_RICKROLL", "Рикролл", "Ссылка: 50% шанс ×3 урона, иначе ×0.5.", g, "medium",
         {"handler": "random_proc", "media_types": ["link"], "outcomes": [
             {"chance": 0.5, "effects": {"damage_multiplier": 3.0, "notification": "🎶 Рикролл сработал!"}},
             {"chance": 0.5, "effects": {"damage_multiplier": 0.5}},
         ]}, True),
        # cross-type (6)
        ("MEDIA_STORM", "Медиабуря", "Любое не-текстовое сообщение наносит ×2 урона.", g, "easy",
         {"handler": "media", "media_types": ["text"], "not_in": True, "effects": {"damage_multiplier": 2.0}}, True),
        ("PURIST", "Пуристка", "Текст ×1.6 урона, любое медиа ×0.8.", g, "easy",
         {"handler": "media", "media_types": ["text"], "effects": {"damage_multiplier": 1.6}, "else_effects": {"damage_multiplier": 0.8}}, True),
        ("MULTIMEDIA_LANCE", "Мультимедийное копьё", "Не-текстовые сообщения игнорируют броню монстра.", g, "easy",
         {"handler": "media", "media_types": ["text"], "not_in": True, "effects": {"ignore_monster_armor": True}}, True),
        ("SILENT_FILM", "Немое кино", "Фото, гифки и видео наносят ×1.8 урона.", g, "easy",
         {"handler": "media", "media_types": ["photo", "gif", "video"], "effects": {"damage_multiplier": 1.8}}, True),
        ("LOUDSPEAKER", "Громкоговоритель", "Войсы и аудио: ×1.8 урона и 5% вампиризм.", g, "easy",
         {"handler": "media", "media_types": ["voice", "audio"], "effects": {"damage_multiplier": 1.8, "heal_pct_of_damage": 0.05}}, True),
        ("MEME_ARTILLERY", "Мем-артиллерия", "Стикеры и гифки: ×1.7 урона и 10% шанс крита.", g, "easy",
         {"handler": "media", "media_types": ["sticker", "gif"], "effects": {"damage_multiplier": 1.7, "force_crit_chance": 0.10}}, True),
    ]


def _f2_time_calendar() -> list[tuple]:
    """Family 2 — время суток / календарь (21). trigger_group=time_calendar."""
    g = "time_calendar"
    tz = "Europe/Moscow"
    return [
        ("NIGHT_HUNTER", "Ночная охотница", "Сообщения ночью (22:00–06:00) наносят ×2 урона.", g, "easy",
         {"handler": "time_window", "hour_start": 22, "hour_end": 6, "timezone": tz, "effects": {"damage_multiplier": 2.0}}, True),
        ("DAWN_PATROL", "Рассветный дозор", "Удары на рассвете (05:00–08:00) наносят ×2.5 урона.", g, "easy",
         {"handler": "time_window", "hour_start": 5, "hour_end": 8, "timezone": tz, "effects": {"damage_multiplier": 2.5}}, True),
        ("LUNCH_BREAK", "Обеденный перерыв", "12:00–14:00: урон ×1.8.", g, "easy",
         {"handler": "time_window", "hour_start": 12, "hour_end": 14, "timezone": tz, "effects": {"damage_multiplier": 1.8}}, True),
        ("EVENING_RITUAL", "Вечерний ритуал", "18:00–22:00: урон +40%.", g, "easy",
         {"handler": "time_window", "hour_start": 18, "hour_end": 22, "timezone": tz, "effects": {"damage_multiplier": 1.4}}, True),
        ("WITCHING_HOUR", "Час зверя", "03:00–04:00: урон ×4.", g, "easy",
         {"handler": "time_window", "hour_start": 3, "hour_end": 4, "timezone": tz, "effects": {"damage_multiplier": 4.0, "notification": "🐺 Час зверя!"}}, True),
        ("WEEKEND_WARRIOR", "Воин выходных", "В субботу и воскресенье урон ×1.5.", g, "easy",
         {"handler": "time_window", "weekdays": [6, 7], "timezone": tz, "effects": {"damage_multiplier": 1.5}}, True),
        ("MONDAY_RAGE", "Ярость понедельника", "По понедельникам урон ×1.8.", g, "easy",
         {"handler": "time_window", "weekdays": [1], "timezone": tz, "effects": {"damage_multiplier": 1.8}}, True),
        ("FRIDAY_PARTY", "Пятничный кураж", "По пятницам: урон ×1.6 и золото ×1.3.", g, "easy",
         {"handler": "time_window", "weekdays": [5], "timezone": tz, "effects": {"damage_multiplier": 1.6, "gold_multiplier": 1.3}}, True),
        ("MIDWEEK_FOCUS", "Фокус среды", "По средам: 25% шанс критического удара.", g, "easy",
         {"handler": "time_window", "weekdays": [3], "timezone": tz, "effects": {"force_crit_chance": 0.25}}, True),
        ("MIRROR_HOUR", "Зеркальный час", "Когда час равен минуте (11:11, 22:22) — урон ×5.", g, "medium",
         {"handler": "time_window", "mode": "mirror_time", "timezone": tz, "effects": {"damage_multiplier": 5.0, "notification": "🪞 Зеркальный час!"}}, True),
        ("EVEN_HOUR_SURGE", "Чётный час", "В чётные часы урон +25%.", g, "easy",
         {"handler": "time_window", "mode": "even_hour", "timezone": tz, "effects": {"damage_multiplier": 1.25}}, True),
        ("ODD_HOUR_EDGE", "Нечётный час", "В нечётные часы: 15% шанс крита.", g, "easy",
         {"handler": "time_window", "mode": "odd_hour", "timezone": tz, "effects": {"force_crit_chance": 0.15}}, True),
        ("NIGHT_MERCHANT", "Ночная торговка", "00:00–06:00: золото с убийств ×2.", g, "easy",
         {"handler": "time_window", "hour_start": 0, "hour_end": 6, "timezone": tz, "effects": {"gold_multiplier": 2.0}}, True),
        ("MORNING_LOOT", "Утренний лут", "06:00–10:00: шанс редкого дропа ×1.5.", g, "easy",
         {"handler": "time_window", "hour_start": 6, "hour_end": 10, "timezone": tz, "effects": {"drop_chance_multiplier": 1.5}}, True),
        ("PRIME_TIME", "Прайм-тайм", "19:00–21:00: урон ×1.7 и 20% шанс доп. удара на 30%.", g, "easy",
         {"handler": "time_window", "hour_start": 19, "hour_end": 21, "timezone": tz, "effects": {"damage_multiplier": 1.7, "extra_hit_chance": 0.20, "extra_hit_pct": 0.30}}, True),
        ("NIGHT_STICKERS", "Ночные стикеры", "Стикеры ночью (23:00–06:00) наносят ×3.5 урона.", g, "easy",
         {"handler": "time_window", "hour_start": 23, "hour_end": 6, "media_types": ["sticker"], "timezone": tz, "effects": {"damage_multiplier": 3.5}}, True),
        ("SUNDAY_SERMON", "Воскресная проповедь", "Войсы по воскресеньям наносят ×3 урона.", g, "easy",
         {"handler": "time_window", "weekdays": [7], "media_types": ["voice"], "timezone": tz, "effects": {"damage_multiplier": 3.0}}, True),
        ("NEW_DAY_SPARK", "Искра нового дня", "00:00–01:00: урон ×2.2 и снятие дебаффов с ОВ.", g, "medium",
         {"handler": "time_window", "hour_start": 0, "hour_end": 1, "timezone": tz, "effects": {"damage_multiplier": 2.2, "clear_waifu_debuffs": True}}, True),
        ("SIESTA", "Сиеста", "14:00–16:00: монстр дремлет и не контратакует.", g, "easy",
         {"handler": "time_window", "hour_start": 14, "hour_end": 16, "timezone": tz, "effects": {"ignore_monster_death_damage": True, "damage_multiplier": 1.2}}, True),
        ("DEADLINE_RUSH", "Дедлайн", "23:00–00:00: урон ×2 и 10% вампиризм.", g, "easy",
         {"handler": "time_window", "hour_start": 23, "hour_end": 0, "timezone": tz, "effects": {"damage_multiplier": 2.0, "heal_pct_of_damage": 0.10}}, True),
        ("CHRONO_TRIAD", "Хроно-триада", "В часы, кратные трём (00, 03, …, 21), урон ×1.6.", g, "easy",
         {"handler": "time_window", "mode": "hour_mod", "mod": 3, "remainder": 0, "timezone": tz, "effects": {"damage_multiplier": 1.6}}, True),
    ]


def _f3_tempo() -> list[tuple]:
    """Family 3 — темп и паузы (17). trigger_group=tempo."""
    g = "tempo"
    return [
        ("RAPID_FIRE", "Скорострельность", "Сообщение быстрее 5 секунд после прошлого — урон ×1.4.", g, "easy",
         {"handler": "tempo", "mode": "fast", "window_seconds": 5, "effects": {"damage_multiplier": 1.4}}, True),
        ("LIGHTNING_REFLEX", "Молниеносность", "Сообщение быстрее 3 секунд — 30% шанс крита.", g, "easy",
         {"handler": "tempo", "mode": "fast", "window_seconds": 3, "effects": {"force_crit_chance": 0.30}}, True),
        ("BERSERK_TEMPO", "Темп берсерка", "Серия быстрых (<10 с) сообщений: +10% урона за каждое, до 10 стаков.", g, "medium",
         {"handler": "tempo", "mode": "fast_streak", "window_seconds": 10, "max_stacks": 10, "effects": {"damage_bonus": 0.10}}, True),
        ("COLD_BLOOD", "Хладнокровие", "Пауза 30+ секунд: следующий удар +50%.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 30, "effects": {"damage_multiplier": 1.5}}, True),
        ("AMBUSH_TIMING", "Выжидание", "Пауза 2+ минуты: удар ×2.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 120, "effects": {"damage_multiplier": 2.0}}, True),
        ("SNIPER_BREATH", "Дыхание снайпера", "Пауза 5+ минут: удар ×3, игнорирует уклонение.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 300, "effects": {"damage_multiplier": 3.0, "ignore_monster_dodge": True}}, True),
        ("CHARGED_MINUTES", "Заряд минут", "После минуты тишины: +20% урона за каждую минуту, максимум ×3.", g, "medium",
         {"handler": "tempo", "mode": "pause_scaled", "min_seconds": 60, "max_stacks": 10, "effects": {"damage_bonus": 0.20, "max_damage_multiplier": 3.0}}, True),
        ("METRONOME", "Метроном", "Интервал между сообщениями 10–20 секунд: урон ×1.5.", g, "easy",
         {"handler": "tempo", "mode": "band", "min_seconds": 10, "max_seconds": 20, "effects": {"damage_multiplier": 1.5}}, True),
        ("RHYTHM_KEEPER", "Хранительница ритма", "Интервал совпадает с предыдущим (±20%) — урон ×1.8.", g, "medium",
         {"handler": "tempo", "mode": "rhythm", "tolerance": 0.2, "effects": {"damage_multiplier": 1.8, "notification": "🥁 В ритме!"}}, True),
        ("UNHURRIED", "Неторопливая", "Сообщение спустя 60+ секунд: урон +60%.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 60, "effects": {"damage_multiplier": 1.6}}, True),
        ("SPRINT", "Спринт", "Серия быстрых (<10 с) сообщений: +15% за стак, до 3 стаков.", g, "medium",
         {"handler": "tempo", "mode": "fast_streak", "window_seconds": 10, "max_stacks": 3, "effects": {"damage_bonus": 0.15}}, True),
        ("PATIENT_BLADE", "Терпеливый клинок", "Пауза 10+ минут: гарантированный крит.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 600, "effects": {"force_crit": True, "notification": "🗡️ Терпение вознаграждено!"}}, True),
        ("QUICK_STICKER", "Быстрый стикер", "Стикер быстрее 6 секунд после прошлого сообщения — ×2.5.", g, "easy",
         {"handler": "tempo", "mode": "fast", "window_seconds": 6, "media_types": ["sticker"], "effects": {"damage_multiplier": 2.5}}, True),
        ("SLOW_BURN", "Медленное пламя", "Интервал 30–120 секунд: +35% урона и 5% вампиризм.", g, "easy",
         {"handler": "tempo", "mode": "band", "min_seconds": 30, "max_seconds": 120, "effects": {"damage_multiplier": 1.35, "heal_pct_of_damage": 0.05}}, True),
        ("FLASH_STEP", "Шаг-вспышка", "Сообщение быстрее 2 секунд: ×0.9 урона, но игнорирует броню и уклонение.", g, "easy",
         {"handler": "tempo", "mode": "fast", "window_seconds": 2, "effects": {"damage_multiplier": 0.9, "ignore_monster_armor": True, "ignore_monster_dodge": True}}, True),
        ("OVERCLOCK", "Разгон", "Серия быстрых (<8 с) сообщений: +8% за стак, до 12 стаков.", g, "medium",
         {"handler": "tempo", "mode": "fast_streak", "window_seconds": 8, "max_stacks": 12, "effects": {"damage_bonus": 0.08}}, True),
        ("ZEN_STRIKE", "Дзен-удар", "Пауза 30+ минут: удар ×4 и лечение 10% макс. HP.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 1800, "effects": {"damage_multiplier": 4.0, "heal_pct_max_hp": 0.10, "notification": "🧘 Дзен!"}}, True),
    ]


def _f4_text_content() -> list[tuple]:
    """Family 4 — контент текста (22): 8 по длине (active) + 14 по содержимому
    (inactive — ждут extra_data["text"] из пайплайна). trigger_group=text_content."""
    g = "text_content"
    return [
        # length-based — active
        ("HAIKU", "Хайку", "Текст из 11–17 символов наносит ×2 урона.", g, "easy",
         {"handler": "text_length", "op": "between", "min_length": 11, "max_length": 17, "effects": {"damage_multiplier": 2.0}}, True),
        ("SHORT_JAB", "Короткий джеб", "Текст короче 5 символов — ×1.5 урона.", g, "easy",
         {"handler": "text_length", "op": "lt", "length": 5, "effects": {"damage_multiplier": 1.5}}, True),
        ("ESSAY", "Эссе", "Текст длиннее 300 символов — ×2.5 урона.", g, "easy",
         {"handler": "text_length", "op": "gt", "length": 300, "effects": {"damage_multiplier": 2.5}}, True),
        ("EVEN_COUNT", "Чётный счёт", "Текст с чётным числом символов — +30% урона.", g, "easy",
         {"handler": "text_length", "op": "even", "effects": {"damage_multiplier": 1.3}}, True),
        ("ODD_COUNT", "Нечётный счёт", "Текст с нечётным числом символов — 15% шанс крита.", g, "easy",
         {"handler": "text_length", "op": "odd", "effects": {"force_crit_chance": 0.15}}, True),
        ("LUCKY_SEVEN_CHARS", "Семь символов", "Текст ровно из 7 символов — ×3 урона.", g, "easy",
         {"handler": "text_length", "op": "eq", "length": 7, "effects": {"damage_multiplier": 3.0, "notification": "7️⃣ Семь символов!"}}, True),
        ("TELEGRAPH", "Телеграф", "Текст из 5–10 символов: +25% урона, игнорирует уклонение.", g, "easy",
         {"handler": "text_length", "op": "between", "min_length": 5, "max_length": 10, "effects": {"damage_multiplier": 1.25, "ignore_monster_dodge": True}}, True),
        ("NOVELLA", "Новелла", "Текст длиннее 150 символов: +15% за каждые 50 сверх, до ×2.8.", g, "medium",
         {"handler": "text_length", "op": "gt", "length": 150, "per_block": 50, "max_stacks": 12, "effects": {"damage_bonus": 0.15, "max_damage_multiplier": 2.8}}, True),
        # content-based — inactive until pipeline feeds extra_data["text"]
        ("CAPS_FURY", "Ярость капса", "Сообщение ЦЕЛИКОМ КАПСОМ наносит ×2 урона.", g, "medium",
         {"handler": "text_content", "mode": "caps", "effects": {"damage_multiplier": 2.0}}, False),
        ("QUESTION_MARK", "Вопрос ребром", "Текст, оканчивающийся на «?» — 25% шанс крита.", g, "medium",
         {"handler": "text_content", "mode": "question", "effects": {"force_crit_chance": 0.25}}, False),
        ("EXCLAMATION_STORM", "Восклицание", "Текст, оканчивающийся на «!» — ×1.6 урона.", g, "medium",
         {"handler": "text_content", "mode": "exclamation", "effects": {"damage_multiplier": 1.6}}, False),
        ("EMOJI_SPICE", "Эмодзи-приправа", "Эмодзи в тексте — +35% урона.", g, "medium",
         {"handler": "text_content", "mode": "emoji", "effects": {"damage_multiplier": 1.35}}, False),
        ("NUMERIC_CODE", "Числовой код", "Сообщение только из цифр — ×2.2 урона.", g, "medium",
         {"handler": "text_content", "mode": "digits_only", "effects": {"damage_multiplier": 2.2}}, False),
        ("ONE_WORD_VERDICT", "Вердикт", "Сообщение из одного слова — ×1.7 урона.", g, "medium",
         {"handler": "text_content", "mode": "one_word", "effects": {"damage_multiplier": 1.7}}, False),
        ("PALINDROME_MAGIC", "Магия палиндрома", "Текст-палиндром наносит ×5 урона.", g, "hard",
         {"handler": "text_content", "mode": "palindrome", "effects": {"damage_multiplier": 5.0, "notification": "🔄 Палиндром!"}}, False),
        ("WALL_OF_TEXT", "Стена текста", "Сообщение длиннее 30 слов — ×2 урона.", g, "medium",
         {"handler": "text_content", "mode": "word_count_gt", "word_count": 30, "effects": {"damage_multiplier": 2.0}}, False),
        ("SAME_CHAR_SCREAM", "Монотонный вопль", "Сообщение из одного повторяющегося символа — ×2.5.", g, "medium",
         {"handler": "text_content", "mode": "same_char", "effects": {"damage_multiplier": 2.5}}, False),
        ("INTERROGATION", "Допрос", "Вопрос («?» в конце): монстр наносит себе 20% базового урона.", g, "medium",
         {"handler": "text_content", "mode": "question", "effects": {"monster_self_damage_pct_base": 0.20}}, False),
        ("CAPS_SIEGE", "Осада капсом", "ВЕСЬ КАПС: игнорирует броню и аффиксы монстра.", g, "medium",
         {"handler": "text_content", "mode": "caps", "effects": {"ignore_monster_armor": True, "ignore_monster_affixes": True}}, False),
        ("EMOJI_HEALER", "Эмодзи-лекарь", "Эмодзи в тексте: лечение 10% нанесённого урона.", g, "medium",
         {"handler": "text_content", "mode": "emoji", "effects": {"heal_pct_of_damage": 0.10}}, False),
        ("ONE_WORD_EXECUTION", "Лаконичная казнь", "Одно слово: 30% шанс крита, крит-урон ×1.5.", g, "medium",
         {"handler": "text_content", "mode": "one_word", "effects": {"force_crit_chance": 0.30, "crit_damage_multiplier": 1.5}}, False),
        ("DIGIT_GAMBIT", "Цифровой гамбит", "Только цифры: 50% шанс дополнительного удара на 100%.", g, "medium",
         {"handler": "text_content", "mode": "digits_only", "effects": {"extra_hit_chance": 0.50, "extra_hit_pct": 1.0}}, False),
    ]


def _f5_combo_counter() -> list[tuple]:
    """Family 5 — комбо, серии и счётчики (24). trigger_group=combo_counter."""
    g = "combo_counter"
    return [
        ("TEXT_CRESCENDO", "Крещендо", "Каждое последующее текстовое сообщение +10% урона, до 10 стаков; медиа обрывает серию.", g, "medium",
         {"handler": "counter", "mode": "text_streak", "min_stacks": 2, "max_stacks": 10, "effects": {"damage_bonus": 0.10}}, True),
        ("THIRD_STRIKE", "Третий удар", "Каждое 3-е сообщение в бою наносит ×1.5 урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 3, "effects": {"damage_multiplier": 1.5}}, True),
        ("PENTA_BEAT", "Пентабит", "Каждое 5-е сообщение наносит ×2 урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 5, "effects": {"damage_multiplier": 2.0}}, True),
        ("DECIMATOR", "Дециматор", "Каждое 10-е сообщение — гарантированный крит и ×2 урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 10, "effects": {"force_crit": True, "damage_multiplier": 2.0, "notification": "🔟 Дециматор!"}}, True),
        ("DEVILS_DOZEN", "Чёртова дюжина", "Каждое 13-е сообщение наносит ×6.66 урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 13, "effects": {"damage_multiplier": 6.66, "notification": "😈 Чёртова дюжина!"}}, True),
        ("PRIME_INSTINCT", "Инстинкт простых чисел", "Сообщения с простым номером (2, 3, 5, 7, 11…) наносят +40% урона.", g, "medium",
         {"handler": "counter", "mode": "prime", "effects": {"damage_multiplier": 1.4}}, True),
        ("GOLDEN_SPIRAL", "Золотая спираль", "Сообщения с номером Фибоначчи (1, 2, 3, 5, 8, 13…) наносят ×2.5 урона.", g, "medium",
         {"handler": "counter", "mode": "fibonacci", "effects": {"damage_multiplier": 2.5, "notification": "🌀 Золотая спираль!"}}, True),
        ("MILESTONE_25", "Четвертьсотня", "25-е сообщение боя наносит ×8 урона.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 25, "effects": {"damage_multiplier": 8.0, "notification": "💥 25-й удар!"}}, True),
        ("STICKER_CHAIN", "Стикерная цепь", "Подряд идущие стикеры: +15% урона за каждый, до 8 стаков.", g, "medium",
         {"handler": "counter", "mode": "type_streak", "media_type": "sticker", "min_stacks": 2, "max_stacks": 8, "effects": {"damage_bonus": 0.15}}, True),
        ("MEDIA_RAIN", "Медиа-ливень", "Подряд идущие медиа (не текст): +12% за каждое, до 8 стаков.", g, "medium",
         {"handler": "counter", "mode": "type_streak", "media_type": "media", "min_stacks": 2, "max_stacks": 8, "effects": {"damage_bonus": 0.12}}, True),
        ("SHAPESHIFTER", "Перевёртыш", "Серия сообщений без повтора типа: +15% за каждое, до 6 стаков.", g, "medium",
         {"handler": "counter", "mode": "no_repeat_streak", "min_stacks": 1, "max_stacks": 6, "effects": {"damage_bonus": 0.15}}, True),
        ("PING_PONG", "Пинг-понг", "Тип сообщения отличается от предыдущего — +30% урона.", g, "easy",
         {"handler": "counter", "mode": "alternate", "effects": {"damage_multiplier": 1.3}}, True),
        ("COLLECTOR_3", "Коллекционерка", "3 разных типа медиа за бой — +35% урона.", g, "easy",
         {"handler": "counter", "mode": "unique_media", "n": 3, "effects": {"damage_multiplier": 1.35}}, True),
        ("COLLECTOR_5", "Архивариус", "5 разных типов медиа за бой — +75% урона.", g, "easy",
         {"handler": "counter", "mode": "unique_media", "n": 5, "effects": {"damage_multiplier": 1.75}}, True),
        ("FULL_DECK", "Полная колода", "7 разных типов медиа за бой — урон ×3.", g, "medium",
         {"handler": "counter", "mode": "unique_media", "n": 7, "effects": {"damage_multiplier": 3.0, "notification": "🃏 Полная колода!"}}, True),
        ("VOICE_CHAIN", "Голосовая цепь", "Подряд идущие войсы: +25% за каждый, до 5 стаков.", g, "medium",
         {"handler": "counter", "mode": "type_streak", "media_type": "voice", "min_stacks": 2, "max_stacks": 5, "effects": {"damage_bonus": 0.25}}, True),
        ("GIF_CAROUSEL", "Гиф-карусель", "Подряд идущие гифки: +20% за каждую, до 6 стаков.", g, "medium",
         {"handler": "counter", "mode": "type_streak", "media_type": "gif", "min_stacks": 2, "max_stacks": 6, "effects": {"damage_bonus": 0.20}}, True),
        ("SEVENTH_SEAL", "Седьмая печать", "Каждое 7-е сообщение: ×2 урона, игнорирует броню.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 7, "effects": {"damage_multiplier": 2.0, "ignore_monster_armor": True}}, True),
        ("EVEN_BEAT", "Чётный бит", "Каждое 2-е сообщение наносит +20% урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 2, "effects": {"damage_multiplier": 1.2}}, True),
        ("MILESTONE_50", "Полусотня", "50-е сообщение боя: ×10 урона и лечение 20% макс. HP.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 50, "effects": {"damage_multiplier": 10.0, "heal_pct_max_hp": 0.20, "notification": "🏅 Полусотня!"}}, True),
        ("PHOTO_SESSION", "Фотосессия", "Подряд идущие фото: +18% за каждое, до 6 стаков.", g, "medium",
         {"handler": "counter", "mode": "type_streak", "media_type": "photo", "min_stacks": 2, "max_stacks": 6, "effects": {"damage_bonus": 0.18}}, True),
        ("ALTERNATE_CRIT", "Чередование", "Тип сообщения отличается от предыдущего — 20% шанс крита.", g, "easy",
         {"handler": "counter", "mode": "alternate", "effects": {"force_crit_chance": 0.20}}, True),
        ("OPENING_GAMBIT", "Дебютный гамбит", "Первое сообщение боя наносит ×2 урона.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 1, "effects": {"damage_multiplier": 2.0}}, True),
        ("CENTURION", "Центурион", "100-е сообщение боя наносит ×20 урона.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 100, "effects": {"damage_multiplier": 20.0, "notification": "💯 Центурион!"}}, True),
    ]


def _f6_crit() -> list[tuple]:
    """Family 6 — крит-механики (17). trigger_group=crit."""
    g = "crit"
    return [
        ("SHARPENED_EDGE", "Заточенное лезвие", "Критический урон ×1.75.", g, "easy",
         {"handler": "passive", "effects": {"crit_damage_multiplier": 1.75}}, True),
        ("LUCKY_STRIKE", "Счастливый удар", "Постоянный 12% шанс критического удара.", g, "easy",
         {"handler": "passive", "effects": {"force_crit_chance": 0.12}}, True),
        ("ASSASSIN_OPENER", "Удар из тени", "Первый удар по монстру: 30% шанс крита, крит-урон ×2.5.", g, "easy",
         {"handler": "monster_state", "condition": "first_hit", "effects": {"force_crit_chance": 0.30, "crit_damage_multiplier": 2.5}}, True),
        ("FULL_HP_EXECUTION", "Чистое начало", "Монстр на полном HP — гарантированный крит.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "full", "effects": {"force_crit": True}}, True),
        ("GLASS_CANNON", "Стеклянная пушка", "Крит-урон ×3, но обычный урон ×0.85.", g, "easy",
         {"handler": "passive", "effects": {"damage_multiplier": 0.85, "crit_damage_multiplier": 3.0}}, True),
        ("CRIT_VAMPIRE", "Кровавый крит", "20% шанс: крит + лечение 15% нанесённого урона.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.20, "effects": {"force_crit": True, "heal_pct_of_damage": 0.15}}, True),
        ("STICKER_SLAYER", "Стикер-убийца", "Стикеры: крит-урон ×2.2.", g, "easy",
         {"handler": "media", "media_types": ["sticker"], "effects": {"crit_damage_multiplier": 2.2}}, True),
        ("NIGHT_PRECISION", "Ночная точность", "22:00–06:00: +30% шанс критического удара.", g, "easy",
         {"handler": "time_window", "hour_start": 22, "hour_end": 6, "timezone": "Europe/Moscow", "effects": {"force_crit_chance": 0.30}}, True),
        ("BOSS_PIERCER", "Пронзательница боссов", "Против боссов крит-урон ×2.", g, "easy",
         {"handler": "monster_state", "condition": "boss", "effects": {"crit_damage_multiplier": 2.0}}, True),
        ("WOUNDED_PRECISION", "Раненая точность", "HP ОВ ниже 40% — 25% шанс крита.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.40, "effects": {"force_crit_chance": 0.25}}, True),
        ("SPEED_CRIT", "Скоростной крит", "Сообщение быстрее 4 секунд — 35% шанс крита.", g, "easy",
         {"handler": "tempo", "mode": "fast", "window_seconds": 4, "effects": {"force_crit_chance": 0.35}}, True),
        ("CRIT_SPLASH", "Критический всплеск", "15% шанс: крит + волна 30% урона по остальным монстрам.", g, "medium",
         {"handler": "random_proc", "proc_chance": 0.15, "effects": {"force_crit": True, "remaining_monsters_damage_multiplier": 0.30}}, True),
        ("EXECUTIONER_EYE", "Глаз палача", "Монстр ниже 30% HP — 40% шанс крита.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.30, "effects": {"force_crit_chance": 0.40}}, True),
        ("RICOCHET_CRIT", "Рикошет", "10% шанс: крит и дополнительный удар на 50%.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.10, "effects": {"force_crit": True, "extra_hits": [0.50]}}, True),
        ("CALM_CRIT", "Спокойный расчёт", "Пауза 60+ секунд: крит-урон ×2.2.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 60, "effects": {"crit_damage_multiplier": 2.2}}, True),
        ("ELITE_PIERCER", "Гроза элиток", "Против монстров с аффиксами: 30% шанс крита, крит-урон ×1.5.", g, "easy",
         {"handler": "monster_state", "condition": "elite", "effects": {"force_crit_chance": 0.30, "crit_damage_multiplier": 1.5}}, True),
        ("ALL_IN", "Ва-банк", "8% шанс: гарантированный крит с крит-уроном ×4.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.08, "effects": {"force_crit": True, "crit_damage_multiplier": 4.0, "notification": "🎰 Ва-банк!"}}, True),
    ]


def _f7_hp_state() -> list[tuple]:
    """Family 7 — HP-состояния (22). trigger_group=hp_state."""
    g = "hp_state"
    return [
        ("DESPERATION", "Отчаяние", "HP ОВ ниже 25% — урон ×1.8.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.25, "effects": {"damage_multiplier": 1.8}}, True),
        ("ADRENALINE", "Адреналин", "HP ОВ ниже 50% — урон +25%.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.50, "effects": {"damage_multiplier": 1.25}}, True),
        ("DEATHS_DOOR", "У последней черты", "HP ОВ ниже 10% — урон ×3 и 20% вампиризм.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.10, "effects": {"damage_multiplier": 3.0, "heal_pct_of_damage": 0.20}}, True),
        ("FRESH_START", "Свежесть", "ОВ на полном HP — урон ×1.5.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "full", "effects": {"damage_multiplier": 1.5}}, True),
        ("HEALTHY_GLOW", "Здоровый блеск", "HP ОВ выше 80% — +20% урона и дроп ×1.2.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "above", "pct": 0.80, "effects": {"damage_multiplier": 1.2, "drop_chance_multiplier": 1.2}}, True),
        ("BALANCE_POINT", "Точка равновесия", "HP ОВ между 40% и 60% — урон ×1.7.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "between", "min_pct": 0.40, "max_pct": 0.60, "effects": {"damage_multiplier": 1.7}}, True),
        ("PAIN_PRICE", "Цена боли", "+9% урона за каждые потерянные 10% HP ОВ, до +72%.", g, "medium",
         {"handler": "hp_state", "side": "waifu", "op": "per_missing", "max_stacks": 8, "effects": {"damage_bonus": 0.09}}, True),
        ("EXECUTIONER", "Палач", "Монстр ниже 25% HP — урон ×2.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.25, "effects": {"damage_multiplier": 2.0}}, True),
        ("FINISHER_50", "Добивательница", "Монстр ниже 50% HP — урон +35%.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.50, "effects": {"damage_multiplier": 1.35}}, True),
        ("LAST_INCH", "Последний дюйм", "Монстр ниже 5% HP — урон ×5.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.05, "effects": {"damage_multiplier": 5.0}}, True),
        ("FRESH_TARGET", "Свежая цель", "Монстр выше 90% HP — урон ×1.6.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "above", "pct": 0.90, "effects": {"damage_multiplier": 1.6}}, True),
        ("GIANT_SLAYER", "Гроза великанов", "HP монстра минимум вдвое больше HP ОВ — урон ×2.", g, "medium",
         {"handler": "hp_state", "op": "david", "ratio": 2.0, "effects": {"damage_multiplier": 2.0, "notification": "🏹 Давид против Голиафа!"}}, True),
        ("TITAN_FELLER", "Низвергательница титанов", "Монстр с 1000+ HP — урон +50%.", g, "easy",
         {"handler": "monster_state", "condition": "big_hp", "value": 1000, "effects": {"damage_multiplier": 1.5}}, True),
        ("BLOOD_PACT", "Кровавый пакт", "HP ОВ ниже 50% — +15% урона и 10% вампиризм.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.50, "effects": {"damage_multiplier": 1.15, "heal_pct_of_damage": 0.10}}, True),
        ("UNDERDOG", "Аутсайдер", "HP ОВ ниже 30% — удары игнорируют броню и аффиксы.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.30, "effects": {"ignore_monster_armor": True, "ignore_monster_affixes": True}}, True),
        ("IRON_WILL", "Железная воля", "HP ОВ ниже 20% — монстр не контратакует.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.20, "effects": {"ignore_monster_death_damage": True}}, True),
        ("OVERFLOW", "Переизбыток сил", "ОВ на полном HP: 30% шанс дополнительного удара на 60%.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "full", "effects": {"extra_hit_chance": 0.30, "extra_hit_pct": 0.60}}, True),
        ("PHOENIX_SPARK", "Искра феникса", "HP ОВ ниже 15% — каждый удар лечит 3% макс. HP.", g, "easy",
         {"handler": "hp_state", "side": "waifu", "op": "below", "pct": 0.15, "effects": {"heal_pct_max_hp": 0.03}}, True),
        ("SURGICAL", "Хирургическая точность", "Монстр на 45–55% HP — гарантированный крит.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "between", "min_pct": 0.45, "max_pct": 0.55, "effects": {"force_crit": True}}, True),
        ("MOMENTUM", "Импульс", "Монстр ниже 75% HP — урон +20%.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.75, "effects": {"damage_multiplier": 1.2}}, True),
        ("SCALES_OF_FATE", "Весы судьбы", "+6% урона за каждые 10% HP, потерянные монстром, до +60%.", g, "medium",
         {"handler": "hp_state", "side": "monster", "op": "per_missing", "max_stacks": 10, "effects": {"damage_bonus": 0.06}}, True),
        ("VITALITY_TAX", "Налог на живучесть", "Монстр выше 50% HP — +25% урона, игнорирует уклонение.", g, "easy",
         {"handler": "hp_state", "side": "monster", "op": "above", "pct": 0.50, "effects": {"damage_multiplier": 1.25, "ignore_monster_dodge": True}}, True),
    ]


def _f8_reactive() -> list[tuple]:
    """Family 8 — реактивные / защитные (18). trigger_group=reactive."""
    g = "reactive"
    return [
        ("RIPOSTE", "Рипост", "После уклонения от атаки монстра следующий удар +60%.", g, "medium",
         {"handler": "state_flag", "flag": "counter_dodge_ready", "consume": True, "listen_dodge": True, "effects": {"damage_multiplier": 1.6, "notification": "🤺 Рипост!"}}, True),
        ("MATADOR", "Матадор", "После уклонения следующее сообщение бьёт дважды (доп. удар 70%).", g, "medium",
         {"handler": "state_flag", "flag": "counter_dodge_ready", "consume": True, "listen_dodge": True, "effects": {"extra_hits": [0.70]}}, True),
        ("VENDETTA", "Вендетта", "Получив урон в бою, ОВ наносит +20% урона до конца боя.", g, "medium",
         {"handler": "state_flag", "flag": "received_damage_this_fight", "effects": {"damage_multiplier": 1.2}}, True),
        ("PAIN_CONVERTER", "Конвертер боли", "+5% урона за каждые 50 полученного в бою урона, до +50%.", g, "medium",
         {"handler": "session_scale", "mode": "received_damage", "per_damage": 50, "max_stacks": 10, "effects": {"damage_bonus": 0.05}}, True),
        ("THORNS_AURA", "Терновая аура", "Каждый удар ОВ дополнительно ранит монстра на 10% базового урона.", g, "easy",
         {"handler": "passive", "effects": {"monster_self_damage_pct_base": 0.10}}, True),
        ("AVENGER", "Мстительница", "Первый удар после ранения — +45% урона.", g, "medium",
         {"handler": "state_flag", "flag": "revenge_ready", "consume": True, "effects": {"damage_multiplier": 1.45}}, True),
        ("GRUDGE_KEEPER", "Злопамятность", "Первый удар после ранения бьёт дважды (доп. удар 80%).", g, "medium",
         {"handler": "state_flag", "flag": "revenge_ready", "consume": True, "effects": {"extra_hits": [0.80]}}, True),
        ("DEBUFF_EATER", "Пожирательница проклятий", "После дебаффа от монстра: следующий удар ×1.6 и снятие дебаффов.", g, "medium",
         {"handler": "state_flag", "flag": "curse_counter_ready", "consume": True, "listen_debuff": True, "effects": {"damage_multiplier": 1.6, "clear_waifu_debuffs": True}}, True),
        ("UNBREAKABLE", "Несгибаемость", "После нокаута в этой сессии ОВ наносит +40% урона.", g, "medium",
         {"handler": "state_flag", "flag": "knocked_out_this_session", "effects": {"damage_multiplier": 1.4}}, True),
        ("COMEBACK_KID", "Возвращение", "После нокаута в сессии: дроп ×1.5 и золото ×1.3.", g, "medium",
         {"handler": "state_flag", "flag": "knocked_out_this_session", "effects": {"drop_chance_multiplier": 1.5, "gold_multiplier": 1.3}}, True),
        ("FIRST_BLOOD_REPLY", "Ответ на первую кровь", "Получив урон в бою — 15% шанс крита на каждом ударе.", g, "medium",
         {"handler": "state_flag", "flag": "received_damage_this_fight", "effects": {"force_crit_chance": 0.15}}, True),
        ("SHELL_SHOCK", "Контузия", "10% шанс: монстр наносит себе 50% базового урона ОВ.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.10, "effects": {"monster_self_damage_pct_base": 0.50, "notification": "💫 Контузия!"}}, True),
        ("GUARDIAN_ANGEL", "Ангел-хранитель", "Каждый удар лечит ОВ на 2% макс. HP.", g, "easy",
         {"handler": "passive", "effects": {"heal_pct_max_hp": 0.02}}, True),
        ("KILL_FEAST", "Пир после битвы", "Убийство монстра: 50% шанс восстановить 15% макс. HP.", g, "medium",
         {"handler": "on_kill", "proc_chance": 0.50, "effects": {"heal_pct_max_hp": 0.15, "notification": "🍖 Пир после битвы!"}}, True),
        ("SOUL_HARVEST", "Жатва душ", "Каждое убийство восстанавливает 5% макс. HP.", g, "medium",
         {"handler": "on_kill", "proc_chance": 1.0, "effects": {"heal_pct_max_hp": 0.05}}, True),
        ("BLOOD_DEBT", "Кровавый долг", "Убийство: 40% шанс восстановить 25% макс. HP.", g, "medium",
         {"handler": "on_kill", "proc_chance": 0.40, "effects": {"heal_pct_max_hp": 0.25, "notification": "🩸 Кровавый долг оплачен!"}}, True),
        ("SECOND_WIND", "Второе дыхание", "Удар после паузы 3+ минуты лечит ОВ на 10% макс. HP.", g, "easy",
         {"handler": "tempo", "mode": "pause", "min_seconds": 180, "effects": {"heal_pct_max_hp": 0.10}}, True),
        ("RETRIBUTION", "Возмездие", "После уклонения: гарантированный крит с крит-уроном ×2.", g, "medium",
         {"handler": "state_flag", "flag": "counter_dodge_ready", "consume": True, "listen_dodge": True, "effects": {"force_crit": True, "crit_damage_multiplier": 2.0, "notification": "⚖️ Возмездие!"}}, True),
    ]


def _f9_dungeon_progress() -> list[tuple]:
    """Family 9 — прогресс боя / данжа (23). trigger_group=dungeon_progress."""
    g = "dungeon_progress"
    return [
        ("KILL_MOMENTUM", "Раскатка", "+6% урона за каждого убитого в сессии монстра, до +60%.", g, "medium",
         {"handler": "session_scale", "mode": "per_kill", "max_stacks": 10, "effects": {"damage_bonus": 0.06}}, True),
        ("MF_SNOWBALL", "Снежный ком удачи", "+4% к шансу дропа за каждого убитого, до 15 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "per_kill", "max_stacks": 15, "effects": {"drop_bonus": 0.04}}, True),
        ("GOLD_RUSH_KILLS", "Золотая лихорадка", "+5% золота за каждого убитого в сессии, до 10 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "per_kill", "max_stacks": 10, "effects": {"gold_bonus": 0.05}}, True),
        ("BOSS_BANE", "Бич боссов", "Против боссов: +60% урона, игнорирует аффиксы.", g, "easy",
         {"handler": "monster_state", "condition": "boss", "effects": {"damage_multiplier": 1.6, "ignore_monster_affixes": True}}, True),
        ("BOSS_TREASURER", "Казначейша босса", "Боссы: золото ×2 и дроп ×1.5.", g, "easy",
         {"handler": "monster_state", "condition": "boss", "effects": {"gold_multiplier": 2.0, "drop_chance_multiplier": 1.5}}, True),
        ("TRASH_SWEEPER", "Чистильщица", "Против обычных монстров (не боссов) урон ×1.4.", g, "easy",
         {"handler": "monster_state", "condition": "not_boss", "effects": {"damage_multiplier": 1.4}}, True),
        ("ELITE_BREAKER", "Крушительница элит", "Против монстров с аффиксами урон ×1.6.", g, "easy",
         {"handler": "monster_state", "condition": "elite", "effects": {"damage_multiplier": 1.6}}, True),
        ("AFFIX_FEAST", "Пир на аффиксах", "+12% урона за каждый аффикс монстра, до 5 стаков.", g, "easy",
         {"handler": "monster_state", "condition": "affix_scaled", "max_stacks": 5, "effects": {"damage_bonus": 0.12}}, True),
        ("CLEAN_KILL", "Чистая работа", "Против монстров без аффиксов: ×1.5 урона и 10% шанс крита.", g, "easy",
         {"handler": "monster_state", "condition": "clean", "effects": {"damage_multiplier": 1.5, "force_crit_chance": 0.10}}, True),
        ("OPENING_STRIKE", "Разведка боем", "Первый удар по каждому монстру наносит ×1.7 урона.", g, "easy",
         {"handler": "monster_state", "condition": "first_hit", "effects": {"damage_multiplier": 1.7}}, True),
        ("SPLASH_MASTER", "Веер", "Каждый удар задевает остальных монстров на 10% урона.", g, "medium",
         {"handler": "passive", "effects": {"remaining_monsters_damage_multiplier": 0.10}}, True),
        ("CHAIN_REACTION", "Цепная реакция", "Первый удар по новому монстру: +30% от урона прошлого боя.", g, "medium",
         {"handler": "session_scale", "mode": "echo", "echo_pct": 0.30, "require_first_hit": True, "effects": {"notification": "⛓️ Цепная реакция!"}}, True),
        ("WAR_MARCH", "Военный марш", "+5% урона за каждые 150 урона, нанесённого в этом бою, до 8 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "fight_damage", "per_damage": 150, "max_stacks": 8, "effects": {"damage_bonus": 0.05}}, True),
        ("CLEAN_CUT", "Чистый разрез", "Убитые монстры не призывают подмогу при смерти.", g, "medium",
         {"handler": "passive", "effects": {"prevent_monster_death_spawn": True}}, True),
        ("NO_MERCY", "Без пощады", "Монстр ниже 40% HP: удары задевают остальных на 25%.", g, "medium",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.40, "effects": {"remaining_monsters_damage_multiplier": 0.25}}, True),
        ("TROPHY_HUNTER", "Охота за трофеем", "Против боссов: 50% шанс критического удара.", g, "easy",
         {"handler": "monster_state", "condition": "boss", "effects": {"force_crit_chance": 0.50}}, True),
        ("VANGUARD", "Авангард", "Первый удар по монстру: ×1.5 и игнорирует уклонение.", g, "easy",
         {"handler": "monster_state", "condition": "first_hit", "effects": {"damage_multiplier": 1.5, "ignore_monster_dodge": True}}, True),
        ("MARATHON_RUNNER", "Марафонец", "+3% урона за каждые 300 урона за сессию, до 15 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "session_damage", "per_damage": 300, "max_stacks": 15, "effects": {"damage_bonus": 0.03}}, True),
        ("EARLY_BIRD_GOLD", "Ранний вклад", "В первом подземелье дня золото ×2.", g, "medium",
         {"handler": "state_flag", "flag": "first_daily_dungeon", "effects": {"gold_multiplier": 2.0}}, True),
        ("SURVIVOR_RAGE", "Ярость выжившей", "После провала прошлого подземелья — 25% шанс крита.", g, "medium",
         {"handler": "state_flag", "flag": "waifu_last_dungeon_knocked_out", "effects": {"force_crit_chance": 0.25}}, True),
        ("EVEN_PREY", "Чётная добыча", "Против монстров с чётным номером урон +30%.", g, "easy",
         {"handler": "monster_state", "condition": "id_mod", "mod": 2, "remainder": 0, "effects": {"damage_multiplier": 1.3}}, True),
        ("SEVENTH_VICTIM", "Седьмая жертва", "Каждый монстр с номером, кратным 7, получает ×2.5 урона.", g, "easy",
         {"handler": "monster_state", "condition": "id_mod", "mod": 7, "remainder": 0, "effects": {"damage_multiplier": 2.5}}, True),
        ("ABYSS_GAZE", "Взгляд бездны", "Монстры с 800+ HP: +20% урона, игнорирует броню.", g, "easy",
         {"handler": "monster_state", "condition": "big_hp", "value": 800, "effects": {"damage_multiplier": 1.2, "ignore_monster_armor": True}}, True),
    ]


def _f10_economy() -> list[tuple]:
    """Family 10 — экономика / лут (18). trigger_group=economy."""
    g = "economy"
    return [
        ("MIDAS_TOUCH", "Прикосновение Мидаса", "Золото с убийств ×1.5.", g, "easy",
         {"handler": "passive", "effects": {"gold_multiplier": 1.5}}, True),
        ("TREASURE_NOSE", "Чутьё на клад", "Шанс редкого дропа ×1.25.", g, "easy",
         {"handler": "passive", "effects": {"drop_chance_multiplier": 1.25}}, True),
        ("BEGGARS_FURY", "Ярость нищенки", "Золота меньше 100 — урон ×1.7.", g, "easy",
         {"handler": "economy", "condition": "gold_below", "value": 100, "effects": {"damage_multiplier": 1.7}}, True),
        ("TYCOON", "Магнатка", "Золота больше 10000 — дроп ×1.5 и +15% урона.", g, "easy",
         {"handler": "economy", "condition": "gold_above", "value": 10000, "effects": {"drop_chance_multiplier": 1.5, "damage_multiplier": 1.15}}, True),
        ("INVESTOR", "Инвесторша", "Золота больше 5000 — урон +20%.", g, "easy",
         {"handler": "economy", "condition": "gold_above", "value": 5000, "effects": {"damage_multiplier": 1.2}}, True),
        ("POOR_LUCK", "Удача бедноты", "Золота меньше 500 — дроп ×1.4.", g, "easy",
         {"handler": "economy", "condition": "gold_below", "value": 500, "effects": {"drop_chance_multiplier": 1.4}}, True),
        ("GOLD_GUARD", "Золотая стража", "Золота больше 2000 — +15% урона, монстр ранит себя на 10% базы.", g, "easy",
         {"handler": "economy", "condition": "gold_above", "value": 2000, "effects": {"damage_multiplier": 1.15, "monster_self_damage_pct_base": 0.10}}, True),
        ("PAWNBROKER", "Ломбардщица", "+2% урона за каждый проданный за сессию предмет, до +40%.", g, "medium",
         {"handler": "session_scale", "mode": "items_sold", "max_stacks": 20, "effects": {"damage_bonus": 0.02}}, True),
        ("AUCTIONEER", "Аукционистка", "+6% к дропу за каждую продажу в сессии, до 5 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "items_sold", "max_stacks": 5, "effects": {"drop_bonus": 0.06}}, True),
        ("GOLDEN_BULLET", "Золотая пуля", "5% шанс: урон ×3 и золото ×3.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.05, "effects": {"damage_multiplier": 3.0, "gold_multiplier": 3.0, "notification": "🥇 Золотая пуля!"}}, True),
        ("COIN_FLIP_TRADE", "Орёл и решка", "50/50: либо золото ×2, либо урон ×1.5.", g, "easy",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.5, "effects": {"gold_multiplier": 2.0}},
             {"chance": 0.5, "effects": {"damage_multiplier": 1.5}},
         ]}, True),
        ("LUCKY_CHARM", "Талисман удачи", "Удача ОВ 30+ — дроп ×1.3.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "luck", "mode": "above", "value": 30, "effects": {"drop_chance_multiplier": 1.3}}, True),
        ("DRAGON_HOARD", "Драконья казна", "Золота больше 20000: урон ×1.5, дроп ×1.5, золото ×1.5.", g, "easy",
         {"handler": "economy", "condition": "gold_above", "value": 20000, "effects": {"damage_multiplier": 1.5, "drop_chance_multiplier": 1.5, "gold_multiplier": 1.5}}, True),
        ("SCROOGE", "Скряга", "Золота больше 1000 — золото с убийств ×1.4.", g, "easy",
         {"handler": "economy", "condition": "gold_above", "value": 1000, "effects": {"gold_multiplier": 1.4}}, True),
        ("RAGS_TO_RICHES", "Из грязи в князи", "Золота меньше 50 — урон ×2.5.", g, "easy",
         {"handler": "economy", "condition": "gold_below", "value": 50, "effects": {"damage_multiplier": 2.5}}, True),
        ("TITHE", "Десятина", "Каждое 10-е сообщение приносит двойное золото с убийства.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 10, "effects": {"gold_multiplier": 2.0}}, True),
        ("LOOT_MAGNET", "Магнит лута", "Против боссов шанс дропа ×2.", g, "easy",
         {"handler": "monster_state", "condition": "boss", "effects": {"drop_chance_multiplier": 2.0}}, True),
        ("PROFITEER", "Барышница", "+1% к дропу за каждую продажу в сессии, до 20 стаков.", g, "medium",
         {"handler": "session_scale", "mode": "items_sold", "max_stacks": 20, "effects": {"drop_bonus": 0.01}}, True),
    ]


def _f11_meta_inventory() -> list[tuple]:
    """Family 11 — мета / инвентарь (18). trigger_group=meta_inventory."""
    g = "meta_inventory"
    return [
        ("LONE_LEGEND", "Одинокая легенда", "Единственная экипированная легендарка — урон ×1.4.", g, "easy",
         {"handler": "meta_scale", "source": "legendary_count", "mode": "equals", "value": 1, "effects": {"damage_multiplier": 1.4}}, True),
        ("LEGION_OF_LEGENDS", "Легион легенд", "+8% урона за каждую экипированную легендарку, до 6.", g, "easy",
         {"handler": "meta_scale", "source": "legendary_count", "mode": "per_item", "max_stacks": 6, "effects": {"damage_bonus": 0.08}}, True),
        ("TWIN_SOULS", "Парные души", "2+ легендарки — урон +25%.", g, "easy",
         {"handler": "meta_scale", "source": "legendary_count", "mode": "at_least", "value": 2, "effects": {"damage_multiplier": 1.25}}, True),
        ("FULL_REGALIA", "Полные регалии", "4+ легендарки — урон ×1.6 и дроп ×1.3.", g, "easy",
         {"handler": "meta_scale", "source": "legendary_count", "mode": "at_least", "value": 4, "effects": {"damage_multiplier": 1.6, "drop_chance_multiplier": 1.3}}, True),
        ("TRINITY", "Триединство", "Ровно 3 легендарки — урон ×1.45.", g, "easy",
         {"handler": "meta_scale", "source": "legendary_count", "mode": "equals", "value": 3, "effects": {"damage_multiplier": 1.45}}, True),
        ("APPRENTICE_SURGE", "Рывок ученицы", "Уровень ОВ 15 и ниже — урон ×1.8.", g, "easy",
         {"handler": "meta_scale", "source": "waifu_level", "mode": "below", "value": 15, "effects": {"damage_multiplier": 1.8}}, True),
        ("VETERAN_EDGE", "Грань ветерана", "Уровень ОВ 40+ — урон +30%.", g, "easy",
         {"handler": "meta_scale", "source": "waifu_level", "mode": "above", "value": 40, "effects": {"damage_multiplier": 1.3}}, True),
        ("GROWTH_SPURT", "Скачок роста", "+5% урона за каждые 5 уровней ОВ, до 10 стаков.", g, "easy",
         {"handler": "meta_scale", "source": "waifu_level", "mode": "per_n_levels", "per_n": 5, "max_stacks": 10, "effects": {"damage_bonus": 0.05}}, True),
        ("MUSCLE_MEMORY", "Мышечная память", "Сила ОВ 40+ — урон +25%.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "strength", "mode": "above", "value": 40, "effects": {"damage_multiplier": 1.25}}, True),
        ("ACROBAT", "Акробатка", "Ловкость ОВ 40+ — 20% шанс крита.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "agility", "mode": "above", "value": 40, "effects": {"force_crit_chance": 0.20}}, True),
        ("SCHOLAR", "Учёная", "Интеллект ОВ 40+ — +25% урона, игнорирует аффиксы.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "intelligence", "mode": "above", "value": 40, "effects": {"damage_multiplier": 1.25, "ignore_monster_affixes": True}}, True),
        ("FORTUNE_FAVORED", "Любимица фортуны", "Удача ОВ 40+ — дроп ×1.4 и 10% шанс крита.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "luck", "mode": "above", "value": 40, "effects": {"drop_chance_multiplier": 1.4, "force_crit_chance": 0.10}}, True),
        ("BRAWN_SCALING", "Сила в числах", "+4% урона за каждые 10 силы ОВ, до 10 стаков.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "strength", "mode": "per_points", "per_n": 10, "max_stacks": 10, "effects": {"damage_bonus": 0.04}}, True),
        ("WIT_SCALING", "Острый ум", "+4% урона за каждые 10 интеллекта ОВ, до 10 стаков.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "intelligence", "mode": "per_points", "per_n": 10, "max_stacks": 10, "effects": {"damage_bonus": 0.04}}, True),
        ("NIMBLE_SCALING", "Проворство", "+4% урона за каждые 10 ловкости ОВ, до 10 стаков.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "agility", "mode": "per_points", "per_n": 10, "max_stacks": 10, "effects": {"damage_bonus": 0.04}}, True),
        ("JACKPOT_SENSE", "Чутьё джекпота", "Удача ОВ 60+ — 25% шанс крита, крит-урон ×1.5.", g, "easy",
         {"handler": "meta_scale", "source": "stat", "stat": "luck", "mode": "above", "value": 60, "effects": {"force_crit_chance": 0.25, "crit_damage_multiplier": 1.5}}, True),
        ("LEVEL_RESONANCE", "Резонанс уровней", "Уровень ОВ 30+ — крит-урон ×1.6.", g, "easy",
         {"handler": "meta_scale", "source": "waifu_level", "mode": "above", "value": 30, "effects": {"crit_damage_multiplier": 1.6}}, True),
        ("ROOKIE_NERVE", "Дерзость новичка", "Уровень ОВ 10 и ниже — урон ×2.2 и дроп ×1.5.", g, "easy",
         {"handler": "meta_scale", "source": "waifu_level", "mode": "below", "value": 10, "effects": {"damage_multiplier": 2.2, "drop_chance_multiplier": 1.5}}, True),
    ]


def _f12_exotic() -> list[tuple]:
    """Family 12 — экзотика / случайность (34). trigger_group=exotic."""
    g = "exotic"
    return [
        ("CASINO_ROYALE", "Казино «Рояль»", "Каждый удар: 10% ×0, 60% ×1, 25% ×2, 5% ×5.", g, "medium",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.10, "effects": {"damage_multiplier": 0.0, "notification": "🎲 Зеро!"}},
             {"chance": 0.60, "effects": {"damage_multiplier": 1.0}},
             {"chance": 0.25, "effects": {"damage_multiplier": 2.0}},
             {"chance": 0.05, "effects": {"damage_multiplier": 5.0, "notification": "🎰 Куш ×5!"}},
         ]}, True),
        ("COIN_OF_FATE", "Монета судьбы", "Каждый удар: 50% ×0.5 или 50% ×2.", g, "easy",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.5, "effects": {"damage_multiplier": 0.5}},
             {"chance": 0.5, "effects": {"damage_multiplier": 2.0}},
         ]}, True),
        ("CHAOS_DICE", "Кость хаоса", "Урон каждого удара умножается на случайное число от 0.5 до 3.", g, "easy",
         {"handler": "random_proc", "uniform": {"min_mult": 0.5, "max_mult": 3.0}, "effects": {}}, True),
        ("RUSSIAN_ROULETTE", "Рулетка", "1 из 6: урон ×6. Иначе ×0.9.", g, "easy",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.1667, "effects": {"damage_multiplier": 6.0, "notification": "🔫 Барабан сыграл!"}},
             {"chance": 0.8333, "effects": {"damage_multiplier": 0.9}},
         ]}, True),
        ("JACKPOT", "Джекпот", "1% шанс нанести ×25 урона.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.01, "effects": {"damage_multiplier": 25.0, "notification": "💎 ДЖЕКПОТ!"}}, True),
        ("GREMLIN", "Гремлин", "25% шанс: монстр наносит себе 40% базового урона ОВ.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.25, "effects": {"monster_self_damage_pct_base": 0.40}}, True),
        ("MIRROR_IMAGE", "Отражение", "15% шанс дополнительного удара на 100% урона.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.15, "effects": {"extra_hits": [1.0]}}, True),
        ("SHADOW_CLONE", "Теневой клон", "8% шанс: два дополнительных удара по 70%.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.08, "effects": {"extra_hits": [0.7, 0.7], "notification": "👤 Теневой клон!"}}, True),
        ("GLITCH_STRIKE", "Глитч", "Урон умножается на случайное число 0.8–1.9, 10% шанс крита.", g, "easy",
         {"handler": "random_proc", "uniform": {"min_mult": 0.8, "max_mult": 1.9}, "effects": {"force_crit_chance": 0.10}}, True),
        ("ANCHOR_STRIKE", "Якорный удар", "Вместо удара — три волны по 45% урона.", g, "medium",
         {"handler": "passive", "effects": {"replace_with_hits": [0.45, 0.45, 0.45]}}, True),
        ("ECHO_CHAMBER", "Эхо-камера", "20% шанс повторить удар на 50% урона.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.20, "effects": {"extra_hits": [0.5]}}, True),
        ("DOUBLE_ELEVEN", "Одиннадцать-одиннадцать", "Каждое 11-е сообщение наносит ×3 урона.", g, "easy",
         {"handler": "counter", "mode": "every_n", "n": 11, "effects": {"damage_multiplier": 3.0}}, True),
        ("PACIFIST_PARADOX", "Парадокс пацифистки", "Урон ×0.5, но каждый удар лечит 25% нанесённого урона.", g, "easy",
         {"handler": "passive", "effects": {"damage_multiplier": 0.5, "heal_pct_of_damage": 0.25}}, True),
        ("DEVILS_BARGAIN", "Сделка с дьяволом", "30% шанс ×2.5 урона, иначе ×0.85.", g, "easy",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.30, "effects": {"damage_multiplier": 2.5}},
             {"chance": 0.70, "effects": {"damage_multiplier": 0.85}},
         ]}, True),
        ("OVERKILL_SPLASH", "Сверхубийство", "Монстр ниже 15% HP: волна 50% урона по остальным.", g, "medium",
         {"handler": "hp_state", "side": "monster", "op": "below", "pct": 0.15, "effects": {"remaining_monsters_damage_multiplier": 0.50}}, True),
        ("PHANTOM_FINALE", "Фантомный финал", "Каждое 8-е сообщение: четыре фантомных удара по 30%.", g, "medium",
         {"handler": "counter", "mode": "every_n", "n": 8, "effects": {"replace_with_hits": [0.3, 0.3, 0.3, 0.3]}}, True),
        ("STATIC_CHARGE", "Статический заряд", "Серия быстрых (<6 с) сообщений: +12% за стак, до 8.", g, "medium",
         {"handler": "tempo", "mode": "fast_streak", "window_seconds": 6, "max_stacks": 8, "effects": {"damage_bonus": 0.12}}, True),
        ("MONSTER_WHISPERER", "Заклинательница", "Монстры с номером, кратным 3, ранят себя на 25% базы.", g, "easy",
         {"handler": "monster_state", "condition": "id_mod", "mod": 3, "remainder": 0, "effects": {"monster_self_damage_pct_base": 0.25}}, True),
        ("BLACK_CAT", "Чёрная кошка", "13-е сообщение боя: ×4 урона и снятие дебаффов.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 13, "effects": {"damage_multiplier": 4.0, "clear_waifu_debuffs": True, "notification": "🐈‍⬛ Чёрная кошка!"}}, True),
        ("QUANTUM_STRIKE", "Квантовый удар", "33% шанс: ×1.33 урона, игнорирует броню, аффиксы и уклонение.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.33, "effects": {"damage_multiplier": 1.33, "ignore_monster_armor": True, "ignore_monster_affixes": True, "ignore_monster_dodge": True}}, True),
        ("VOID_TOUCH", "Касание пустоты", "5% шанс: монстр наносит себе 100% базового урона ОВ.", g, "easy",
         {"handler": "random_proc", "proc_chance": 0.05, "effects": {"monster_self_damage_pct_base": 1.0, "notification": "🕳️ Касание пустоты!"}}, True),
        ("HIGH_ROLLER", "Хайроллер", "Каждый удар: 50% ×3 или 50% ×0.5.", g, "easy",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.5, "effects": {"damage_multiplier": 3.0}},
             {"chance": 0.5, "effects": {"damage_multiplier": 0.5}},
         ]}, True),
        ("SLOT_MACHINE", "Однорукий бандит", "30% ×1.5, 10% ×2.5, 3% ×7, иначе ×1.", g, "medium",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.30, "effects": {"damage_multiplier": 1.5}},
             {"chance": 0.10, "effects": {"damage_multiplier": 2.5}},
             {"chance": 0.03, "effects": {"damage_multiplier": 7.0, "notification": "🎰 Три семёрки!"}},
         ]}, True),
        ("CURSED_BLESSING", "Проклятое благословение", "Урон ×2.2, но золото с убийств ×0.5.", g, "easy",
         {"handler": "passive", "effects": {"damage_multiplier": 2.2, "gold_multiplier": 0.5}}, True),
        ("GREEDY_GAMBIT", "Жадный гамбит", "Золото ×2.5, но урон ×0.7.", g, "easy",
         {"handler": "passive", "effects": {"damage_multiplier": 0.7, "gold_multiplier": 2.5}}, True),
        ("BERSERKER_TRANCE", "Транс берсерка", "Серия быстрых (<5 с) сообщений: +20% за стак, до 5.", g, "medium",
         {"handler": "tempo", "mode": "fast_streak", "window_seconds": 5, "max_stacks": 5, "effects": {"damage_bonus": 0.20}}, True),
        ("MIMIC", "Мимик", "Тип сообщения совпадает с предыдущим — +35% урона.", g, "easy",
         {"handler": "counter", "mode": "repeat_type", "effects": {"damage_multiplier": 1.35}}, True),
        ("DEJA_VU", "Дежавю", "Тип сообщения совпадает с предыдущим — 25% шанс крита.", g, "easy",
         {"handler": "counter", "mode": "repeat_type", "effects": {"force_crit_chance": 0.25}}, True),
        ("PERFECT_MINUTE", "Минута в минуту", "Интервал ровно 59–61 секунда — урон ×4.", g, "easy",
         {"handler": "tempo", "mode": "band", "min_seconds": 59, "max_seconds": 61, "effects": {"damage_multiplier": 4.0, "notification": "⏱️ Минута в минуту!"}}, True),
        ("ENTROPY", "Энтропия", "Урон умножается на случайное число от 0.3 до 4.", g, "easy",
         {"handler": "random_proc", "uniform": {"min_mult": 0.3, "max_mult": 4.0}, "effects": {}}, True),
        ("LIFE_FEAST", "Пир жизни", "Убийство монстра: 30% шанс восстановить 35% макс. HP.", g, "medium",
         {"handler": "on_kill", "proc_chance": 0.30, "effects": {"heal_pct_max_hp": 0.35, "notification": "🌿 Пир жизни!"}}, True),
        ("NUMBER_OF_BEAST", "Число зверя", "66-е сообщение боя наносит ×6.6 урона.", g, "easy",
         {"handler": "counter", "mode": "milestone", "n": 66, "effects": {"damage_multiplier": 6.6, "notification": "👹 Число зверя!"}}, True),
        ("PRISM", "Призма", "4 разных типа медиа за бой: каждый удар задевает остальных на 15%.", g, "medium",
         {"handler": "counter", "mode": "unique_media", "n": 4, "effects": {"remaining_monsters_damage_multiplier": 0.15}}, True),
        ("WILD_MAGIC", "Дикая магия", "20% крит, 20% доп. удар 60%, 20% +50% урона, 40% ничего.", g, "medium",
         {"handler": "random_proc", "outcomes": [
             {"chance": 0.20, "effects": {"force_crit": True}},
             {"chance": 0.20, "effects": {"extra_hits": [0.6]}},
             {"chance": 0.20, "effects": {"damage_multiplier": 1.5}},
         ]}, True),
    ]


def _bonus_rows() -> list[tuple]:
    """(bonus_key, name, description_tpl, trigger_group, complexity, params, is_active)."""
    rows: list[tuple] = []
    rows += _f1_media_type()
    rows += _f2_time_calendar()
    rows += _f3_tempo()
    rows += _f4_text_content()
    rows += _f5_combo_counter()
    rows += _f6_crit()
    rows += _f7_hp_state()
    rows += _f8_reactive()
    rows += _f9_dungeon_progress()
    rows += _f10_economy()
    rows += _f11_meta_inventory()
    rows += _f12_exotic()
    return rows


def upgrade() -> None:
    bonuses = sa.table(
        "legendary_bonuses",
        sa.column("bonus_key", sa.String),
        sa.column("name", sa.String),
        sa.column("description_tpl", sa.Text),
        sa.column("trigger_group", sa.String),
        sa.column("impl_complexity", sa.String),
        sa.column("params", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
    )
    rows = _bonus_rows()
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys)), "duplicate bonus_key in pool"
    op.bulk_insert(
        bonuses,
        [
            {
                "bonus_key": k,
                "name": n,
                "description_tpl": d,
                "trigger_group": grp,
                "impl_complexity": c,
                "params": p,
                "is_active": active,
            }
            for k, n, d, grp, c, p, active in rows
        ],
    )


def downgrade() -> None:
    keys = [r[0] for r in _bonus_rows()]
    op.execute(
        sa.text("DELETE FROM legendary_bonuses WHERE bonus_key = ANY(:keys)").bindparams(
            sa.bindparam("keys", keys, type_=postgresql.ARRAY(sa.String))
        )
    )

