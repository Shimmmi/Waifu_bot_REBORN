# Этап 2: критерии входа (Combat / Bot / WebApp + Redis Streams)

**Для небольшого онлайна Этап 2 не стартует.** Этот документ — «ворота» перед микросервисной декомпозицией (ROADMAP_SHORT Этап 2, Roadmap Phase 5–6, Blueprint Sprint 5–6).

## Что такое Этап 2

| Компонент | Назначение |
|-----------|------------|
| Bot Service | Приём Telegram, быстрая публикация события |
| Event Bus | Redis Streams (Stage 1) → RabbitMQ/Kafka (позже) |
| Combat Service | `POST /combat/attack`, урон, spam, drops |
| WebApp API | Отдельный деплой от бота (опционально) |

Целевой поток: `Telegram → Bot → PlayerMessageEvent → Stream → Combat → PostgreSQL`.

Сейчас: всё в [`bot_handlers.group_message_damage`](../src/waifu_bot/services/bot_handlers.py) в одной сессии.

## Обязательные предпосылки (все пункты)

1. **Этап 1 infra закрыт:** PgBouncer, Redis AOF, индексы `0096`, алерты ([STAGE1_INFRA.md](STAGE1_INFRA.md)).
2. **Baseline метрики:** ≥2 недели с `PERF_METRICS_ENABLED=true` или Prometheus; задокументированы P95 handler/SQL/LLM.
3. **Workers или обоснованный отказ:** решение по [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md) (внедрили Dramatiq **или** доказали, что semaphore + locks достаточно).
4. **Event contracts:** envelope из Blueprint §6 (`event_id`, `version`, `PlayerMessageEvent` payload) — черновик в `shared/events/` до кода.
5. **Команда:** backend + DevOps на сопровождение 3+ сервисов и мониторинг Streams.

## Триггеры «можно начинать Этап 2»

Достаточно **двух** из списка, устойчиво ≥2 недели:

| # | Триггер | Ориентир |
|---|---------|----------|
| T1 | Групповой throughput | **>3–5k сообщений/час** в одном чате **или** **>10** активных групповых чатов с боем |
| T2 | Handler latency | P95 `group_message_damage_ms` **>500 ms** после Этапа 1 + in-process opts |
| T3 | Horizontal combat | Нужно **>2** реплик логики урона независимо от API |
| T4 | Failure isolation | Инциденты LLM/экспедиций роняют webhook или WebApp |

## Стоп-факторы (Этап 2 отложить)

- DAU <500, 1 VPS, нет DevOps.
- Не закрыт PgBouncer (N сервисов × pool убьёт PostgreSQL).
- Нет идемпотентности для `PlayerMessageEvent` (дубликаты Telegram update).
- Продуктово нужен dual-path GD+solo без согласованной saga.

## План миграции (кратко, Strangler Fig)

1. Ввести `PlayerMessageEvent` publish **параллельно** текущему handler (dual write).
2. Shadow consumer combat-service без ответа в чат.
3. Сравнить урон/награды с монолитом.
4. Переключить чтение состояния боя на combat API для части трафика.
5. Убрать прямой `process_message_damage` из handler.

Оценка: **6–10 недель** calendar time (не 2–4 нед. из SHORT).

## Альтернатива до полного Этапа 2

**In-monolith Event Bus** (ROADMAP_SHORT Вариант 3): один процесс, подписчики combat/guild/rewards на `asyncio` tasks. Меньше ops, часть выигрыша latency; всё равно рефакторинг `group_message_damage`.

## Связанные документы

- [OPTIMIZATION_STAGES_ANALYSIS.md](OPTIMIZATION_STAGES_ANALYSIS.md)
- [WAIFU_REBORN_IMPLEMENTATION_BLUEPRINT.md](WAIFU_REBORN_IMPLEMENTATION_BLUEPRINT.md) §6, §12 Sprint 5–6
- [WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP.md](WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP.md) Phase 5–6
