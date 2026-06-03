# Анализ планов оптимизации: Этап 1 (малый онлайн) и Этап 2

Сравнение [WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP_SHORT.md](WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP_SHORT.md), [WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP.md](WAIFU_REBORN_ARCHITECTURE_REFACTORING_ROADMAP.md) и [WAIFU_REBORN_IMPLEMENTATION_BLUEPRINT.md](WAIFU_REBORN_IMPLEMENTATION_BLUEPRINT.md) с текущим кодом и in-process оптимизациями.

**См. также:** [PERFORMANCE_RUNBOOK.md](PERFORMANCE_RUNBOOK.md), [STAGE1_INFRA.md](STAGE1_INFRA.md), [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md), [STAGE2_GATE.md](STAGE2_GATE.md).

---

## 1. Три разных «словаря этапов»

| Источник | «Этап 1» | «Этап 2» |
|----------|----------|----------|
| ROADMAP_SHORT (§ «Что бы я сделал») | PgBouncer, индексы PG, Dramatiq, LLM worker | Combat / Bot / WebApp + Redis Streams |
| Enterprise Roadmap | Phase 1 = Observability | Phase 2 = Infrastructure (PgBouncer) |
| Blueprint | Sprint 1–2 (obs + PgBouncer), Sprint 3–4 (workers + LLM) | Sprint 5–6 (Event Bus + Combat Service) |

**Для малого онлайна:** шкала **ROADMAP_SHORT Этап 1** + уже сделанный in-process пакет ([FIX_OPTIMISATION_ANALYSIS](FIX_OPTIMISATION_ANALYSIS.md)).

---

## 2. Общая диагностика

Узкие места (все три документа сходятся):

1. Один asyncio-процесс — webhook, WebApp, 9 фоновых петель, LLM, SSE.
2. `group_message_damage` — длинная цепочка на каждое групповое сообщение.
3. Нет task queue (только `while True` loops).
4. PostgreSQL без PgBouncer/replica при росте connection pool.

In-process оптимизации бьют в hot path; SHORT Этап 1 — в фон + PgBouncer; SHORT Этап 2 — в микросервисы и очереди.

---

## 3. Этап 1 для небольшого онлайна

### Уже в коде

- TTL `game_config`, Redis `gd_v1_active`, activity debounce, abyss guard, tavern audio `create_task`, `background_lock`, LLM semaphore(2), chat rewards 30s, SSE refetch, опционально `gd_v1_skip_group_solo_while_active`.

### Рекомендуется (ops, низкий риск)

| Задача | Документ / артефакт | Статус |
|--------|---------------------|--------|
| PgBouncer + Redis AOF | [STAGE1_INFRA.md](STAGE1_INFRA.md), `infra/` | Настроить на VPS |
| Индексы hot path | миграция `0096_performance_hot_path_indexes`, `scripts/pg_index_audit.sql` | Применить migrate |
| Baseline P95 | `PERF_METRICS_ENABLED`, [perf_metrics.py](../src/waifu_bot/services/perf_metrics.py) | Включить на 1–2 недели |
| Dramatiq + LLM worker | [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md) | Только по симптомам |

**Не делать на малом онлайне:** Dragonfly, replica, K8s, Combat Service (Этап 2).

---

## 4. Этап 2 — анализ

- Combat / Bot / WebApp отдельно + Redis Streams; заявка ×3–×10.
- Соответствует Roadmap Phase 5–6, Blueprint Sprint 5–6.
- **Цена:** 6–10 недель production-ready, saga/идемпотентность, DevOps.
- **Для малого онлайна:** не начинать; критерии входа — [STAGE2_GATE.md](STAGE2_GATE.md).
- **Компромисс:** in-monolith Event Bus (ROADMAP_SHORT Вариант 3), если Этап 1 исчерпан.

---

## 5. Порядок работ (малый онлайн)

1. [STAGE1_INFRA.md](STAGE1_INFRA.md) — PgBouncer, Redis AOF, алерты.
2. `alembic upgrade head` (индексы 0096).
3. `PERF_METRICS_ENABLED=true` на 1–2 недели, смотреть логи `perf_metric summary`.
4. При симптомах — [STAGE1_WORKERS_DECISION.md](STAGE1_WORKERS_DECISION.md).
5. Этап 2 — только при [STAGE2_GATE.md](STAGE2_GATE.md).

---

*Аналитический документ; план Cursor: `optimization_stages_analysis` (не редактировать файл плана).*
