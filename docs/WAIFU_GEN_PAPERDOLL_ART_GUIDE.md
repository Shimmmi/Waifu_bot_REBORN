# Гайд: заполнение paperdoll-ассетов генератора

Пошаговая инструкция, как из одной 2D-болванки (Ragnarok Online / lego-стиль) нарезать слои и положить WebP в репозиторий.  
Код читает файлы из `static/game/waifu-gen/`. Подробности рантайма: [`paperdoll/README.md`](../static/game/waifu-gen/paperdoll/README.md), compositor — `src/waifu_bot/webapp/pages/ro-paperdoll-compositor.js`.

---

## 0. Два разных набора ассетов

| Набор | Путь | Зачем | Размер |
|-------|------|-------|--------|
| **Слои куклы** | `static/game/waifu-gen/paperdoll/` | Steam step 2 (внешность) + overlay | **512×512**, RGBA, прозрачный фон |
| **UI-карточки** | `static/game/waifu-gen/cosmetic/`, `races/`, `classes/` | иконки в пикерах / модалках | **256×256** |

Этот гайд в первую очередь про **слои куклы**. Карточки можно сделать позже кропами тех же слоёв.

---

## 1. Инструменты и правила холста

### Инструменты

- Aseprite, Photoshop, Krita, Clip Studio — любой редактор со слоями и экспортом PNG/WebP.
- Удобный пайплайн: **один master-файл** (PSD / `.aseprite`) со слоями → экспорт каждого слоя в WebP с тем же именем, что в папках ниже.
- Конвертация PNG → WebP: экспорт из редактора или `cwebp` / Pillow.

### Обязательные правила

1. **Canvas:** ровно **512×512** пикселей для всех `paperdoll/**/*.webp`.
2. **Фон:** полностью прозрачный (не чёрный, не клетчатый).
3. **Pivot / якорь:** ступни у **нижнего центра** кадра (примерно y = 480–500), торс по центру X. Все слои одной модели должны совпадать **пиксель-в-пиксель** — иначе при смене причёски/одежды кукла «прыгает».
4. **Без** пола, тени сцены, рамок, UI-хрома.
5. **Имена файлов** — только латинские **slug** из таблиц ниже (`long_straight_brown.webp`), без пробелов, кириллицы и CamelCase.
6. **Замена арта:** просто перезапишите файл по тому же пути. В клиенте сделайте hard-refresh (или bump `?v=` у скриптов/страницы).

### Как резать болванку

Держите в master-файле слои в том же порядке, что рисует игра (снизу вверх):

```text
base (тело)
  → race_feature (уши/рога/…)
    → outfit (одежда)
      → hair (волосы)
        → eyes (глаза)
          → accessory (аксессуар)
```

Практический порядок работы:

1. Спрятать всё лишнее → экспортировать **только тело** → `base/.../body.webp`.
2. Включить слой расовых черт → экспорт → `race-feature/...`.
3. Одежда без волос → `outfit/...`.
4. Волосы без тела/одежды → матрица `hair/{style}_{color}.webp`.
5. Глаза → матрица `eyes/{shape}_{color}.webp`.
6. Аксессуары по одному → `accessory/...`.

**Цвет волос и глаз в рантайме не перекрашивается.** Нужны готовые комбинации файлов. Рисуйте силуэт один раз, затем 9/16 recolor (Hue / Color Overlay / палитра), не рисуйте каждую пару с нуля.

---

## 2. Куда класть слои куклы

Корень: `static/game/waifu-gen/paperdoll/`

### 2.1. Base (тело) — 7 файлов

Путь: `paperdoll/base/{race_slug}/body.webp`

| race_slug | Файл |
|-----------|------|
| `human` | `paperdoll/base/human/body.webp` |
| `elf` | `paperdoll/base/elf/body.webp` |
| `beastman` | `paperdoll/base/beastman/body.webp` |
| `angel` | `paperdoll/base/angel/body.webp` |
| `vampire` | `paperdoll/base/vampire/body.webp` |
| `demon` | `paperdoll/base/demon/body.webp` |
| `fey` | `paperdoll/base/fey/body.webp` |

**Что на слое:** силуэт тела без волос, без радужки глаз, без одежды, без ушей/рогов/хвоста расы. Допустимы нейтральный рот/нос.  
**MVP:** один нейтральный `human/body.webp`, скопировать на остальные расы, потом слегка тонировать.

### 2.2. Race feature (особенность расы)

Путь: `paperdoll/race-feature/{race_slug}/{variant}.webp`

| race_slug | variant | Файл |
|-----------|---------|------|
| `human` | `default` | `race-feature/human/default.webp` |
| `elf` | `default` | `race-feature/elf/default.webp` |
| `beastman` | `wolf` | `race-feature/beastman/wolf.webp` |
| `beastman` | `cat` | `race-feature/beastman/cat.webp` |
| `beastman` | `fox` | `race-feature/beastman/fox.webp` |
| `angel` | `default` | `race-feature/angel/default.webp` |
| `vampire` | `default` | `race-feature/vampire/default.webp` |
| `demon` | `default` | `race-feature/demon/default.webp` |
| `demon` | `horns_curved` | `race-feature/demon/horns_curved.webp` |
| `fey` | `default` | `race-feature/fey/default.webp` |

**Что на слое:** только отличительный признак (уши эльфа, рога, звериные уши и т.д.). Для «пустых» рас слой может быть почти прозрачным, но файл `default.webp` должен существовать.

### 2.3. Outfit (одежда конструктора) — 11 файлов

Путь: `paperdoll/outfit/{outfit}.webp`

| slug | Файл |
|------|------|
| `plate_armor` | `outfit/plate_armor.webp` |
| `leather_armor` | `outfit/leather_armor.webp` |
| `chainmail` | `outfit/chainmail.webp` |
| `dress` | `outfit/dress.webp` |
| `robes` | `outfit/robes.webp` |
| `casual` | `outfit/casual.webp` |
| `swimsuit` | `outfit/swimsuit.webp` |
| `bikini` | `outfit/bikini.webp` |
| `uniform` | `outfit/uniform.webp` |
| `kimono` | `outfit/kimono.webp` |
| `cloak` | `outfit/cloak.webp` |

**Что на слое:** только одежда поверх тела, без волос и аксессуаров лица.  
Позже поверх может лечь `equip/costume/` из инвентаря (это отдельный набор, не этот гайд).

### 2.4. Hair — матрица причёска × цвет

Путь: `paperdoll/hair/{hairstyle}_{hair_color}.webp`

Compositor сначала ищет этот файл; если его нет — fallback на устаревший `paperdoll/hair/{hairstyle}.webp`.

**18 причёсок (`hairstyle`):**

| slug | RU (ориентир) |
|------|----------------|
| `short_bob` | Короткое каре |
| `spiky_short` | Короткие колючие |
| `pixie` | Пикси |
| `shaggy` | Лохматые |
| `medium_straight` | Средние прямые |
| `medium_wavy` | Средние волнистые |
| `medium_straight_bangs` | Средние прямые с чёлкой |
| `medium_wavy_2` | Средние волнистые (вар. 2) |
| `messy_medium` | Средние растрёпанные |
| `side_pony` | Боковой хвост |
| `twin_tails` | Два хвоста |
| `long_pony` | Длинный хвост |
| `long_straight` | Длинные прямые |
| `long_curls` | Длинные кудри |
| `twin_tails_alt` | Два хвоста (вар. 2) |
| `side_braid` | Боковая коса |
| `space_buns` | Два пучка |
| `hime_cut` | Химэ-кат |

**9 цветов (`hair_color`):**

`blonde`, `black`, `brown`, `red`, `white`, `silver`, `blue`, `pink`, `green`

**Примеры:**

```text
paperdoll/hair/long_straight_brown.webp
paperdoll/hair/hime_cut_pink.webp
paperdoll/hair/twin_tails_blonde.webp
```

Всего комбинаций: **18 × 9 = 162** файла.

**Пайплайн:** силуэт причёски (альфа) → 9 перекрасок. Не дублируйте линию контура 162 раза.

### 2.5. Eyes — матрица тип × цвет

Путь: `paperdoll/eyes/{eye_shape}_{eye_color}.webp`

**24 формы (`eye_shape`):**

`bright`, `tsundere`, `cute`, `melancholy`, `serious`, `energetic`, `mystic`, `gentle`, `dormant_sleepy`, `shocked`, `playful`, `cold`, `confused`, `determination`, `yandere`, `shyness`, `confidence`, `tearful`, `joyful`, `anger`, `sleepy`, `annoyed`, `pouty`, `seductive`

**16 цветов (`eye_color`):**

`red`, `burgundy`, `pink`, `sky_blue`, `blue`, `turquoise`, `aquamarine`, `green`, `emerald`, `lime`, `yellow`, `amber`, `gold`, `orange`, `violet`, `gray`

**Примеры:**

```text
paperdoll/eyes/cute_amber.webp
paperdoll/eyes/yandere_red.webp
paperdoll/eyes/serious_violet.webp
```

Всего: **24 × 16 = 384** файла.

**Пайплайн:** форма глаз один раз → recolor только радужки.

### 2.6. Accessory

Путь: `paperdoll/accessory/{slug}.webp`

Нужны файлы для всех slug **кроме** логического `none` (рантайм скрывает слой, если аксессуар не выбран):

| slug | Файл |
|------|------|
| `necklace` | `accessory/necklace.webp` |
| `earrings` | `accessory/earrings.webp` |
| `makeup_light` | `accessory/makeup_light.webp` |
| `makeup_bold` | `accessory/makeup_bold.webp` |
| `scars` | `accessory/scars.webp` |
| `freckles` | `accessory/freckles.webp` |
| `glasses` | `accessory/glasses.webp` |
| `eyepatch` | `accessory/eyepatch.webp` |
| `face_paint` | `accessory/face_paint.webp` |
| `choker` | `accessory/choker.webp` |
| `gloves` | `accessory/gloves.webp` |
| `hat` | `accessory/hat.webp` |
| `hood` | `accessory/hood.webp` |
| `circlet` | `accessory/circlet.webp` |
| `hair_ribbon` | `accessory/hair_ribbon.webp` |

(Заглушка `accessory/none.webp` может лежать в репо от scaffold — в игре не используется.)

---

## 3. UI-карточки (отдельно от куклы)

Эти файлы **не** подставляет paperdoll-compositor. Они нужны для превью в пикерах (Telegram-модалки / иконки).

| Группа | Путь |
|--------|------|
| Цвета волос | `cosmetic/hair-colors/{color}.webp` |
| Причёски | `cosmetic/hair-styles/{hairstyle}.webp` |
| Цвета глаз | `cosmetic/eye-colors/{color}.webp` |
| Типы глаз | `cosmetic/eye-shapes/{shape}.webp` |
| Одежда | `cosmetic/outfits/{outfit}.webp` |
| Аксессуары | `cosmetic/accessories/{slug}.webp` |
| Расы | `races/{race_slug}.webp` |
| Классы | `classes/{class_slug}.webp` |

Размер: **256×256**. Можно сделать упрощённый кроп соответствующего слоя куклы.

Классы: `knight`, `warrior`, `archer`, `mage`, `assassin`, `healer`, `merchant`.

---

## 4. Рекомендуемый порядок заполнения (MVP → полный)

1. **Base:** `base/human/body.webp` → скопировать на 6 остальных рас.
2. **Hair smoke-test:** 1–2 причёски × все 9 цветов (например `long_straight_*`, `short_bob_*`). Проверить в Steam step 2, что цвет реально меняется.
3. **Eyes smoke-test:** 1 форма × все 16 цветов (например `cute_*`).
4. **Outfit:** 2–3 ключевых (`robes`, `casual`, `plate_armor`).
5. **Race feature:** `elf/default`, `beastman/wolf|cat|fox`, `demon/horns_curved`.
6. Добить остальные причёски, глаза, одежду, аксессуары пакетами.
7. В конце — UI `cosmetic/` / `races/` / `classes/`.

Вне этого гайда (не трогать сейчас): `paperdoll/equip/` (оружие/костюм из инвентаря на overlay), AI-портрет, Spine.

---

## 5. Как проверить в клиенте

1. Запустить Steam desktop → окно создания вайфу.
2. Step 1: имя, раса, класс → **Далее**.
3. Step 2: листать стрелки «Цвет волос», «Причёска», «Тип глаз», «Цвет глаз», «Одежда», «Особенность расы», «Аксессуар».
4. Слои должны совпадать по pivot (нет смещений).
5. После «В игру» overlay должен показать ту же layered-куклу (если `paperdoll_cosmetics` сохранились).

Перегенерация цветных заглушек в репо:

```bash
bash scripts/scaffold_waifu_gen_assets.sh
```

Скрипт **не затирает** смысл вашего арта только если вы не перезаписываете файлы вручную после него: при повторном запуске stub’ы пересоздаются поверх — сначала бэкапьте готовый арт или не гоняйте scaffold по уже залитым файлам без нужды.

---

## 6. Дерево папок (ориентир)

```text
static/game/waifu-gen/
  races/{race}.webp
  classes/{class}.webp
  cosmetic/
    hair-colors/{color}.webp
    hair-styles/{hairstyle}.webp
    eye-colors/{color}.webp
    eye-shapes/{shape}.webp
    outfits/{outfit}.webp
    accessories/{acc}.webp
  paperdoll/
    base/{race}/body.webp
    race-feature/{race}/{variant}.webp
    outfit/{outfit}.webp
    hair/{hairstyle}_{hair_color}.webp
    eyes/{eye_shape}_{eye_color}.webp
    accessory/{acc}.webp
    equip/          ← не этот гайд (инвентарь / overlay)
```

---

## 7. Чеклист перед коммитом арта

- [ ] Все новые файлы 512×512 (paperdoll) или 256×256 (cosmetic).
- [ ] Прозрачный фон, общий pivot.
- [ ] Имена = slug из таблиц (ни одного «Hair Long Brown.webp»).
- [ ] Для волос есть `{style}_{color}.webp`, не только `{style}.webp`.
- [ ] Для глаз есть нужные `{shape}_{color}.webp` под выбранные в UI цвета.
- [ ] Проверена смена цвета волос и глаз в Steam step 2.
- [ ] Не закоммичены случайные PSD/исходники в `static/` (исходники лучше хранить отдельно).
