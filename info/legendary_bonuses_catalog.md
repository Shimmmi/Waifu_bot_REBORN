# Каталог легендарных бонусов (пул 316)

Бонусы привязаны к шаблонам через `legendary_bonus_ids` (миграция `0107`, матрица `legendary_bonus_distribution.md`).

**Источники:** `0091_legendary_bonuses_core.py` (46 legacy), `0105_legendary_bonus_pool.py` (+270 generic).
**Handlers:** legacy → `BONUS_HANDLERS[bonus_key]`; pool → `GENERIC_HANDLERS[params.handler]` в `generic.py`.

**Всего:** 316 бонусов · **активных:** 316 · **неактивных:** 0

## Сводка по семействам

| trigger_group | шт. | handler |
|---------------|-----|---------|
| media_type | 36 | generic primitives |
| time_calendar | 21 | generic primitives |
| tempo | 17 | generic primitives |
| text_content | 22 | generic primitives |
| combo_counter | 24 | generic primitives |
| crit | 17 | generic primitives |
| hp_state | 22 | generic primitives |
| reactive | 25 | generic primitives |
| dungeon_progress | 23 | generic primitives |
| economy | 18 | generic primitives |
| meta_inventory | 18 | generic primitives |
| exotic | 34 | generic primitives |

---

## 1. Тип сообщения (`media_type`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| AUDIO_BASSLINE | Басовая волна | easy | yes | media | Аудио наносит ×3 урона. |
| AUDIO_ENCORE | Бис! | easy | yes | media | Аудио: 25% шанс повторного удара на 80% урона. |
| AUDIO_RESONANCE | Резонанс | easy | yes | media | Аудио игнорирует броню и лечит 10% нанесённого урона. |
| GIF_FRENZY | Кадровая ярость | easy | yes | media | Гифка: 30% шанс дополнительного удара на 70% урона. |
| GIF_GLITCH | Глитч-кадр | easy | yes | media | Гифка: 20% шанс крита, игнорирует уклонение. |
| GIF_HYPNOSIS | Гипноз | easy | yes | media | Гифка: монстр заворожён и не контратакует. |
| GIF_LOOP | Зацикленность | easy | yes | media | Гифки наносят ×2.5 урона. |
| GRAPHOMANIA_ECHO | Эхо графомана | easy | yes | media | Текст: 15% шанс дополнительного удара на 60% урона. |
| INK_CRIT | Чернильный крит | easy | yes | media | Текст: 20% шанс критического удара. |
| LINK_PHISHING | Фишинг | easy | yes | media | Ссылка игнорирует броню и аффиксы монстра. |
| LINK_RICKROLL | Рикролл | medium | yes | random_proc | Ссылка: 50% шанс ×3 урона, иначе ×0.5. |
| LINK_VIRUS | Вирусная ссылка | easy | yes | media | Ссылки наносят ×4 урона. |
| LOUDSPEAKER | Громкоговоритель | easy | yes | media | Войсы и аудио: ×1.8 урона и 5% вампиризм. |
| MEDIA_STORM | Медиабуря | easy | yes | media | Любое не-текстовое сообщение наносит ×2 урона. |
| MEME_ARTILLERY | Мем-артиллерия | easy | yes | media | Стикеры и гифки: ×1.7 урона и 10% шанс крита. |
| MULTIMEDIA_LANCE | Мультимедийное копьё | easy | yes | media | Не-текстовые сообщения игнорируют броню монстра. |
| PEN_VAMPIRISM | Перо-вампир | easy | yes | media | Текстовые удары лечат ОВ на 8% нанесённого урона. |
| PHOTO_ALBUM | Фотоальбом | easy | yes | media | Фото: два дополнительных удара по 40% урона. |
| PHOTO_FLASH | Вспышка | easy | yes | media | Фотографии наносят ×2.5 урона. |
| PHOTO_FOCUS | Резкость | easy | yes | media | Фото: 25% шанс критического удара. |
| PHOTO_XRAY | Рентген | easy | yes | media | Фото игнорирует броню и уклонение монстра. |
| PURIST | Пуристка | easy | yes | media | Текст ×1.6 урона, любое медиа ×0.8. |
| SILENT_FILM | Немое кино | easy | yes | media | Фото, гифки и видео наносят ×1.8 урона. |
| STICKER_CRIT | Липкий крит | easy | yes | media | Стикер: 30% шанс критического удара. |
| STICKER_DOUBLE_TAP | Двойное касание | easy | yes | media | Стикер: 25% шанс второго удара на 50% урона. |
| STICKER_LIFELINE | Стикер-аптечка | easy | yes | media | Каждый стикер лечит ОВ на 3% макс. HP. |
| STICKER_PIERCE | Острый стикер | easy | yes | media | Стикеры игнорируют броню монстра. |
| STICKER_TRIPLE | Стикер-залп | easy | yes | media | Стикеры наносят ×3 урона. |
| VIDEO_BLOCKBUSTER | Блокбастер | easy | yes | media | Видео: 15% шанс крита, крит-урон ×2.5. |
| VIDEO_MONTAGE | Монтаж | medium | yes | media | Видео: три склейки по 50% урона вместо одного удара. |
| VIDEO_PREMIERE | Премьера | easy | yes | media | Видео наносит ×2.5 урона. |
| VOICE_COMMAND | Командный тон | easy | yes | media | Войс: 35% шанс критического удара. |
| VOICE_LULLABY | Колыбельная | medium | yes | media | Войс: монстр наносит себе 30% базового урона. |
| VOICE_SIREN | Сирена | easy | yes | media | Войс: ×1.5 урона, игнорирует уклонение. |
| VOICE_THUNDER | Громовой голос | easy | yes | media | Голосовые сообщения наносят ×3 урона. |
| WORD_BLADE | Словесный клинок | easy | yes | media | Текстовые сообщения наносят ×1.4 урона. |

<details><summary>params JSON</summary>

```json
{
  "AUDIO_BASSLINE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "audio"
      ],
      "effects": {
        "damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "AUDIO_ENCORE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "audio"
      ],
      "effects": {
        "extra_hit_chance": 0.25,
        "extra_hit_pct": 0.8
      }
    },
    "active": true
  },
  "AUDIO_RESONANCE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "audio"
      ],
      "effects": {
        "ignore_monster_armor": true,
        "heal_pct_of_damage": 0.1
      }
    },
    "active": true
  },
  "GIF_FRENZY": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "gif"
      ],
      "effects": {
        "extra_hit_chance": 0.3,
        "extra_hit_pct": 0.7
      }
    },
    "active": true
  },
  "GIF_GLITCH": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "gif"
      ],
      "effects": {
        "force_crit_chance": 0.2,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "GIF_HYPNOSIS": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "gif"
      ],
      "effects": {
        "ignore_monster_death_damage": true,
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "GIF_LOOP": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "gif"
      ],
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "GRAPHOMANIA_ECHO": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "effects": {
        "extra_hit_chance": 0.15,
        "extra_hit_pct": 0.6
      }
    },
    "active": true
  },
  "INK_CRIT": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "effects": {
        "force_crit_chance": 0.2
      }
    },
    "active": true
  },
  "LINK_PHISHING": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "link"
      ],
      "effects": {
        "ignore_monster_armor": true,
        "ignore_monster_affixes": true,
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "LINK_RICKROLL": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "media_types": [
        "link"
      ],
      "outcomes": [
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 3.0,
            "notification": "🎶 Рикролл сработал!"
          }
        },
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 0.5
          }
        }
      ]
    },
    "active": true
  },
  "LINK_VIRUS": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "link"
      ],
      "effects": {
        "damage_multiplier": 4.0
      }
    },
    "active": true
  },
  "LOUDSPEAKER": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "voice",
        "audio"
      ],
      "effects": {
        "damage_multiplier": 1.8,
        "heal_pct_of_damage": 0.05
      }
    },
    "active": true
  },
  "MEDIA_STORM": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "not_in": true,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "MEME_ARTILLERY": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker",
        "gif"
      ],
      "effects": {
        "damage_multiplier": 1.7,
        "force_crit_chance": 0.1
      }
    },
    "active": true
  },
  "MULTIMEDIA_LANCE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "not_in": true,
      "effects": {
        "ignore_monster_armor": true
      }
    },
    "active": true
  },
  "PEN_VAMPIRISM": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "effects": {
        "heal_pct_of_damage": 0.08
      }
    },
    "active": true
  },
  "PHOTO_ALBUM": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "photo"
      ],
      "effects": {
        "extra_hits": [
          0.4,
          0.4
        ]
      }
    },
    "active": true
  },
  "PHOTO_FLASH": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "photo"
      ],
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "PHOTO_FOCUS": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "photo"
      ],
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  },
  "PHOTO_XRAY": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "photo"
      ],
      "effects": {
        "ignore_monster_armor": true,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "PURIST": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "effects": {
        "damage_multiplier": 1.6
      },
      "else_effects": {
        "damage_multiplier": 0.8
      }
    },
    "active": true
  },
  "SILENT_FILM": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "photo",
        "gif",
        "video"
      ],
      "effects": {
        "damage_multiplier": 1.8
      }
    },
    "active": true
  },
  "STICKER_CRIT": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "force_crit_chance": 0.3
      }
    },
    "active": true
  },
  "STICKER_DOUBLE_TAP": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "extra_hit_chance": 0.25,
        "extra_hit_pct": 0.5
      }
    },
    "active": true
  },
  "STICKER_LIFELINE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "heal_pct_max_hp": 0.03
      }
    },
    "active": true
  },
  "STICKER_PIERCE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "ignore_monster_armor": true,
        "damage_multiplier": 1.2
      }
    },
    "active": true
  },
  "STICKER_TRIPLE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "VIDEO_BLOCKBUSTER": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "video"
      ],
      "effects": {
        "force_crit_chance": 0.15,
        "crit_damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "VIDEO_MONTAGE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "video"
      ],
      "effects": {
        "replace_with_hits": [
          0.5,
          0.5,
          0.5
        ]
      }
    },
    "active": true
  },
  "VIDEO_PREMIERE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "video"
      ],
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "VOICE_COMMAND": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "voice"
      ],
      "effects": {
        "force_crit_chance": 0.35
      }
    },
    "active": true
  },
  "VOICE_LULLABY": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "voice"
      ],
      "effects": {
        "monster_self_damage_pct_base": 0.3
      }
    },
    "active": true
  },
  "VOICE_SIREN": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "voice"
      ],
      "effects": {
        "damage_multiplier": 1.5,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "VOICE_THUNDER": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "voice"
      ],
      "effects": {
        "damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "WORD_BLADE": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "text"
      ],
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  }
}
```

</details>

## 2. Время суток / календарь (`time_calendar`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| CHRONO_TRIAD | Хроно-триада | easy | yes | time_window | В часы, кратные трём (00, 03, …, 21), урон ×1.6. |
| DAWN_PATROL | Рассветный дозор | easy | yes | time_window | Удары на рассвете (05:00–08:00) наносят ×2.5 урона. |
| DEADLINE_RUSH | Дедлайн | easy | yes | time_window | 23:00–00:00: урон ×2 и 10% вампиризм. |
| EVENING_RITUAL | Вечерний ритуал | easy | yes | time_window | 18:00–22:00: урон +40%. |
| EVEN_HOUR_SURGE | Чётный час | easy | yes | time_window | В чётные часы урон +25%. |
| FRIDAY_PARTY | Пятничный кураж | easy | yes | time_window | По пятницам: урон ×1.6 и золото ×1.3. |
| LUNCH_BREAK | Обеденный перерыв | easy | yes | time_window | 12:00–14:00: урон ×1.8. |
| MIDWEEK_FOCUS | Фокус среды | easy | yes | time_window | По средам: 25% шанс критического удара. |
| MIRROR_HOUR | Зеркальный час | medium | yes | time_window | Когда час равен минуте (11:11, 22:22) — урон ×5. |
| MONDAY_RAGE | Ярость понедельника | easy | yes | time_window | По понедельникам урон ×1.8. |
| MORNING_LOOT | Утренний лут | easy | yes | time_window | 06:00–10:00: шанс редкого дропа ×1.5. |
| NEW_DAY_SPARK | Искра нового дня | medium | yes | time_window | 00:00–01:00: урон ×2.2 и снятие дебаффов с ОВ. |
| NIGHT_HUNTER | Ночная охотница | easy | yes | time_window | Сообщения ночью (22:00–06:00) наносят ×2 урона. |
| NIGHT_MERCHANT | Ночная торговка | easy | yes | time_window | 00:00–06:00: золото с убийств ×2. |
| NIGHT_STICKERS | Ночные стикеры | easy | yes | time_window | Стикеры ночью (23:00–06:00) наносят ×3.5 урона. |
| ODD_HOUR_EDGE | Нечётный час | easy | yes | time_window | В нечётные часы: 15% шанс крита. |
| PRIME_TIME | Прайм-тайм | easy | yes | time_window | 19:00–21:00: урон ×1.7 и 20% шанс доп. удара на 30%. |
| SIESTA | Сиеста | easy | yes | time_window | 14:00–16:00: монстр дремлет и не контратакует. |
| SUNDAY_SERMON | Воскресная проповедь | easy | yes | time_window | Войсы по воскресеньям наносят ×3 урона. |
| WEEKEND_WARRIOR | Воин выходных | easy | yes | time_window | В субботу и воскресенье урон ×1.5. |
| WITCHING_HOUR | Час зверя | easy | yes | time_window | 03:00–04:00: урон ×4. |

<details><summary>params JSON</summary>

```json
{
  "CHRONO_TRIAD": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "mode": "hour_mod",
      "mod": 3,
      "remainder": 0,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "DAWN_PATROL": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 5,
      "hour_end": 8,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "DEADLINE_RUSH": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 23,
      "hour_end": 0,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 2.0,
        "heal_pct_of_damage": 0.1
      }
    },
    "active": true
  },
  "EVENING_RITUAL": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 18,
      "hour_end": 22,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "EVEN_HOUR_SURGE": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "mode": "even_hour",
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.25
      }
    },
    "active": true
  },
  "FRIDAY_PARTY": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "weekdays": [
        5
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.6,
        "gold_multiplier": 1.3
      }
    },
    "active": true
  },
  "LUNCH_BREAK": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 12,
      "hour_end": 14,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.8
      }
    },
    "active": true
  },
  "MIDWEEK_FOCUS": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "weekdays": [
        3
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  },
  "MIRROR_HOUR": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "mode": "mirror_time",
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 5.0,
        "notification": "🪞 Зеркальный час!"
      }
    },
    "active": true
  },
  "MONDAY_RAGE": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "weekdays": [
        1
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.8
      }
    },
    "active": true
  },
  "MORNING_LOOT": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 6,
      "hour_end": 10,
      "timezone": "Europe/Moscow",
      "effects": {
        "drop_chance_multiplier": 1.5
      }
    },
    "active": true
  },
  "NEW_DAY_SPARK": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 0,
      "hour_end": 1,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 2.2,
        "clear_waifu_debuffs": true
      }
    },
    "active": true
  },
  "NIGHT_HUNTER": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 22,
      "hour_end": 6,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "NIGHT_MERCHANT": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 0,
      "hour_end": 6,
      "timezone": "Europe/Moscow",
      "effects": {
        "gold_multiplier": 2.0
      }
    },
    "active": true
  },
  "NIGHT_STICKERS": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 23,
      "hour_end": 6,
      "media_types": [
        "sticker"
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 3.5
      }
    },
    "active": true
  },
  "ODD_HOUR_EDGE": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "mode": "odd_hour",
      "timezone": "Europe/Moscow",
      "effects": {
        "force_crit_chance": 0.15
      }
    },
    "active": true
  },
  "PRIME_TIME": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 19,
      "hour_end": 21,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.7,
        "extra_hit_chance": 0.2,
        "extra_hit_pct": 0.3
      }
    },
    "active": true
  },
  "SIESTA": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 14,
      "hour_end": 16,
      "timezone": "Europe/Moscow",
      "effects": {
        "ignore_monster_death_damage": true,
        "damage_multiplier": 1.2
      }
    },
    "active": true
  },
  "SUNDAY_SERMON": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "weekdays": [
        7
      ],
      "media_types": [
        "voice"
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "WEEKEND_WARRIOR": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "weekdays": [
        6,
        7
      ],
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "WITCHING_HOUR": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 3,
      "hour_end": 4,
      "timezone": "Europe/Moscow",
      "effects": {
        "damage_multiplier": 4.0,
        "notification": "🐺 Час зверя!"
      }
    },
    "active": true
  }
}
```

</details>

## 3. Темп и паузы (`tempo`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| AMBUSH_TIMING | Выжидание | easy | yes | tempo | Пауза 2+ минуты: удар ×2. |
| BERSERK_TEMPO | Темп берсерка | medium | yes | tempo | Серия быстрых (<10 с) сообщений: +10% урона за каждое, до 10 стаков. |
| CHARGED_MINUTES | Заряд минут | medium | yes | tempo | После минуты тишины: +20% урона за каждую минуту, максимум ×3. |
| COLD_BLOOD | Хладнокровие | easy | yes | tempo | Пауза 30+ секунд: следующий удар +50%. |
| FLASH_STEP | Шаг-вспышка | easy | yes | tempo | Сообщение быстрее 2 секунд: ×0.9 урона, но игнорирует броню и уклонение. |
| LIGHTNING_REFLEX | Молниеносность | easy | yes | tempo | Сообщение быстрее 3 секунд — 30% шанс крита. |
| METRONOME | Метроном | easy | yes | tempo | Интервал между сообщениями 10–20 секунд: урон ×1.5. |
| OVERCLOCK | Разгон | medium | yes | tempo | Серия быстрых (<8 с) сообщений: +8% за стак, до 12 стаков. |
| PATIENT_BLADE | Терпеливый клинок | easy | yes | tempo | Пауза 10+ минут: гарантированный крит. |
| QUICK_STICKER | Быстрый стикер | easy | yes | tempo | Стикер быстрее 6 секунд после прошлого сообщения — ×2.5. |
| RAPID_FIRE | Скорострельность | easy | yes | tempo | Сообщение быстрее 5 секунд после прошлого — урон ×1.4. |
| RHYTHM_KEEPER | Хранительница ритма | medium | yes | tempo | Интервал совпадает с предыдущим (±20%) — урон ×1.8. |
| SLOW_BURN | Медленное пламя | easy | yes | tempo | Интервал 30–120 секунд: +35% урона и 5% вампиризм. |
| SNIPER_BREATH | Дыхание снайпера | easy | yes | tempo | Пауза 5+ минут: удар ×3, игнорирует уклонение. |
| SPRINT | Спринт | medium | yes | tempo | Серия быстрых (<10 с) сообщений: +15% за стак, до 3 стаков. |
| UNHURRIED | Неторопливая | easy | yes | tempo | Сообщение спустя 60+ секунд: урон +60%. |
| ZEN_STRIKE | Дзен-удар | easy | yes | tempo | Пауза 30+ минут: удар ×4 и лечение 10% макс. HP. |

<details><summary>params JSON</summary>

```json
{
  "AMBUSH_TIMING": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 120,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "BERSERK_TEMPO": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast_streak",
      "window_seconds": 10,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.1
      }
    },
    "active": true
  },
  "CHARGED_MINUTES": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause_scaled",
      "min_seconds": 60,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.2,
        "max_damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "COLD_BLOOD": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 30,
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "FLASH_STEP": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast",
      "window_seconds": 2,
      "effects": {
        "damage_multiplier": 0.9,
        "ignore_monster_armor": true,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "LIGHTNING_REFLEX": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast",
      "window_seconds": 3,
      "effects": {
        "force_crit_chance": 0.3
      }
    },
    "active": true
  },
  "METRONOME": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "band",
      "min_seconds": 10,
      "max_seconds": 20,
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "OVERCLOCK": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast_streak",
      "window_seconds": 8,
      "max_stacks": 12,
      "effects": {
        "damage_bonus": 0.08
      }
    },
    "active": true
  },
  "PATIENT_BLADE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 600,
      "effects": {
        "force_crit": true,
        "notification": "🗡️ Терпение вознаграждено!"
      }
    },
    "active": true
  },
  "QUICK_STICKER": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast",
      "window_seconds": 6,
      "media_types": [
        "sticker"
      ],
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "RAPID_FIRE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast",
      "window_seconds": 5,
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "RHYTHM_KEEPER": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "rhythm",
      "tolerance": 0.2,
      "effects": {
        "damage_multiplier": 1.8,
        "notification": "🥁 В ритме!"
      }
    },
    "active": true
  },
  "SLOW_BURN": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "band",
      "min_seconds": 30,
      "max_seconds": 120,
      "effects": {
        "damage_multiplier": 1.35,
        "heal_pct_of_damage": 0.05
      }
    },
    "active": true
  },
  "SNIPER_BREATH": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 300,
      "effects": {
        "damage_multiplier": 3.0,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "SPRINT": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast_streak",
      "window_seconds": 10,
      "max_stacks": 3,
      "effects": {
        "damage_bonus": 0.15
      }
    },
    "active": true
  },
  "UNHURRIED": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 60,
      "effects": {
        "damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "ZEN_STRIKE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 1800,
      "effects": {
        "damage_multiplier": 4.0,
        "heal_pct_max_hp": 0.1,
        "notification": "🧘 Дзен!"
      }
    },
    "active": true
  }
}
```

</details>

## 4. Контент текста (`text_content`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| CAPS_FURY | Ярость капса | medium | yes | text_content | Сообщение ЦЕЛИКОМ КАПСОМ наносит ×2 урона. |
| CAPS_SIEGE | Осада капсом | medium | yes | text_content | ВЕСЬ КАПС: игнорирует броню и аффиксы монстра. |
| DIGIT_GAMBIT | Цифровой гамбит | medium | yes | text_content | Только цифры: 50% шанс дополнительного удара на 100%. |
| EMOJI_HEALER | Эмодзи-лекарь | medium | yes | text_content | Эмодзи в тексте: лечение 10% нанесённого урона. |
| EMOJI_SPICE | Эмодзи-приправа | medium | yes | text_content | Эмодзи в тексте — +35% урона. |
| ESSAY | Эссе | easy | yes | text_length | Текст длиннее 300 символов — ×2.5 урона. |
| EVEN_COUNT | Чётный счёт | easy | yes | text_length | Текст с чётным числом символов — +30% урона. |
| EXCLAMATION_STORM | Восклицание | medium | yes | text_content | Текст, оканчивающийся на «!» — ×1.6 урона. |
| HAIKU | Хайку | easy | yes | text_length | Текст из 11–17 символов наносит ×2 урона. |
| INTERROGATION | Допрос | medium | yes | text_content | Вопрос («?» в конце): монстр наносит себе 20% базового урона. |
| LUCKY_SEVEN_CHARS | Семь символов | easy | yes | text_length | Текст ровно из 7 символов — ×3 урона. |
| NOVELLA | Новелла | medium | yes | text_length | Текст длиннее 150 символов: +15% за каждые 50 сверх, до ×2.8. |
| NUMERIC_CODE | Числовой код | medium | yes | text_content | Сообщение только из цифр — ×2.2 урона. |
| ODD_COUNT | Нечётный счёт | easy | yes | text_length | Текст с нечётным числом символов — 15% шанс крита. |
| ONE_WORD_EXECUTION | Лаконичная казнь | medium | yes | text_content | Одно слово: 30% шанс крита, крит-урон ×1.5. |
| ONE_WORD_VERDICT | Вердикт | medium | yes | text_content | Сообщение из одного слова — ×1.7 урона. |
| PALINDROME_MAGIC | Магия палиндрома | hard | yes | text_content | Текст-палиндром наносит ×5 урона. |
| QUESTION_MARK | Вопрос ребром | medium | yes | text_content | Текст, оканчивающийся на «?» — 25% шанс крита. |
| SAME_CHAR_SCREAM | Монотонный вопль | medium | yes | text_content | Сообщение из одного повторяющегося символа — ×2.5. |
| SHORT_JAB | Короткий джеб | easy | yes | text_length | Текст короче 5 символов — ×1.5 урона. |
| TELEGRAPH | Телеграф | easy | yes | text_length | Текст из 5–10 символов: +25% урона, игнорирует уклонение. |
| WALL_OF_TEXT | Стена текста | medium | yes | text_content | Сообщение длиннее 30 слов — ×2 урона. |

<details><summary>params JSON</summary>

```json
{
  "CAPS_FURY": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "caps",
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "CAPS_SIEGE": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "caps",
      "effects": {
        "ignore_monster_armor": true,
        "ignore_monster_affixes": true
      }
    },
    "active": true
  },
  "DIGIT_GAMBIT": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "digits_only",
      "effects": {
        "extra_hit_chance": 0.5,
        "extra_hit_pct": 1.0
      }
    },
    "active": true
  },
  "EMOJI_HEALER": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "emoji",
      "effects": {
        "heal_pct_of_damage": 0.1
      }
    },
    "active": true
  },
  "EMOJI_SPICE": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "emoji",
      "effects": {
        "damage_multiplier": 1.35
      }
    },
    "active": true
  },
  "ESSAY": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "gt",
      "length": 300,
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "EVEN_COUNT": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "even",
      "effects": {
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "EXCLAMATION_STORM": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "exclamation",
      "effects": {
        "damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "HAIKU": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "between",
      "min_length": 11,
      "max_length": 17,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "INTERROGATION": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "question",
      "effects": {
        "monster_self_damage_pct_base": 0.2
      }
    },
    "active": true
  },
  "LUCKY_SEVEN_CHARS": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "eq",
      "length": 7,
      "effects": {
        "damage_multiplier": 3.0,
        "notification": "7️⃣ Семь символов!"
      }
    },
    "active": true
  },
  "NOVELLA": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "gt",
      "length": 150,
      "per_block": 50,
      "max_stacks": 12,
      "effects": {
        "damage_bonus": 0.15,
        "max_damage_multiplier": 2.8
      }
    },
    "active": true
  },
  "NUMERIC_CODE": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "digits_only",
      "effects": {
        "damage_multiplier": 2.2
      }
    },
    "active": true
  },
  "ODD_COUNT": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "odd",
      "effects": {
        "force_crit_chance": 0.15
      }
    },
    "active": true
  },
  "ONE_WORD_EXECUTION": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "one_word",
      "effects": {
        "force_crit_chance": 0.3,
        "crit_damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "ONE_WORD_VERDICT": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "one_word",
      "effects": {
        "damage_multiplier": 1.7
      }
    },
    "active": true
  },
  "PALINDROME_MAGIC": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "palindrome",
      "effects": {
        "damage_multiplier": 5.0,
        "notification": "🔄 Палиндром!"
      }
    },
    "active": true
  },
  "QUESTION_MARK": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "question",
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  },
  "SAME_CHAR_SCREAM": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "same_char",
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "SHORT_JAB": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "lt",
      "length": 5,
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "TELEGRAPH": {
    "handler": "text_length",
    "params": {
      "handler": "text_length",
      "op": "between",
      "min_length": 5,
      "max_length": 10,
      "effects": {
        "damage_multiplier": 1.25,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "WALL_OF_TEXT": {
    "handler": "text_content",
    "params": {
      "handler": "text_content",
      "mode": "word_count_gt",
      "word_count": 30,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  }
}
```

</details>

## 5. Комбо, серии и счётчики (`combo_counter`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ALTERNATE_CRIT | Чередование | easy | yes | counter | Тип сообщения отличается от предыдущего — 20% шанс крита. |
| CENTURION | Центурион | easy | yes | counter | 100-е сообщение боя наносит ×20 урона. |
| COLLECTOR_3 | Коллекционерка | easy | yes | counter | 3 разных типа медиа за бой — +35% урона. |
| COLLECTOR_5 | Архивариус | easy | yes | counter | 5 разных типов медиа за бой — +75% урона. |
| DECIMATOR | Дециматор | easy | yes | counter | Каждое 10-е сообщение — гарантированный крит и ×2 урона. |
| DEVILS_DOZEN | Чёртова дюжина | easy | yes | counter | Каждое 13-е сообщение наносит ×6.66 урона. |
| EVEN_BEAT | Чётный бит | easy | yes | counter | Каждое 2-е сообщение наносит +20% урона. |
| FULL_DECK | Полная колода | medium | yes | counter | 7 разных типов медиа за бой — урон ×3. |
| GIF_CAROUSEL | Гиф-карусель | medium | yes | counter | Подряд идущие гифки: +20% за каждую, до 6 стаков. |
| GOLDEN_SPIRAL | Золотая спираль | medium | yes | counter | Сообщения с номером Фибоначчи (1, 2, 3, 5, 8, 13…) наносят ×2.5 урона. |
| MEDIA_RAIN | Медиа-ливень | medium | yes | counter | Подряд идущие медиа (не текст): +12% за каждое, до 8 стаков. |
| MILESTONE_25 | Четвертьсотня | easy | yes | counter | 25-е сообщение за данж наносит ×8 урона. |
| MILESTONE_50 | Полусотня | easy | yes | counter | 50-е сообщение за данж: ×10 урона и лечение 20% макс. HP. |
| OPENING_GAMBIT | Дебютный гамбит | easy | yes | counter | Первое сообщение боя наносит ×2 урона. |
| PENTA_BEAT | Пентабит | easy | yes | counter | Каждое 5-е сообщение наносит ×2 урона. |
| PHOTO_SESSION | Фотосессия | medium | yes | counter | Подряд идущие фото: +18% за каждое, до 6 стаков. |
| PING_PONG | Пинг-понг | easy | yes | counter | Тип сообщения отличается от предыдущего — +30% урона. |
| PRIME_INSTINCT | Инстинкт простых чисел | medium | yes | counter | Сообщения с простым номером (2, 3, 5, 7, 11…) наносят +40% урона. |
| SEVENTH_SEAL | Седьмая печать | easy | yes | counter | Каждое 7-е сообщение: ×2 урона, игнорирует броню. |
| SHAPESHIFTER | Перевёртыш | medium | yes | counter | Серия сообщений без повтора типа: +15% за каждое, до 6 стаков. |
| STICKER_CHAIN | Стикерная цепь | medium | yes | counter | Подряд идущие стикеры: +15% урона за каждый, до 8 стаков. |
| TEXT_CRESCENDO | Крещендо | medium | yes | counter | Каждое последующее текстовое сообщение +10% урона, до 10 стаков; медиа обрывает серию. |
| THIRD_STRIKE | Третий удар | easy | yes | counter | Каждое 3-е сообщение в бою наносит ×1.5 урона. |
| VOICE_CHAIN | Голосовая цепь | medium | yes | counter | Подряд идущие войсы: +25% за каждый, до 5 стаков. |

<details><summary>params JSON</summary>

```json
{
  "ALTERNATE_CRIT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "alternate",
      "effects": {
        "force_crit_chance": 0.2
      }
    },
    "active": true
  },
  "CENTURION": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "n": 100,
      "effects": {
        "damage_multiplier": 20.0,
        "notification": "💯 Центурион!"
      }
    },
    "active": true
  },
  "COLLECTOR_3": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "unique_media",
      "n": 3,
      "effects": {
        "damage_multiplier": 1.35
      }
    },
    "active": true
  },
  "COLLECTOR_5": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "unique_media",
      "n": 5,
      "effects": {
        "damage_multiplier": 1.75
      }
    },
    "active": true
  },
  "DECIMATOR": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 10,
      "effects": {
        "force_crit": true,
        "damage_multiplier": 2.0,
        "notification": "🔟 Дециматор!"
      }
    },
    "active": true
  },
  "DEVILS_DOZEN": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 13,
      "effects": {
        "damage_multiplier": 6.66,
        "notification": "😈 Чёртова дюжина!"
      }
    },
    "active": true
  },
  "EVEN_BEAT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 2,
      "effects": {
        "damage_multiplier": 1.2
      }
    },
    "active": true
  },
  "FULL_DECK": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "unique_media",
      "n": 7,
      "effects": {
        "damage_multiplier": 3.0,
        "notification": "🃏 Полная колода!"
      }
    },
    "active": true
  },
  "GIF_CAROUSEL": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "type_streak",
      "media_type": "gif",
      "min_stacks": 2,
      "max_stacks": 6,
      "effects": {
        "damage_bonus": 0.2
      }
    },
    "active": true
  },
  "GOLDEN_SPIRAL": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "fibonacci",
      "effects": {
        "damage_multiplier": 2.5,
        "notification": "🌀 Золотая спираль!"
      }
    },
    "active": true
  },
  "MEDIA_RAIN": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "type_streak",
      "media_type": "media",
      "min_stacks": 2,
      "max_stacks": 8,
      "effects": {
        "damage_bonus": 0.12
      }
    },
    "active": true
  },
  "MILESTONE_25": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "scope": "session",
      "n": 25,
      "effects": {
        "damage_multiplier": 8.0,
        "notification": "💥 25-й удар!"
      }
    },
    "active": true
  },
  "MILESTONE_50": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "scope": "session",
      "n": 50,
      "effects": {
        "damage_multiplier": 10.0,
        "heal_pct_max_hp": 0.2,
        "notification": "🏅 Полусотня!"
      }
    },
    "active": true
  },
  "OPENING_GAMBIT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "n": 1,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "PENTA_BEAT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 5,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "PHOTO_SESSION": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "type_streak",
      "media_type": "photo",
      "min_stacks": 2,
      "max_stacks": 6,
      "effects": {
        "damage_bonus": 0.18
      }
    },
    "active": true
  },
  "PING_PONG": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "alternate",
      "effects": {
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "PRIME_INSTINCT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "prime",
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "SEVENTH_SEAL": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 7,
      "effects": {
        "damage_multiplier": 2.0,
        "ignore_monster_armor": true
      }
    },
    "active": true
  },
  "SHAPESHIFTER": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "no_repeat_streak",
      "min_stacks": 1,
      "max_stacks": 6,
      "effects": {
        "damage_bonus": 0.15
      }
    },
    "active": true
  },
  "STICKER_CHAIN": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "type_streak",
      "media_type": "sticker",
      "min_stacks": 2,
      "max_stacks": 8,
      "effects": {
        "damage_bonus": 0.15
      }
    },
    "active": true
  },
  "TEXT_CRESCENDO": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "text_streak",
      "min_stacks": 2,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.1
      }
    },
    "active": true
  },
  "THIRD_STRIKE": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 3,
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "VOICE_CHAIN": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "type_streak",
      "media_type": "voice",
      "min_stacks": 2,
      "max_stacks": 5,
      "effects": {
        "damage_bonus": 0.25
      }
    },
    "active": true
  }
}
```

</details>

## 6. Крит-механики (`crit`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ALL_IN | Ва-банк | easy | yes | random_proc | 8% шанс: гарантированный крит с крит-уроном ×4. |
| ASSASSIN_OPENER | Удар из тени | easy | yes | monster_state | Первый удар по монстру: 30% шанс крита, крит-урон ×2.5. |
| BOSS_PIERCER | Пронзательница боссов | easy | yes | monster_state | Против боссов крит-урон ×2. |
| CALM_CRIT | Спокойный расчёт | easy | yes | tempo | Пауза 60+ секунд: крит-урон ×2.2. |
| CRIT_SPLASH | Критический всплеск | medium | yes | random_proc | 15% шанс: крит + волна 30% урона по остальным монстрам. |
| CRIT_VAMPIRE | Кровавый крит | easy | yes | random_proc | 20% шанс: крит + лечение 15% нанесённого урона. |
| ELITE_PIERCER | Гроза элиток | easy | yes | monster_state | Против монстров с аффиксами: 30% шанс крита, крит-урон ×1.5. |
| EXECUTIONER_EYE | Глаз палача | easy | yes | hp_state | Монстр ниже 30% HP — 40% шанс крита. |
| FULL_HP_EXECUTION | Чистое начало | easy | yes | hp_state | Монстр на полном HP — гарантированный крит. |
| GLASS_CANNON | Стеклянная пушка | easy | yes | passive | Крит-урон ×3, но обычный урон ×0.85. |
| LUCKY_STRIKE | Счастливый удар | easy | yes | passive | Постоянный 12% шанс критического удара. |
| NIGHT_PRECISION | Ночная точность | easy | yes | time_window | 22:00–06:00: +30% шанс критического удара. |
| RICOCHET_CRIT | Рикошет | easy | yes | random_proc | 10% шанс: крит и дополнительный удар на 50%. |
| SHARPENED_EDGE | Заточенное лезвие | easy | yes | passive | Критический урон ×1.75. |
| SPEED_CRIT | Скоростной крит | easy | yes | tempo | Сообщение быстрее 4 секунд — 35% шанс крита. |
| STICKER_SLAYER | Стикер-убийца | easy | yes | media | Стикеры: крит-урон ×2.2. |
| WOUNDED_PRECISION | Раненая точность | easy | yes | hp_state | HP ОВ ниже 40% — 25% шанс крита. |

<details><summary>params JSON</summary>

```json
{
  "ALL_IN": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.08,
      "effects": {
        "force_crit": true,
        "crit_damage_multiplier": 4.0,
        "notification": "🎰 Ва-банк!"
      }
    },
    "active": true
  },
  "ASSASSIN_OPENER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "first_hit",
      "effects": {
        "force_crit_chance": 0.3,
        "crit_damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "BOSS_PIERCER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "boss",
      "effects": {
        "crit_damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "CALM_CRIT": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 60,
      "effects": {
        "crit_damage_multiplier": 2.2
      }
    },
    "active": true
  },
  "CRIT_SPLASH": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.15,
      "effects": {
        "force_crit": true,
        "remaining_monsters_damage_multiplier": 0.3
      }
    },
    "active": true
  },
  "CRIT_VAMPIRE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.2,
      "effects": {
        "force_crit": true,
        "heal_pct_of_damage": 0.15
      }
    },
    "active": true
  },
  "ELITE_PIERCER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "elite",
      "effects": {
        "force_crit_chance": 0.3,
        "crit_damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "EXECUTIONER_EYE": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.3,
      "effects": {
        "force_crit_chance": 0.4
      }
    },
    "active": true
  },
  "FULL_HP_EXECUTION": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "full",
      "effects": {
        "force_crit": true
      }
    },
    "active": true
  },
  "GLASS_CANNON": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "damage_multiplier": 0.85,
        "crit_damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "LUCKY_STRIKE": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "force_crit_chance": 0.12
      }
    },
    "active": true
  },
  "NIGHT_PRECISION": {
    "handler": "time_window",
    "params": {
      "handler": "time_window",
      "hour_start": 22,
      "hour_end": 6,
      "timezone": "Europe/Moscow",
      "effects": {
        "force_crit_chance": 0.3
      }
    },
    "active": true
  },
  "RICOCHET_CRIT": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.1,
      "effects": {
        "force_crit": true,
        "extra_hits": [
          0.5
        ]
      }
    },
    "active": true
  },
  "SHARPENED_EDGE": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "crit_damage_multiplier": 1.75
      }
    },
    "active": true
  },
  "SPEED_CRIT": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast",
      "window_seconds": 4,
      "effects": {
        "force_crit_chance": 0.35
      }
    },
    "active": true
  },
  "STICKER_SLAYER": {
    "handler": "media",
    "params": {
      "handler": "media",
      "media_types": [
        "sticker"
      ],
      "effects": {
        "crit_damage_multiplier": 2.2
      }
    },
    "active": true
  },
  "WOUNDED_PRECISION": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.4,
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  }
}
```

</details>

## 7. HP-состояния (`hp_state`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ADRENALINE | Адреналин | easy | yes | hp_state | HP ОВ ниже 50% — урон +25%. |
| BALANCE_POINT | Точка равновесия | easy | yes | hp_state | HP ОВ между 40% и 60% — урон ×1.7. |
| BLOOD_PACT | Кровавый пакт | easy | yes | hp_state | HP ОВ ниже 50% — +15% урона и 10% вампиризм. |
| DEATHS_DOOR | У последней черты | easy | yes | hp_state | HP ОВ ниже 10% — урон ×3 и 20% вампиризм. |
| DESPERATION | Отчаяние | easy | yes | hp_state | HP ОВ ниже 25% — урон ×1.8. |
| EXECUTIONER | Палач | easy | yes | hp_state | Монстр ниже 25% HP — урон ×2. |
| FINISHER_50 | Добивательница | easy | yes | hp_state | Монстр ниже 50% HP — урон +35%. |
| FRESH_START | Свежесть | easy | yes | hp_state | ОВ на полном HP — урон ×1.5. |
| FRESH_TARGET | Свежая цель | easy | yes | hp_state | Монстр выше 90% HP — урон ×1.6. |
| GIANT_SLAYER | Гроза великанов | medium | yes | hp_state | HP монстра минимум вдвое больше HP ОВ — урон ×2. |
| HEALTHY_GLOW | Здоровый блеск | easy | yes | hp_state | HP ОВ выше 80% — +20% урона и дроп ×1.2. |
| IRON_WILL | Железная воля | easy | yes | hp_state | HP ОВ ниже 20% — монстр не контратакует. |
| LAST_INCH | Последний дюйм | easy | yes | hp_state | Монстр ниже 5% HP — урон ×5. |
| MOMENTUM | Импульс | easy | yes | hp_state | Монстр ниже 75% HP — урон +20%. |
| OVERFLOW | Переизбыток сил | easy | yes | hp_state | ОВ на полном HP: 30% шанс дополнительного удара на 60%. |
| PAIN_PRICE | Цена боли | medium | yes | hp_state | +9% урона за каждые потерянные 10% HP ОВ, до +72%. |
| PHOENIX_SPARK | Искра феникса | easy | yes | hp_state | HP ОВ ниже 15% — каждый удар лечит 3% макс. HP. |
| SCALES_OF_FATE | Весы судьбы | medium | yes | hp_state | +6% урона за каждые 10% HP, потерянные монстром, до +60%. |
| SURGICAL | Хирургическая точность | easy | yes | hp_state | Монстр на 45–55% HP — гарантированный крит. |
| TITAN_FELLER | Низвергательница титанов | easy | yes | monster_state | Монстр с 1000+ HP — урон +50%. |
| UNDERDOG | Аутсайдер | easy | yes | hp_state | HP ОВ ниже 30% — удары игнорируют броню и аффиксы. |
| VITALITY_TAX | Налог на живучесть | easy | yes | hp_state | Монстр выше 50% HP — +25% урона, игнорирует уклонение. |

<details><summary>params JSON</summary>

```json
{
  "ADRENALINE": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.5,
      "effects": {
        "damage_multiplier": 1.25
      }
    },
    "active": true
  },
  "BALANCE_POINT": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "between",
      "min_pct": 0.4,
      "max_pct": 0.6,
      "effects": {
        "damage_multiplier": 1.7
      }
    },
    "active": true
  },
  "BLOOD_PACT": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.5,
      "effects": {
        "damage_multiplier": 1.15,
        "heal_pct_of_damage": 0.1
      }
    },
    "active": true
  },
  "DEATHS_DOOR": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.1,
      "effects": {
        "damage_multiplier": 3.0,
        "heal_pct_of_damage": 0.2
      }
    },
    "active": true
  },
  "DESPERATION": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.25,
      "effects": {
        "damage_multiplier": 1.8
      }
    },
    "active": true
  },
  "EXECUTIONER": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.25,
      "effects": {
        "damage_multiplier": 2.0
      }
    },
    "active": true
  },
  "FINISHER_50": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.5,
      "effects": {
        "damage_multiplier": 1.35
      }
    },
    "active": true
  },
  "FRESH_START": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "full",
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "FRESH_TARGET": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "above",
      "pct": 0.9,
      "effects": {
        "damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "GIANT_SLAYER": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "op": "david",
      "ratio": 2.0,
      "effects": {
        "damage_multiplier": 2.0,
        "notification": "🏹 Давид против Голиафа!"
      }
    },
    "active": true
  },
  "HEALTHY_GLOW": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "above",
      "pct": 0.8,
      "effects": {
        "damage_multiplier": 1.2,
        "drop_chance_multiplier": 1.2
      }
    },
    "active": true
  },
  "IRON_WILL": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.2,
      "effects": {
        "ignore_monster_death_damage": true
      }
    },
    "active": true
  },
  "LAST_INCH": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.05,
      "effects": {
        "damage_multiplier": 5.0
      }
    },
    "active": true
  },
  "MOMENTUM": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.75,
      "effects": {
        "damage_multiplier": 1.2
      }
    },
    "active": true
  },
  "OVERFLOW": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "full",
      "effects": {
        "extra_hit_chance": 0.3,
        "extra_hit_pct": 0.6
      }
    },
    "active": true
  },
  "PAIN_PRICE": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "per_missing",
      "max_stacks": 8,
      "effects": {
        "damage_bonus": 0.09
      }
    },
    "active": true
  },
  "PHOENIX_SPARK": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.15,
      "effects": {
        "heal_pct_max_hp": 0.03
      }
    },
    "active": true
  },
  "SCALES_OF_FATE": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "per_missing",
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.06
      }
    },
    "active": true
  },
  "SURGICAL": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "between",
      "min_pct": 0.45,
      "max_pct": 0.55,
      "effects": {
        "force_crit": true
      }
    },
    "active": true
  },
  "TITAN_FELLER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "big_hp",
      "value": 1000,
      "effects": {
        "damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "UNDERDOG": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "waifu",
      "op": "below",
      "pct": 0.3,
      "effects": {
        "ignore_monster_armor": true,
        "ignore_monster_affixes": true
      }
    },
    "active": true
  },
  "VITALITY_TAX": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "above",
      "pct": 0.5,
      "effects": {
        "damage_multiplier": 1.25,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  }
}
```

</details>

## 8. Реактивные / защитные (`reactive`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| AVENGER | Мстительница | medium | yes | state_flag | Первый удар после ранения — +45% урона. |
| BLOOD_DEBT | Кровавый долг | medium | yes | on_kill | Убийство: 40% шанс восстановить 25% макс. HP. |
| COMEBACK_KID | Возвращение | medium | yes | state_flag | После нокаута в сессии: дроп ×1.5 и золото ×1.3. |
| COUNTER_CURSE | Контрдеклятие | hard | yes | legacy | После дебаффа — +{damage_bonus_pct}% и снятие. |
| COUNTER_DODGE | Ответный удар | medium | yes | legacy | После уклонения — следующий удар крит. |
| DEBUFF_EATER | Пожирательница проклятий | medium | yes | state_flag | После дебаффа от монстра: следующий удар ×1.6 и снятие дебаффов. |
| FIRST_BLOOD_REPLY | Ответ на первую кровь | medium | yes | state_flag | Получив урон в бою — 15% шанс крита на каждом ударе. |
| GRUDGE_KEEPER | Злопамятность | medium | yes | state_flag | Первый удар после ранения бьёт дважды (доп. удар 80%). |
| GUARDIAN_ANGEL | Ангел-хранитель | easy | yes | passive | Каждый удар лечит ОВ на 2% макс. HP. |
| HUNT_FRENZY | Охотничий азарт | easy | yes | legacy | Первый удар после убийства — ×{damage_multiplier}. |
| KILLING_BLOW_HEAL | Добивание с выгодой | medium | yes | legacy | {proc_chance_pct}% шанс +{heal_pct}% HP при добивании. |
| KILL_FEAST | Пир после битвы | medium | yes | on_kill | Убийство монстра: 50% шанс восстановить 15% макс. HP. |
| MATADOR | Матадор | medium | yes | state_flag | После уклонения следующее сообщение бьёт дважды (доп. удар 70%). |
| PAIN_CONVERTER | Конвертер боли | medium | yes | session_scale | +5% урона за каждые 50 полученного в бою урона, до +50%. |
| PHOENIX_RAGE | Феникс | hard | yes | legacy | После воскрешения — ×{damage_multiplier} на {duration_minutes} мин. |
| RETRIBUTION | Возмездие | medium | yes | state_flag | После уклонения: гарантированный крит с крит-уроном ×2. |
| REVENGE_CRYSTAL | Кристалл мести | hard | yes | legacy | Возврат {return_multiplier_pct}% полученного урона. |
| REVENGE_THIRST | Жажда мести | medium | yes | legacy | Первый удар после ранения — крит. |
| RIPOSTE | Рипост | medium | yes | state_flag | После уклонения от атаки монстра следующий удар +60%. |
| SECOND_WIND | Второе дыхание | easy | yes | tempo | Удар после паузы 3+ минуты лечит ОВ на 10% макс. HP. |
| SHELL_SHOCK | Контузия | easy | yes | random_proc | 10% шанс: монстр наносит себе 50% базового урона ОВ. |
| SOUL_HARVEST | Жатва душ | medium | yes | on_kill | Каждое убийство восстанавливает 5% макс. HP. |
| THORNS_AURA | Терновая аура | easy | yes | passive | Каждый удар ОВ дополнительно ранит монстра на 10% базового урона. |
| UNBREAKABLE | Несгибаемость | medium | yes | state_flag | После нокаута в этой сессии ОВ наносит +40% урона. |
| VENDETTA | Вендетта | medium | yes | state_flag | Получив урон в бою, ОВ наносит +20% урона до конца боя. |

<details><summary>params JSON</summary>

```json
{
  "AVENGER": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "revenge_ready",
      "consume": true,
      "effects": {
        "damage_multiplier": 1.45
      }
    },
    "active": true
  },
  "BLOOD_DEBT": {
    "handler": "on_kill",
    "params": {
      "handler": "on_kill",
      "proc_chance": 0.4,
      "effects": {
        "heal_pct_max_hp": 0.25,
        "notification": "🩸 Кровавый долг оплачен!"
      }
    },
    "active": true
  },
  "COMEBACK_KID": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "knocked_out_this_session",
      "effects": {
        "drop_chance_multiplier": 1.5,
        "gold_multiplier": 1.3
      }
    },
    "active": true
  },
  "COUNTER_CURSE": {
    "handler": "legacy",
    "params": {
      "damage_bonus": 0.75
    },
    "active": true
  },
  "COUNTER_DODGE": {
    "handler": "legacy",
    "params": {},
    "active": true
  },
  "DEBUFF_EATER": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "curse_counter_ready",
      "consume": true,
      "listen_debuff": true,
      "effects": {
        "damage_multiplier": 1.6,
        "clear_waifu_debuffs": true
      }
    },
    "active": true
  },
  "FIRST_BLOOD_REPLY": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "received_damage_this_fight",
      "effects": {
        "force_crit_chance": 0.15
      }
    },
    "active": true
  },
  "GRUDGE_KEEPER": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "revenge_ready",
      "consume": true,
      "effects": {
        "extra_hits": [
          0.8
        ]
      }
    },
    "active": true
  },
  "GUARDIAN_ANGEL": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "heal_pct_max_hp": 0.02
      }
    },
    "active": true
  },
  "HUNT_FRENZY": {
    "handler": "legacy",
    "params": {
      "damage_multiplier": 2.0
    },
    "active": true
  },
  "KILLING_BLOW_HEAL": {
    "handler": "legacy",
    "params": {
      "proc_chance": 0.6,
      "heal_pct": 0.1
    },
    "active": true
  },
  "KILL_FEAST": {
    "handler": "on_kill",
    "params": {
      "handler": "on_kill",
      "proc_chance": 0.5,
      "effects": {
        "heal_pct_max_hp": 0.15,
        "notification": "🍖 Пир после битвы!"
      }
    },
    "active": true
  },
  "MATADOR": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "counter_dodge_ready",
      "consume": true,
      "listen_dodge": true,
      "effects": {
        "extra_hits": [
          0.7
        ]
      }
    },
    "active": true
  },
  "PAIN_CONVERTER": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "received_damage",
      "per_damage": 50,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.05
      }
    },
    "active": true
  },
  "PHOENIX_RAGE": {
    "handler": "legacy",
    "params": {
      "duration_minutes": 5,
      "damage_multiplier": 2.0
    },
    "active": true
  },
  "RETRIBUTION": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "counter_dodge_ready",
      "consume": true,
      "listen_dodge": true,
      "effects": {
        "force_crit": true,
        "crit_damage_multiplier": 2.0,
        "notification": "⚖️ Возмездие!"
      }
    },
    "active": true
  },
  "REVENGE_CRYSTAL": {
    "handler": "legacy",
    "params": {
      "return_multiplier": 1.5
    },
    "active": true
  },
  "REVENGE_THIRST": {
    "handler": "legacy",
    "params": {},
    "active": true
  },
  "RIPOSTE": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "counter_dodge_ready",
      "consume": true,
      "listen_dodge": true,
      "effects": {
        "damage_multiplier": 1.6,
        "notification": "🤺 Рипост!"
      }
    },
    "active": true
  },
  "SECOND_WIND": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "pause",
      "min_seconds": 180,
      "effects": {
        "heal_pct_max_hp": 0.1
      }
    },
    "active": true
  },
  "SHELL_SHOCK": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.1,
      "effects": {
        "monster_self_damage_pct_base": 0.5,
        "notification": "💫 Контузия!"
      }
    },
    "active": true
  },
  "SOUL_HARVEST": {
    "handler": "on_kill",
    "params": {
      "handler": "on_kill",
      "proc_chance": 1.0,
      "effects": {
        "heal_pct_max_hp": 0.05
      }
    },
    "active": true
  },
  "THORNS_AURA": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "monster_self_damage_pct_base": 0.1
      }
    },
    "active": true
  },
  "UNBREAKABLE": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "knocked_out_this_session",
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "VENDETTA": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "received_damage_this_fight",
      "effects": {
        "damage_multiplier": 1.2
      }
    },
    "active": true
  }
}
```

</details>

## 9. Прогресс боя / данжа (`dungeon_progress`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ABYSS_GAZE | Взгляд бездны | easy | yes | monster_state | Монстры с 800+ HP: +20% урона, игнорирует броню. |
| AFFIX_FEAST | Пир на аффиксах | easy | yes | monster_state | +12% урона за каждый аффикс монстра, до 5 стаков. |
| BOSS_BANE | Бич боссов | easy | yes | monster_state | Против боссов: +60% урона, игнорирует аффиксы. |
| BOSS_TREASURER | Казначейша босса | easy | yes | monster_state | Боссы: золото ×2 и дроп ×1.5. |
| CHAIN_REACTION | Цепная реакция | medium | yes | session_scale | Первый удар по новому монстру: +30% от урона прошлого боя. |
| CLEAN_CUT | Чистый разрез | medium | yes | passive | Убитые монстры не призывают подмогу при смерти. |
| CLEAN_KILL | Чистая работа | easy | yes | monster_state | Против монстров без аффиксов: ×1.5 урона и 10% шанс крита. |
| EARLY_BIRD_GOLD | Ранний вклад | medium | yes | state_flag | В первом подземелье дня золото ×2. |
| ELITE_BREAKER | Крушительница элит | easy | yes | monster_state | Против монстров с аффиксами урон ×1.6. |
| EVEN_PREY | Чётная добыча | easy | yes | monster_state | Против монстров с чётным номером урон +30%. |
| GOLD_RUSH_KILLS | Золотая лихорадка | medium | yes | session_scale | +5% золота за каждого убитого в сессии, до 10 стаков. |
| KILL_MOMENTUM | Раскатка | medium | yes | session_scale | +6% урона за каждого убитого в сессии монстра, до +60%. |
| MARATHON_RUNNER | Марафонец | medium | yes | session_scale | +3% урона за каждые 300 урона за сессию, до 15 стаков. |
| MF_SNOWBALL | Снежный ком удачи | medium | yes | session_scale | +4% к шансу дропа за каждого убитого, до 15 стаков. |
| NO_MERCY | Без пощады | medium | yes | hp_state | Монстр ниже 40% HP: удары задевают остальных на 25%. |
| OPENING_STRIKE | Разведка боем | easy | yes | monster_state | Первый удар по каждому монстру наносит ×1.7 урона. |
| SEVENTH_VICTIM | Седьмая жертва | easy | yes | monster_state | Каждый монстр с номером, кратным 7, получает ×2.5 урона. |
| SPLASH_MASTER | Веер | medium | yes | passive | Каждый удар задевает остальных монстров на 10% урона. |
| SURVIVOR_RAGE | Ярость выжившей | medium | yes | state_flag | После провала прошлого подземелья — 25% шанс крита. |
| TRASH_SWEEPER | Чистильщица | easy | yes | monster_state | Против обычных монстров (не боссов) урон ×1.4. |
| TROPHY_HUNTER | Охота за трофеем | easy | yes | monster_state | Против боссов: 50% шанс критического удара. |
| VANGUARD | Авангард | easy | yes | monster_state | Первый удар по монстру: ×1.5 и игнорирует уклонение. |
| WAR_MARCH | Военный марш | medium | yes | session_scale | +5% урона за каждые 150 урона, нанесённого в этом бою, до 8 стаков. |

<details><summary>params JSON</summary>

```json
{
  "ABYSS_GAZE": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "big_hp",
      "value": 800,
      "effects": {
        "damage_multiplier": 1.2,
        "ignore_monster_armor": true
      }
    },
    "active": true
  },
  "AFFIX_FEAST": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "affix_scaled",
      "max_stacks": 5,
      "effects": {
        "damage_bonus": 0.12
      }
    },
    "active": true
  },
  "BOSS_BANE": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "boss",
      "effects": {
        "damage_multiplier": 1.6,
        "ignore_monster_affixes": true
      }
    },
    "active": true
  },
  "BOSS_TREASURER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "boss",
      "effects": {
        "gold_multiplier": 2.0,
        "drop_chance_multiplier": 1.5
      }
    },
    "active": true
  },
  "CHAIN_REACTION": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "echo",
      "echo_pct": 0.3,
      "require_first_hit": true,
      "effects": {
        "notification": "⛓️ Цепная реакция!"
      }
    },
    "active": true
  },
  "CLEAN_CUT": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "prevent_monster_death_spawn": true
      }
    },
    "active": true
  },
  "CLEAN_KILL": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "clean",
      "effects": {
        "damage_multiplier": 1.5,
        "force_crit_chance": 0.1
      }
    },
    "active": true
  },
  "EARLY_BIRD_GOLD": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "first_daily_dungeon",
      "effects": {
        "gold_multiplier": 2.0
      }
    },
    "active": true
  },
  "ELITE_BREAKER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "elite",
      "effects": {
        "damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "EVEN_PREY": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "id_mod",
      "mod": 2,
      "remainder": 0,
      "effects": {
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "GOLD_RUSH_KILLS": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "per_kill",
      "max_stacks": 10,
      "effects": {
        "gold_bonus": 0.05
      }
    },
    "active": true
  },
  "KILL_MOMENTUM": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "per_kill",
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.06
      }
    },
    "active": true
  },
  "MARATHON_RUNNER": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "session_damage",
      "per_damage": 300,
      "max_stacks": 15,
      "effects": {
        "damage_bonus": 0.03
      }
    },
    "active": true
  },
  "MF_SNOWBALL": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "per_kill",
      "max_stacks": 15,
      "effects": {
        "drop_bonus": 0.04
      }
    },
    "active": true
  },
  "NO_MERCY": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.4,
      "effects": {
        "remaining_monsters_damage_multiplier": 0.25
      }
    },
    "active": true
  },
  "OPENING_STRIKE": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "first_hit",
      "effects": {
        "damage_multiplier": 1.7
      }
    },
    "active": true
  },
  "SEVENTH_VICTIM": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "id_mod",
      "mod": 7,
      "remainder": 0,
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "SPLASH_MASTER": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "remaining_monsters_damage_multiplier": 0.1
      }
    },
    "active": true
  },
  "SURVIVOR_RAGE": {
    "handler": "state_flag",
    "params": {
      "handler": "state_flag",
      "flag": "waifu_last_dungeon_knocked_out",
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  },
  "TRASH_SWEEPER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "not_boss",
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "TROPHY_HUNTER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "boss",
      "effects": {
        "force_crit_chance": 0.5
      }
    },
    "active": true
  },
  "VANGUARD": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "first_hit",
      "effects": {
        "damage_multiplier": 1.5,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "WAR_MARCH": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "fight_damage",
      "per_damage": 150,
      "max_stacks": 8,
      "effects": {
        "damage_bonus": 0.05
      }
    },
    "active": true
  }
}
```

</details>

## 10. Экономика / лут (`economy`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| AUCTIONEER | Аукционистка | medium | yes | session_scale | +6% к дропу за каждую продажу в сессии, до 5 стаков. |
| BEGGARS_FURY | Ярость нищенки | easy | yes | economy | Золота меньше 100 — урон ×1.7. |
| COIN_FLIP_TRADE | Орёл и решка | easy | yes | random_proc | 50/50: либо золото ×2, либо урон ×1.5. |
| DRAGON_HOARD | Драконья казна | easy | yes | economy | Золота больше 20000: урон ×1.5, дроп ×1.5, золото ×1.5. |
| GOLDEN_BULLET | Золотая пуля | easy | yes | random_proc | 5% шанс: урон ×3 и золото ×3. |
| GOLD_GUARD | Золотая стража | easy | yes | economy | Золота больше 2000 — +15% урона, монстр ранит себя на 10% базы. |
| INVESTOR | Инвесторша | easy | yes | economy | Золота больше 5000 — урон +20%. |
| LOOT_MAGNET | Магнит лута | easy | yes | monster_state | Против боссов шанс дропа ×2. |
| LUCKY_CHARM | Талисман удачи | easy | yes | meta_scale | Удача ОВ 30+ — дроп ×1.3. |
| MIDAS_TOUCH | Прикосновение Мидаса | easy | yes | passive | Золото с убийств ×1.5. |
| PAWNBROKER | Ломбардщица | medium | yes | session_scale | +2% урона за каждый проданный за сессию предмет, до +40%. |
| POOR_LUCK | Удача бедноты | easy | yes | economy | Золота меньше 500 — дроп ×1.4. |
| PROFITEER | Барышница | medium | yes | session_scale | +1% к дропу за каждую продажу в сессии, до 20 стаков. |
| RAGS_TO_RICHES | Из грязи в князи | easy | yes | economy | Золота меньше 50 — урон ×2.5. |
| SCROOGE | Скряга | easy | yes | economy | Золота больше 1000 — золото с убийств ×1.4. |
| TITHE | Десятина | easy | yes | counter | Каждое 10-е сообщение приносит двойное золото с убийства. |
| TREASURE_NOSE | Чутьё на клад | easy | yes | passive | Шанс редкого дропа ×1.25. |
| TYCOON | Магнатка | easy | yes | economy | Золота больше 10000 — дроп ×1.5 и +15% урона. |

<details><summary>params JSON</summary>

```json
{
  "AUCTIONEER": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "items_sold",
      "max_stacks": 5,
      "effects": {
        "drop_bonus": 0.06
      }
    },
    "active": true
  },
  "BEGGARS_FURY": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_below",
      "value": 100,
      "effects": {
        "damage_multiplier": 1.7
      }
    },
    "active": true
  },
  "COIN_FLIP_TRADE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.5,
          "effects": {
            "gold_multiplier": 2.0
          }
        },
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 1.5
          }
        }
      ]
    },
    "active": true
  },
  "DRAGON_HOARD": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_above",
      "value": 20000,
      "effects": {
        "damage_multiplier": 1.5,
        "drop_chance_multiplier": 1.5,
        "gold_multiplier": 1.5
      }
    },
    "active": true
  },
  "GOLDEN_BULLET": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.05,
      "effects": {
        "damage_multiplier": 3.0,
        "gold_multiplier": 3.0,
        "notification": "🥇 Золотая пуля!"
      }
    },
    "active": true
  },
  "GOLD_GUARD": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_above",
      "value": 2000,
      "effects": {
        "damage_multiplier": 1.15,
        "monster_self_damage_pct_base": 0.1
      }
    },
    "active": true
  },
  "INVESTOR": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_above",
      "value": 5000,
      "effects": {
        "damage_multiplier": 1.2
      }
    },
    "active": true
  },
  "LOOT_MAGNET": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "boss",
      "effects": {
        "drop_chance_multiplier": 2.0
      }
    },
    "active": true
  },
  "LUCKY_CHARM": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "luck",
      "mode": "above",
      "value": 30,
      "effects": {
        "drop_chance_multiplier": 1.3
      }
    },
    "active": true
  },
  "MIDAS_TOUCH": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "gold_multiplier": 1.5
      }
    },
    "active": true
  },
  "PAWNBROKER": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "items_sold",
      "max_stacks": 20,
      "effects": {
        "damage_bonus": 0.02
      }
    },
    "active": true
  },
  "POOR_LUCK": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_below",
      "value": 500,
      "effects": {
        "drop_chance_multiplier": 1.4
      }
    },
    "active": true
  },
  "PROFITEER": {
    "handler": "session_scale",
    "params": {
      "handler": "session_scale",
      "mode": "items_sold",
      "max_stacks": 20,
      "effects": {
        "drop_bonus": 0.01
      }
    },
    "active": true
  },
  "RAGS_TO_RICHES": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_below",
      "value": 50,
      "effects": {
        "damage_multiplier": 2.5
      }
    },
    "active": true
  },
  "SCROOGE": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_above",
      "value": 1000,
      "effects": {
        "gold_multiplier": 1.4
      }
    },
    "active": true
  },
  "TITHE": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 10,
      "effects": {
        "gold_multiplier": 2.0
      }
    },
    "active": true
  },
  "TREASURE_NOSE": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "drop_chance_multiplier": 1.25
      }
    },
    "active": true
  },
  "TYCOON": {
    "handler": "economy",
    "params": {
      "handler": "economy",
      "condition": "gold_above",
      "value": 10000,
      "effects": {
        "drop_chance_multiplier": 1.5,
        "damage_multiplier": 1.15
      }
    },
    "active": true
  }
}
```

</details>

## 11. Мета / инвентарь (`meta_inventory`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ACROBAT | Акробатка | easy | yes | meta_scale | Ловкость ОВ 40+ — 20% шанс крита. |
| APPRENTICE_SURGE | Рывок ученицы | easy | yes | meta_scale | Уровень ОВ 15 и ниже — урон ×1.8. |
| BRAWN_SCALING | Сила в числах | easy | yes | meta_scale | +4% урона за каждые 10 силы ОВ, до 10 стаков. |
| FORTUNE_FAVORED | Любимица фортуны | easy | yes | meta_scale | Удача ОВ 40+ — дроп ×1.4 и 10% шанс крита. |
| FULL_REGALIA | Полные регалии | easy | yes | meta_scale | 4+ легендарки — урон ×1.6 и дроп ×1.3. |
| GROWTH_SPURT | Скачок роста | easy | yes | meta_scale | +5% урона за каждые 5 уровней ОВ, до 10 стаков. |
| JACKPOT_SENSE | Чутьё джекпота | easy | yes | meta_scale | Удача ОВ 60+ — 25% шанс крита, крит-урон ×1.5. |
| LEGION_OF_LEGENDS | Легион легенд | easy | yes | meta_scale | +8% урона за каждую экипированную легендарку, до 6. |
| LEVEL_RESONANCE | Резонанс уровней | easy | yes | meta_scale | Уровень ОВ 30+ — крит-урон ×1.6. |
| LONE_LEGEND | Одинокая легенда | easy | yes | meta_scale | Единственная экипированная легендарка — урон ×1.4. |
| MUSCLE_MEMORY | Мышечная память | easy | yes | meta_scale | Сила ОВ 40+ — урон +25%. |
| NIMBLE_SCALING | Проворство | easy | yes | meta_scale | +4% урона за каждые 10 ловкости ОВ, до 10 стаков. |
| ROOKIE_NERVE | Дерзость новичка | easy | yes | meta_scale | Уровень ОВ 10 и ниже — урон ×2.2 и дроп ×1.5. |
| SCHOLAR | Учёная | easy | yes | meta_scale | Интеллект ОВ 40+ — +25% урона, игнорирует аффиксы. |
| TRINITY | Триединство | easy | yes | meta_scale | Ровно 3 легендарки — урон ×1.45. |
| TWIN_SOULS | Парные души | easy | yes | meta_scale | 2+ легендарки — урон +25%. |
| VETERAN_EDGE | Грань ветерана | easy | yes | meta_scale | Уровень ОВ 40+ — урон +30%. |
| WIT_SCALING | Острый ум | easy | yes | meta_scale | +4% урона за каждые 10 интеллекта ОВ, до 10 стаков. |

<details><summary>params JSON</summary>

```json
{
  "ACROBAT": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "agility",
      "mode": "above",
      "value": 40,
      "effects": {
        "force_crit_chance": 0.2
      }
    },
    "active": true
  },
  "APPRENTICE_SURGE": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "waifu_level",
      "mode": "below",
      "value": 15,
      "effects": {
        "damage_multiplier": 1.8
      }
    },
    "active": true
  },
  "BRAWN_SCALING": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "strength",
      "mode": "per_points",
      "per_n": 10,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.04
      }
    },
    "active": true
  },
  "FORTUNE_FAVORED": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "luck",
      "mode": "above",
      "value": 40,
      "effects": {
        "drop_chance_multiplier": 1.4,
        "force_crit_chance": 0.1
      }
    },
    "active": true
  },
  "FULL_REGALIA": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "legendary_count",
      "mode": "at_least",
      "value": 4,
      "effects": {
        "damage_multiplier": 1.6,
        "drop_chance_multiplier": 1.3
      }
    },
    "active": true
  },
  "GROWTH_SPURT": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "waifu_level",
      "mode": "per_n_levels",
      "per_n": 5,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.05
      }
    },
    "active": true
  },
  "JACKPOT_SENSE": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "luck",
      "mode": "above",
      "value": 60,
      "effects": {
        "force_crit_chance": 0.25,
        "crit_damage_multiplier": 1.5
      }
    },
    "active": true
  },
  "LEGION_OF_LEGENDS": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "legendary_count",
      "mode": "per_item",
      "max_stacks": 6,
      "effects": {
        "damage_bonus": 0.08
      }
    },
    "active": true
  },
  "LEVEL_RESONANCE": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "waifu_level",
      "mode": "above",
      "value": 30,
      "effects": {
        "crit_damage_multiplier": 1.6
      }
    },
    "active": true
  },
  "LONE_LEGEND": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "legendary_count",
      "mode": "equals",
      "value": 1,
      "effects": {
        "damage_multiplier": 1.4
      }
    },
    "active": true
  },
  "MUSCLE_MEMORY": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "strength",
      "mode": "above",
      "value": 40,
      "effects": {
        "damage_multiplier": 1.25
      }
    },
    "active": true
  },
  "NIMBLE_SCALING": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "agility",
      "mode": "per_points",
      "per_n": 10,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.04
      }
    },
    "active": true
  },
  "ROOKIE_NERVE": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "waifu_level",
      "mode": "below",
      "value": 10,
      "effects": {
        "damage_multiplier": 2.2,
        "drop_chance_multiplier": 1.5
      }
    },
    "active": true
  },
  "SCHOLAR": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "intelligence",
      "mode": "above",
      "value": 40,
      "effects": {
        "damage_multiplier": 1.25,
        "ignore_monster_affixes": true
      }
    },
    "active": true
  },
  "TRINITY": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "legendary_count",
      "mode": "equals",
      "value": 3,
      "effects": {
        "damage_multiplier": 1.45
      }
    },
    "active": true
  },
  "TWIN_SOULS": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "legendary_count",
      "mode": "at_least",
      "value": 2,
      "effects": {
        "damage_multiplier": 1.25
      }
    },
    "active": true
  },
  "VETERAN_EDGE": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "waifu_level",
      "mode": "above",
      "value": 40,
      "effects": {
        "damage_multiplier": 1.3
      }
    },
    "active": true
  },
  "WIT_SCALING": {
    "handler": "meta_scale",
    "params": {
      "handler": "meta_scale",
      "source": "stat",
      "stat": "intelligence",
      "mode": "per_points",
      "per_n": 10,
      "max_stacks": 10,
      "effects": {
        "damage_bonus": 0.04
      }
    },
    "active": true
  }
}
```

</details>

## 12. Экзотика / жёсткие условия (`exotic`)

| bonus_key | name | complexity | active | handler | description |
|-----------|------|------------|--------|---------|-------------|
| ANCHOR_STRIKE | Якорный удар | medium | yes | passive | Вместо удара — три волны по 45% урона. |
| BERSERKER_TRANCE | Транс берсерка | medium | yes | tempo | Серия быстрых (<5 с) сообщений: +20% за стак, до 5. |
| BLACK_CAT | Чёрная кошка | easy | yes | counter | 13-е сообщение боя: ×4 урона и снятие дебаффов. |
| CASINO_ROYALE | Казино «Рояль» | medium | yes | random_proc | Каждый удар: 10% ×0, 60% ×1, 25% ×2, 5% ×5. |
| CHAOS_DICE | Кость хаоса | easy | yes | random_proc | Урон каждого удара умножается на случайное число от 0.5 до 3. |
| COIN_OF_FATE | Монета судьбы | easy | yes | random_proc | Каждый удар: 50% ×0.5 или 50% ×2. |
| CURSED_BLESSING | Проклятое благословение | easy | yes | passive | Урон ×2.2, но золото с убийств ×0.5. |
| DEJA_VU | Дежавю | easy | yes | counter | Тип сообщения совпадает с предыдущим — 25% шанс крита. |
| DEVILS_BARGAIN | Сделка с дьяволом | easy | yes | random_proc | 30% шанс ×2.5 урона, иначе ×0.85. |
| DOUBLE_ELEVEN | Одиннадцать-одиннадцать | easy | yes | counter | Каждое 11-е сообщение наносит ×3 урона. |
| ECHO_CHAMBER | Эхо-камера | easy | yes | random_proc | 20% шанс повторить удар на 50% урона. |
| ENTROPY | Энтропия | easy | yes | random_proc | Урон умножается на случайное число от 0.3 до 4. |
| GLITCH_STRIKE | Глитч | easy | yes | random_proc | Урон умножается на случайное число 0.8–1.9, 10% шанс крита. |
| GREEDY_GAMBIT | Жадный гамбит | easy | yes | passive | Золото ×2.5, но урон ×0.7. |
| GREMLIN | Гремлин | easy | yes | random_proc | 25% шанс: монстр наносит себе 40% базового урона ОВ. |
| HIGH_ROLLER | Хайроллер | easy | yes | random_proc | Каждый удар: 50% ×3 или 50% ×0.5. |
| JACKPOT | Джекпот | easy | yes | random_proc | 1% шанс нанести ×25 урона. |
| LIFE_FEAST | Пир жизни | medium | yes | on_kill | Убийство монстра: 30% шанс восстановить 35% макс. HP. |
| MIMIC | Мимик | easy | yes | counter | Тип сообщения совпадает с предыдущим — +35% урона. |
| MIRROR_IMAGE | Отражение | easy | yes | random_proc | 15% шанс дополнительного удара на 100% урона. |
| MONSTER_WHISPERER | Заклинательница | easy | yes | monster_state | Монстры с номером, кратным 3, ранят себя на 25% базы. |
| NUMBER_OF_BEAST | Число зверя | easy | yes | counter | 66-е сообщение боя наносит ×6.6 урона. |
| OVERKILL_SPLASH | Сверхубийство | medium | yes | hp_state | Монстр ниже 15% HP: волна 50% урона по остальным. |
| PACIFIST_PARADOX | Парадокс пацифистки | easy | yes | passive | Урон ×0.5, но каждый удар лечит 25% нанесённого урона. |
| PERFECT_MINUTE | Минута в минуту | easy | yes | tempo | Интервал ровно 59–61 секунда — урон ×4. |
| PHANTOM_FINALE | Фантомный финал | medium | yes | counter | Каждое 8-е сообщение: четыре фантомных удара по 30%. |
| PRISM | Призма | medium | yes | counter | 4 разных типа медиа за бой: каждый удар задевает остальных на 15%. |
| QUANTUM_STRIKE | Квантовый удар | easy | yes | random_proc | 33% шанс: ×1.33 урона, игнорирует броню, аффиксы и уклонение. |
| RUSSIAN_ROULETTE | Рулетка | easy | yes | random_proc | 1 из 6: урон ×6. Иначе ×0.9. |
| SHADOW_CLONE | Теневой клон | easy | yes | random_proc | 8% шанс: два дополнительных удара по 70%. |
| SLOT_MACHINE | Однорукий бандит | medium | yes | random_proc | 30% ×1.5, 10% ×2.5, 3% ×7, иначе ×1. |
| STATIC_CHARGE | Статический заряд | medium | yes | tempo | Серия быстрых (<6 с) сообщений: +12% за стак, до 8. |
| VOID_TOUCH | Касание пустоты | easy | yes | random_proc | 5% шанс: монстр наносит себе 100% базового урона ОВ. |
| WILD_MAGIC | Дикая магия | medium | yes | random_proc | 20% крит, 20% доп. удар 60%, 20% +50% урона, 40% ничего. |

<details><summary>params JSON</summary>

```json
{
  "ANCHOR_STRIKE": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "replace_with_hits": [
          0.45,
          0.45,
          0.45
        ]
      }
    },
    "active": true
  },
  "BERSERKER_TRANCE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast_streak",
      "window_seconds": 5,
      "max_stacks": 5,
      "effects": {
        "damage_bonus": 0.2
      }
    },
    "active": true
  },
  "BLACK_CAT": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "n": 13,
      "effects": {
        "damage_multiplier": 4.0,
        "clear_waifu_debuffs": true,
        "notification": "🐈‍⬛ Чёрная кошка!"
      }
    },
    "active": true
  },
  "CASINO_ROYALE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.1,
          "effects": {
            "damage_multiplier": 0.0,
            "notification": "🎲 Зеро!"
          }
        },
        {
          "chance": 0.6,
          "effects": {
            "damage_multiplier": 1.0
          }
        },
        {
          "chance": 0.25,
          "effects": {
            "damage_multiplier": 2.0
          }
        },
        {
          "chance": 0.05,
          "effects": {
            "damage_multiplier": 5.0,
            "notification": "🎰 Куш ×5!"
          }
        }
      ]
    },
    "active": true
  },
  "CHAOS_DICE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "uniform": {
        "min_mult": 0.5,
        "max_mult": 3.0
      },
      "effects": {}
    },
    "active": true
  },
  "COIN_OF_FATE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 0.5
          }
        },
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 2.0
          }
        }
      ]
    },
    "active": true
  },
  "CURSED_BLESSING": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "damage_multiplier": 2.2,
        "gold_multiplier": 0.5
      }
    },
    "active": true
  },
  "DEJA_VU": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "repeat_type",
      "effects": {
        "force_crit_chance": 0.25
      }
    },
    "active": true
  },
  "DEVILS_BARGAIN": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.3,
          "effects": {
            "damage_multiplier": 2.5
          }
        },
        {
          "chance": 0.7,
          "effects": {
            "damage_multiplier": 0.85
          }
        }
      ]
    },
    "active": true
  },
  "DOUBLE_ELEVEN": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 11,
      "effects": {
        "damage_multiplier": 3.0
      }
    },
    "active": true
  },
  "ECHO_CHAMBER": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.2,
      "effects": {
        "extra_hits": [
          0.5
        ]
      }
    },
    "active": true
  },
  "ENTROPY": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "uniform": {
        "min_mult": 0.3,
        "max_mult": 4.0
      },
      "effects": {}
    },
    "active": true
  },
  "GLITCH_STRIKE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "uniform": {
        "min_mult": 0.8,
        "max_mult": 1.9
      },
      "effects": {
        "force_crit_chance": 0.1
      }
    },
    "active": true
  },
  "GREEDY_GAMBIT": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "damage_multiplier": 0.7,
        "gold_multiplier": 2.5
      }
    },
    "active": true
  },
  "GREMLIN": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.25,
      "effects": {
        "monster_self_damage_pct_base": 0.4
      }
    },
    "active": true
  },
  "HIGH_ROLLER": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 3.0
          }
        },
        {
          "chance": 0.5,
          "effects": {
            "damage_multiplier": 0.5
          }
        }
      ]
    },
    "active": true
  },
  "JACKPOT": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.01,
      "effects": {
        "damage_multiplier": 25.0,
        "notification": "💎 ДЖЕКПОТ!"
      }
    },
    "active": true
  },
  "LIFE_FEAST": {
    "handler": "on_kill",
    "params": {
      "handler": "on_kill",
      "proc_chance": 0.3,
      "effects": {
        "heal_pct_max_hp": 0.35,
        "notification": "🌿 Пир жизни!"
      }
    },
    "active": true
  },
  "MIMIC": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "repeat_type",
      "effects": {
        "damage_multiplier": 1.35
      }
    },
    "active": true
  },
  "MIRROR_IMAGE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.15,
      "effects": {
        "extra_hits": [
          1.0
        ]
      }
    },
    "active": true
  },
  "MONSTER_WHISPERER": {
    "handler": "monster_state",
    "params": {
      "handler": "monster_state",
      "condition": "id_mod",
      "mod": 3,
      "remainder": 0,
      "effects": {
        "monster_self_damage_pct_base": 0.25
      }
    },
    "active": true
  },
  "NUMBER_OF_BEAST": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "milestone",
      "n": 66,
      "effects": {
        "damage_multiplier": 6.6,
        "notification": "👹 Число зверя!"
      }
    },
    "active": true
  },
  "OVERKILL_SPLASH": {
    "handler": "hp_state",
    "params": {
      "handler": "hp_state",
      "side": "monster",
      "op": "below",
      "pct": 0.15,
      "effects": {
        "remaining_monsters_damage_multiplier": 0.5
      }
    },
    "active": true
  },
  "PACIFIST_PARADOX": {
    "handler": "passive",
    "params": {
      "handler": "passive",
      "effects": {
        "damage_multiplier": 0.5,
        "heal_pct_of_damage": 0.25
      }
    },
    "active": true
  },
  "PERFECT_MINUTE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "band",
      "min_seconds": 59,
      "max_seconds": 61,
      "effects": {
        "damage_multiplier": 4.0,
        "notification": "⏱️ Минута в минуту!"
      }
    },
    "active": true
  },
  "PHANTOM_FINALE": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "every_n",
      "n": 8,
      "effects": {
        "replace_with_hits": [
          0.3,
          0.3,
          0.3,
          0.3
        ]
      }
    },
    "active": true
  },
  "PRISM": {
    "handler": "counter",
    "params": {
      "handler": "counter",
      "mode": "unique_media",
      "n": 4,
      "effects": {
        "remaining_monsters_damage_multiplier": 0.15
      }
    },
    "active": true
  },
  "QUANTUM_STRIKE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.33,
      "effects": {
        "damage_multiplier": 1.33,
        "ignore_monster_armor": true,
        "ignore_monster_affixes": true,
        "ignore_monster_dodge": true
      }
    },
    "active": true
  },
  "RUSSIAN_ROULETTE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.1667,
          "effects": {
            "damage_multiplier": 6.0,
            "notification": "🔫 Барабан сыграл!"
          }
        },
        {
          "chance": 0.8333,
          "effects": {
            "damage_multiplier": 0.9
          }
        }
      ]
    },
    "active": true
  },
  "SHADOW_CLONE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.08,
      "effects": {
        "extra_hits": [
          0.7,
          0.7
        ],
        "notification": "👤 Теневой клон!"
      }
    },
    "active": true
  },
  "SLOT_MACHINE": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.3,
          "effects": {
            "damage_multiplier": 1.5
          }
        },
        {
          "chance": 0.1,
          "effects": {
            "damage_multiplier": 2.5
          }
        },
        {
          "chance": 0.03,
          "effects": {
            "damage_multiplier": 7.0,
            "notification": "🎰 Три семёрки!"
          }
        }
      ]
    },
    "active": true
  },
  "STATIC_CHARGE": {
    "handler": "tempo",
    "params": {
      "handler": "tempo",
      "mode": "fast_streak",
      "window_seconds": 6,
      "max_stacks": 8,
      "effects": {
        "damage_bonus": 0.12
      }
    },
    "active": true
  },
  "VOID_TOUCH": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "proc_chance": 0.05,
      "effects": {
        "monster_self_damage_pct_base": 1.0,
        "notification": "🕳️ Касание пустоты!"
      }
    },
    "active": true
  },
  "WILD_MAGIC": {
    "handler": "random_proc",
    "params": {
      "handler": "random_proc",
      "outcomes": [
        {
          "chance": 0.2,
          "effects": {
            "force_crit": true
          }
        },
        {
          "chance": 0.2,
          "effects": {
            "extra_hits": [
              0.6
            ]
          }
        },
        {
          "chance": 0.2,
          "effects": {
            "damage_multiplier": 1.5
          }
        }
      ]
    },
    "active": true
  }
}
```

</details>
