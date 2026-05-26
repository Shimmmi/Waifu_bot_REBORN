# Магазин — hero-баннеры (`/static/game/ui/shop/`)

Hero-баннер на странице магазина — **одно композитное изображение 3:2** (лавка + NPC за прилавком в одном кадре). Подменяется по **текущему акту** игрока (`act` 1…5) и **активной вкладке**.

Код: [`applyShopHeroImages`](../../../src/waifu_bot/webapp/app.js) — контейнер `aspect-ratio: 3/2`, `object-fit: cover`.

## Файлы (15 штук + fallback)

По каждому акту `N` = 1…5:

| Файл | Вкладки | Сцена |
|------|---------|-------|
| `act-{N}/merchant.webp` | Купить, Продать | Лавка + торговец за прилавком |
| `act-{N}/gambler.webp` | Gamble | Уголок барыги + барыга за столом |
| `act-{N}/blacksmith.webp` | Заточка | Кузница + кузнец у наковальни |

Общие fallback в корне `shop/`:

- `merchant.webp`
- `gambler.webp`
- `blacksmith.webp`

## Цепочка загрузки (на вкладку)

1. `/static/game/ui/shop/act-{N}/{kind}.webp`
2. `/static/game/ui/shop/{kind}_act{N}.webp`
3. `/static/game/ui/shop/{kind}.webp`

Если цепочка не дала файла — эмодзи-заглушка в разметке (`🧙` / `🎲` / `⚒`).

## Требования к ассетам

- **Соотношение:** 3:2 landscape (например 1536×1024 или 1200×800)
- **Формат:** WebP, **без alpha** (полноценный фон сцены)
- **Композиция:** NPC **за прилавком/столом/наковальней**, виден **от груди/пояса вверх**; не full body, не cutout, не прозрачный фон
- **Стиль:** anime illustration, cel shading, тёплые янтарные акценты

Промпты для генерации: [PROMPTS.md](./PROMPTS.md)

## Папка на диске

```
static/game/ui/shop/
  merchant.webp          # общий fallback
  gambler.webp
  blacksmith.webp
  act-1/
    merchant.webp
    gambler.webp
    blacksmith.webp
  act-2/ … act-5/
```

Legacy `shop.background.webp` и отдельные «портреты с alpha» **не используются** hero-баннером.
