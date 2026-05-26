# Промпты для hero-баннеров магазина (аниме, 3:2)

Одна **цельная сцена** на файл: интерьер + NPC встроены в кадр. NPC за прилавком/столом/наковальней, **upper body** (от груди/пояса), лицо читаемо. Не full body, не cutout, не transparent background.

## Общие настройки

| Параметр | Значение |
|----------|----------|
| Соотношение | **3:2 landscape** (1536×1024 или 1200×800) |
| Стиль | anime illustration, cel shading, game key visual |
| Палитра | amber `#c8922a` / `#e8b84b`, dark `#0d0a08`–`#1a1410` |
| Negative | `photorealistic, 3d render, chibi, blurry, watermark, text, logo, speech bubble, UI overlay, transparent background, cutout character, full body portrait, floating character, white background, nsfw, deformed hands, extra fingers` |

### Style prefix (начало каждого промпта)

```
Anime fantasy game shop scene, single unified illustration, cel-shaded, cinematic warm amber lighting, dark cozy atmosphere, 3:2 landscape aspect ratio, merchant behind wooden counter upper body visible, integrated environment not cutout, no text, high quality key visual
```

Замените «merchant behind wooden counter» на контекст сцены (gambler behind table, smith behind anvil и т.д.).

---

## Акт 1 — Вердгленд

### `act-1/merchant.webp`

```
[STYLE] Cozy forest-border general store interior, wooden shelves with basic swords potions leather gear, herbs and lanterns, green forest and morning mist through paned window, friendly middle-aged trader in green-brown cloak with gold trim behind wooden counter, upper body visible leaning on counter, kind smile, warm torchlight, starter-region peaceful mood, single complete scene
```

### `act-1/gambler.webp`

```
[STYLE] Hidden gambling nook inside forest trading post, dice cups sealed mystery bags on counter, sly young rogue in green hooded coat behind worn wooden table, upper body visible, mischievous grin, lucky charms, amber lantern light, forest-border mood, single complete scene
```

### `act-1/blacksmith.webp`

```
[STYLE] Small village smithy interior, stone hearth and anvil, basic weapons on rack, sturdy craftsman in leather apron behind workbench, upper body visible holding hammer, soot on arms, warm forge glow, forest-village mood, single complete scene
```

---

## Акт 2 — Каменный пояс

### `act-2/merchant.webp`

```
[STYLE] Mountain stone trading post shop carved into rock, iron racks with heavier armor, ore samples and mining lanterns, bearded mountain trader in fur-lined coat behind stone counter, upper body visible, ledger and pickaxe-shaped staff nearby, cold grey light mixed with amber braziers, rugged pass mood, single complete scene
```

### `act-2/gambler.webp`

```
[STYLE] Shady gambling corner in mountain outpost, iron dice cup locked chest with faint runes, scarred gambler in miner clothes behind metal-reinforced table, upper body visible, cunning half-smile, teal and amber accents, single complete scene
```

### `act-2/blacksmith.webp`

```
[STYLE] Mountain forge inside rock hall, massive anvil sparks flying, broad-shouldered smith in heavy leather apron behind anvil, upper body visible, iron goggles on forehead, grey stone and warm firelight, single complete scene
```

---

## Акт 3 — Пепельные степи

### `act-3/merchant.webp`

```
[STYLE] Ruined imperial trading hall used as shop, ash-grey pillars broken banners, salvaged relic gear on shelves, worn imperial remnant trader in tattered gold-embroidered coat behind cracked marble counter, upper body visible, melancholic shrewd eyes, drifting ash particles, amber candles in cold grey hall, single complete scene
```

### `act-3/gambler.webp`

```
[STYLE] Fortune-teller gambling stall in ash-steppe ruins, tarot cards and glowing dice on cloth-covered table, masked gambler in ash-grey robes with purple lining behind table, upper body visible, smoke wisps, enigmatic pose, single complete scene
```

### `act-3/blacksmith.webp`

```
[STYLE] Portable imperial armorer workshop in ash wastes, ember sparks in dusty air, refined armorer in soot-stained elegant coat behind portable anvil, upper body visible, reforging broken blade, disciplined expression, single complete scene
```

---

## Акт 4 — Мёртвые земли

### `act-4/merchant.webp`

```
[STYLE] Cursed dark emporium in Deadlands, black wood and bone-carved shelves, necrotic relics displayed, pale living trader in dark purple robes with gold clasps behind bone-inlaid counter, upper body visible, hollow polite smile, sickly green lanterns and amber ward candles, single complete scene
```

### `act-4/gambler.webp`

```
[STYLE] Sinister gambling alcove, skull dice and sealed black reliquary on table, hooded gambler with faint purple glow behind counter, upper body visible, soul wisps, trickster of dead lands mood, single complete scene
```

### `act-4/blacksmith.webp`

```
[STYLE] Necromantic forge in dead lands, anvil etched with runes, grim forge master in dark apron with bone motifs behind anvil, upper body visible, hammer wreathed in green soul-flame, stern face, single complete scene
```

---

## Акт 5 — Преддверие Грани

### `act-5/merchant.webp`

```
[STYLE] Reality-warped final-act shop at the Threshold, impossible architecture floating platforms, starfield void through windows, legendary gear on radiant displays, ancient cosmic trader in white-gold robes with void-black trim behind crystalline counter, upper body visible, calm otherworldly eyes, epic final-chapter mood, single complete scene
```

### `act-5/gambler.webp`

```
[STYLE] Cosmic gambler booth at reality edge, void dice showing galaxies sealed mystery orb on table, trickster entity in humanoid form behind counter, upper body visible, half shadow half starlight face, playful dangerous smile, amber and void palette, single complete scene
```

### `act-5/blacksmith.webp`

```
[STYLE] Celestial forge at the Threshold, divine anvil crackling amber lightning and void energy, mythic forge master in black-gold armor apron behind anvil, upper body visible, forging legendary weapon silhouette, heroic stance, single complete scene
```

---

## Чеклист после генерации

1. Экспорт **WebP**, **без alpha** (полноценный фон сцены).
2. Проверить в UI: контейнер **3:2**, NPC не обрезан по лицу.
3. Имена: `merchant.webp`, `gambler.webp`, `blacksmith.webp` в `act-1` … `act-5`.
4. Не генерировать отдельный `shop.background.webp` для hero.

## Batch-шаблон (SD / MJ / DALL·E)

```
{STYLE_PREFIX} {ACT_SPECIFIC_SCENE}, {ACT_MOOD_KEYWORDS}, 3:2 --neg {NEGATIVE}
```

Пример Midjourney для Act 1 merchant:

```
anime fantasy game shop scene, cel-shaded, amber gold accents, unified illustration, trader behind counter upper body, 3:2 --ar 3:2
Cozy forest-border general store, wooden shelves, morning mist window --no text photorealistic transparent background cutout
```
