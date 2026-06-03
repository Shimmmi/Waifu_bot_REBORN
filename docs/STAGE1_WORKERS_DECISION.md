# Этап 1: когда внедрять Dramatiq и отдельный LLM worker

Документ фиксирует **условный** переход с asyncio loops в монолите на очередь задач (ROADMAP_SHORT Этап 1, Roadmap Phase 3–4). **По умолчанию для малого онлайна — не внедрять**, пока не выполнены критерии ниже.

## Уже есть без Dramatiq

| Мера | Эффект |
|------|--------|
| `background_lock` | Один лидер на tick при нескольких uvicorn workers |
| LLM `Semaphore(2)` | Ограничение параллельных OpenRouter вызовов |
| Параллельные GD reward DM | `asyncio.gather` в `gd_v1_worker` |
| In-process caches | Меньше SQL на hot path |

Этого обычно достаточно при 1 VPS, сотнях DAU и редких GD/экспедициях.

## Критерии «пора на workers»

Включайте планирование Dramatiq + отдельного LLM process, если **любое** из условий держится ≥3–7 дней:

1. **P95 `group_message_damage_ms` > 500 ms** при `PERF_METRICS_ENABLED=true` (логи `perf_metric summary`).
2. **Заметные лаги бота в группе** во время `gd_v1_round` или `expedition_tick` (10–15+ с без ответов), при этом webhook не 403.
3. **>1** полноценный app-процесс (не только uvicorn workers), и фоновые тики мешают API даже с `background_lock`.
4. **OpenRouter tail latency** регулярно >10 s и совпадает с жалобами на «бот завис».

## Что выносить первым (при срабатывании)

Порядок из ROADMAP_SHORT / Roadmap Phase 3:

| Очередь / worker | Текущий loop | Риск |
|------------------|--------------|------|
| `gd_v1_round` | `background._gd_v1_round_tick` | Высокий (LLM + mass TG) |
| `expedition_tick` | `_expedition_tick_loop_fn` | Средний (LLM) |
| `expedition_notify` | `_expedition_notify_tick` | Низкий |
| `guild_war_narrative` | `_guild_war_narrative_fn` | Средний (LLM batch) |
| LLM-only process | все `post_chat_completions` | Изоляция tail latency |

**Не выносить в первую волну:** `group_message_damage` (остаётся синхронным в монолите до Этапа 2).

## Рекомендуемый стек (при решении «да»)

- **Dramatiq** + Redis broker (как в ROADMAP_SHORT Вариант 1).
- Отдельный systemd unit: `waifu-worker` (gameplay) + опционально `waifu-llm-worker`.
- Миграция: dual-run tick (loop + task) → shadow → отключить loop (Roadmap Phase 3).

## Что не делать преждевременно

- Celery «потому что в старых ТЗ» — в репо живые loops, не Celery.
- Полный LLM microservice (Blueprint Sprint 4) без очереди в монолите — сначала Dramatiq-обёртка вокруг существующих функций.

## Реализация в репозитории

| Компонент | Путь |
|-----------|------|
| Режим фона | `BACKGROUND_MODE=inline\|worker\|dual` в `.env` |
| Dramatiq actors | [`src/waifu_bot/worker/actors/`](../src/waifu_bot/worker/actors/) |
| Scheduler | `python -m waifu_bot.worker.scheduler` или `waifu-bot.cli scheduler` |
| LLM offload | `LLM_WORKER_ENABLED=true` + `llm_client.should_offload_llm` |
| systemd | [`infra/systemd/`](../infra/systemd/) |
| Docker | [`docker-compose.yml`](../docker-compose.yml), [`docs/DOCKER.md`](DOCKER.md) |

```bash
# Worker mode (prod)
BACKGROUND_MODE=worker
python -m waifu_bot.cli worker -Q default
python -m waifu_bot.cli scheduler
LLM_WORKER_ENABLED=true
python -m waifu_bot.cli worker -Q llm
```

## Связанные файлы

- Loops: [`src/waifu_bot/services/background.py`](../src/waifu_bot/services/background.py)
- Registry: [`src/waifu_bot/services/background_ticks.py`](../src/waifu_bot/services/background_ticks.py)
- LLM: [`src/waifu_bot/services/llm_client.py`](../src/waifu_bot/services/llm_client.py)
- Baseline: `PERF_METRICS_ENABLED`, [`perf_metrics.py`](../src/waifu_bot/services/perf_metrics.py)
