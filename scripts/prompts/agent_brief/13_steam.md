## Задача

Напиши **§13 Steam-миграция**.

## Содержание

- Цель: PC-клиент (Electron) + локальный/облачный API
- **Сохранить без изменений:** `src/waifu_bot/game/`, services (бизнес-логика)
- **Изолировать/заменить:** aiogram handlers, Telegram WebApp auth, chat-based damage transport
- Steam replacements: keyboard/mouse input tracker, WebSocket для real-time, Steam auth вместо Telegram initData
- FastAPI как единый backend (уже есть)
- Frontend: переиспользовать webapp HTML/JS или переписать в React/Electron shell
- Что теряется без Telegram: group chat social, BotFather commands → in-game UI
- Поэтапный план миграции (фазы 0–3, концептуально)
- Риски и зависимости

## Формат

- Заголовок H2: `## 13. Steam-миграция`
- Таблица: компонент → Telegram сейчас → Steam target → сложность
- Объём: 1500–2000 слов
