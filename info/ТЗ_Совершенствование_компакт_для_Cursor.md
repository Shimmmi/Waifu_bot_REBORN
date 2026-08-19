# ТЗ: Экран «Совершенствование» (Paragon) — компакт-редизайн, для Cursor

**Версия:** 1.0
**Тип задачи:** визуальный рефакторинг + доработка UX (плотная сетка бонусов, вынос списка в модалку)
**Референс-реализация:** `paragon_redesign_compact.html` (статичный концепт с моковыми данными, приложен отдельно)

---

## 0. Важная оговорка — читать перед началом

В отличие от ТЗ по `dungeons.html`, в этот раз у меня **нет исходного HTML/CSS этой страницы** — только скриншот. Это значит, что ниже нет диффов «поверх строки N файла X», как в прошлый раз: я не знаю реальных `id`, классов и того, что на них завязан JS.

Экрана «Совершенствование» нет и в списке основных страниц исходного ТЗ проекта (`profile.html`, `dungeons.html`, `shop.html`, `tavern.html`, `caravan.html`, `training_hall.html`, `guild_hall.html`, `settings.html`, `waifu_generator.html`) — то есть это более новая фича (см. память проекта: paragon-система, добавлена после базового ТЗ v0.2). Файл может называться как угодно (`paragon.html`, `ascension.html`, отдельная вкладка внутри `training_hall.html` и т.п.) и я не знаю, как называется на самом деле.

**Шаг 0 для Cursor, обязательный перед началом работы:**

1. Найти реальный файл экрана — поиском по уникальным строкам с самого скриншота, которые почти наверняка не встречаются больше нигде в проекте:
   ```
   grep -rn "Переназначить" webapp/
   grep -rn "Текущие бонусы" webapp/
   grep -rn "ОПГ" webapp/
   ```
2. Как только файл найден — реальные `id`/классы **имеют приоритет** над всем, что предложено ниже. Этот документ описывает *целевую* реализацию (то, к чему должна прийти вёрстка) и *контракт данных* (что именно JS должен туда подставлять) — но конкретные имена селекторов в существующем файле нужно сохранить там, где они уже используются в JS, по тому же принципу «изолировать, а не переписывать», что и в ТЗ по `dungeons.html`.
3. Если файла не существует и страница рендерится динамически (например, генерируется JS-шаблоном без отдельного `.html`) — see Приложение А, где размечено, какие блоки статичны, а какие обязаны быть шаблонизированы.

Все имена классов ниже намеренно с префиксом `parg-`, чтобы не столкнуться с чем-то одноимённым в 15-тысячестрочном общем `styles.css` (там уже есть, например, общий `.chip`, `.tabs`, `.badge` и т.д. — коллизия имён отдельного компонента с общим бандлом даёт трудноуловимые баги). Единственное исключение — шапка (см. п.1).

---

## 1. Шапка (HUD) — переиспользовать `.attic-*`, не изобретать заново

На скриншоте шапка (аватар, чипы, бургер-меню) — тот же набор элементов, что и на `dungeons.html`: аватар, бейдж уровня, чип-«таблетка», пустые слоты, чип ресурса, чип золота, меню. Это должен быть **тот же самый общий компонент `.attic` / `header.attic`**, описанный в ТЗ по dungeons.html (раздел 5), а не отдельная реализация под эту страницу.

Если Cursor уже применил редизайн шапки из того ТЗ — здесь просто подключить `body.page-<paragon>` к тому же общему CSS, ничего не дублировать. Если ещё нет — сначала сделать шапку по тому ТЗ (раздел 5), потому что переизобретение `.hud`/`.chip` здесь второй раз — это ровно то дублирование, которого проект и так пытается избежать («изолировать, а не переписывать»).

**Не подтверждено:** значение зелёного бейджа «3» у аватара на скриншоте — это уровень персонажа (маловероятно, был 34 на прошлых макетах), тир совершенствования, или что-то третье. Уточнить у продукта перед вёрсткой; в макете использовано как декоративный плейсхолдер.

---

## 2. Дизайн-токены

Если в проект уже добавлен блок токенов из ТЗ по dungeons.html — **переиспользовать один в один**, ничего не дублировать, просто подключить эту страницу к тому же CSS-файлу/бандлу. Полный список — для самодостаточности документа:

```css
body.page-paragon { /* имя body-класса — уточнить по факту (см. п.0) */
  --ink:        #0a0705;
  --panel:      #1b130c;
  --panel-2:    #241a10;
  --parchment:  #ecdfc6;
  --parchment-dim: #9c8b76;
  --parchment-faint: #6b5c4b;
  --gold:       #e2a93f;
  --gold-bright:#ffd97a;
  --gold-dim:   rgba(226,169,63,.16);
  --ember:      #e2543f;
  --ember-bright:#ff8a65;
  --rune:       #49c9b3;      /* EXP/прогресс — тот же цвет, что уже был на зелёном progress-bar */
  --rune-bright:#7ff0dd;
  --arcane:     #5b9bf0;      /* смысловой цвет для ИНТ-бонусов */
  --arcane-bright:#8fc0ff;
  --line:       rgba(226,169,63,.18);

  --font-display: "Cinzel", serif;
  --font-body: "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-hud: "Rajdhani", var(--font-body);
}
```

Шрифты — см. ТЗ по dungeons.html, раздел 3 (там же обоснование самохостинга вместо Google Fonts `<link>` из-за истории перф-работы над этим же вебаппом). Если Cinzel/Manrope/Rajdhani уже подключены для dungeons.html — ничего повторно грузить не нужно, шрифты общие на всё приложение.

Сигнатурные утилиты (резные уголки `.corners`, печать `.seal`) — тоже переиспользовать из dungeons-редизайна как есть, они уже написаны как переносимые (без завязки на структуру конкретной страницы). Если ещё не вынесены в общий файл — вынести сейчас в `webapp/design-system.css`, чтобы третья страница не копировала их в третий раз.

---

## 3. Целевая структура экрана (по разделам сверху вниз)

```
.parg-screen
├── header.attic (переиспользуемый, см. п.1)
└── main
    ├── .parg-tree-strip        — 3 иконки-дерева в одну строку
    ├── .parg-tabbar            — активная вкладка + "?" + счётчик очков
    ├── .parg-tier-card         — печать тира + EXP-бар (горизонтальная, компактная)
    ├── .parg-choose-btn        — CTA "Выбрать бонус" (locked/ready)
    ├── .parg-buffs-block       — "Текущие бонусы": плотная сетка 2×N со скроллом
    └── .parg-permanent-trigger — компактный триггер, открывает модалку "Постоянные"

.parg-modal (Постоянные бонусы, список)
.parg-modal (подтверждение переназначения, поверх списка)
```

Ключевое архитектурное решение этой итерации: **экран не растёт с количеством данных.** «Текущих бонусов» может быть и 3, и 10 — секция ограничена `max-height` с внутренним скроллом. «Постоянных» бонусов на высоких тирах эндгейма может быть уже несколько десятков — поэтому они вообще не в основном потоке страницы, а в модалке с собственным скроллом. Экран физически не может «уехать» вниз произвольно — это и был запрос: всё должно помещаться на одном экране телефона независимо от объёма прогресса игрока.

---

## 4. Компонент: `.parg-tree-strip`

```html
<div class="parg-tree-strip">
  <div class="parg-tree-item" data-tree="warrior" title="Воин">
    <span class="ico">⚔️</span><span class="lvl">5</span>
  </div>
  <div class="parg-tree-item" data-tree="shadow" title="Тень">
    <span class="ico">🗡️</span><span class="lvl">14</span>
  </div>
  <div class="parg-tree-item" data-tree="sage" title="Мудрец">
    <span class="ico">📖</span><span class="lvl">40</span>
  </div>
</div>
```

```css
.parg-tree-strip{ display:flex; background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.parg-tree-item{ flex:1; display:flex; align-items:center; justify-content:center; gap:5px; padding:6px 4px; border-right:1px solid var(--line); }
.parg-tree-item:last-child{ border-right:none; }
.parg-tree-item .lvl{ font:700 12.5px/1 var(--font-hud); color:var(--parchment); }
```

**Данные:** массив из 3 объектов `{tree: 'warrior'|'shadow'|'sage', level: number}`. Иконки/цвета — фиксированы по `tree` (маппинг в CSS через `data-tree`, не через инлайн-стили).

**Открытый вопрос (см. п.9):** кликабельны ли эти три пункта — переключают контент ниже на дерево-специфичный вид, или это просто read-only сводка. В `data-tree` уже заложен хук для клика на будущее, но обработчик сейчас не навешен.

---

## 5. Компонент: `.parg-tabbar`

```html
<div class="parg-tabbar">
  <div class="parg-tab-pill" data-active="true">✦ Совершенствование</div>
  <button class="parg-help-btn" aria-label="Как это работает">?</button>
  <div class="parg-points"><span class="cap">ОПГ</span><span class="val" id="opgValue">0</span></div>
</div>
```

**Данные:** `opgValue` — число нераспределённых очков. **Состояние:** если `opgValue > 0`, `.val` должен получать класс `.parg-points__val--active` (золотой цвет вместо приглушённого) — сейчас в макете это состояние не показано (везде 0), но CSS-крючок заложить сразу:

```css
.parg-points .val{ font:700 14px/1 var(--font-hud); color:var(--parchment-faint); }
.parg-points .val.parg-points__val--active{ color:var(--gold-bright); }
```

**Открытый вопрос:** если под "Совершенствование" реально есть соседние вкладки (сейчас показана только одна, активная) — нужен список остальных вкладок, чтобы сверстать полноценный таббар, а не один статичный pill.

---

## 6. Компонент: `.parg-tier-card` + `.parg-choose-btn`

```html
<div class="parg-tier-card">
  <div class="parg-tier-seal" id="tierSeal">3</div>
  <div class="parg-tier-mid">
    <div class="parg-tier-title-row">
      <span class="n" id="tierTitle">Совершенствование · Тир 1</span>
      <span class="p" id="tierPct">90%</span>
    </div>
    <div class="parg-exp-bar"><div class="fill" id="expFill" style="--pct:90%"></div></div>
    <div class="parg-exp-readout" id="expReadout">12 537 / 13 895 EXP</div>
  </div>
</div>
<button class="parg-choose-btn" id="chooseBonusBtn" disabled>
  🔒 Выбрать бонус — ещё <span id="expRemaining">1 358</span> EXP
</button>
```

**Данные / контракт:**

| Элемент | Источник | Формат |
|---|---|---|
| `#tierSeal` | текущий уровень совершенствования (тот же, что в шапке — см. открытый вопрос п.1) | целое число |
| `#tierTitle` | название системы + `· Тир {N}` | строка |
| `#tierPct`, `--pct` на `.fill` | `currentExp / requiredExp * 100`, округление до целого | 0–100 |
| `#expReadout` | `currentExp` и `requiredExp` с разделением тысяч пробелом (рус. локаль) | `"12 537 / 13 895 EXP"` |
| `#expRemaining` | `requiredExp - currentExp` | число |
| `#chooseBonusBtn[disabled]` | `true`, если `opgValue === 0` **и/или** тир ещё не пройден — уточнить точное условие разблокировки (см. п.9) | boolean |

**Состояние "доступно":**

```css
.parg-choose-btn.locked{ background:var(--panel-2); border:1px solid var(--line); color:var(--parchment-faint); cursor:not-allowed; }
.parg-choose-btn.ready{ background:linear-gradient(180deg, var(--gold-bright), var(--gold)); color:#241708; box-shadow:0 4px 12px rgba(226,169,63,.35); }
```

JS-обработчик клика на `.ready`-состоянии этой кнопки открывает экран выбора бонуса — **этот экран не спроектирован в рамках текущего ТЗ**, см. п.10.

---

## 7. Компонент: `.parg-buffs-block` («Текущие бонусы»)

```html
<div class="parg-buffs-block">
  <div class="parg-sec-row">
    <h3 class="parg-sec-title">Текущие бонусы</h3>
    <span class="parg-sec-count" id="buffCount">0</span>
  </div>
  <div class="parg-buff-scroll">
    <div class="parg-buff-grid" id="buffGrid"><!-- рендерится JS --></div>
  </div>
</div>
```

Одна карточка бонуса (рендерится в цикле по массиву от бэкенда):

```html
<div class="parg-buff-chip parg-buff-chip--int">
  <span class="ico">🧠</span>
  <span class="name">+ИНТ</span>
  <span class="val">+20</span>
</div>
```

**Контракт данных:** массив объектов `{icon: string, name: string, value: string, kind: 'int'|'crit'|'gold'|'neutral'}`. `kind` определяет цвет `.val` (см. CSS ниже) — если у бонуса нет очевидной категории, использовать `neutral` (цвет по умолчанию, без покраски).

```css
.parg-buff-scroll{ position:relative; max-height:158px; overflow-y:auto; border-radius:10px; }
.parg-buff-grid{ display:grid; grid-template-columns:1fr 1fr; gap:5px; }
.parg-buff-chip{ display:flex; align-items:center; gap:5px; height:32px; padding:0 8px; border-radius:8px; background:var(--panel); border:1px solid var(--line); min-width:0; }
.parg-buff-chip .name{ flex:1; min-width:0; font:600 10px/1.1 var(--font-body); color:var(--parchment-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.parg-buff-chip .val{ font:700 11.5px/1 var(--font-hud); color:var(--parchment); }
.parg-buff-chip--int .val{ color:var(--arcane-bright); }
.parg-buff-chip--crit .val{ color:var(--ember-bright); }
.parg-buff-chip--gold .val{ color:var(--gold-bright); }
```

**Важно про `max-height:158px`.** Это жёстко подобранное число под сетку 2×2 видимых рядов на телефонном экране — если в проекте есть другие точки breakpoint'ов (например, отдельная раскладка для планшетов/десктоп-теста в Telegram Web), стоит завести это значение в CSS-переменную (`--buff-scroll-max-h`) и переопределять в media query, а не хардкодить в одном месте.

**Проверить при 0 бонусов:** сейчас пустое состояние не предусмотрено. Добавить: если массив пуст — показать одну строку-заглушку на всю ширину грида (`grid-column: 1 / -1`) вида «Пока нет активных бонусов» вместо пустого `158px`-провала.

---

## 8. Компонент: триггер + модалка «Постоянные бонусы»

### 8.1 Триггер на основном экране

```html
<button class="parg-permanent-trigger" id="openPermanent">
  <div class="parg-stack-avatars" id="stackAvatars"><!-- до 3 медальонов, рендерится JS --></div>
  <div class="txt">
    <span class="title">Постоянные бонусы</span>
    <span class="sub" id="permanentSub">3 получено · тир 1</span>
  </div>
  <span class="arrow">›</span>
</button>
```

**Контракт:** `stackAvatars` — иконки первых 2–3 полученных бонусов (для превью), `permanentSub` — `"{count} получено · тир {maxTier}"`.

### 8.2 Модалка списка

```html
<div class="parg-modal" id="permanentModal" role="dialog" aria-modal="true" aria-labelledby="permanentModalTitle">
  <div class="parg-modal-backdrop"></div>
  <div class="parg-list-modal">
    <div class="parg-list-modal-head">
      <h2 id="permanentModalTitle">Постоянные бонусы</h2>
      <button class="parg-sheet-close" aria-label="Закрыть">✕</button>
    </div>
    <div class="parg-list-modal-body" id="permanentList"><!-- node-card × N, рендерится JS --></div>
  </div>
</div>
```

Одна карточка бонуса в модалке:

```html
<div class="parg-node-card">
  <div class="top">
    <div class="parg-node-medal parg-node-medal--int">🧠</div>
    <div class="info"><div class="name">+ИНТ</div><div class="val">+20</div></div>
    <div class="tier">ур. 1</div>
  </div>
  <button class="parg-respec-btn" data-node-id="{id}" data-cost="{cost}">🔄 Переназначить</button>
</div>
```

**Контракт:** массив `{id, icon, name, value, kind, tier, respecCost}`. `respecCost` — **из реальной формулы cost scaling для paragon respec** (в проекте она уже спроектирована, см. память по эндгейм-экономике) — числа `1800/2400/3100` в макете чисто иллюстративные, не использовать как реальные значения.

**Производительность на эндгейме.** На высоких тирах (60+ уровень) этих карточек может стать много (десятки). `.parg-list-modal-body` уже `overflow-y:auto`, но при большом N стоит рассмотреть виртуализацию рендера (рендерить только видимые + буфер) — учитывая уже задокументированную в проекте чувствительность к перформансу этой же страницы (`dungeons.html`, HAR-аудит), не стоит наступать на те же грабли здесь на новом экране. Порог, с которого включать виртуализацию — ориентировочно 30+ карточек, точную границу подобрать по факту.

### 8.3 Модалка подтверждения (поверх списка)

Открывается по клику на `.parg-respec-btn`, **не закрывая** модалку списка (два независимых слоя, второй с более высоким `z-index`):

```html
<div class="parg-modal parg-modal--confirm" id="respecModal" role="dialog" aria-modal="true">
  <div class="parg-modal-backdrop"></div>
  <div class="parg-confirm-modal">
    <div class="cap">Переназначение бонуса</div>
    <h2 id="respecTitle">—</h2>
    <p id="respecDesc">—</p>
    <div class="parg-confirm-cost">🪙 <span id="respecCost">—</span></div>
    <div class="foot">
      <button class="parg-btn-cancel" id="respecCancel">Отмена</button>
      <button class="parg-btn-primary" id="respecOk" data-node-id="">Подтвердить</button>
    </div>
  </div>
</div>
```

```css
#permanentModal{ z-index:200; }
#respecModal{ z-index:220; }
```

**По подтверждению (`#respecOk`):** вызов реального API респека с `node-id` из `data-node-id`, дождаться ответа, обновить список в `#permanentList` и агрегированные `.parg-buff-chip` в `#buffGrid` (после респека изменится и сводка "Текущие бонусы", раз в неё, судя по всему, суммируются активные постоянные бонусы), закрыть только `#respecModal`, оставить `#permanentModal` открытым.

**Accessibility:** обе модалки — потенциальный фокус-трап. Проверить, что `Tab`/`Shift+Tab` не убегают за пределы верхней открытой модалки, и что `Esc`/тап по backdrop закрывают только верхний слой, не оба сразу.

---

## 9. QA-чеклист

- [ ] Экран целиком помещается без скролла страницы на вьюпорте ~375×667 (iPhone SE — самый тесный частый кейс) и ~360×740 (частый Android). Если не помещается — сначала сокращать `.parg-buff-scroll { max-height }`, а не убирать элементы.
- [ ] `.parg-buff-grid` корректно рендерит 1, 3, 10, 30 бонусов — сетка не ломается, скролл появляется/пропадает по необходимости, пустое состояние (п.7) показывается при 0.
- [ ] `.parg-list-modal-body` со скроллом — свайп внутри модалки не триггерит закрытие/scroll фонового экрана (частый баг с `overscroll-behavior` в Telegram WebView — задать `overscroll-behavior: contain` на `.parg-list-modal-body`).
- [ ] Клик на `.parg-respec-btn` → модалка подтверждения открывается **поверх**, список остаётся открытым и видимым под ней (проверить визуально, что бэкдроп подтверждения не выглядит как двойное затемнение).
- [ ] Отмена в модалке подтверждения не теряет прокрутку списка постоянных бонусов (если юзер долистал вниз, после закрытия confirm-модалки список не должен прыгать наверх).
- [ ] `.parg-choose-btn` — оба состояния (`locked`/`ready`) визуально различимы без цвета (для читаемости при плохой яркости экрана) — есть 🔒 иконка на заблокированном, не только цвет.
- [ ] `prefers-reduced-motion: reduce` — если добавляли пульсацию/анимации на `.ready`-кнопку, отключается.
- [ ] Фокус-стейты (`:focus-visible`) видны на всех интерактивных элементах — плитки деревьев, `?`, кнопки в модалках.
- [ ] Числа с разделением тысяч (`12 537`) — корректный пробел-разделитель, не запятая/точка (важно для рус. локали проекта).

---

## 10. Открытые вопросы

**10.1 — Реальный файл/структура.** См. п.0. Без него весь документ — целевая спецификация, а не диф.

**10.2 — Семантика бейджа «3» у аватара в шапке** и совпадает ли эта шапка технически с `.attic` из dungeons.html, или это отдельная реализация, которую тоже придётся сводить к общей.

**10.3 — Кликабельность `.parg-tree-strip`.** Три дерева — это фильтр контента ниже (тогда нужен полноценный state-переключатель и, вероятно, у каждого дерева свой независимый тир/EXP/бонусы) или чисто справочная сводка. От ответа зависит, remain ли `.parg-tier-card`/`.parg-buffs-block` синглтоном или их нужно параметризовать по дереву.

**10.4 — Условие разблокировки `.parg-choose-btn`.** Сейчас в макете это просто "EXP до порога", но `ОПГ 0` в шапке намекает, что может быть отдельная валюта очков, не совпадающая с EXP-баром напрямую. Уточнить точную формулу/условие.

**10.5 — Экран выбора бонуса.** Кнопка "Выбрать бонус" в `.ready`-состоянии должна что-то открывать — этот флоу не спроектирован ни в одном из макетов. Если бонусы на выбор — фиксированный список 2-3 опций (как в Diablo-подобных играх) — это отдельная итерация дизайна, логично сделать её следующим шагом.

**10.6 — Модель "бонус выбирается или назначается автоматически".** В памяти проекта это было открытым вопросом эндгейм-экономики. Судя по связке "Выбрать бонус" (разовый выбор при разблокировке) + "Переназначить" (респек постфактum) на этом экране — похоже на модель "игрок выбирает при получении, может перевыбрать за валюту" (не случайная выдача). Стоит свериться с актуальной версией дизайн-документа эндгейм-экономики, чтобы не разойтись.

**10.7 — Реальная формула стоимости респека.** Числа 1800/2400/3100 в макете — заглушки. Подставить формулу cost scaling, которая уже спроектирована для paragon respec (см. память проекта).

**10.8 — Порог виртуализации списка** в п.8.2 — 30 карточек ориентировочно, нужно эмпирически проверить на реальном тестовом аккаунте с максимальным прогрессом.
