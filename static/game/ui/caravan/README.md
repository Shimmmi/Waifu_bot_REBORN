# Caravan static assets

Фон и погонщик подменяются по **текущему акту** игрока (`act` 1…5). Ищутся файлы в таком порядке:

## Фон
1. `/static/game/ui/caravan/act-{N}/caravan.background.webp`
2. `/static/game/ui/caravan/bg_act{N}.webp`
3. `/static/game/ui/caravan/caravan.background.webp` (общий fallback)

## Погонщик
1. `/static/game/ui/caravan/act-{N}/driver.webp`
2. `/static/game/ui/caravan/driver_act{N}.webp`
3. `/static/game/ui/caravan/caravan.driver.webp` (общий fallback)

## Точка на карте (иконка акта)
Используется на странице каравана поверх `caravan.background.webp`:
1. `/static/game/ui/caravan/act-{N}/map-pin.webp`
2. `/static/game/ui/caravan/pin_act{N}.webp`

Если файлов нет, показывается эмодзи акта из `ACT_META` в `app.js`.

### Позиции точек на карте
Координаты пинов заданы в процентах в `src/waifu_bot/webapp/caravan.html` (классы `.caravan-pin--1` … `.caravan-pin--5`). Подгоняйте `left` / `top` под финальный арт карты; при сильно разном фоне по актам позже можно вынести отдельные координаты на акт.

Достаточно положить общие `caravan.background.webp` и `caravan.driver.webp` — страница будет работать; для уникального вида по актам добавьте папки `act-1` … `act-5` или файлы `bg_act1.webp` / `driver_act1.webp` и т.д.

В репозитории уже созданы **заглушки WebP**: в каждой из `act-1` … `act-5` — `caravan.background.webp` и `driver.webp`, в корне этой папки — общие `caravan.background.webp` и `caravan.driver.webp` (имена совпадают с цепочкой fallback в `app.js`). Замените файлы на финальный арт без смены имён.
