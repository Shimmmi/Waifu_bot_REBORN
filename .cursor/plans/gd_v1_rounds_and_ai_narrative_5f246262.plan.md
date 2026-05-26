---
name: GD v1 rounds and AI narrative
overview: "Исправить отсутствие срабатывания раунда по истечении 30 минут: сейчас тик привязан к глобальному sleep процесса, а не к `started_at`/дедлайну цикла. Добавить дедлайн раунда в БД, короткий poll, ручной форс раунда и расширенный промпт для ИИ; опционально — ранний commit состояния боя до вызова LLM для явного сбора следующего раунда во время генерации нарратива."
todos:
  - id: migration-deadline
    content: "Alembic: gd_cycles.round_deadline_at; модель GDCycle"
    status: completed
  - id: deadline-lifecycle
    content: Выставлять/сбрасывать round_deadline_at при старте похода и после раунда; защита от гонок
    status: completed
  - id: main-poll-loop
    content: Заменить глобальный sleep-30m на короткий poll + выбор циклов с истёкшим дедлайном
    status: completed
  - id: force-round-cmd
    content: Команда /gd_v1_force_round (test/admin) + общий хелпер обработки одного цикла
    status: completed
  - id: prompt-enrich
    content: "Расширить build_user_prompt_round / context: сырой buffer + сводка исходов"
    status: completed
  - id: commit-before-ai
    content: "Опционально: commit battle_state после process_gd_round, затем AI + send + GDRound"
    status: completed
isProject: false
---

# GD v1: дедлайн раундов, ручной запуск нарратива, промпт

## Почему «через 30 минут ничего не происходит»

Сейчас в `[src/waifu_bot/main.py](src/waifu_bot/main.py)` цикл `_gd_v1_round_loop` делает так:

1. Читает `gd_round_duration_minutes` из конфига (по умолчанию 30).
2. `**await asyncio.sleep(max(60, sleep_sec))**` — полный интервал **до** первого же вызова `[run_gd_v1_round_ticks](src/waifu_bot/services/gd_v1_worker.py)`.
3. Потом один раз обрабатывает **все** активные циклы.

То есть закрытие раунда **не привязано** к моменту старта похода и сообщения «30 минут на раунд». Оно привязано к **фазе таймера процесса** (время с последнего тика / с первого sleep после старта приложения). Игрок может ждать от 0 до ~30 минут в зависимости от того, когда стартовал uvicorn и когда сработала предыдущая итерация — это выглядит как «цикл сломан».

Дополнительно проверить в логах строки `GD v1 round tick failed` и успешность `[generate_gd_round_narrative](src/waifu_bot/services/gd_narrative_ai.py)` (при пустом `OPENROUTER_API_KEY` в чат уходит stub «Бой продолжается», а не полная тишина).

**Redis для буфера:** `[record_round_action](src/waifu_bot/services/gd_cycle_service.py)` при `redis is None` ничего не пишет; в штатном пути handlers используют `[GDCycleService(redis_core.get_redis())](src/waifu_bot/services/bot_handlers.py)` — при живом Redis буфер накапливается. Это не первичная причина «нет тика», но при падении Redis урон/медиа в GD не попадут в раунд.

```mermaid
sequenceDiagram
  participant App as FastAPI_process
  participant Loop as gd_v1_round_loop
  participant DB as Postgres_Redis
  participant AI as OpenRouter
  participant TG as Telegram
  Note over Loop: Сейчас: sleep 30m затем tick
  Loop->>DB: run_gd_v1_round_ticks
  Loop->>AI: generate_gd_round_narrative
  Loop->>TG: send_message
```



---

## Задача 1: дедлайн раунда по времени, а не глобальный sleep

**Идея:** хранить для активного цикла момент окончания сбора действий текущего раунда (`round_deadline_at` UTC). Короткий цикл опроса (например 15–30 с) выбирает циклы `status == 'active' AND round_deadline_at <= now()` и для них вызывает тот же пайплайн, что сейчас внутри `run_gd_v1_round_ticks` (pop buffer → `process_gd_round` → нарратив → persist).

**Изменения:**

1. **Миграция Alembic** — колонка на `[gd_cycles](src/waifu_bot/db/models/gd_cycle.py)`, например `round_deadline_at: DateTime(timezone=True), nullable=True`.
2. **При переходе в `active`** в `[close_registration_and_maybe_start](src/waifu_bot/services/gd_cycle_service.py)`: после выставления `started_at` и `battle_state_json` задать `round_deadline_at = now + timedelta(minutes=gd_round_duration_minutes)` (из `get_game_config_map`, как сейчас читается длительность).
3. **После успешного завершения раунда** (в `[run_gd_v1_round_ticks](src/waifu_bot/services/gd_v1_worker.py)`, если цикл не `finished`): обновить `round_deadline_at` на `now + interval` для следующего раунда.
4. **Заменить `_gd_v1_round_loop`** в `[main.py](src/waifu_bot/main.py)`: убрать один длинный sleep как единственный триггер; вместо этого `while True: sleep(15..30);` затем `SELECT` активных циклов с истёкшим дедлайном и для каждого (или батчем) вызвать обработку. Защита от двойной обработки одного цикла: атомарно «снять» дедлайн (например `UPDATE ... SET round_deadline_at = NULL WHERE id = ? AND round_deadline_at <= now()` returning rows) **или** advisory lock по `cycle_id` — нужно выбрать один простой вариант в реализации.
5. **Первый раунд:** дедлайн выставляется при старте похода — сообщение в чате про «30 минут» совпадает с логикой.

---

## Задача 2: ручной запуск «закрыть раунд и сгенерировать нарратив»

**Поведение:** команда только для доверенных пользователей (как существующие `[/gd_v1_test](src/waifu_bot/services/bot_handlers.py)_`* — расширить тем же `GD_V1_MANUAL_TEST_USER_IDS` **или** `ADMIN_IDS` из настроек; зафиксировать в коде/константе по согласованию).

- Новая команда, например `/gd_v1_force_round` в группе: для активного GD v1 в этом `chat_id` выставить `round_deadline_at = now()` (или сразу вызвать общую функцию «обработать один цикл если дедлайн прошёл»), чтобы в течение ближайшего poll сработал тот же код, что и по таймеру.
- Альтернатива без ожидания poll: вызвать из хендлера общий async-хелпер `process_due_gd_round(cycle_id)` (вынести тело из цикла `run_gd_v1_round_ticks` для одного цикла), чтобы не дублировать логику.

Поток 2.1–2.2 уже есть: старт объявления `[GD_V1_START_CHAT_MESSAGE](src/waifu_bot/game/constants.py)`, сбор в Redis через `[record_round_action](src/waifu_bot/services/gd_cycle_service.py)`, симуляция в `[process_gd_round](src/waifu_bot/services/gd_round_engine.py)`.

---

## Задача 2.3: более проработанный промпт под ИИ

Расширить контекст для LLM:

- В `[_build_ai_context](src/waifu_bot/services/gd_round_engine.py)` и/или `[build_user_prompt_round](src/waifu_bot/services/gd_narrative_ai.py)` явно включить:
  - агрегированный **сырой буфер** (`buffer["users"]`: накопленные `text_len`, список `media`, silent);
  - краткую сводку **урона/хилов** из `outcomes` (хиты, ключевые флаги), без нарушения правила «без цифр в финальном ответе» (цифры в user-промпте для модели допустимы, если system так задан).
- При необходимости поднять `max_tokens` / чуть увеличить `gd_ai_timeout_seconds` в game_config для тяжёлых раундов.

---

## Задача 2.4–2.5: сбор следующего раунда пока крутится ИИ и выкладка нарратива в чат

**Факт сейчас:** в начале тика вызывается `[pop_round_buffer](src/waifu_bot/services/gd_cycle_service.py)` — ключ Redis удаляется; пока выполняются `process_gd_round` и `generate_gd_round_narrative`, новые сообщения снова создают ключ и копятся **для следующего раунда**. То есть overlap по Redis уже частично есть.

**Но:** `cycle.battle_state_json` с увеличенным `collecting_for_round` попадает в БД только в `[session.commit()](src/waifu_bot/services/gd_v1_worker.py)` **после** нарратива и `_persist_round`. Пока commit не прошёл, другие части приложения, читающие цикл из БД, видят старое состояние (обычно на буфер это не влияет).

**Улучшение (рекомендуемое в той же задаче или отдельным коммитом):** разделить транзакцию:

1. После `process_gd_round`: сохранить в БД обновлённый `battle_state_json` и сброшенный буфер (уже сделано логически через pop), **commit**.
2. Затем вызвать `generate_gd_round_narrative` и `send_message`.
3. Вставить/обновить строку `[GDRound](src/waifu_bot/db/models/gd_cycle.py)` (например сначала без `ai_narrative`, потом update — или одна вставка после AI).

Так явно выполняется сценарий: «пока нарратив считается, следующий раунд уже собирается в Redis при актуальном состоянии боя в БД». Обработать отказ AI: раунд в БД уже продвинут — нарратив в чат = stub + лог, запись `gd_rounds` с `ai_narrative=null` при желании.

---

## Файлы затронуты (ожидаемо)

- `[src/waifu_bot/main.py](src/waifu_bot/main.py)` — poll по дедлайну.
- `[src/waifu_bot/db/models/gd_cycle.py](src/waifu_bot/db/models/gd_cycle.py)` + новая миграция Alembic.
- `[src/waifu_bot/services/gd_cycle_service.py](src/waifu_bot/services/gd_cycle_service.py)` — выставление `round_deadline_at` при старте.
- `[src/waifu_bot/services/gd_v1_worker.py](src/waifu_bot/services/gd_v1_worker.py)` — обновление дедлайна после раунда; рефактор commit/AI по желанию; вынос обработки одного цикла для force-команды.
- `[src/waifu_bot/services/bot_handlers.py](src/waifu_bot/services/bot_handlers.py)` — команда ручного форса.
- `[src/waifu_bot/services/gd_narrative_ai.py](src/waifu_bot/services/gd_narrative_ai.py)` / `[gd_round_engine.py](src/waifu_bot/services/gd_round_engine.py)` — расширенный промпт.

---

## Проверка после внедрения

- Старт тестового похода → в БД у активного цикла `round_deadline_at` ≈ now+30m.
- Через ~30 минут после старта (с допуском на шаг poll) в чат уходит нарратив (или stub при отключённом OpenRouter).
- `/gd_v1_force_round` сокращает ожидание до следующего poll или немедленно гоняет пайплайн.
- Логи: нет необработанных исключений в `run_gd_v1_round_ticks`; при необходимости добавить info-log «GD round tick cycle_id=… round=…».

