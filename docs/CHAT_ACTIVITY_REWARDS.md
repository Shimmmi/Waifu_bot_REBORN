# Награды за активность в групповом чате

Игрок получает **золото**, **опыт основной вайфу (ОВ)** и **сундуки на вехах** за сообщения в групповом/супергрупповом чате с ботом. Награды начисляются **параллельно** существующим механикам (GD v1, рейд гильдии, соло-бой).

## Поток данных

```mermaid
flowchart LR
  TG[Telegram message] --> GH[group_message_damage]
  GH --> CRH[try_award_chat_message]
  CRH --> RB[Redis chat_reward:buf]
  BG[background flush 60s] --> DB[(player_chat_reward_wallet)]
  WEB[profile.html claim] --> API[POST /api/chat-rewards/claim]
  API --> Player[gold + exp + items]
```

## Формула баллов

За одно засчитываемое сообщение:

```
base = media_coef + min(text_chars / chars_per_point, max_text_bonus)
points = min(points_per_msg_cap, round(base))
gold = round(points * gold_per_point * gold_mult)
exp  = round(points * exp_per_point * exp_mult)
```

### Коэффициенты медиа

| Тип | Баллы |
|-----|-------|
| TEXT, STICKER, LINK | 1 |
| PHOTO, GIF | 2 |
| VIDEO, VOICE, AUDIO | 3 |

Ключи баланса — в `game_config` (`chat_reward.*`).

## Ограничения

- Мин. длина **текста** (TEXT/LINK): `chat_reward.min_chars` (по умолчанию 3).
- Кулдаун между засчитываемыми сообщениями: `chat_reward.min_seconds_between_msgs` (8 с).
- Дневной cap баллов (UTC): `chat_reward.daily_points_cap` (600).

## Множители

1. **Статы ОВ**: УДЧ → золото (`LCK_GOLD_COEFF`), ИНТ → опыт (`INT_EXP_BONUS_COEFF`), ОБА + уникальные авторы в чате за час.
2. **Пассивки**: `sa_chatter` (`chat_gold_pct`), `sh_lurker` (`chat_exp_pct`).
3. **Гильдия**: «Светская гильдия» (`chat_reward_pct`), «Легенда гильдии» (`global_reward_pct`).
4. **Раса/класс**: таблицы в `main_waifu_base_stats.py`.

## Сундуки (вехи)

Каждые `chat_reward.chest_milestone_step` (1000) lifetime-баллов — +1 сундук в кошелёк. Редкость растёт с числом открытых сундуков.

## Как забрать

1. Откройте **Профиль** в веб-приложении.
2. Блок «Награды за чат» показывает накопленное (с учётом Redis-буфера).
3. Кнопка **«Забрать награды»** → `POST /api/chat-rewards/claim`.

Накопление из Redis сливается в БД фоновой задачей (~раз в минуту).

## API

- `GET /api/chat-rewards/status` — кошелёк, день, lifetime, множители.
- `POST /api/chat-rewards/claim` — выдача gold/exp/предметов.

## FAQ

**Считаются ли команды `/help`?** Нет — только не-командные сообщения (как в `group_message_damage`).

**Работает ли во время GD/рейда/соло?** Да, хук вызывается до веток боя.

**Почему 0 наград?** Дневной cap, кулдаун, слишком короткий текст или нет Redis (буфер не пишется).
