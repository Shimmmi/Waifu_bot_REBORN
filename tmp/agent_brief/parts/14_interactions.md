14. Карта взаимодействий

14.1 Соло-атака через Telegram-сообщение

```mermaid
sequenceDiagram
    participant TG as Telegram (юзер/чат)
    participant Webhook as Aiogram Webhook
    participant Svc as CombatService
    participant LLM as LLM-клиент
    participant DB as PostgreSQL
    participant WA as Telegram WebApp (SSE)

    TG->>Webhook: Текстовое сообщение с уроном
    Webhook->>Svc: Обработать урон
    Svc->>DB: Загрузить статы персонажа
    Svc-->>Svc: Расчёт урона, проверка наград
    Svc->>DB: Сохранить результат
    Svc->>LLM: Сгенерировать нарратив битвы
    LLM-->>Svc: Текст
    Svc-->>Webhook: Результат + нарратив
    Webhook-->>TG: Ответ в чат
    Svc->>WA: SSE-событие обновления
    WA-->>WA: Обновить UI
```

Сообщение с уроном, отправленное в групповой чат или в бот, преобразуется в боевой расчёт. Система применяет формулы, сопоставляемые с `game_config`, генерирует LLM-описание и одновременно отправляет результат через Telegram и SSE-канал WebApp. Это обеспечивает синхронизацию для всех клиентов.

14.2 Экспедиция (старт, тики, LLM-повествование, сбор)

```mermaid
sequenceDiagram
    participant User as Игрок (Telegram/WebApp)
    participant API as Expedition API
    participant Worker as Expedition Worker
    participant LLM as LLM
    participant DB as PostgreSQL
    participant TG as Telegram

    User->>API: Запуск экспедиции
    API->>DB: Создать активную экспедицию
    API-->>User: Подтверждение
    loop Каждый тик (фон)
        Worker->>DB: Загрузить активные экспедиции
        Worker->>LLM: Запросить событие тика
        LLM-->>Worker: Текст события
        Worker->>DB: Обновить прогресс и записать нарратив
        Worker-->>TG: Отправить обновление в чат (если включено)
    end
    User->>API: Claim (сбор награды)
    API->>DB: Завершить экспедицию, выдать лут
    API-->>User: Награда + финальный нарратив
```

Фоновый воркер с заданным интервалом обновляет состояние всех активных экспедиций, получая нарративные вставки через LLM. Игроки наблюдают ход экспедиции в чате или в WebApp и могут прервать её досрочно или забрать итоговую награду. Детали длительности и наград настраиваются в `game_config`.

14.3 Раунд Group Dungeon v1

```mermaid
sequenceDiagram
    participant Chat as Групповой чат Telegram
    participant Buffer as Redis GD Buffer
    participant Worker as GD Round Worker
    participant LLM as LLM
    participant DB as PostgreSQL
    participant TGAPI as Telegram Bot API

    Chat->>Buffer: Сообщения за раунд
    Worker->>Buffer: Извлечь все сообщения раунда
    Worker->>DB: Получить данные цикла и участников
    Worker-->>Worker: Агрегировать урон, применить групповую механику
    Worker->>LLM: Запросить нарратив раунда
    LLM-->>Worker: Описание
    Worker->>DB: Записать итог раунда, прогресс босса
    Worker->>TGAPI: Отправить нарратив в чат
    Worker->>Buffer: Очистить буфер раунда
```

Сообщения, отправленные игроками во время активного окна GD v1, накапливаются в Redis-буфере. Специальный воркер обрабатывает буфер в конце раунда, обсчитывает совокупный урон (формулы см. `COMBAT_FORMULAS`) и формирует LLM-повествование, которое публикуется в групповом чате. Такой поток гарантирует, что ни одно сообщение не потеряется даже при высокой нагрузке.

14.4 Ежедневный рейд гильдии

```mermaid
sequenceDiagram
    participant GM as Глава/офицер гильдии
    participant Cmd as Guild Raid Command
    participant Tactic as Tactics API
    participant Resolver as Raid Resolver
    participant LLM as LLM
    participant DB as PostgreSQL
    participant Chat as Гильд-чат

    GM->>Cmd: Запустить рейд (muster)
    Cmd->>DB: Создать рейдовую сессию
    Cmd-->>GM: Призыв к сбору
    participants->>Cmd: Регистрация участников
    GM->>Tactic: Выбрать тактику
    Tactic->>DB: Сохранить выбор
    Tactic-->>GM: Подтверждение
    Cmd->>Resolver: Запустить расчёт боя
    Resolver->>DB: Загрузить статы участников и тактику
    Resolver-->>Resolver: Применить формулы рейда
    Resolver->>LLM: Сгенерировать нарратив битвы
    LLM-->>Resolver: Эпическое описание
    Resolver->>DB: Сохранить итоги, выдать награды
    Resolver->>Chat: Отправить нарратив и результаты
```

Ежедневный рейд начинается со сбора подтвердивших участие членов гильдии. Глава или офицер выбирает тактику, после чего специальный расчётчик применяет боевые формулы к агрегированным статам. LLM создаёт уникальное повествование, отражающее выбранную стратегию и общий вклад гильдии. Точные коэффициенты синхронизированы с `game_config`.

14.5 Покупка в магазине

```mermaid
sequenceDiagram
    participant User as Игрок (WebApp)
    participant API as Shop API
    participant Wallet as WalletService
    participant Inv as InventoryService
    participant DB as PostgreSQL
    participant SSE as SSE / WebApp

    User->>API: Запрос на покупку (item_id, количество)
    API->>Wallet: Проверить баланс валюты
    Wallet->>DB: Считать баланс
    DB-->>Wallet: Текущий баланс
    alt Недостаточно средств
        Wallet-->>API: Ошибка
        API-->>User: Отказ (недостаточно валюты)
    else Достаточно
        Wallet->>DB: Списать валюту
        API->>Inv: Добавить предмет в инвентарь
        Inv->>DB: Сохранить изменения
        Inv-->>API: Подтверждение добавления
        API-->>User: Успех, обновлённый инвентарь
        API->>SSE: Событие обновления профиля
    end
```

Покупка выполняется атомарно: проверка и списание валюты, выдача предмета и уведомление всех клиентов о новом состоянии инвентаря. Магазин использует те же сервисы кошелька и инвентаря, что и остальная экономика. Конкретные цены и ассортимент определяются конфигурацией магазина, но логика взаимодействия неизменна.

14.6 Загрузка профиля (WebApp → API → сервисы)

```mermaid
sequenceDiagram
    participant WA as Telegram WebApp
    participant Auth as AuthMiddleware
    participant API as Profile API
    participant ProfileSvc as ProfileService
    participant GuildSvc as GuildService
    participant DB as PostgreSQL
    participant Cache as Redis

    WA->>API: GET /profile
    API->>Auth: Проверить JWT / Telegram init data
    Auth-->>API: ID игрока
    API->>ProfileSvc: Получить профиль
    ProfileSvc->>Cache: Проверить кеш профиля
    alt Попадание в кеш
        Cache-->>ProfileSvc: Кешированные данные
    else Промах
        ProfileSvc->>DB: Запрос статов, экипировки, валют
        DB-->>ProfileSvc: Данные
        ProfileSvc->>Cache: Сохранить в кеш
    end
    ProfileSvc-->>API: Данные профиля
    API->>GuildSvc: Обогатить информацией о гильдии
    GuildSvc->>DB: Запросить гильдию
    DB-->>GuildSvc: Гильдия и звание
    GuildSvc-->>API: Гильдейский контекст
    API-->>WA: Итоговый JSON профиля
```

Профиль собирается из нескольких сервисов: основная боевая и экономическая информация кешируется в Redis, данные гильдии подгружаются отдельно. Это позволяет WebApp быстро отрисовать интерфейс, при этом гильдейская принадлежность обновляется реже и не задерживает первичную загрузку. Идентификация игрока ведётся через Telegram WebApp init data или JWT.

14.7 Целевая архитектура миграции на Steam

```mermaid
flowchart LR
    subgraph SteamClient [Steam Client / Deck]
        SC[Steam Client]
    end
    subgraph SteamPlatform [Steam Platform]
        Auth[Steam Auth]
        Leader[Steam Leaderboards]
        Stats[Steam Stats/Achievements]
        Cloud[Steam Cloud]
    end
    subgraph Backend [Game Backend (API + Worker)]
        GW[Gateway - FastAPI]
        Core[Core Game Services Python]
        DB[(PostgreSQL)]
        Cache[(Redis)]
        LLM[LLM Service]
    end
    subgraph Admin [Operators]
        Armory[Armory SPA]
        Tools[Admin Tools]
    end

    SC -->|HTTP/WS| GW
    GW --> Core
    Core --> DB
    Core --> Cache
    Core --> LLM
    Core <-->|Steamworks SDK| Auth
    Core <-->|API| Leader
    Core <-->|API| Stats
    Core <-->|Save Sync| Cloud
    Armory --> GW
    Tools --> GW
```

При миграции на Steam существующий бэкенд остаётся ядром, но обогащается слоем Steamworks-интеграции. Игровая логика, экономика и LLM-нарративы переиспользуются без изменений. Новый шлюз Steam принимает авторизацию через платформу, а достижения, лидерборды и облачные сохранения подключаются через стандартные API Steam. Это сохраняет Telegram WebApp как дополнительного клиента либо позволяет полностью переключиться на Steam.
