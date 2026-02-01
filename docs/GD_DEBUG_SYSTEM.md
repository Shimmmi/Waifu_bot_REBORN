# Система отладки и тестирования GD

Реализация дополнения к ТЗ: безопасная отладка групповых подземелий только в тестовом окружении.

---

## 1. Изоляция сред

- **APP_ENV**: `production` | `testing` | `dev` | `stage`
- Команды разработчика доступны **только при APP_ENV=testing**.
- В `.env` (или `.env.testing`) задаются:
  - `POSTGRES_DSN` — тестовая БД (рекомендуется отдельная для testing).
  - `BOT_TOKEN` — тестовый бот (рекомендуется отдельный токен для testing).
  - `DEV_USER_IDS` — список Telegram user_id разработчиков (через запятую).
  - `DEV_ACCESS_LEVELS` — уровни доступа в формате `user_id:level` (например `305174198:4`).
  - `TEST_CHAT_IDS` — (опционально) список chat_id чатов, в которых разрешены команды отладки. Пусто = любой чат.

**Запуск:**
```bash
# Продакшен (APP_ENV=production или из .env)
python -m waifu_bot.cli run --env production

# Тестирование (команды отладки доступны)
python -m waifu_bot.cli run --env testing
```

---

## 2. Уровни доступа

| Уровень | Роль          | Команды |
|---------|---------------|--------|
| **L1**  | Наблюдатель   | `/gd_debug`, `/gd_logs` |
| **L2**  | Тестировщик   | L1 + `/gd_test_start`, `/gd_complete`, `/gd_skip`, `/gd_hp` |
| **L3**  | Разработчик   | L2 + `/gd_event`, `/gd_sim`, `/gd_rewards_test` |
| **L4**  | Администратор | L3 + `/gd_reset`, `/gd_env`, `/gd_snap` |

По умолчанию пользователь из `DEV_USER_IDS` без записи в `DEV_ACCESS_LEVELS` получает уровень **2**.

---

## 3. Команды

| Команда | Уровень | Описание |
|---------|---------|----------|
| `/gd_debug` | L1 | Отладочная информация о текущей GD-сессии (этап, HP, монстр, регрессии). |
| `/gd_logs [n] [filter]` | L1 | Последние n строк логов (по умолчанию 50). Фильтр: public, debug, verbose, internal. Показываются только действия текущего пользователя, если применимо. |
| `/gd_test_start [dungeon_id]` | L2 | Запуск GD в тестовом режиме (без проверок активности/кулдаунов). Опционально ID шаблона подземелья (1–5). |
| `/gd_complete` | L2 | Мгновенное завершение подземелья с расчётом и выдачей наград в ЛС. |
| `/gd_skip` | L2 | Переход к следующему этапу (или завершение, если босс). |
| `/gd_hp [1-100]` | L2 | Установить HP текущего монстра в процентах от stage_base_hp. |
| `/gd_event [type]` | L3 | Принудительно запустить событие (например `hp_50`, `boss_unique`). |
| `/gd_sim [1-50]` | L3 | Заглушка: имитация N виртуальных игроков (механика в разработке). |
| `/gd_rewards_test` | L3 | Заглушка: информация о текущей сессии (расчёт наград при /gd_complete). |
| `/gd_reset` | L4 | Сообщение о сбросе (рекомендация создать снапшот и использовать /gd_complete). |
| `/gd_env` | L4 | Вывод APP_ENV, testing_mode, количество dev_user_ids. |
| `/gd_snap list` | L4 | Список снапшотов. |
| `/gd_snap create` | L4 | Создать снапшот состояния текущей сессии. |
| `/gd_snap restore <id>` | L4 | Загрузить снапшот (восстановление состояния сессии вручную не реализовано). |
| `/gd_snap delete <id>` | L4 | Удалить снапшот. |

---

## 4. Файлы

- **core/config.py** — `DEV_USER_IDS`, `DEV_ACCESS_LEVELS`, `testing_mode`, `get_dev_access_level()`.
- **core/dev_decorators.py** — `require_testing_mode()`, `require_dev_access()`, `require_admin_chat()`.
- **services/gd_debug.py** — буфер логов (`push_gd_log`, `get_gd_logs`), `SafeLogger`, менеджер снапшотов (`snapshot_create/list/restore/delete`), `get_env_info()`.
- **services/group_dungeon.py** — `start_gd(..., dev_mode=True, template_id=...)`, `get_debug_info()`, `force_complete()`, `skip_stage()`, `set_monster_hp_percent()`, `force_trigger_event()`.
- **services/bot_handlers.py** — обработчики всех перечисленных команд с проверкой уровня доступа.
- **cli.py** — команда `run --env production|testing`.
- **tests/** — структура unit, integration, stress, fixtures; заглушки тестов.

---

## 5. Логирование

В тестовом режиме при уроне в GD, срабатывании события и завершении подземелья в буфер чата пишутся записи через `push_gd_log(chat_id, event_type, message, user_id=..., **details)`. Команда `/gd_logs` возвращает последние записи с опциональной фильтрацией по пользователю и уровню (public/debug/verbose/internal).

---

## 6. Снапшоты

Снапшоты сохраняются в каталог `snapshots/` (или в путь из `GD_SNAPSHOTS_DIR`). Формат: JSON с `timestamp`, `reason`, `session_data`. Создание — перед рискованными действиями; восстановление состояния сессии из снапшота в коде не реализовано (только загрузка данных).
