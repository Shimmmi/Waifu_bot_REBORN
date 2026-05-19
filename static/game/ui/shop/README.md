# Магазин — статика (`/static/game/ui/shop/`)

Фон сцены и портрет торговца подменяются по **текущему акту** игрока (`act` 1…5), по той же логике, что и караван (см. [../caravan/README.md](../caravan/README.md)).

## Фон

1. `/static/game/ui/shop/act-{N}/shop.background.webp`
2. `/static/game/ui/shop/bg_act{N}.webp`
3. `/static/game/ui/shop/background.webp` (общий fallback)

## Торговец

1. `/static/game/ui/shop/act-{N}/merchant.webp`
2. `/static/game/ui/shop/merchant_act{N}.webp`
3. `/static/game/ui/shop/merchant.webp` (общий fallback)

Если цепочка не дала файла, показывается эмодзи-заглушка в разметке страницы.

## Папка на диске

**`<корень проекта>/static/game/ui/shop/`** — рядом с этим README лежат общие `background.webp` и `merchant.webp`; для уникального вида по актам добавляйте `act-1` … `act-5` с файлами из цепочки выше или `bg_act1.webp` / `merchant_act1.webp` в корне `shop/`.
