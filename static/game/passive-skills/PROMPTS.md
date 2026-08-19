# Промпты иконок пассивных навыков

Файлы: `webp/<node_id>.webp`. Соотношение **1:1**. Генерация: **1024×1024**, затем WebP.

Это **эмблемы умений героини** (узлы дерева в зале тренировок), не найденные реликвии скрытых навыков и не pixel-предметы. Карточка режет кадр через `object-fit: cover`. Ячейка дерева часто **шире, чем выше** (~110×84): cover срезает верх и низ квадрата. Модалка: **88×88**. Поверх арта:

| Оверлей | CSS | Зона кадра |
|---------|-----|------------|
| Бейдж уровня | `.passive-skill-cell-lv-badge` `bottom: 6px; left: 6px` | **левый низ** |
| Кнопка прокачки `+🪙` | `.passive-cell-upgrade` `top: 6px; right: 6px` | **правый верх** (широкий чип) |
| Замок | `.passive-skill-cell-lock` `bottom: 6px; right: 6px` | **правый низ** |

Левый верх **свободен** (в отличие от скрытых навыков). Locked: `grayscale(0.25)` — тонкие ленты и прозрачный дым умрут.

Скрытые навыки в соседней вкладке — **реликт мира**. Пассивки — **stance-crest** (стойка/удар). Не второй ряд медальонов. Склейка серии: крошечная **шпилька-штамп** в металле каждого сигила (не лицо).

Старый короткий список: [`ICON_PROMPTS.md`](ICON_PROMPTS.md) — не источник генерации.

## Анализ стиля (решение)

| Набор | Язык | Почему не копировать |
|-------|------|----------------------|
| Предметы | pixel-art, `#1a1025` | Сломает соседство с аниме-залом |
| Скрытые | relic medallion | Трофей мира, не выученное умение |
| Магазин | сцены 3:2 с NPC | Не читается на 84px |
| Старый `ICON_PROMPTS.md` | pastel chibi | Пастель vs янтарь зала; `s_nth` с цифрами |

**Стиль: anime fantasy ability emblem (stance-crest).** Тир 1 легче; тир 4 — больше металла и трещин.

## Стиль-библия

| Делать | Не делать |
|--------|-----------|
| Один сигил, 1–2 крупные формы | Коллаж, толпа, chibi-сцена |
| Cel-shade, тёмный тёплый фон | Photoreal, pixel, pastel candy |
| Сюжет в вертикальной середине | Смысл в BL / TR / BR |
| Ветка: кармин / чернила-теал / сапфир | Три школы одним стальным диском |
| Stance-crest | Висячая медаль, музейная плита |

### Язык силуэтов

| Форма | Кому | Нельзя |
|-------|------|--------|
| Диагональный клинок + ударное **кольцо** | `w_bash` | w_heavy, w_wrath |
| Кираса из трёх огромных колец-дыр | `w_tough` | w_iron, w_fort, w_last |
| Прямоугольное знамя (огонь — заливка) | `w_cry` | w_imm, w_blood |
| Молот + ударное кольцо | `w_heavy` | w_bash, w_wrath |
| Широкий веер чешуек (не торс) | `w_iron` | w_tough, m_rune |
| Багровый серп + коготь | `w_blood` | w_berserk |
| Два огненных топора X | `w_berserk` | w_blood, w_wrath |
| Прямоугольный keep | `w_fort` | w_tough, w_last |
| Треснувший **kite**-щит + лепесток | `w_last` | w_imm, s_ghost |
| Вертикальный двуручник + корона-гарда | `w_wrath` | w_bash, s_crit_m |
| Сфера + короткий воротник-перо | `w_imm` | w_last, w_cry |
| Горизонтальный миндаль-глаз | `s_keen` | s_crit_m, s_media |
| Узел ветра (не слэш) | `s_nimble` | s_shadow, s_phantom |
| Шеврон из лопастей затвора | `s_media` | s_amp, m_media_m |
| Крупная 6-лучевая звезда в тонком кольце | `s_crit_m` | s_keen, w_wrath |
| Два вертикальных плаща + вертикальный зазор | `s_shadow` | s_nimble, s_phantom |
| Треснувшая маска | `s_exploit` | s_lethal |
| Три диагональных такта | `s_nth` | цифры |
| Контрастный полый доспех + искра | `s_ghost` | w_last, w_imm |
| Рупор сбоку (раструб вправо) | `s_amp` | s_media, m_surge |
| Кинжал в шипах | `s_lethal` | s_exploit |
| Тяжёлый горизонтальный разрез | `s_phantom` | s_nimble, s_shadow |
| Прямоугольный том, кольцо только как пояс | `m_arcane` | m_arch, m_wisdom |
| Открытая V-книга | `m_wisdom` | m_lore, m_arcane |
| Кошель + лента (без пера) | `m_trade` | m_bargain, sa_chatter |
| Спираль плёнки (не взрыв) | `m_media_m` | s_media, s_amp, m_surge |
| Цилиндр-свиток, корона на ленте | `m_lore` | m_wisdom, boss_slayer |
| Сжатые латные перчатки (клин, не диск) | `m_bargain` | m_trade |
| Линейная комета (не радиальный взрыв) | `m_surge` | s_amp, s_media, m_media_m |
| Пейзажная табличка + тонкий жезл | `m_cmd` | expedition_veteran, m_lore |
| Гранёный hex-купол | `m_rune` | w_iron, w_fort |
| Короткий обелиск с обручами-воротниками | `m_trans` | m_arch, paragon |
| Навершие-наконечник посоха | `m_arch` | m_arcane, m_trans |
| Горизонтальное перо сквозь низкую стопку монет | `sa_chatter` | m_trade, chatterbox |
| Треугольный капюшон-арка | `sh_lurker` | s_keen, m_wisdom |

## Технические настройки

| Параметр | Значение |
|----------|----------|
| Соотношение | 1:1 |
| Размер | 1024×1024 |
| Safe zone | внутренние четыре пятых, **вертикальная середина** (cover режет верх/низ) |
| Запретные углы | левый низ, правый верх, правый низ |
| Hex в модели | не писать |
| Слово HP / XP / digit в **Prompt** | не писать (только Negative) |

### Style prefix

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette.
```

### Shared negative

```
photorealistic, 3d render, pixel art, chibi clutter, extra characters, nsfw, deformed anatomy, watermark, letters, numbers, logo, text, typography, inscription, engraved writing, caption, plaque, signature, roman numerals, plus sign, currency symbols, coin face text, mint dates, compass labels, NSEW, map labels, percent sign, comic panel, speech bubble, busy background, white background, pastel candy background, UI overlay, inventory slot frame, HP bar, health bar, cooldown clock, analog clock, musical notes, brand logos, modern smartphone, cyberpunk HUD, full-face girl portrait, full-body character, hands holding the object, relic medallion trophy, museum artifact, hanging medal ribbon, coin-rim medallion, museum plinth, compass-rose, circular buckler pile, extra wings, neon eyes, glowing human iris, gacha badge, blurry, artist signature, hex codes
```

Каждый промпт — готовый абзац.

## Палитры веток

| Ветка | Акцент | Тир 4 |
|-------|--------|-------|
| Воин | сталь + кармин | больше массы, трещины |
| Тень | чернила + бирюза/фиолет | глубже тень |
| Мудрец | сапфир + чернильный янтарь | белое золото |

---

## Воин — тир 1

### `w_bash` — Удар — воин T1

Замысел: прямой удар клинком, не молот и не коронованная звезда.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A single thick longsword slashing top-left to bottom-center through a carmine impact-ring (circular shock, not a star), steel and warm gold edge, warrior opening strike, not a hammer, not a crown, not dual axes.
```

**Negative:** `shared negative` + `war hammer, royal crown, dual axes, shield, five-point star`

**Do not:** молот; корона; звезда гнева; слэш в правый верх.

---

### `w_tough` — Закалка — воин T1

Замысел: кираса из трёх огромных колец-дыр, не чешуя.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A cuirass-shaped crest whose chest is three huge oval mail-rings (the holes are the read), a hard shoulder-line and tapering waist, steel and rose-metal rivets, tempered kit, not overlapping fish-scales, not a scale-fan, not a round buckler, not a castle tower, not a cracked kite-shield, not a dress-skirt.
```

**Negative:** `shared negative` + `castle, lotus armor, cracked shield, petal, circular buckler`

**Do not:** круглый щит; башня; чешуя.

---

### `w_cry` — Боевой дух — воин T1

Замысел: прямоугольное знамя, огонь только как заливка ткани.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A rectangular war-standard: short pole plus a thick cross-bar, cloth as a rectangle with flame only as fill inside the flag (flag-shape first, not a free fire-plume), warm red-orange, battle spirit, not a phoenix feather, not a blood crescent, not dual axes, not a heart, not an orb.
```

**Negative:** `shared negative` + `phoenix, heart meter UI, blood moon, heart-shaped cloth, flagpole leaving the frame`

**Do not:** сердце; феникс; серп крови.

---

## Воин — тир 2

### `w_heavy` — Тяжёлый удар — воин T2

Замысел: оглушающий молот, ударное кольцо без звезды.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A massive two-handed warhammer filling the disc, one thick unmarked shock-ring at the head, heavy steel and carmine sparks, crushing blow, not a longsword, not dual axes, not a pointed star.
```

**Negative:** `shared negative` + `longsword, crown, stun icon letters, five-point star`

**Do not:** меч удара; звезда гнева.

---

### `w_iron` — Железная кожа — воин T2

Замысел: широкий веер чешуек, не торс-кираса.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A wide hand-fan of overlapping iron teardrop-scales, the fan-arc is the silhouette and wider than tall, each scale pointing outward, warm steel and carmine, iron skin, not chain-mail holes, not a cuirass of rings, not a buckler, not a castle, not a glowing rune dome, not sapphire-blue, not a dress-skirt, no lotus flower.
```

**Negative:** `shared negative` + `round shield, castle, runic circle, magic glyphs, pastel lavender, silver-blue sage glaze`

**Do not:** щит закалки; hex-купол рун; голубая глазурь мудреца.

---

### `w_blood` — Кровавая ярость — воин T2

Замысел: ярость на грани — серп и коготь, не топоры.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A blood-red crescent moon behind one thick claw-slash, dramatic crimson and black, fury at the brink, not dual flame axes, not a war-banner flame, no gore spray filling the frame.
```

**Negative:** `shared negative` + `dual axes, gore fountain, war banner, heart meter`

**Do not:** топоры берсерка; полоска HP.

---

## Воин — тир 3

### `w_berserk` — Берсерк — воин T3

Замысел: два топора пламени крестом.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. Two thick flame-axes crossed as one heavy X-silhouette, black and carmine, rage of wounds, not a single crescent, not a crowned sword, not a flame-banner, no cute anger-vein sticker.
```

**Negative:** `shared negative` + `blood moon only, royal sword, chibi anger mark`

**Do not:** серп; корона.

---

### `w_fort` — Крепость — воин T3

Замысел: прямоугольный keep, шире чем выше, без баклера.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A rectangular squat keep wider than tall, two or three blocky merlon-teeth, a small steel rivet in the center, heavy stone-steel and carmine window-slots, unbreakable wall, not a round shield that ate a castle, not chain-links, not lotus scales, not a cracked kite-shield.
```

**Negative:** `shared negative` + `chain mail pile, lotus, sakura, battlement numbers, circular buckler`

**Do not:** круглый щит; лепесток рубежа.

---

### `w_last` — Последний рубеж — воин T3

Замысел: второй шанс — kite-щит и лепесток, не феникс.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A cracked kite-shield with one large sakura petal fused along the break, silver and pale carmine, last stand, not a round buckler, not a phoenix, not a ghost outline, not a fortress-keep.
```

**Negative:** `shared negative` + `phoenix, ghost girl, digit 1, castle tower, continue prompt, 1UP, circular buckler`

**Do not:** феникс; цифра 1; круглый щит.

---

## Воин — тир 4

### `w_wrath` — Гнев героя — воин T4

Замысел: крит ближнего — корона и звезда на клинке, тяжелее T1.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A vertical greatsword (not a diagonal opening-slash) with a huge thick crown as the entire crossguard filling the middle mass, one large unmarked five-point star as a heavy plate on the blade, royal steel and deep carmine, ivory-gold weight, not a shock-ring, not a longsword slash from top-left, not a thin loupe-ring, not a six-point jewel-star, not dual axes.
```

**Negative:** `shared negative` + `simple starter sword, magnifying glass, diamond jewelry, latin motto, CRIT letters`

**Do not:** простой удар; огранка тени.

---

### `w_imm` — Бессмертный — воин T4

Замысел: жизнь с убийства — сфера с коротким воротником-пером, не штандарт.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A large cracked unmarked ember-glass orb as the mass, one short charred phoenix pinion clamped around it as a heavy collar (orb first, collar not a vertical plume), heavy gold and cinder, life stolen back, not a rectangular war-banner, not a cracked kite-shield, not a sakura petal, not a translucent ghost, not an infinity mark, no extra wings.
```

**Negative:** `shared negative` + `infinity symbol, sakura shield, ghost girl, extra wings, pair of wings`

**Do not:** лепесток на щите; значок ∞; два крыла.

---

## Тень — тир 1

### `s_keen` — Острый глаз — тень T1

Замысел: видеть удар — широкий миндаль, не круглая линза и не звезда.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A wide horizontal cat-eye almond filling the disc, one unmarked slit running left-right, teal-black and cool lace-metal, keen strike-sight, not a round iris, not a standing oval, not a cut diamond star, not a camera shutter, not a glowing human iris.
```

**Negative:** `shared negative` + `crosshair UI, camera body, diamond brilliant cut, CRIT letters, neon sclera`

**Do not:** круглая линза; звезда мастера крита; шеврон затвора.

---

### `s_nimble` — Проворство — тень T1

Замысел: узел ветра, не слэш и не двойник.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A compact round knot of two thick wind-loops as the whole silhouette, teal-violet, short afterimage only inside the knot, nimble dodge, not a diagonal opening-slash, not a split clone, not a horseshoe of steel, not a horizontal void-cut.
```

**Negative:** `shared negative` + `shadow clone pair, kunai pile, horseshoe, looping wind-ribbon filling the frame`

**Do not:** двойник; горизонтальный разрез фантома.

---

### `s_media` — Чутьё — тень T1

Замысел: медиа бьёт — шеврон лопастей, не глаз и не рупор.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A fan of three thick triangular shutter-blades as one chevron-silhouette, magenta-cyan only as rim flare, teal-black body, media strike sense, never a round lens, never a heart, never a horizontal cat-eye, never a camera brick, never a film-reel, never a loudspeaker.
```

**Negative:** `shared negative` + `DSLR, smartphone, film strip, speaker cone, GIF letters, heart-shaped lens`

**Do not:** миндаль-глаз; рупор; плёнка медиамага.

---

## Тень — тир 2

### `s_crit_m` — Мастер крита — тень T2

Замысел: вес удачи — крупная звезда, не глаз.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A large pointy six-point jewel-star dominating the disc inside a thin unmarked loupe-ring, elegant assassin teal and wine, killing-blow weight, not a cat-eye slit, not a crowned sword, not a camera iris.
```

**Negative:** `shared negative` + `cat eye, royal crown, plus sign, mm marks, CRIT letters, x2`

**Do not:** глаз keen; меч wrath.

---

### `s_shadow` — Шаг тени — тень T2

Замысел: удар в пустоту — два плотных плаща и яркий зазор.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. Two solid vertical ink-cloak slabs left and right, a bright teal vertical gap between them (cloak | gap | cloak), purple-black bodies not mist, the vertical split is the read, full vanish, not a horizontal void-cut, not a round wind-knot, not a posed girl, no extra crowd.
```

**Negative:** `shared negative` + `wind ribbons, first-hit ribbon, girl face, ninja crowd, kunoichi girl, purple mist mush`

**Do not:** узел ветра; горизонтальный фантом; лицо.

---

### `s_exploit` — Уязвимость — тень T2

Замысел: трещина в маске, не кинжал.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A cracked theatrical mask with one large unmarked weak-point chip glowing teal-green, trickster exploit, not a rose dagger, not a skull, not a gem lens.
```

**Negative:** `shared negative` + `skull candy, rose dagger, targeting reticle letters`

**Do not:** кинжал lethal; череп.

---

## Тень — тир 3

### `s_nth` — Серия смерти — тень T3

Замысел: ритм без цифр — три диагональных такта.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A triad of thick diagonal descending strike-bars of stepped brightness as one silent steel rhythm, teal-violet, death-beat, not a metronome, not a repeating-arrow UI, not a first-hit single ribbon, not vertical meter bars.
```

**Negative:** `shared negative` + `countdown numerals, 3-2-1 overlay, combo counter, hit counter, x3, film countdown, repeat arrows, equalizer bars, roman III`

**Do not:** цифры; equalizer; стрелки repeat.

---

### `s_ghost` — Призрак — тень T3

Замысел: встать после смерти — контрастный полый доспех.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A high-contrast hollow-armor outline, opaque mint-white rim and dark warm fill, one large core-spark, readable after grayscale, not translucent-on-black, not a cracked kite-shield, not a phoenix feather, not a split smoke-clone, no girl face.
```

**Negative:** `shared negative` + `sakura shield, phoenix, RIP, tombstone, girl portrait, standing ghost-girl cloak`

**Do not:** рубеж-щит; феникс; девочка-призрак.

---

### `s_amp` — Усиленное медиа — тень T3

Замысел: рупор-волна, не затвор и не вспышка мага.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A side-view bronze-violet speaking-horn, bell facing right, long cone as the silhouette, two thick shockwave rings around the bell only, amplified media, not a front-facing chevron, not a fan of shutter-blades, not a film-reel, not headphones, not a radial spell-burst, not a camera brick.
```

**Negative:** `shared negative` + `camera, film strip, headphones, DJ mixer, treble clef, GIF, equalizer bars`

**Do not:** шеврон чутьё; вспышка surge.

---

## Тень — тир 4

### `s_lethal` — Смертельный удар — тень T4

Замысел: кинжал в розе, тяжелее маски.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A rose-thorn dagger driven through a compact unmarked seal, deep wine and teal shadow, instant sentence, not a cracked mask, not a skull pile, not a first-hit void-cut, gothic but not chibi candy skull.
```

**Negative:** `shared negative` + `cracked mask, cute skull sticker, boss crown`

**Do not:** маска exploit; милый череп.

---

### `s_phantom` — Фантом — тень T4

Замысел: первый удар — тяжёлый горизонтальный разрез, не узел ветра.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A heavy horizontal opening-cut across a dark oval void, one dense silver-violet afterimage plate, T4 metal mass not a thin streamer, first-hit phantom, not a twin clone, not a round wind-knot, not three rhythm bars, not a thorn dagger.
```

**Negative:** `shared negative` + `two silhouettes, three slashes, rose dagger, wind knot, thin ribbon`

**Do not:** узел nimble; двойник shadow; тонкая лента.

---

## Мудрец — тир 1

### `m_arcane` — Аркана — мудрец T1

Замысел: прямоугольный том, кольцо только как пояс.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A thick closed book as a heavy rectangle, spine as a vertical bar, the book-brick is the silhouette, one thin unmarked ring only as a belt around the midsection, scholarly sapphire and ink-amber, magic strike, not open pages, not a V-chevron of leaves, not a grand staff, not a column of rings, not a medallion with a tiny book inside.
```

**Negative:** `shared negative` + `archmage staff, latin on pages, open ledger, camera flash, readable runes, spell text`

**Do not:** открытая книга wisdom; посох arch.

---

### `m_wisdom` — Мудрость — мудрец T1

Замысел: открытая V-книга, крупные искры.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. An open book as a wide V-chevron of two ivory pages, three large amber sparks each bigger than a corner badge, cream and ink-amber, wisdom, blank pages, not a closed tome, not a wrapping ring, not a crowned boss-scroll.
```

**Negative:** `shared negative` + `boss crown, film strip, latin, page calligraphy, XP letters, plus sign, glitter sprinkle`

**Do not:** закрытый том; свиток lore.

---

### `m_trade` — Торговец — мудрец T1

Замысел: кошель, не печать сделки и не башня монет чата.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A fat coin-purse with a gathered neck and one large ribbon as the whole silhouette, gold and mint-sapphire, merchant craft, blank-faced discs, no quill, not a handshake, not a round wax seal, not a shop awning, not a stacked coin-tower.
```

**Negative:** `shared negative` + `handshake, dollar sign, barcode, OPEN sign, shopping cart, coin tower`

**Do not:** печать bargain; башня sa_chatter.

---

## Мудрец — тир 2

### `m_media_m` — Медиамаг — мудрец T2

Замысел: плёнка и монеты за добивание, не боевой затвор.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A coiled unmarked film-ribbon as a thick spiral, the coil is the silhouette, looped around a cluster of blank gold discs, sapphire and coin-gold, media kill bounty, not bursting, not a radial explosion, not a shutter-chevron, not a speaking-horn.
```

**Negative:** `shared negative` + `camera brick, loudspeaker, ACTION, Kodak, dollar sign, sprocket captions`

**Do not:** шеврон media; рупор amp.

---

### `m_lore` — Знания — мудрец T2

Замысел: цилиндр-свиток, корона только на ленте.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A thick rolled ancient scroll as the whole cylinder-silhouette, one tiny unmarked boss-crown stamped as a seal on the ribbon only, blank parchment face, royal purple ink and sapphire, lore of trophies, not an open spark-book, not a shattered colossus circlet filling the disc.
```

**Negative:** `shared negative` + `open book sparks, photoreal crown, museum plaque, manuscript text, illuminated letters, latin`

**Do not:** книга wisdom; корона колосса hidden boss_slayer.

---

### `m_bargain` — Сделка — мудрец T2

Замысел: сжатые латные перчатки клином, не круглая печать.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. Two armored gauntlets clasped as a heavy wedge-silhouette, the clasp is the read, coral wax squeezed only at the knuckles, sapphire metal, one-sided bargain, not a circular wax medallion, not a coin-seal, not a coin purse, not a shop sign, not a heart-shaped tag.
```

**Negative:** `shared negative` + `coin purse, barcode, SALE letters, extra arms, wax alphabet, price tag digits, dollar sign, heart-shaped UI`

**Do not:** кошель; надпись SALE; сердце.

---

## Мудрец — тир 3

### `m_surge` — Магический всплеск — мудрец T3

Замысел: вспышка заклинания после слов, не камера и не рупор.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A thick cyan-amber spell-comet, a linear spear of light with a short unmarked spark-trail from one side, not a radial starburst, media after incantation, not a speaking-horn, not a shutter-chevron, not a film-coil, not a camera body, not a grimoire ring.
```

**Negative:** `shared negative` + `loudspeaker, alphabet runes, digit 3, film countdown, treble clef, FLASH letters, clapperboard, camera flash, subtitle captions`

**Do not:** рупор; цифра 3; камера.

---

### `m_cmd` — Командование — мудрец T3

Замысел: жезл и полевая табличка, не компас ветерана.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A wide rectangular field-slate as the silhouette, blank metal tablet in landscape, a short commander baton only as a thin crossing bar, khaki-gold and sapphire, field leadership, no round disc, no star-pointer, no trail-cord, not a rolled scroll, not three weapon-heads.
```

**Negative:** `shared negative` + `N S E W, GPS, medal ribbon bar, three weapons, army rank pips, compass-rose`

**Do not:** компас скрытого ветерана; три клинка.

---

### `m_rune` — Рунная броня — мудрец T3

Замысел: гранёный hex-купол, не круглая чешуя воина.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A faceted sapphire hex-dome as the whole silhouette over a fragment of geometric fauld-plate, mute incoming pain, not iron lotus scales, not a castle keep, not a round bubble, not pink-lavender candy glaze.
```

**Negative:** `shared negative` + `iron scales, fortress, latin runes, Futhark letters, shield buckler, pastel lavender armor`

**Do not:** железная кожа; крепость; буквы рун.

---

## Мудрец — тир 4

### `m_trans` — Трансцендентность — мудрец T4

Замысел: колонна колец пробуждения, не лестница парагона и не посох.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A short squat white-gold obelisk as the silhouette, unmarked rings only as tight collars around the pillar (pillar first, not a nest of hoops), ivory weight, awakening of all traits, not a staff-finial gem, not a closed book, not a stair of stars, not a hooded figure, not a mountain, not a dungeon well, not a talent-tree yew.
```

**Negative:** `shared negative` + `archmage staff, mountain peak, skill tree, girl face, rainbow sparkle hail, chibi goddess full body, candy background, ivory stair`

**Do not:** посох arch; кольца как главный силуэт; лестница hidden paragon.

---

### `m_arch` — Архимаг — мудрец T4

Замысел: компактное навершие посоха и два кольца, не длинный шест.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A faceted staff-finial gem as a spearhead-silhouette, two thick unmarked spell-rings close around the gem only (gem-head first, no shaft, no ring-column), white-gold and sapphire, archmage capstone, not a closed starter grimoire, not an obelisk of collars, not a full-length pole leaving the frame.
```

**Negative:** `shared negative` + `closed book only, stair of stars, illuminati eye, latin, rainbow chibi, full-length staff leaving the frame, ring column, hanging medal`

**Do not:** том T1; обелиск trans.

---

## Приложение: узлы чата (БД, вне сетки 3×4)

### `sa_chatter` — Болтун — мудрец (чат-золото)

Замысел: горизонтальное перо сквозь низкую стопку монет.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A horizontal speaking-quill as a thick bar through a short squat stack of unmarked coins, stack wider than tall with mass in the vertical middle, sapphire and coin-gold, chat bounty, not a stuffed purse with a ribbon, not a rolled parchment shout-seal, not a bronze circular medallion.
```

**Negative:** `shared negative` + `speech bubble, keyboard, coin purse, telegram logo, hanging medal, tall vertical tower`

**Do not:** кошель m_trade; реликт hidden chatterbox.

---

### `sh_lurker` — Теневой собеседник — тень (чат-опыт)

Замысел: треугольный капюшон-арка, не миндаль-глаз.

**Prompt**

```
Square 1:1 cel-shaded anime fantasy ability emblem, one centered stance-crest filling the inner four-fifths, dark warm brown-black background, soft amber rim light, empty bottom-left, empty top-right, empty bottom-right, tiny metal hairpin fused into the crest, not a hanging medal, crisp readable silhouette. A deep pointed cowl as a dark triangular archway, the hood-cave is the silhouette, one small unmarked amber spark in the hollow, teal-violet ink, silent circle-wisdom, not a cat-eye slit, not a horizontal almond, not a crescent moon, not an open book, not headphones.
```

**Negative:** `shared negative` + `cat eye lens, open book, headphones, speech bubble, XP letters, almond eye, blood moon`

**Do not:** острый глаз; книга мудрости.

---

## Чеклист перед генерацией

1. Prefix на месте; hex и слова HP/XP/digit нет в Prompt.
2. Пустые: левый низ, правый верх, правый низ. Левый верх можно.
3. Силуэт в вертикальной середине (cover режет верх/низ).
4. Сосед по ряду/колонке не спутать (таблица силуэтов).
5. Тир 4 тяжелее тира 1 той же колонки.
6. Не relic medallion / музейная плита.
7. Шпилька-штамп есть; лица нет.
8. Даунскейл ~84px и grayscale locked — форма жива.

### Отбраковка на генерации (критик 9.6/10)

Перегенерировать id, не переписывать библию:

- `w_bash` / `w_heavy` — ударное кольцо съело молот.
- `s_nth` — цифры `III` / `x3`.
- `s_crit_m` — гача-бейдж; `s_lethal` — круглая монета; `w_last` — наклейка-сакура; `s_media` — неон HUD.
- `s_nimble` — сплошной кружок вместо узла с дырами.
- `s_ghost` — стикерная мята.
- `m_lore` — корона выросла на весь диск.
- `m_wisdom` — блёстки «level up».
- `s_amp` — раструб в запретном углу.
- `m_cmd` — пустой кадр (конфликт `plaque` в shared negative).
