# Аудит легендарных бонусов (блокер перековки)

Дата: 2026-08-16. Scope: consume two-pass, midnight-strike TZ, fibonacci kill-reset.

## VIII.1 Midnight-strike

`handler_midnight_strike` нормализует naive timestamp как UTC, затем `astimezone(Europe/Moscow)`.

Окно: `local.hour == 0 and local.minute < window_minutes` (по умолчанию 5).

| UTC | MSK | Ожидание |
|---|---|---|
| 20:59:59 | 23:59:59 | нет |
| 21:00:00 | 00:00:00 | да |
| 21:04:59 | 00:04:59 | да |
| 21:05:00 | 00:05:00 | нет (`minute < 5`) |

Повторный `replace(tzinfo=MSK)` не требуется. Тесты: `tests/unit/test_legendary_endgame_audit.py`.

## VIII.2 Fibonacci

`generic_counter` mode=`fibonacci` смотрит `total_messages_in_fight` (scope fight) или session.

Reset: `LegendaryCombatBridge.on_monster_killed` → `reset_fight_level_keys`. Живые входы:

- соло / испытание: `combat.py` kill path (один `_handle_run_monster_defeated`)
- бездна: `abyss_combat.py` после смерти моба

GD не подключает `LegendaryCombatBridge` — вне скоупа.

Challenge обязан идти тем же kill-reset, что соло: `run_kind='challenge'` не ветвит `on_monster_killed`.

## VIII.3 Consume two-pass

Проблема sequential `working_state`: первый consume гасил флаг до второго хендлера.

Исправление в `run_outgoing_handlers`:

1. Заморозить `frozen_tick_state = dict(ctx_base.battle_state)`
2. Каждый хендлер получает **копию** исходного state тика
3. `consume_patch` мержится после агрегации

Тест: два бонуса с одним `flag` + `consume=true` на одном хите — оба эффекта, затем флаг `false`.

## Перековка

Пул = `roll_legendary_bonus_ids` eligibility, исключить текущий id. RAID (rarity 6) запрещён. После apply перезагрузить bridge через следующий бой (`LegendaryCombatBridge.load`). `_CANDIDATE_CACHE` не инвалидировать.
