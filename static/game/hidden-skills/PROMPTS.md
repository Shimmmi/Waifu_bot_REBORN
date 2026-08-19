# Промпты иконок скрытых навыков

Файлы: `webp/<skill_id>.webp`. Соотношение **1:1**. Генерация: **1024×1024**, затем WebP.

Это **реликвии-трофеи** (Morrowind-style hidden achievements), не узлы дерева пассивок и не инвентарные pixel-иконки. В зале тренировок карточка режет кадр через `object-fit: cover` (~84px) и кладёт бейдж уровня **в левый верхний угол** (`top: 6px; left: 6px`, ~22×22px).

## Стиль-библия

**Имя стиля:** anime fantasy relic medallion.

| Делать | Не делать |
|--------|-----------|
| Один центрированный артефакт / печать / эмблема | Портрет, chibi-сцена, толпа |
| Cel-shade, мягкий anime key-visual | Photoreal, 3D render, pixel art |
| Тёмный тёплый фон (как `#0f0c0a`–`#1e1814`), янтарь-блик (как `#c8922a`) | Белый/неоновый фон, UI-хром, hex-коды в кадре |
| 1–2 крупные формы, читаемые с 84px | Мелкая гравировка, коллаж из 10 объектов |
| Сюжет в центральных ~80% | Важные детали у краёв и в **левом верхнем** углу |
| Крошечный waifu-силуэт только как штамп-мотив | Персонаж на весь кадр |

Отличие от пассивок: пассивки — «символ умения героини». Скрытые навыки — «найденный реликт мира» (Вердгленд → Грань).

Вехи категории **Прогресс** должны выглядеть старше и тяжелее, чем **Активность**: больше металла, слоновой кости, трещин, меньше «милой искристости».

### Язык силуэтов (чтобы 42 диска не слиплись)

Каждый навык — **своя крупная форма**. Запрещены дубликаты:

| Форма | Кому можно | Кому нельзя |
|-------|------------|-------------|
| Закрытый щит | `stoic` | warlord, untouchable |
| Открытое C / зигзаг-молния | `speedster` | stoic |
| Солнце-диск | `early_bird` | consistent, gd_regular |
| Маска совы | `night_owl` | sticker_master |
| Хендж: столбы + пустой центр | `consistent` | gd_regular, early_bird |
| Кольцо дороги + след | `marathon` | plus_master |
| Ключ + одна арка (без лишних дверей) | `dungeon_diver` | expedition_veteran, plus_master |
| Компас со шнуром | `expedition_veteran` | dungeon_diver |
| Толстая капсула-подзорная | `photographer` | director |
| Свиток-катушка + плитка | `director` | photographer |
| Один чакрам | `gif_fighter` | photographer |
| Короткие шипы колосса | `boss_slayer` | legend |
| Ключ из печатей | `legend` | boss_slayer |
| Сапфир в когте | `elite_hunter` | enchant_apex |
| Стальная подкова-парирование | `untouchable` | perfectionist, speedster |
| Цепь из крупных звеньев | `perfectionist` | untouchable |
| Сложенный фолио | `echo_atlas` | echo_catalog |
| Реликварий осколков | `echo_catalog` | echo_atlas |
| Гора | `apex` | paragon, tree_master |
| Боковая лестница | `paragon` | abyss_walker |
| Арки вверх | `plus_master` | abyss_walker |
| Колодец вниз | `abyss_walker` | plus_master |
| Пентагон остриём вниз | `challenger` | warlord |
| Нагрудник/горжет | `warlord` | gladiator, stoic |
| Шлем | `gladiator` | warlord |
| Книга с клыком | `bestiary_lord` | codex_sage |
| Круглый кодекс снаряжения | `codex_sage` | bestiary_lord |
| Молот с душой | `enchanter_soul` | endgame_smith, enchant_apex |
| Треугольный герб из трёх инструментов | `endgame_smith` | enchanter_soul |
| Кристалл в сломанном хвостовике | `enchant_apex` | elite_hunter |
| Торк с лентой | `loyal_commander` | legend, team_player |
| Три головки оружия | `team_player` | gd_regular |
| Кватрефойл-стол анфас | `gd_regular` | consistent, merchant_friend |
| Весы на диске | `merchant_friend` | gd_regular |
| Дерево из трёх ветвей | `tree_master` | apex, paragon |

## Технические настройки

| Параметр | Значение |
|----------|----------|
| Соотношение | 1:1 |
| Размер генерации | 1024×1024 |
| Safe zone | центральные 80%; углы — только фон |
| Запретная зона | левый верх (~22×22px на карточке) — бейдж уровня |
| Модель | та же, что предметы/магазин (`OPENROUTER_MODEL_IMAGE`), без pixel-art лора |
| Hex в промпте модели | **не писать** — модели рисуют строки `#c8922a`. Цвета держать словами: dark warm brown-black, amber, dawn-gold |

### Style prefix (вставлять в начало каждого промпта)

Короткий, чтобы уникальный объект не голодал. Запреты — только в Negative.

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette.
```

### Shared negative

```
photorealistic, 3d render, pixel art, chibi clutter, extra characters, nsfw, deformed anatomy, watermark, letters, numbers, logo, text, typography, inscription, engraved writing, caption, plaque, signature, roman numerals, plus sign, currency symbols, coin face text, mint dates, compass labels, NSEW, map labels, musical notes, treble clef, brand lettering, analog clock, clock hands, sundial numerals, comic panel, speech bubble, busy background, white background, UI overlay, inventory slot frame, UI corner badge, notification badge, clock face with digits, brand logos, modern smartphone, cyberpunk HUD, human face, girl portrait, hands holding the object, blurry, artist signature, hex codes
```

Каждый промпт ниже — **готовый абзац**: prefix уже вклеен. Копировать целиком.

## Палитры категорий

Акцент — **глазурь**, не заливка всего диска. Янтарный ободок остаётся склейкой серии.

| Категория | Акцент (не ломая янтарь UI) |
|-----------|-----------------------------|
| Активность | рассветное золото, воздух, бледное небо |
| Медиа | пурпур + циан только на кромке стекла/лака |
| Боевые | сталь, кармин большим пятном |
| Экономика | монетное золото, **крупный** изумруд |
| Социальные | тёплый бирюзовый ≥40% пикселей объекта |
| Особые | белое золото |
| Подземелья | туманный фиолет, стекло осколков |
| Прогресс | слоновая кость, тяжёлый янтарь, трещины, мало блёсток |

---

## Активность

### `chatterbox` — Болтун

Замысел: сила слова как оружие — печать из свитка и пера, не комикс-пузырь с буквами.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A circular bronze seal: the quill is the diameter bar of the disc, blank parchment is the disc body, one abstract ink blot as the inner fill, not shout-shaped, no glyphs, dawn-gold and pale sky accents, warm torchlight from below.
```

**Negative:** `shared negative` + `shout lines, comic glyphs, written ink, alphabet, speech bubble, keyboard, chat UI`

**Do not:** буквы, «lol», облачко комикса.

---

### `early_bird` — Ранняя пташка

Замысел: первый свет над Туманным краем, не петух и не часы 6:00.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One large round sun-disc filling most of the inner 80 percent, a single dark pine-ridge band across the lower third of that disc, one stylized light-feather as a broad horizontal vane lying on the pine-ridge, not a lightning slash, not a bird, not a rooster, not extra wings, dawn-disc not a divine star, no corona filling the square, pale gold and cold morning blue.
```

**Negative:** `shared negative` + `rooster, analog clock, clock hands, digital time, alarm, 6:00, extra wings, full bird`

**Do not:** петух на весь кадр; циферблат; стая крыльев.

---

### `marathon` — Марафонец

Замысел: бесконечная дорога свёрнута в кольцо — выносливость, не кроссовки.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One smooth worn-stone road-ring as the whole medallion, a single huge simplified boot-sole (heel and toe-pad) filling the ring's hole as the inner silhouette, dawn-gold dust, no cobble noise, no runner figure, no snake head, no lantern.
```

**Negative:** `shared negative` + `sportswear, nike swoosh, stopwatch, running athlete, ouroboros snake head, lantern`

**Do not:** спортивный марафон; фитнес-браслет; змея; фонарь круга (`gd_regular`).

---

### `night_owl` — Ночная сова

Замысел: лунная сова как геральдический тотем ночной охоты.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A silver-indigo heraldic round owl-mask medallion without pointed ears, stylized hunting-slit eyes of dark glass (not round glowing orbs, not a human face), a crescent moon inlaid in the brow only, no full bird body, night-gold flecks, cool moonlight mixed with amber rim.
```

**Negative:** `shared negative` + `cute sticker owl, neon kawaii eyes, harry potter glasses, human face`

**Do not:** мультяшная сова-стикер; неоновые глаза; очки.

---

### `consistent` — Постоянство

Замысел: календарь как каменный круг дней, без цифр и сетки Excel.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A bronze ring-relic whose silhouette is a stone henge: six or seven tall unmarked standing-stones as separate thick pillars standing on the ring with a clearly empty dark center, not pie-wedges, not sun-rays, not a filled glowing disc, dawn-gold only as worn lichen on the stone faces, no gnomon, no clock hands, no numerals, not a table, not a lantern, not seat-knobs.
```

**Negative:** `shared negative` + `sundial, clock, roman numerals, calendar grid, the digit 7, round table, camp lantern, sunburst, sun disc, pie chart, filled glowing pie`

**Do not:** календарный лист с числами; циферблат; солнечный диск (`early_bird`); стол круга (`gd_regular`).

---

### `speedster` — Молния

Замысел: один мгновенный удар. Не путать со Стоиком (закрытый щит).

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A bronze coin-medallion hollowed into an open C-shaped speed-ring (one quadrant missing), a fat zigzag bolt inlaid in bronze enamel across the gap as part of the coin, pale gold not electric-white glow, not a VFX beam, first-strike, speed as an open ring plus an enamel slash, not a closed shield, not a halo, not Zeus, not a steel horseshoe.
```

**Negative:** `shared negative` + `heavy shield, thick armor, storm god, hairline scratch, closed ring, VFX beam, steel horseshoe`

**Do not:** щит; тонкая царапина; Зевс; подкова-парирование (`untouchable`).

---

### `stoic` — Стоик

Замысел: долгий бой — тяжёлый щит-бастион. Не путать с Молнией и с нагрудником warlord.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A battered round tower-shield medallion with a dominant dawn-gold face, iron only as a dented rim, a short horizontal bar-slot on a flat dawn-gold disc, shield stays a flat round tower-shield not a 3D helm, not a gorget, heavy endurance silhouette, activity-endurance not a warlord breastplate, not a lightning C-ring.
```

**Negative:** `shared negative` + `lightning bolt, thin rapier, sprint, paperdoll armor, gorget`

**Do not:** молния; нагрудник экипировки (`warlord`).

---

## Медиа

Все пять — разные носители и разные силуэты. Не камера у всех подряд. Пурпур-циан — кромка, не заливка.

### `sticker_master` — Стикермастер

Замысел: маска-печать, как наклейка-талисман, не логотип мессенджера.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A cracked lacquered theatrical fox-mask wax seal as one round disc (Verdglend fox-spirit seal, not chibi, not Noh theater), two huge ear-shapes, the sticker-peel as a thick lifted lip covering a third of the rim, not a hairline, magenta-cyan glaze on bronze only, no brand logos.
```

**Negative:** `shared negative` + `telegram logo, LINE logo, WhatsApp, emoji grid, vinyl sticker sheet, kawaii chibi fox`

**Do not:** логотип Telegram; сетка эмодзи; милая наклейка.

---

### `photographer` — Фотограф

Замысел: зачарованный объектив как подзорная труба. Не круглое «стеклянное око» режиссёра.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One stubby brass spyglass as a fat horizontal capsule filling the inner 80 percent, barrel as thick as half the disc height, length no longer than the disc, never a skinny tube, never a face-on lens disc filling the frame, a small objective-cap of glass with only one simple dark pine-ridge band inside, magenta-cyan only as rim-flare, unmarked barrel, no camera body, no shutter button, no modern DSLR, no round glass eye.
```

**Negative:** `shared negative` + `DSLR, smartphone, polaroid frame, instagram, mm marks, brand on lens, face-on lens disc, film reel, skinny telescope, landscape painting inside glass`

**Do not:** зеркалка; смартфон; круглая линза анфас (`director`); тонкая труба.

---

### `audiophile` — Меломан

Замысел: боевой голос — лютня-рупор, не кибер-наушники.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A war-lute whose body is a large bronze speaking-horn (one fused object), a short lute-neck as a single bar, two or three thick concentric sound rings, magenta-cyan metal sheen, medieval, not consumer audio gear, no notes.
```

**Negative:** `shared negative` + `headphones, earbuds, DJ mixer, equalizer bars, musical notes, treble clef, G-clef, sheet music`

**Do not:** AirPods; диджейский пульт; нотный стан.

---

### `director` — Режиссёр

Замысел: свиток видения, не хлопушка и не круглая линза фотографа.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A coiled silvered memory-ribbon (vision-scroll, not celluloid) wrapped around a dark rectangular viewing-slate showing foggy Threshold ruins as a simple mass, sprocket-like empty dots with no letters, cinematic magenta-cyan rim light, silhouette is coil plus tablet, not a round lens, no clapperboard, no countdown leader.
```

**Negative:** `shared negative` + `clapperboard, Hollywood, ACTION letters, Kodak, 35mm, film countdown, runes, face-on camera lens, spyglass`

**Do not:** хлопушка; слово ACTION; круглая линза (`photographer`).

---

### `gif_fighter` — Анимист

Замысел: зацикленное движение как один чакрам с ореолом. Не логотип GIF.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One bronze chakram frozen mid-spin filling the inner 80 percent, two thick cyan-magenta enamel rims inlaid in the chakram, not motion blur, not a third disc, looped-time relic, no file-format mark.
```

**Negative:** `shared negative` + `GIF letters, 88x31, Compuserve, bouncing internet meme, three overlapping discs, camera lens, motion blur`

**Do not:** надпись GIF; мем-лягушка; три полных диска; motion blur.

---

## Боевые

### `executioner` — Каратель

Замысел: добивающий удар — клинок на наковальне казни, не груда трупов.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Round anvil-disc filling the frame, a short heavy finishing-blade as a vertical centerline, one large crimson spark at the contact point in the center, steel and carmine, solemn not gory, no corpses.
```

**Negative:** `shared negative` + `gore, severed heads, blood fountain, skull pile`

**Do not:** груда черепов (это ближе к boss_slayer).

---

### `boss_slayer` — Охотник на боссов

Замысел: сломанная корона колосса. Не путать с элитой (синий камень) и легендой (ключ из печатей).

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A squat shattered iron colossus-circlet trophy pulled fully inside the inner 80 percent, three thick truncated spikes, the broken spike as a wide central snap not a tip at the frame edge, torn carmine velvet lining and cold steel, obviously broken, no blue gem, no small finishing dagger, not a white-gold key, not jewelry.
```

**Negative:** `shared negative` + `blue elite orb, small knife, cute skull sticker, photoreal crown, jewelry circlet, master key`

**Do not:** синий элит-камень; милый череп; целая корона; ключ легенды.

---

### `elite_hunter` — Охотник за элитой

Замысел: синий элитный осколок-аффикс как добыча. Единственный сильный синий в наборе.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A large round uncut sapphire elite-mark occupying most of the disc, gem stays an uncut blue lump, three thick iron hunter-talons wrapping it, talons are iron claws not an ivory tang, jagged not a cut jewel, no octagonal crystal, carmine flecks, not a royal crown, not an ivory weapon-core, not a finishing sword.
```

**Negative:** `shared negative` + `gold crown, executioner axe, rainbow gem, cut diamond jewelry, ivory tang`

**Do not:** корона босса; радужный гем; кристалл +10.

---

### `survivor` — Выживший

Замысел: треснувший минеральный амулет, ещё бьётся. Левый верх пустой.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A circular cracked carnelian heart-amulet of stone filling the inner 80 percent, both lobes fully below the top-left badge zone, ugly steel wire as two or three thick bands, inner carmine coal-glow still alive, chips missing, mineral not a cartoon heart, no full anatomy, no gore splash.
```

**Negative:** `shared negative` + `red cross, medical plus, anatomical heart, hospital, HP bar UI, valentine cartoon heart`

**Do not:** полоска HP; анатомический орган; медицинский крест.

---

### `untouchable` — Неприкасаемый

Замысел: ветер отклоняет удар — открытый разрыв. Не путать с перфекционистом (замкнутая цепь).

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A thick open horseshoe of dented parry-steel as a physical crescent-relic, ring thickness at least one-fifth of the diameter, one large carmine spear-head frozen in the gap never touching the metal, a wall-trophy you could pick up, silhouette is an open C of metal, not wind, not a ribbon of air, not a closed halo, not a chain, not a heart, not a shield, not a lightning bolt.
```

**Negative:** `shared negative` + `angel halo, heart, shield wall, closed metal ring, chain links, wind VFX, energy ribbon, motion blur, lightning bolt, air slash`

**Do not:** нимб/цепь перфекциониста; полный щит стоика; ветер-VFX; молния speedster.

---

### `dungeon_diver` — Исследователь

Замысел: картограф уникальных врат. Не компас ветерана и не высота плюса.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Two shapes only: one large dungeon-arch and one huge brass skeleton-key driven through it, the key as thick as the arch pillars, a single unmarked keyhole in the keystone, no extra doors, no nested arches, no plus signs, no rim ticks, explorer steel and carmine wax, first-discovery relic, not a compass, not stacked difficulty rings, not three climbing gates.
```

**Negative:** `shared negative` + `plus symbol, GPS, tourist map labels, N S E W, north arrow, compass rose, nested arches, stacked gates, extra doors`

**Do not:** знак «+»; Google Maps; компас экспедиции; стопка арок (`plus_master`).

---

## Экономика

### `hoarder` — Скряга

Замысел: запечатанный кошель, который не открывают.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A fat sealed leather coin-pouch as one round silhouette, two huge knots and one green-gold wax lock, anonymous blank-faced discs pressing the seams as broad lumps but none spilling, no mint marks, miserly emerald and coin-gold.
```

**Negative:** `shared negative` + `open treasure chest, raining coins, dollar sign, yen, coin lettering, mint date`

**Do not:** открытый сундук; знак $.

---

### `merchant_friend` — Завсегдатай

Замысел: печать лавки Вердгленда, не календарь GD и не надпись на вывеске.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One round wooden shop-disc filling the inner 80 percent, a single large blank balance-scale as the only symbol on the face, coin-gold and emerald, marketplace weight, no awning, no lantern, no signboard, no writing surface, not a guild table.
```

**Negative:** `shared negative` + `barcode, shopping cart, supermarket, store sign, painted letters, OPEN sign, shop name, round table`

**Do not:** тележка; штрихкод; вывеска с текстом; стол круга.

---

### `gambler` — Азартный

Замысел: запечатанный кубок судьбы, не казино-неон.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Closed mystery dice-cup as one barrel silhouette of dark wood and gold bands, a large legendary-gold slit of light on the front face (not rim sparkle), emerald felt as a small inner oval, fate not Vegas neon.
```

**Negative:** `shared negative` + `slot machine, playing cards with pips, poker chips logo, dice numerals, jackpot`

**Do not:** однорукий бандит; карты с цифрами; кости с цифрами.

---

## Социальные

### `team_player` — Командный игрок

Замысел: три клинка в одном кольце — бой отряда. Не путать с gd_regular (дни круга).

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Three large weapon-heads (sword, spear, staff) each a third of the disc, bound by one thick warm-teal ring filling at least forty percent of the object in teal, party combat relic, no calendar, no five-person crowd, teal and amber.
```

**Negative:** `shared negative` + `calendar, handshake clipart, sports jersey, round table, camp lantern`

**Do not:** календарь; рукопожатие-клипарт; стол круга.

---

### `expedition_veteran` — Ветеран экспедиций

Замысел: походный компас со следами многих дорог. Не ключ исследователя и не торк командира.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A heavy weathered expedition compass-disc with a bent needle and a knotted trail-cord wrapped around the rim as the many-roads tell, blank unlabeled rose with no cardinal letters, warm teal occupying at least forty percent of the compass-disc, khaki only as wear, veteran many-roads, no skeleton key, no dungeon-arch, no star-pendant, no three-weapon ring.
```

**Negative:** `shared negative` + `GPS device, army medal ribbon bar, N S E W, compass text, skeleton key`

**Do not:** современный GPS; ключ в арке (`dungeon_diver`).

---

### `loyal_commander` — Верный командир

Замысел: клятва одной наёмнице — торк, не звезда-гача и не компас.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A worn open oath-torc (fat open neck-ring) fully inside the inner 80 percent, a tiny stamped companion-mark as a hooded cloak-shape with no face, ribbon as a thick banner occupying the lower third, teal-gold, devotion to one mercenary, not a five-point star badge, not a compass, not three weapons, not a steel horseshoe.
```

**Negative:** `shared negative` + `digit 5, constellation chart, harem silhouettes, military rank pips, five-point star medal`

**Do not:** рой звёзд; несколько силуэтов; гача-медаль.

---

## Особые

### `perfectionist` — Перфекционист

Замысел: безупречная серия — целая цепь без разрыва. Не untouchable (открытый полумесяц).

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A chunky white-gold torus of six huge identical heavy links, one link glowing brighter as the vow, deathless-run relic, no hairline chain, no sparkle hail, no wind-gap, no cracked heart.
```

**Negative:** `shared negative` + `wind slash, cracked gem, five-star rating UI, open crescent, hairline chain`

**Do not:** разрыв-уклонение; звёзды рейтинга.

---

### `enchanter_soul` — Душа кузнеца

Замысел: душа в молоте для порога +5. Не путать с +10 кристаллом и тройным эндгейм-гербом.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A huge short one-handed spirit-hammer, the head filling seventy percent, short thick wooden haft fully inside the disc, glowing ember-soul in the head only, plain leather wrap with no tally marks, white-gold and forge-orange, soul of tempering, not a diamond, not three tools, not a triangular anvil-crest.
```

**Negative:** `shared negative` + `plus five, digit 5, plus sign, diamond, tongs, grindstone trio, plus-ten gem`

**Do not:** знак +5/+10; алмаз; набор из трёх инструментов.

---

### `legend` — Легенда

Замысел: мастерство скрытых навыков как ключ из чужих печатей, не корона босса и не королевский титул.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A white-gold master-key whose bow is fused from exactly three large distinct relic-seals (circle, diamond, and square plates, each big enough to read at small size), a thick key-shaft and a huge simple bit matching the bow in mass, silhouette is one key not three floating plates, hanging as one key, mastery of many hidden crafts, not a spiky royal crown, not a colossus circlet, no throne, no king portrait.
```

**Negative:** `shared negative` + `motto, latin on seals, royal king, ermine robe, trophy cup with plaque, crown inscription, shattered iron crown`

**Do not:** король на троне; кубок с табличкой; корона колосса (`boss_slayer`).

---

## Подземелья

### `echo_atlas` — Атлас эха

Замысел: карта многих побед над эхом. Не витрина уникальных осколков.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A thick folded fog-map as a rectangular folio with one corner turned back, the visible face stamped with exactly three oversized identical blank echo-gate marks clustered in the center (quantity of victories), mist-violet and shard-light, unlabeled map of hunts, silhouette is a folded packet, not a jewel-case, not a display of unique gems.
```

**Negative:** `shared negative` + `place names, numbered legend, cartographic text, GPS, museum vitrine, unique mixed gems`

**Do not:** витрина коллекции (`echo_catalog`); цифры актов.

---

### `echo_catalog` — Свидетель осколков

Замысел: каждый уникальный осколок на своём месте. Не атлас повторных побед.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A circular violet-glass reliquary holding three huge uniquely shaped shards (triangle, crescent, teardrop) plus one large empty dark socket still waiting, collection of distinct echoes, not a folded map, not stacked identical stamps.
```

**Negative:** `shared negative` + `folded map, identical stamps, pokédex UI, place names`

**Do not:** сложенный фолио-атлас; сетка покедекса.

---

## Прогресс

Тяжелее, старше, меньше «милоты». Слоновая кость + янтарь + трещины. Мало блёсток.

### `apex` — Предел формы

Замысел: вершина 60 — гора-предел формы ОВ.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A carved ivory mountain-seal as a squat triangle whose peak sits in the upper-center of the inner 80 percent, not touching the top edge, heavy amber veins like a completed growth-ring, one hard summit, thick silhouette, capstone relic, not a skill-tree, not a spiral of stairs.
```

**Negative:** `shared negative` + `60, Lv, level-up arrows, XP bar, tree of nodes, spiral stair`

**Do not:** полоска опыта; дерево навыков; лестница paragon.

---

### `paragon` — Путь совершенствования

Замысел: бесконечная лестница после потолка — не гора 60 и не колодец вниз.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Side-view of four huge ivory stair-slabs climbing toward a broken capstone-ring that sits in the upper-center of the inner 80 percent, last step fully inside the disc and below the top edge, dim amber inlays on the slabs not a peppering of gems, post-cap path, not a mountain peak, not a pit looking down, not branching skill nodes, no steps exiting the frame.
```

**Negative:** `shared negative` + `level numbers, mountain peak only, talent tree, Diablo globe, concentric well, floor numbers, steps leaving the frame`

**Do not:** только гора (`apex`); шарик парагона Diablo; колодец бездны; ступени за кадром.

---

### `plus_master` — Покоритель плюса

Замысел: высота Dungeon+ как арки вверх. Не карта уникальных данжей и не колодец вниз.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. Three nested dungeon-arches stacked vertically climbing upward, each arch thicker and slightly smaller, ivory and deep amber, a blunt stone lintel in the middle arch, never a plus-shaped bar, never a typographic plus, never a plus-shaped cutout, height of difficulty, not a compass, not a pit looking down, not concentric holes.
```

**Negative:** `shared negative` + `plus sign, typography plus, dungeon_diver compass, GPS, digit, abyss well, concentric rings receding inward`

**Do not:** типографский «+»; компас исследователя; колодец вниз (`abyss_walker`).

---

### `abyss_walker` — Ходок Бездны

Замысел: колодец без дна, смотрящий вниз. Не арки плюса вверх.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A circular abyss-well of three fat receding dark stone steps looking straight down into a black throat, a thick pale ivory lip so the hole reads on a dark card, one large amber flame hanging in the center (not on the rim), ivory crack, descent not a mountain, not climbing arches, not a calendar.
```

**Negative:** `shared negative` + `lovecraft tentacles overload, elevator UI, floor numbers, stacked climbing arches, plus_master well`

**Do not:** номера этажей; щупальца на весь кадр; арки вверх (`plus_master`).

---

### `challenger` — Испытатель

Замысел: дневная печать испытания как безмолвные клинья, не гильдейский орден warlord.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A pentagonal trial-seal with a flat edge on top and the point down (no point in the top-left), five large unmarked ivory wedges, one wedge fully lit in heavy amber, daily ordeal relic, not a gear-armor trophy, not an arena crest.
```

**Negative:** `shared negative` + `roman numerals, I V X, digit 5, medal ribbon, sports trophy, breastplate`

**Do not:** цифры I–V; кубок стадиона; нагрудник.

---

### `warlord` — Военачальник

Замысел: мощь экипировки как нагрудная пластина. Не арена наёмниц и не щит стоика.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A compact gorget-and-pectoral fragment as a wide inverted-trapezoid breastplate trophy filling the inner 80 percent, layered plates inlaid with pitted ivory and heavy amber, a few large metal rivets as simple bosses not a grid of slots, warlord of equipment, not a coliseum, not a helm, not a pentagonal daily seal, not a round tower-shield.
```

**Negative:** `shared negative` + `coliseum, rating numbers, paperdoll UI, six armor slots, digit 6, mercenary helm, round shield`

**Do not:** арена; бумажная кукла экипа; шлем гладиатора; щит стоика.

---

### `gladiator` — Гладиатор таверны

Замысел: гребень арены наёмниц. Не нагрудник warlord.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One large dented mercenary nasal-helm filling the inner 80 percent, visor as a thick sand-colored oval, a short cheap tavern plume crest kept inside the top 80 percent, a ring of sawdust-sand inlaid in the brim, ivory and amber, hired blades in the hall, not a breastplate, not the Coliseum, not a pentagon.
```

**Negative:** `shared negative` + `SPQR, latin letters, Roman coliseum photoreal, rating Elo numbers, six armor slots, gorget`

**Do not:** Колизей-фото; слоты брони ОВ; нагрудник.

---

### `bestiary_lord` — Покоритель бестиария

Замысел: книга видов, закрытая на звериной печати. Не кодекс предметов.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A closed thick bestiary as one block, a huge nameless beast-head sigil on the cover, one large fang-clasp, ivory closed pages with no writing visible, amber claw, monster-lore trophy, not an item catalog scroll, not three gear silhouettes.
```

**Negative:** `shared negative` + `pokédex screen, latin captions, sword catalog, open book text, title on cover, item names`

**Do not:** покедекс; свиток предметов (`codex_sage`).

---

### `endgame_smith` — Кузнец предела

Замысел: три инструмента эндгейма как один герб. Не душа-молот +5 и не кристалл +10.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. One triangular ivory-amber anvil-crest; three short chunky tool-heads grow from the three points (temper-needle, refine-prism, reforge-tong) as protrusions of a single object, not a pile, heavy legendary craft, not a lone spirit-hammer, not a lone diamond.
```

**Negative:** `shared negative` + `single hammer, plus-ten gem only, anvil with digits, tool pile, spirit-hammer`

**Do not:** один молот (`enchanter_soul`); один кристалл (`enchant_apex`).

---

### `enchant_apex` — Мастер +10

Замысел: потолок заточки как кристалл в старом хвостовике. Без цифры 10. Не сапфир элиты.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A fat octagonal spear-core crystal driven through a cracked ivory weapon-tang (gem is the core, ivory is the mass), old hairline cracks on the mount, ivory fire inside, fully inside the inner 80 percent, capstone of enchanting, not a claw-set sapphire, not a hammer, not three tools, no plus-sign, no numerals, no skinny diamond tips.
```

**Negative:** `shared negative` + `+10, plus ten, numeral 10, hammer, tongs, item UI stars, hunter talons, uncut sapphire`

**Do not:** надпись +10; молот кузнеца; элитный сапфир.

---

### `codex_sage` — Хранитель кодекса

Замысел: библиотека предметов — круглый кодекс шаблонов. Не бестиарий зверей.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A circular ivory item-codex medallion, the two rolled-end knobs as large as the disc radius, one vertical stack of three huge blank unlabeled stencil cutouts: sword, ring, and amulet as empty shapes, sage amber ribbon, library of gear templates, not a wide unfurled strip, not a fanged bestiary, not a beast-head cover.
```

**Negative:** `shared negative` + `animal claw, latin item names, spreadsheet, script, handwriting, fang clasp, beast sigil`

**Do not:** клык бестиария; названия предметов.

---

### `gd_regular` — Завсегдатай круга

Замысел: дневной круг похода гильдии. Не team_player (три клинка), не merchant_friend (весы) и не хендж consistent.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A flattened quatrefoil guild-table medallion seen straight-on: four huge seat-blocks as thick lobes around one large central camp-lantern boss, thick wooden ivory-amber rim, returning to the circle of days, no perspective furniture legs, no chair grid, no seven standing-stones, no three-weapon bundle, no shop scale, no calendar numerals.
```

**Negative:** `shared negative` + `clock face, weekly planner, seat numbers, crossed swords trio, storefront, henge stones, balance scale, perspective table legs, dining scene`

**Do not:** три клинка; вывеска магазина; числа дат; каменный хендж; стол в перспективе.

---

### `tree_master` — Архитектор дерева

Замысел: полностью собранное древо узлов. Не гора 60 и не спираль совершенствования.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy relic medallion, one centered artifact filling the inner 80 percent, dark warm brown-black background, soft amber rim light, empty corners, empty top-left, crisp readable silhouette. A carved ivory temple-yew as one plaque, a heavy trunk, three thick architectural branches as ribs, amber as inlaid bosses fused into the wood, exactly five huge dull amber orbs total, no sparkle hail, no connecting lines, no node graph, temple-tree relic, not a mountain, not a spiral stair, not a bestiary.
```

**Negative:** `shared negative` + `plus on nodes, node labels, talent calculator UI, oak photoreal, mountain, sparkle hail, connecting lines, skill tree graph`

**Do not:** гора apex; спираль paragon; UI калькулятора талантов; граф узлов.

---

## Чеклист перед генерацией

1. Prefix на месте, 1:1, тёмный фон, янтарь словами (без hex в строке модели).
2. Левый верх пустой. Сюжет в центральных ~80%.
3. Нет букв, цифр, логотипов, компаса NSEW, плюсов, нот.
4. Силуэт не совпадает с соседом в таблице «Язык силуэтов».
5. Прогресс выглядит тяжелее Активности (кость, трещины, меньше блёсток).
6. После генерации: кроп как `cover`, даунскейл до ~84px — силуэт всё ещё читается. Locked-карточка (`opacity: 0.45`, grayscale) тоже должна держать форму.

### Отбраковка на генерации (критик 9.5/10)

Перегенерировать этот id, не переписывать библию:

- `consistent` — заполненный диск / sunburst вместо столбов с пустым центром.
- `photographer` — круглая линза анфас вместо толстой капсулы.
- `plus_master` — типографский «+»; нужен каменный линтель.
- `tree_master` — граф узлов с линиями; нужна табличка-тис.
- `executioner` — объект лезет в бейдж; держать inner 80%.
- `speedster` / `untouchable` / `loyal_commander` — на grayscale второй мотив (эмаль / наконечник / баннер) слишком тонкий.
- `chatterbox` — чернила стали буквами; `director` — перфорация стала текстом; `loyal_commander` — лицо на штампе плаща.
