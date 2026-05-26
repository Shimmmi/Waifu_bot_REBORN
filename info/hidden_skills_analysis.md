# Скрытые навыки: полный справочник (29 навыков)

Источники: [`0035_hidden_skills.py`](../alembic/versions/0035_hidden_skills.py), [`0053_story_bosses_narrative_flags.py`](../alembic/versions/0053_story_bosses_narrative_flags.py), [`hidden_skills.py`](../src/waifu_bot/services/hidden_skills.py), [`combat.py`](../src/waifu_bot/services/combat.py).

**Легенда статусов**

| Статус | Значение |
|--------|----------|
| OK | Счётчик крутится и эффект применяется |
| FX | Эффект подключён, счётчик отдельно (sync/set) |
| CT | Счётчик крутится, эффект не подключён (до фикса) |
| — | Не реализовано |

---

## Активность (7)

| id | Название | Пороги ур. 1–5 | Эффект (ур. 1→5) | Событие / счётчик | Статус |
|----|----------|----------------|------------------|-------------------|--------|
| chatterbox | Болтун | 100…10000 msg | `dmg_text_pct` 2→16% | `dungeon_message` | OK |
| early_bird | Ранняя пташка | 1…365 дней | `first_hit_per_hour_pct` 20→120% | `early_message` (после 6:00 МСК, 1/сутки) | OK |
| marathon | Марафонец | 1…60 сессий | `hp_regen_per_active_hour` 5→50 | 6 ч активности (`try_track_marathon_session`) | OK |
| night_owl | Ночная сова | 10…1000 msg | `gold_night_pct` 10→80% | `night_message` (00–04 МСК) | OK |
| consistent | Постоянство | 7…365 дней | `exp_bonus_pct` 3→40% | streak дней (`try_track_consistent_day`) | OK |
| speedster | Молния | 10…5000 fast | `first_hit_crit_pct` 5→50% | `fast_kill` (1–3 msg) | OK |
| stoic | Стоик | 10…5000 slow | `final_armor_pct` 5→50% | `slow_kill` (7+ msg) | OK |

---

## Медиа (5)

| id | Эффект | Событие | Статус |
|----|--------|---------|--------|
| sticker_master | `media_sticker_mult` ×1.0→1.7 | `sticker_hit` | OK |
| photographer | `media_photo_mult` ×1.3→2.6 | `photo_hit` | OK |
| audiophile | `media_audio_mult` ×2.2→4.5 | `audio_hit` | OK |
| director | `media_video_mult` ×2.8→6.5 | `video_hit` | OK |
| gif_fighter | `media_gif_mult` ×1.7→4.0 | `gif_hit` | OK |

---

## Боевые (6)

| id | Эффект | Счётчик | Статус |
|----|--------|---------|--------|
| executioner | `finisher_dmg_pct` 10→80% | `dungeon_kill` | OK |
| boss_slayer | `boss_reward_pct` 10→90% | `boss_kill` | OK |
| elite_hunter | `elite_drop_pct` 5→55% | `elite_kill` | OK |
| survivor | `low_hp_dmg_reduce` 8→65% | `near_death_survived` | OK |
| untouchable | `first_hits_evade_pct` 10→85% | `no_damage_dungeon_streak` (set) | OK |
| dungeon_diver | `first_clear_exp_pct` 20→150% | `unique_dungeon` | OK |

---

## Экономика (3)

| id | Эффект | Счётчик | Статус |
|----|--------|---------|--------|
| hoarder | `gold_drop_pct` 5→52% | `saving_period` (`try_hoarder_saving_streak`) | OK |
| merchant_friend | `shop_discount_pct` 2→20% | `shop_purchase` | OK |
| gambler | `gamble_legendary_pct` 1→15% | `gamble_use` | OK |

---

## Социальные (3)

| id | Эффект | Счётчик | Статус |
|----|--------|---------|--------|
| team_player | `group_dmg_pct` 5→52% | `group_message` (чат id &lt; 0) | OK |
| expedition_veteran | `expedition_reward_pct` 5→52% | `expedition_complete` | OK |
| loyal_commander | `loyal_unit_success_pct` 3→40% | `sync_loyal_commander_counter` | OK |

---

## Особые (3)

| id | Эффект | Счётчик | Статус |
|----|--------|---------|--------|
| perfectionist | `perfect_rarity_pct` 5→55% | `perfect_dungeon_streak` (set) | OK |
| enchanter_soul | `enchant_cost_pct`, `enchant_chance_pct` −5→−40% | `enchant_5plus` | OK |
| legend | `all_stats_pct` +1→+8 п.п. | `refresh_legend_counter` (др. навыки ≥3) | OK |

---

## Подземелья (2)

| id | Эффект | Событие | Статус |
|----|--------|---------|--------|
| echo_atlas | `boss_reward_pct` 1→9% | `story_boss_total_kills` | OK |
| echo_catalog | `exp_bonus_pct` 1→5% | `story_boss_unique_kills` | OK |

---

## Применение эффектов в коде

| effect_type | Файл / функция |
|-------------|----------------|
| `dmg_text_pct`, `media_*_mult`, `first_hit_per_hour_pct`, `first_hit_crit_pct`, `finisher_dmg_pct`, `group_dmg_pct` | `combat.py` → `process_message_damage` + trace |
| `all_stats_pct` | `effective_stats.stat_multipliers_from_passive_hidden` + trace `hidden_all_stats` |
| `exp_bonus_pct`, `gold_drop_pct`, `gold_night_pct` | `combat._get_waifu_armor_and_secondary`, награды |
| `boss_reward_pct`, `elite_drop_pct` | `combat._handle_run_monster_defeated` |
| `final_armor_pct`, `low_hp_dmg_reduce` | реторс монстра + `build_incoming_damage_breakdown_ru` |
| `first_hits_evade_pct` | `combat._dodge_fraction_for_retaliation` |
| `first_clear_exp_pct` | бонус опыта при первом прохождении данжа |
| `shop_discount_pct` | `passive_skills.apply_passive_buy_price` (+ hidden) |
| `gamble_legendary_pct` | `shop.gamble` → веса редкости |
| `expedition_reward_pct`, `loyal_unit_success_pct` | `expedition.py` |
| `enchant_cost_pct`, `enchant_chance_pct` | `enchanting.enchant_inventory_item` |
| `perfect_rarity_pct` | `combat` дроп + `blend_rarity_weights_with_magic_find` |
| `hp_regen_per_active_hour` | `energy.apply_regen` (опционально по player_id) |

---

## API и UI

- `GET /skills/hidden` — прогресс + `effect_types`, `effect_values`, `current_effects`, `next_effects`.
- `training_hall.html` вкладка «?» — карточки открытых навыков, клик → `#hidden-skill-modal`.

---

## Логирование боя

Исходящий урон (`damage_breakdown`): `hidden_dmg_text`, `hidden_media_mult`, `hidden_first_hit_hour`, `hidden_first_hit_crit`, `hidden_finisher`, `hidden_all_stats`, `hidden_group_dmg`.

Входящий урон: `hidden_final_armor`, `hidden_low_hp_reduce`.
