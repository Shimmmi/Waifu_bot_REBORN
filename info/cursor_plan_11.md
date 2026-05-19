# План для Cursor: Цветовая унификация магазина + позиция диалога

---

## Задача 1: Цветовая унификация shop.html с остальными страницами

Все страницы (tavern.html, dungeons.html) используют единую палитру.
shop.html должен выглядеть как часть того же приложения.

### CSS-переменные — добавить в начало <style> в shop.html

```css
:root {
  --ink:        #0d0a08;   /* основной фон */
  --surface:    #1a1410;   /* фон карточек */
  --surface2:   #221c16;   /* фон карточек товаров */
  --amber:      #c8922a;
  --amber-glow: #e8b84b;
  --ash:        #8a7a6a;
  --muted:      #6a5a4a;
  --cream:      #e8dcc8;
}
```

### Атрик (header.attic) — привести к единому виду

```css
/* shop.html — заменить текущие стили атрика на: */
.attic {
  background: rgba(13, 10, 8, .95);
  border-bottom: 1px solid rgba(200, 146, 42, .2);
  padding: 7px 10px;
  z-index: 50;
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}
.attic-row {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-wrap: nowrap;
  overflow: hidden;
}
.chip {
  background: rgba(255, 255, 255, .06);
  border: 1px solid rgba(200, 146, 42, .2);
  border-radius: 20px;
  padding: 3px 9px;
  font-size: 11px;
  white-space: nowrap;
  color: var(--cream);
  flex-shrink: 0;
}
.chip b, .chip strong { color: var(--amber-glow); }
```

### Карточки товаров — компактный вид

Текущие карточки слишком высокие — много пустого места.
Перестроить layout карточки:

```css
.shop-item-card {
  background: #221c16;
  border: 1px solid rgba(200, 146, 42, .18);
  border-radius: 8px;
  padding: 6px 5px 5px;
  cursor: pointer;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  transition: border-color .15s;
}

/* Цена — правый верхний угол (badge) */
.shop-item-price-badge {
  position: absolute;
  top: 4px; right: 4px;
  background: rgba(200, 146, 42, .18);
  color: var(--amber-glow);
  font-size: 9px; font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  line-height: 1.4;
}

/* Уровень — левый верхний угол (badge) */
.shop-item-level {
  position: absolute;
  top: 4px; left: 4px;
  background: rgba(0, 0, 0, .72);
  color: #999;
  font-size: 9px; font-weight: 700;
  padding: 1px 4px;
  border-radius: 4px;
  line-height: 1.4;
}

/* Цветная полоска редкости сверху карточки */
.shop-item-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  border-radius: 8px 8px 0 0;
  background: transparent;
}
.shop-item-card.rarity-uncommon::before  { background: rgba(74, 222, 128, .5); }
.shop-item-card.rarity-rare::before      { background: rgba(96, 165, 250, .5); }
.shop-item-card.rarity-epic::before      { background: rgba(192, 132, 252, .55); }
.shop-item-card.rarity-legendary::before { background: rgba(251, 191, 36, .65); }

/* Иконка — силуэт (затемнённая) */
.shop-item-icon {
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  filter: brightness(.35) saturate(.25);
  flex-shrink: 0;
}

/* Название — компактное, 2 строки макс */
.shop-item-name {
  font-size: 9.5px;
  color: #b0a090;
  text-align: center;
  line-height: 1.2;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  width: 100%;
}
```

В JS при рендере карточки убрать отдельный блок цены снизу —
цена теперь в `.shop-item-price-badge` поверх иконки:

```javascript
// renderShopItem() — новый шаблон карточки:
function renderShopItem(item) {
  return `
    <div class="shop-item-card rarity-${item.rarity}"
         onclick="WaifuApp.openShopItemModal(${item.id})">
      <div class="shop-item-level">${item.level}</div>
      <div class="shop-item-price-badge">🪙 ${item.price}</div>
      <div class="shop-item-icon">
        <!-- SVG иконка типа предмета -->
        ${getItemTypeIcon(item.item_type, item.subtype)}
      </div>
      <div class="shop-item-name">${item.name}</div>
    </div>`;
}
```

### Вкладки магазина (btabs) — унифицировать с nav

```css
.shop-btabs-wrap {
  flex-shrink: 0;
  background: rgba(13, 10, 8, .97);
  border-top: 1px solid rgba(200, 146, 42, .15);
  padding: 5px 10px;
  height: auto; /* не фиксировать */
}
.shop-btabs {
  display: flex; gap: 4px;
  background: rgba(26, 20, 14, .9);
  border: 1px solid rgba(200, 146, 42, .2);
  border-radius: 12px;
  padding: 4px;
}
.shop-btab {
  flex: 1; padding: 7px 4px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
  color: var(--muted);
  font-size: 10.5px; font-weight: 700;
  cursor: pointer; transition: all .18s; text-align: center;
}
.shop-btab.active {
  background: rgba(200, 146, 42, .15);
  border-color: rgba(200, 146, 42, .35);
  color: var(--amber-glow);
}
```

### Навигация (nav.basement) — проверить цвета

```css
.nav.basement {
  background: rgba(13, 10, 8, .99);
  border-top: 1px solid rgba(200, 146, 42, .12);
}
.nav.basement a {
  color: var(--muted); /* #6a5a4a */
}
.nav.basement a[data-page="shop"],
.nav.basement a:hover {
  color: var(--amber-glow);
  background: rgba(200, 146, 42, .08);
}
```

---

## Задача 2: Позиция диалога торговца

Диалог должен появляться в **нижней правой части** экрана —
в свободной зоне справа от торговца, прямо над вкладками магазина.
Хвостик пузыря направлен вниз-влево к телу торговца.

### CSS изменение в shop.html

```css
/* БЫЛО: */
.shop-dialog {
  position: fixed;
  top: 52px; left: 10px; right: 10px;
  /* ... */
  transform: translateY(-6px) scale(.96);
}

/* СТАЛО: */
.shop-dialog {
  position: fixed;
  bottom: 116px;  /* над btabs(~52px) + nav(~52px) + зазор */
  left: 108px;    /* правее торговца */
  right: 10px;
  background: rgba(255, 248, 215, .97);
  border: 2px solid #c8922a;
  border-radius: 14px;
  padding: 10px 12px 9px;
  z-index: 1100;
  pointer-events: none;
  opacity: 0;
  transform: translateY(6px) scale(.97);  /* всплывает снизу */
  transition: opacity .22s ease, transform .22s ease;
}
.shop-dialog.show {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
}

/* Хвостик — вниз-влево к торговцу */
.shop-dialog::before {
  content: '';
  position: absolute;
  bottom: -11px; left: 18px;
  border: 6px solid transparent;
  border-top-color: rgba(255, 248, 215, .97);
}
.shop-dialog::after {
  content: '';
  position: absolute;
  bottom: -15px; left: 16px;
  border: 7px solid transparent;
  border-top-color: #c8922a;
}
```

### Если высота nav или btabs отличается от 52px

Подправить `bottom` по формуле:
```
bottom = высота_.nav + высота_.shop-btabs-wrap + 8px (зазор)
```
Пример: nav=56px, btabs=48px → `bottom: 112px`

---

## Итоговый чеклист

### CSS
- [ ] Добавить CSS-переменные (--ink, --amber, --amber-glow, --surface2, --cream, --muted)
- [ ] Атрик: `background: rgba(13,10,8,.95)`, chips с amber border, strong → amber-glow
- [ ] Карточки: убрать нижнюю строку с ценой, перенести цену в badge top-right
- [ ] Карточки: добавить 2px цветную полоску сверху по редкости
- [ ] Карточки: иконка filter brightness(.35) saturate(.25) — силуэт
- [ ] btabs: dark background, amber active state
- [ ] nav: muted неактивные, amber-glow активная с rgba bg
- [ ] Dialog: `bottom: 116px; left: 108px; right: 10px` (над btabs+nav)
- [ ] Dialog хвостик: `bottom: -11px; left: 18px` (вниз-влево)

### JS
- [ ] renderShopItem() — новый шаблон: level badge left, price badge right, name снизу
- [ ] Убрать отдельный элемент `.shop-item-price` снизу карточки
