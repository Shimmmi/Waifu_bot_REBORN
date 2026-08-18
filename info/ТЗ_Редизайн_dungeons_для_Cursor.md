# ТЗ: Редизайн dungeons.html — внедрение в прод

**Версия:** 1.0
**Тип задачи:** визуальный рефакторинг (CSS/дизайн-токены), без изменения бизнес-логики
**Затрагиваемые файлы:** `dungeons.html`, `styles.css` (или бандл `styles.min.css`), опционально новый файл `dungeons-redesign.css`
**Не затрагиваются:** `dungeons.js`, `app.js`, `combat-island.js`, любые backend/API контракты

Референс-макет (визуальная концепция, статичный, без бэкенда): `dungeons_redesign.html`, приложен отдельно. Этот документ описывает, как перенести решения из макета в реальный прод-файл, не сломав JS.

---

## 0. Контекст и цель

`dungeons.html` — живая страница с ~3600 строк разметки, плотно завязанная на `WaifuApp.*` (обработчики `onclick`), на конкретные `id` (JS пишет в них текст/атрибуты напрямую) и на конкретные CSS-классы (JS добавляет/убирает их для смены состояния: `elite-blue`, `locked`, `fading`, `active` и т.д.). Полная замена разметки без доступа к `dungeons.js`/`app.js`/`combat-island.js` — риск сломать боевой цикл (`group_message_damage` рендерит сюда результат каждого сообщения в чате).

**Правило миграции: isolate, don't rewrite.**
Меняем только визуальный слой (CSS, немного разметки-обёртки там, где это безопасно). Не переименовываем и не удаляем ничего, что перечислено в разделе 1 «Не трогать».

Все примеры кода ниже — **готовые к вставке диффы**, привязанные к реальным селекторам из выгруженных `dungeons.html` / `styles.css` (не выдуманные).

---

## 1. Не трогать (жёсткий список)

Cursor должен проверить каждое из этих имён перед любым rename/удалением — на них завязан JS:

**IDs, в которые JS пишет напрямую:**
`#badge-level`, `#badge-gold`, `#attic-level-ring-fg`, `#attic-level-circle`, `#attic-dungeon-label`, `#attic-dungeon-progress`, `#attic-exp-cells`, `#attic-player-avatar-img`, `#attic-player-avatar-fallback`, `#attic-menu-btn` / `#attic-menu`, `#dungeon-tabs`, `#solo-active`, `#solo-active-content`, `#solo-dungeon-name`, `#solo-dungeon-progress`, `#solo-dungeon-progress-ov`, `#monster-visual`, `#monster-img`, `#monster-placeholder`, `#monster-emoji`, `#monster-placeholder-label`, `#monster-name-text`, `#monster-name-type`, `#monster-name-level`, `#monster-affixes`, `#solo-combat-island`, `#battle-log-btn`, `#solo-active-meta`, `#solo-battle-log-host`, `#unconscious-banner`, `#unconscious-timer`, `#solo-dungeons`, `#challenge-day-strip`, `#reward-modal`, `#reward-modal-subtitle`, `#reward-modal-body`, `#plus-bottomsheet`, `#plus-options-list`, `#solo-exit-btn`.

**Классы, которые JS добавляет/убирает динамически (состояние, не тема):**
`.active` (на `.tab` и `.tab-panel`), `.elite-blue` / `.elite-gold` / `.elite-red` / `.boss` (на `#monster-visual`), `.fading` (на `.monster-img`), `.visible` (на `.monster-placeholder`), `.locked` (на карточках подземелий), `.selected` (на `.plus-option`), `.solo-hit-flash` (на `#monster-visual`, уже есть анимация — расширяем, не переименовываем).

**Атрибуты, которые читает клиентский фоллбэк-механизм картинок монстров:**
`data-family`, `data-slug`, `data-tier` на `#monster-visual` (см. ТЗ, раздел «Изображения монстров»). CSS уже использует `data-family` для подбора `--monster-bg` (см. 1.9) — это нужно сохранить как основной механизм тематизации по семейству монстра.

**Классы, генерируемые JS-шаблонами карточек подземелий** (значит, их нельзя переименовать в CSS, не поправив генератор во втором файле, которого у нас нет):
`.solo-dungeon-card`, `.dungeon-tile`, `.solo-dungeon-card__frame`, `.solo-dungeon-card__bg`, `.solo-dungeon-card__overlay`, `.solo-dungeon-card__hdr`, `.solo-dungeon-card__title`, `.solo-dungeon-card__bottombar`, `.solo-dungeon-card__bottombar--compact`, `.solo-dungeon-card__meta-line`, `.solo-dungeon-card__meta-line--diff`, `.solo-dungeon-card__meta-line--muted`, `.solo-dungeon-card__meta-line--lock`, `.solo-dungeon-plus-btn`, `.grade-mark--1/--2`, `.act-block`, `.act-title`, `.act-subtitle`, `.affix-chip.blue/.gold/.red`, `.plus-option`, `.plus-option-badge`, `.plus-option-info`, `.plus-option-label`, `.plus-option-desc`.

**Правило:** всё из этого списка — **только новые CSS-объявления поверх существующих селекторов**, никаких переименований. Где нужна новая разметка (например обёртка для декоративного элемента) — добавляем новый вложенный `<span>`/`::before`/`::after`, никогда не оборачиваем/не убираем существующий узел с id/классом из списка.

---

## 2. Дизайн-токены

Страница уже задаёт локальные переменные в `body.page-dungeons` (файл `dungeons.html`, строки ~50–62):

```css
body.page-dungeons {
  --bg: #0d0a08;
  --card: #1a1410;
  --text: #e8dcc8;
  --muted: #9a8a7a;
  --accent: #e8b84b;
  --border: rgba(200, 146, 42, 0.28);
}
```

Их трогать не нужно — по всему файлу (и в `styles.css`) на них ссылаются десятки правил (`var(--accent)`, `var(--border)` и т.д.). **Добавляем новые токены рядом**, не заменяя старые:

```css
body.page-dungeons {
  /* --- существующие, не менять --- */
  --bg: #0d0a08;
  --card: #1a1410;
  --text: #e8dcc8;
  --muted: #9a8a7a;
  --accent: #e8b84b;
  --border: rgba(200, 146, 42, 0.28);

  /* --- новые токены редизайна --- */
  --gold-bright: #ffd97a;      /* хайлайт золота: свечения, ховеры */
  --panel-2: #241a10;          /* второй стоп градиента карточек */
  --ember: #e2543f;            /* HP-бар монстра, урон, опасность */
  --ember-bright: #ff8a65;
  --rune: #49c9b3;             /* энергия / позитив (HP ОВ, "пройдено") */
  --rune-bright: #7ff0dd;
  --parchment-faint: #6b5c4b;  /* третий уровень приглушённого текста */
  --line: var(--border);       /* алиас для новых компонентов — семантичнее по имени */

  /* редкость — только для предметов (награды, инвентарь), не для хрома */
  --r-common: #9a8f82;
  --r-uncommon: #5fbf80;
  --r-rare: #5b9bf0;
  --r-epic: #b177f0;
  --r-legendary: #f3c766;

  --font-display: "Cinzel", serif;
  --font-body: "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-hud: "Rajdhani", var(--font-body);
}
```

Почему так: `--accent`/`--border`/`--text` используются вне зависимости от этого редизайна (десятки мест в 15k-строчном `styles.css`), переименование = риск волнового сноса стилей на других вкладках этой же страницы (`tab-group`, `tab-abyss`, модалки предметов). Новые токены — чисто аддитивны, откатываются одним `git revert` файла, если что-то не понравится.

---

## 3. Шрифты

`Cinzel` уже используется по всему файлу (`font-family: Cinzel, serif` — строки 104, 386, 427 и другие), но явного `<link>` на Google Fonts в `<head>` нет — либо шрифт подтягивается откуда-то из бандла, либо сейчас честно рендерится системный serif-фоллбэк. **Проверить в Cursor:** есть ли `@font-face` для Cinzel в `styles.min.css` / где-то в `/webapp/assets/`.

Новые роли:
- `--font-display` (Cinzel) — уже есть, только заголовки/акценты, не тело текста.
- `--font-body` (Manrope) — UI-текст, кнопки, лейблы. Сейчас страница использует system-ui — Manrope даёт более «геймовый» плотный шрифт без доп. веса на трафик (переменный шрифт).
- `--font-hud` (Rajdhani) — цифры: уровень, урон, таймеры, HP-читаут. Контраст с засечками Cinzel — так делают в большинстве топовых RPG (числа — техническим гротеском, заголовки — декоративным).

**Важно (перф-аудит):** учитывая ваш прошлый HAR-анализ `dungeons.html` (цель — 9s → 1–1.5s first load), **не советую** просто добавить `<link href="https://fonts.googleapis.com/...">` — это лишний DNS+TLS хендшейк на критичном пути рендера чата.

Рекомендация: самостоятельно захостить `.woff2` (только нужные начертания: Manrope 600/700/800, Rajdhani 600/700, Cinzel 600/700/900 — уже должен быть, если используется) в `/webapp/assets/fonts/` рядом с уже существующими статик-ассетами, подключить через `@font-face` с `font-display: swap`, и добавить `<link rel="preload" as="font" ... crossorigin>` только для Manrope-700 (самый частый вес, шапка/кнопки), чтобы не блокировать LCP. Полный список открытых вопросов — п. 14.

```css
@font-face {
  font-family: "Manrope";
  src: url("/webapp/assets/fonts/manrope-var.woff2") format("woff2");
  font-weight: 400 800;
  font-display: swap;
}
@font-face {
  font-family: "Rajdhani";
  src: url("/webapp/assets/fonts/rajdhani-600.woff2") format("woff2");
  font-weight: 600 700;
  font-display: swap;
}
```

---

## 4. Фирменный приём (сигнатурный элемент)

Резные уголки-скобки — рамка «страницы бестиария под лупой». Один переиспользуемый класс, без доп. разметки (8 линейных градиентов в одном `::after`):

```css
.page-dungeons .frame-corners { position: relative; }
.page-dungeons .frame-corners::after {
  content: "";
  position: absolute;
  inset: 6px;
  z-index: 3;
  pointer-events: none;
  --cc: var(--corner-color, var(--gold-bright));
  --cs: var(--corner-size, 14px);
  background:
    linear-gradient(var(--cc), var(--cc)) top left / var(--cs) 2px no-repeat,
    linear-gradient(var(--cc), var(--cc)) top left / 2px var(--cs) no-repeat,
    linear-gradient(var(--cc), var(--cc)) top right / var(--cs) 2px no-repeat,
    linear-gradient(var(--cc), var(--cc)) top right / 2px var(--cs) no-repeat,
    linear-gradient(var(--cc), var(--cc)) bottom left / var(--cs) 2px no-repeat,
    linear-gradient(var(--cc), var(--cc)) bottom left / 2px var(--cs) no-repeat,
    linear-gradient(var(--cc), var(--cc)) bottom right / var(--cs) 2px no-repeat,
    linear-gradient(var(--cc), var(--cc)) bottom right / 2px var(--cs) no-repeat;
  opacity: 0.85;
  filter: drop-shadow(0 0 4px rgba(226, 169, 63, 0.45));
}
```

Применяется добавлением класса `frame-corners` к существующим контейнерам (см. п. 8.1, 10.1) — **не создаёт новых элементов**, безопасно.

Восковая печать (используется на чипе сложности и номере акта):

```css
.page-dungeons .seal {
  --seal-c: var(--accent);
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #1a1006;
  font: 700 13px/1 var(--font-hud);
  background: radial-gradient(circle at 32% 28%, #fff3d6 0%, var(--gold-bright) 22%, var(--seal-c) 62%, #8a611c 100%);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.45), inset 0 0 0 1px rgba(255, 255, 255, 0.25);
}
.page-dungeons .seal::before {
  content: "";
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  background: repeating-conic-gradient(rgba(0, 0, 0, 0.18) 0deg 4deg, transparent 4deg 12deg);
  opacity: 0.55;
  mix-blend-mode: multiply;
}
```

---

## 5. ОЧ / шапка (`.attic-*`) — ⚠️ решение перед стартом

`.attic` и все `.attic-*` определены **глобально в `styles.css`** (строки ~1268–1860), без префикса `.page-dungeons` — это общий компонент для всех 9 страниц (`profile.html`, `shop.html`, `tavern.html` и т.д., см. раздел №0 исходного ТЗ проекта).

**Это значит: править `.attic-*` напрямую в `styles.css` — правки применятся сразу на всех страницах.** Это не плохо (шапка должна быть визуально единой), но это отдельное решение, которое стоит принять осознанно, а не как побочный эффект правки dungeons.html. Варианты:

- **A. Только эта страница (быстрее, безопаснее).** Дублируем нужные правила под `body.page-dungeons` в `dungeons.html`, специфичность `body.page-dungeons .attic-row .chip` перебьёт общий `.attic-row .chip`. Шапка на dungeons.html станет визуально отличаться от shop/tavern до тех пор, пока не сделаете то же для них.
- **B. Глобально сразу.** Правим `.attic-*` в `styles.css` напрямую — шапка обновится везде за один PR. Выше риск (нужно визуально проверить все 9 страниц), но нет временной неконсистентности.

**Рекомендация:** начать с A на этом файле, вынести правки в отдельный CSS-блок с комментарием `/* TODO: promote to global .attic-* when ready */`, чтобы через одну итерацию скопировать блок в `styles.css` без правки самих правил.

Правки (вариант A, вставить в `<style>` внутри `dungeons.html`):

```css
/* --- ОЧ: чипы как "рунные таблички" вместо плоских пилюль --- */
body.page-dungeons .attic-row .chip {
  background: linear-gradient(180deg, var(--panel-2), var(--card));
  border: 1px solid var(--border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
  font-family: var(--font-hud);
  font-weight: 700;
}
body.page-dungeons .attic-gold-chip { color: var(--gold-bright); }

/* --- Кольцо уровня: тёплое свечение вместо плоской заливки --- */
body.page-dungeons #attic-level-ring-fg {
  stroke: var(--gold-bright);
  filter: drop-shadow(0 0 3px rgba(226, 169, 63, 0.55));
}
body.page-dungeons #badge-level {
  font-family: var(--font-hud);
}

/* --- Прогресс подземелья в чипе: точки вместо текста-скобок --- */
body.page-dungeons .attic-dungeon-progress-fill {
  background: linear-gradient(90deg, var(--accent), var(--gold-bright));
  box-shadow: 0 0 6px rgba(226, 169, 63, 0.5);
}
```

Ничего из этого не переименовывает `#attic-level-ring-fg`, `#badge-level`, `.attic-dungeon-progress*` — JS продолжает писать `stroke-dashoffset`/текст как раньше, меняется только визуальная тема.

**Чипа энергии в текущей разметке шапки нет** (есть только уровень+кольцо, чип подземелья, чип операций `🗺`, чип золота, меню). Это отдельный вопрос — см. п. 14.1.

---

## 6. Вкладки (`#dungeon-tabs .tab`)

Уже частично стилизованы инлайново в `dungeons.html` (строки 222–263), с `!important` — значит, override должен либо бить по специфичности выше, либо тоже использовать `!important` **только на тех же свойствах**, где он уже стоит (`background`, `border-color`, `color`, `box-shadow`, `transform`).

```css
.page-dungeons #dungeon-tabs .tab.active {
  background: linear-gradient(180deg, rgba(226, 169, 63, 0.22), rgba(226, 169, 63, 0.08)) !important;
  box-shadow: 0 0 14px rgba(226, 169, 63, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
}
.page-dungeons #dungeon-tabs .tab {
  transition: flex-basis 0.2s ease, flex-grow 0.2s ease, background 0.18s ease,
              border-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}
```

Существующая транзишн-цепочка уже покрывает морфинг ширины активной вкладки — трогать `flex`-логику не нужно, только визуальные свойства.

---

## 7. Список подземелий (`.act-block`, `.solo-dungeon-card`)

`.act-block`, `.act-title`, `.dungeon-acts` уже в `styles.css` под `.page-dungeons` (строки 5363–5390) — безопасная зона, правим свободно.

`.solo-dungeon-card.dungeon-tile` и все `__frame/__bg/__overlay/__hdr/__title/__bottombar/__meta-line` — генерируются JS-шаблоном (файла генератора у нас нет, но имена классов зафиксированы в текущем инлайн-CSS `dungeons.html` строки 293–530). Правим только свойства, не трогаем структуру:

```css
/* Уголки-скобки на арт-плашке карточки — сигнатурный приём */
.page-dungeons .solo-dungeon-card__frame {
  --corner-color: var(--gold-bright);
  --corner-size: 11px;
}
.page-dungeons .solo-dungeon-card__frame::after {
  content: "";
  position: absolute;
  inset: 5px;
  pointer-events: none;
  background:
    linear-gradient(var(--corner-color), var(--corner-color)) top left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / 2px var(--corner-size) no-repeat;
  opacity: 0.7;
}
.page-dungeons .solo-dungeon-card.locked .solo-dungeon-card__frame::after { opacity: 0.3; }

/* Карточка активного подземелья — золотой контур вместо серого */
.page-dungeons .solo-dungeon-card.dungeon-tile.active-run {
  /* примечание: класса .active-run сейчас в разметке нет — см. открытый вопрос 14.2 */
  border-color: rgba(226, 169, 63, 0.6);
  box-shadow: 0 0 0 1px rgba(226, 169, 63, 0.25), 0 8px 24px rgba(0, 0, 0, 0.35);
}

/* Числа (уровень монстров, "+15") — HUD-шрифт для контраста с названием */
.page-dungeons .solo-dungeon-card__meta-line strong {
  font-family: var(--font-hud);
  font-weight: 700;
  color: var(--gold-bright);
}
```

`.solo-dungeon-card__frame::after` — новый псевдоэлемент на уже существующем контейнере, ничего не переставляет местами внутри карточки.

---

## 8. Карточка активного боя

### 8.1 Портрет монстра (`.monster-visual`)

Уже поддерживает состояния `elite-blue/gold/red`, `boss`, тематизацию по `data-family` через `--monster-bg` (`styles.css` 5605–5624, 5809–5817) — это ровно то, что нужно, ничего изобретать не надо, только усилить свечение и добавить уголки:

```css
.page-dungeons .monster-visual {
  --corner-color: var(--gold-bright);
  --corner-size: 16px;
}
.page-dungeons .monster-visual::before {
  /* уголки поверх текущего фона, ниже оверлеев (z-index: 2 у .monster-overlay-*) */
  content: "";
  position: absolute;
  inset: 6px;
  z-index: 1;
  pointer-events: none;
  background:
    linear-gradient(var(--corner-color), var(--corner-color)) top left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / 2px var(--corner-size) no-repeat;
  opacity: 0.65;
}
/* элитные — уголки в цвет тира, поверх border-color, который уже задан в 5621-5623 */
.page-dungeons .monster-visual.elite-blue { --corner-color: #3b82f6; }
.page-dungeons .monster-visual.elite-gold,
.page-dungeons .monster-visual.boss       { --corner-color: #f59e0b; }
.page-dungeons .monster-visual.elite-red  { --corner-color: #ef4444; }

/* дыхание ауры для элитных — новая, не конфликтует с существующим box-shadow */
.page-dungeons .monster-visual.elite-gold,
.page-dungeons .monster-visual.elite-red,
.page-dungeons .monster-visual.boss {
  animation: mv-aura-breathe 2.6s ease-in-out infinite;
}
@keyframes mv-aura-breathe {
  0%, 100% { filter: brightness(1); }
  50%      { filter: brightness(1.08); }
}
@media (prefers-reduced-motion: reduce) {
  .page-dungeons .monster-visual { animation: none !important; }
}
```

### 8.2 HP-бар монстра/ОВ (`.hp-bar`, `.hp-fill-monster`, `.hp-fill-waifu`)

Текущая реализация (`styles.css` 5819–5849) уже разводит цвета монстра/ОВ через модификаторы — оставляем механику, добавляем «насечки» и явное свечение:

```css
.page-dungeons .hp-bar {
  position: relative;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.4);
}
.page-dungeons .hp-bar::after {
  /* тиковая насечка каждые ~12.5% — чисто декоративный слой, не мешает .hp-fill под собой */
  content: "";
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    90deg, rgba(0, 0, 0, 0.35) 0 1px, transparent 1px 12.5%
  );
  pointer-events: none;
}
.page-dungeons .hp-fill-monster {
  box-shadow: 0 0 8px rgba(226, 84, 63, 0.5);
}
.page-dungeons .hp-fill-waifu {
  box-shadow: 0 0 8px rgba(73, 201, 179, 0.5);
}
```

Анимация удара уже есть в `dungeons.html` (`.solo-hit-flash` на `#monster-visual`, строки 20–26) и плавающий урон (`.solo-damage-float`, строки 27–47) — это уже ровно тот «сочный» фидбэк, который есть в топовых играх. **Ничего менять не нужно**, разве что усилить цвет крита:

```css
.page-dungeons .solo-damage-float--crit {
  color: var(--gold-bright);
  text-shadow: 0 0 8px rgba(226, 169, 63, 0.8), 0 1px 4px rgba(0, 0, 0, 0.85);
}
```

### 8.3 Аффикс-чипы (`.affix-chip.blue/.gold/.red`)

Уже 1:1 совпадают с системой аффиксов из основного ТЗ проекта (🔵 1–2 аффикса / 🟡 3 / 🔴 4, «Раздел: Аффиксы и суффиксы монстров»). Меняем только типографику под HUD-числа там, где есть множители:

```css
.page-dungeons .affix-chip b,
.page-dungeons .affix-chip strong {
  font-family: var(--font-hud);
  font-weight: 700;
}
```

(Если сейчас JS не оборачивает числовые множители в `<b>`/`<strong>` внутри чипа — это правка в шаблоне генерации чипа, не в CSS; см. открытый вопрос 14.3.)

---

## 9. Боттомшит сложности (`#plus-bottomsheet`)

Уже своя тема на `.bottomsheet--dungeon-plus` (`styles.css` 7991–8096). Точечно добавляем печать вместо текущего оформления `.plus-option-badge` (если он сейчас плоский бейдж с числом):

```css
.page-dungeons .plus-option-badge {
  font-family: var(--font-hud);
}
.page-dungeons .plus-option.selected {
  border-color: rgba(226, 169, 63, 0.6);
  box-shadow: 0 0 0 1px rgba(226, 169, 63, 0.25);
}
```

Проверить в Cursor фактическую структуру `.plus-option-badge` перед правкой (возможно, уже используется `.seal`-подобная печать — тогда просто прокинуть новые токены).

---

## 10. Модалка наград (`#reward-modal`)

Уже тёмная тема с градиентом и рамкой (`dungeons.html` 538–571). Добавляем уголки на всю модалку и HUD-шрифт для итоговых цифр:

```css
.page-dungeons #reward-modal .modal-content {
  --corner-color: var(--gold-bright);
  --corner-size: 16px;
  position: relative;
}
.page-dungeons #reward-modal .modal-content::after {
  content: "";
  position: absolute;
  inset: 6px;
  pointer-events: none;
  background:
    linear-gradient(var(--corner-color), var(--corner-color)) top left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) top right / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom left / 2px var(--corner-size) no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / var(--corner-size) 2px no-repeat,
    linear-gradient(var(--corner-color), var(--corner-color)) bottom right / 2px var(--corner-size) no-repeat;
  opacity: 0.6;
}
.page-dungeons #reward-modal-body strong,
.page-dungeons #reward-modal-body b {
  font-family: var(--font-hud);
  color: var(--gold-bright);
}
```

---

## 11. Куда физически класть новый CSS

**Рекомендация: новый файл**, не раздувать существующий `<style>`-блок внутри `dungeons.html` (сейчас там уже ~500 строк служебных переопределений):

1. Создать `webapp/dungeons-redesign.css` со всеми блоками из разделов 2, 4, 6–10 (шапку — по решению из п. 5).
2. Подключить в `<head>` **после** обеих текущих ссылок на стили, чтобы каскад отрабатывал без лишних `!important`:
   ```html
   <link rel="stylesheet" href="/webapp/bundle/styles.min.css?v=waifu-webapp-v88" onerror="this.onerror=null;this.href='/webapp/styles.css?v=waifu-webapp-v57'" />
   <link rel="stylesheet" href="/webapp/bundle/waifu-combat-island.css?v=waifu-webapp-v88" />
   <link rel="stylesheet" href="/webapp/assets/tutorial.css" />
   <link rel="stylesheet" href="/webapp/dungeons-redesign.css?v=1" />  <!-- новое -->
   ```
3. Версионировать через `?v=` как остальные бандлы, чтобы не ловить закешированную старую версию (см. вашу прошлую перф-находку про `no-cache` на статике).
4. Один файл = один понятный diff в PR, откатывается закомментированием одной строки `<link>`.

---

## 12. QA-чеклист перед мержем

Все состояния ниже управляются JS через добавление/снятие классов — проверить, что визуальный слой не блокирует и не искажает логику:

- [ ] Переключение вкладок `Одиночные / Операции / Групповые / Бездна` — `.tab.active` корректно морфит ширину, текст вкладки не обрезается на узких экранах (~360px).
- [ ] Обычный монстр → элитный (`elite-blue`/`elite-gold`/`elite-red`) → босс (`boss`) — рамка/уголки/свечение переключаются, аффикс-чипы не переполняют `.monster-affixes` при 4 аффиксах на маленьком экране.
- [ ] Фоллбэк изображения монстра: `monster-img` → `onerror` → `monster-placeholder.visible` — уголки-рамка не перекрывают эмодзи-заглушку.
- [ ] Карточка подземелья: `locked` (замок, приглушение) vs доступна vs пройдена — не потерять `🔒`-оверлей (`::after` с `content: "🔒"`, строки 524–530 в текущем файле).
- [ ] `#unconscious-banner` (ОВ «без сознания») — не задет новыми правилами `.hp-bar`/`.monster-visual`.
- [ ] Боттомшит сложности открывается/закрывается по тому же UX (backdrop click, кнопка ✕), `.plus-option.selected` виден.
- [ ] `#reward-modal` — контент, который пишет JS в `#reward-modal-body`, не обрезается уголками (`inset: 6px` на `::after`, у самого контента должен быть padding ≥ 10px от края).
- [ ] `prefers-reduced-motion: reduce` — все новые `@keyframes` (`mv-aura-breathe` и т.д.) отключаются.
- [ ] Клавиатурный фокус (`:focus-visible`) виден на кнопках `.dungeon-tab-sm`, `.tab`, карточках подземелий — если раньше не было явного стиля фокуса, добавить.
- [ ] Экран ≤360px (самый частый Telegram-viewport на Android) — чипы шапки не наезжают друг на друга, `.tab-txt` в неактивных вкладках корректно скрыт.
- [ ] Шапка (`.attic-*`) — если правили только под `body.page-dungeons` (вариант A из п.5), визуально сверить с `profile.html`/`shop.html`, что расхождение осознанное и временное.

---

## 13. Поэтапный план внедрения

1. **Токены + шрифты** (разделы 2–3). Ничего не должно визуально измениться, кроме, возможно, начертания текста, если Cinzel сейчас не грузится. Нулевой риск для логики.
2. **Вкладки + список подземелий** (разделы 6–7). Изолированная зона, уже полностью под `.page-dungeons`.
3. **Карточка активного боя** (раздел 8). Самая чувствительная зона — тут больше всего JS-состояний, тестировать через админ-кнопки (`adminKillMonster`, `adminTakeDamage`, `adminGenerateMonsterArt` — уже есть в `.solo-dungeons-admin-buttons`) для быстрой прогонки всех состояний без реального чата.
4. **Боттомшит + модалка наград** (разделы 9–10).
5. **Шапка** (раздел 5) — отдельным PR, после решения A/Б.

---

## 14. Открытые вопросы

**14.1 — Энергии нет в шапке.** Основной ТЗ проекта (раздел №0) требует поле «Текущая энергия» в ОЧ, но в текущей разметке `dungeons.html` его нет (`.attic-exp-chip` — это статус операций/экспедиций `🗺`, не энергия). Добавление чипа энергии — это не только CSS: нужен `id` под значение и JS, который будет его обновлять. Уточнить: делаем сейчас отдельной подзадачей (с бэкендом) или откладываем — редизайн шапки в этом ТЗ рассчитан на **существующий** набор полей.

**14.2 — Нет класса-маркера «идёт бой» на карточке подземелья.** В макете карточка активного подземелья визуально выделена (`active-run`), но в реальном JS-шаблоне карточек такого класса, судя по всему, нет — статус скорее всего рендерится только текстом в `.solo-dungeon-card__meta-line--diff`. Нужно решить: (а) добавить класс в генератор карточек (правка в JS, не в этом ТЗ) или (б) выделять по существующему тексту статуса через `:has()`-селектор (осторожно с поддержкой в Telegram WebView) или (в) не выделять отдельно, ограничиться тем, что активное подземелье и так дублируется в `.battle-card` сверху.

**14.3 — Разметка чисел внутри аффикс-чипов и `.solo-dungeon-card__meta-line`.** Для HUD-шрифта на числах (п. 8.3) нужно, чтобы множители/цифры были обёрнуты в отдельный `<b>`/`<strong>`/`<span>` внутри строки, а не шли одним текстовым узлом с описанием. Проверить в Cursor фактический вывод JS-шаблона — если сейчас это цельная строка, точечная типографика невозможна без правки шаблона (небольшая, в JS, не в CSS).

**14.4 — Шрифты: самохостинг vs Google Fonts.** П.3 рекомендует самохостинг из-за истории перф-работы над этой же страницей. Если для MVP редизайна это избыточно — можно временно подключить через `<link>` на Google Fonts с `rel="preconnect"`, но тогда стоит сознательно принять +1 внешний RTT на первой загрузке и вернуться к самохостингу отдельной задачей.

**14.5 — Промоушен шапки в глобальные стили** (см. п. 5) — нужно ваше решение A или B до того, как Cursor начнёт этот раздел.

---

## Приложение: полный список новых CSS-классов, вводимых этим ТЗ

Ничего из списка ниже не пересекается с существующими именами в `dungeons.html`/`styles.css` (проверено `grep` по обоим файлам):

`.frame-corners`, `.seal` — новые переиспользуемые утилиты.
Остальные правки — довески к существующим селекторам через `::before`/`::after`/новые CSS-свойства, без новых классов в разметке.
