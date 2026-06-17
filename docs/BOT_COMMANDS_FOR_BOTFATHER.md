# Команды бота для BotFather

В BotFather: **Bot Settings → Edit Bot → Edit Commands** (или отправьте боту `/setcommands`).

## WebApp (меню-кнопка)

Кнопка меню с мини-приложением должна открывать **стартовый экран** игры, а не сразу профиль:

- **URL (обязательно):** `https://<ваш-домен>/webapp/index.html`
- Не указывайте корень домена (`https://<домен>/`) — Telegram откроет iframe на `/`, и при `X-Frame-Options: SAMEORIGIN` в nginx Mini App не загрузится (пустой экран, в консоли `horizontalMenu.ts` в Telegram Desktop).

Бот при старте выставляет Menu Button на `{PUBLIC_BASE_URL}/webapp/index.html` (текст кнопки: `WEBAPP_MENU_BUTTON_TEXT`, по умолчанию «Играть»). После смены домена достаточно перезапустить API.

### Проверка заголовков (production)

```bash
./scripts/verify_webapp_headers.sh https://<ваш-домен>
curl -sI https://<ваш-домен>/webapp/index.html | grep -iE 'frame|content-security'
```

Для `location /webapp/` в nginx **не** добавляйте `X-Frame-Options SAMEORIGIN` / `DENY` — иначе Linux Telegram Desktop заблокирует iframe. Вместо этого задайте CSP `frame-ancestors` (см. [infra/nginx/waifu-bot-webapp-snippet.conf](../infra/nginx/waifu-bot-webapp-snippet.conf)); на сервере правка в `/etc/nginx/sites-available/waifu-bot`, затем `sudo nginx -t && sudo systemctl reload nginx`.

С экрана «Новая игра» / «Продолжить» игрок переходит в генератор или в профиль.

---

## 1. Команды по умолчанию (для всех чатов)

Их можно задать как основной список команд (scope: default):

```
start - Приветствие и краткое описание бота
help - Справка по командам
gd_join - Записаться в еженедельный групповой поход (GD v1)
```

**GD v1**: игроки пишут `/gd_join` в группе; после старта цикла сообщения попадают в **буфер текущего раунда** (обработка тиком воркера). Классическое подземелье по сообщениям (`/gd_start`) и цепочки `/engage` отключены.

| Команда | Режим | Назначение |
|--------|--------|------------|
| `/gd_join` | группа | Регистрация в GD v1 (недельный цикл, раунды) |

---

## 2. Команды только для групп (group/supergroup)

```
gd_join - Записаться в еженедельный поход (GD v1)
```

---

## 3. Ручной тест GD v1 (не в меню BotFather)

Команды `gd_v1_test_*` доступны **только** пользователям с Telegram user id из `GD_V1_MANUAL_TEST_USER_IDS` в [game/constants.py](src/waifu_bot/game/constants.py). Для остальных бот отвечает в чат текстом отказа (не игнорирует сообщение молча).

| Команда | Описание |
|--------|----------|
| `gd_v1_test_join` | Как `/gd_join`: запись в текущий цикл регистрации GD v1 |
| `gd_v1_test_start` | Принудительно закрыть регистрацию и начать поход с ≥1 участником |
| `gd_v1_test_reset` | Удалить в чате циклы GD v1 в статусах `registration` / `active` и очистить Redis-буферы раундов |

Команды `/gd_v1_force_round`, `/gd_v1_battle_status`, `/gd_v1_admin_force_victory` (и опционально `/gd_v1_peek_round_buffer`) доступны пользователям из `GD_V1_MANUAL_TEST_USER_IDS` **или** из `ADMIN_IDS` в `.env`. При отсутствии прав бот также отвечает текстом отказа.

Типовой порядок: `gd_v1_test_join` → `gd_v1_test_start` → игра → `gd_v1_test_reset` перед новым прогоном.

Диагностика группового чата (соло-урон по тексту, GD v1, логи): [GROUP_CHAT_SOLO_AND_GD_DIAGNOSTICS.md](GROUP_CHAT_SOLO_AND_GD_DIAGNOSTICS.md).

Переменные `GD_SKIP_ACTIVITY_CHECK`, `GD_DEV_ADMIN_ANY_CHAT` в конфиге оставлены для совместимости со старыми `.env`; команды legacy-отладки GD (`/gd_debug`, `/gd_test_start` и т.д.) **удалены** из бота.

---

## Одной вставкой для BotFather (основные команды)

```
start - Приветствие
help - Справка по командам
gd_join - Еженедельный поход GD v1 (запись в цикл)
```
