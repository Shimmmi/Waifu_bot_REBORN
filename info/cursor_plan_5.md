# ТЗ для CURSOR: Админ-кнопки, API рефреш экспедиций, UI экспедиций, модал завершения

---

## ЗАДАЧА 1: Кнопка «+1 уровень» на странице профиля ОВ (admin-only)

### Где искать
`profile.html` — найти кнопку с классом `tab-reset`:
```html
<button class="tab tab-reset" title="Сбросить вайфу" aria-label="Сбросить вайфу"
        onclick="WaifuApp.resetMainWaifu()">♻️</button>
```

### Что добавить
Рядом с этой кнопкой добавить кнопку +1 уровень. Обе видны только администратору.

```html
<!-- Найти кнопку tab-reset и добавить ПЕРЕД ней или ПОСЛЕ неё: -->
<button class="tab tab-reset admin-only"
        title="Сбросить вайфу"
        aria-label="Сбросить вайфу"
        onclick="WaifuApp.resetMainWaifu()">♻️</button>

<button class="tab tab-levelup admin-only"
        title="Повысить уровень +1"
        aria-label="Повысить уровень ОВ на 1"
        onclick="WaifuApp.adminLevelUpWaifu()">⬆️</button>
```

Убедиться что на кнопке `tab-reset` тоже стоит класс `admin-only` —
если его нет, добавить. Обе кнопки скрыты по умолчанию через CSS:
```css
.admin-only { display: none; }
```
И показываются только для администратора через JS (уже реализовано в app.js).

### Backend: добавить эндпоинт
```
POST /api/admin/waifu/levelup
Authorization: admin only
Body: {} (пустой, берёт текущего игрока из сессии)

Response: { new_level: int, new_exp_max: int, new_hp_max: int }
```

### Frontend: добавить функцию в app.js
```javascript
WaifuApp.adminLevelUpWaifu = async function() {
  try {
    const data = await WaifuApp.apiFetch('/api/admin/waifu/levelup', { method: 'POST' });
    // Обновить UI — перезагрузить профиль
    await WaifuApp.loadProfile();
    WaifuApp.showToast(`Уровень повышен до ${data.new_level}`);
  } catch (e) {
    WaifuApp.showToast('Ошибка: ' + e.message, 'error');
  }
};
```

---

## ЗАДАЧА 2: Исправить кнопку обновления экспедиций (503 → работающий endpoint)

### Симптом
```
POST https://shimmirpgbot.ru/api/admin/expeditions/refresh 503 (Service Unavailable)
```

### Где искать
`app.js` строка ~3335:
```javascript
WaifuApp.adminRefreshExpeditions = async function() { ... }
```

### Причина
Либо эндпоинт `/api/admin/expeditions/refresh` не реализован на backend,
либо реализован но падает (зависимость от базы/воркера).

### Фикс Backend
Создать (или починить) эндпоинт:
```
POST /api/admin/expeditions/refresh
Authorization: admin only

Логика:
1. Удалить текущие неиспользованные слоты игрока на сегодня
   DELETE FROM expedition_slots
   WHERE player_id = :player_id
     AND slot_date = CURRENT_DATE
     AND is_used = FALSE

2. Сгенерировать новые слоты (3 штуки: лёгкая/средняя/тяжёлая)
   — использовать существующую функцию generate_daily_slots()

3. Вернуть новые слоты
Response: { slots: [...], refreshed_at: "..." }
```

### Фикс Frontend
В `app.js` обновить `adminRefreshExpeditions`:
```javascript
WaifuApp.adminRefreshExpeditions = async function() {
  const btn = document.getElementById('expedition-admin-refresh');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

  try {
    await WaifuApp.apiFetch('/api/admin/expeditions/refresh', { method: 'POST' });
    // Перезагрузить слоты после успешного рефреша
    await WaifuApp.loadExpeditionSlots();
    WaifuApp.showToast('Экспедиции обновлены');
  } catch (e) {
    WaifuApp.showToast('Ошибка обновления: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🔄'; }
  }
};
```

---

## ЗАДАЧА 3: Редизайн UI вкладки «Экспедиции»

### Концепция
Слоты экспедиций — карточки с фоновым изображением (по биому), текст и кнопка поверх.
Стиль: тёмный, атмосферный, с эффектом глубины через gradient overlay.

### HTML: новая структура карточки слота

Заменить рендер в `renderExpeditionSlots()` / `WaifuApp.populateExpeditionsTab()`:

```javascript
function renderSlotCard(slot, chanceData) {
  const difficultyConfig = {
    1: { label: 'Лёгкая',  color: '#4ade80', star: '★☆☆',  bgClass: 'biome-forest'  },
    2: { label: 'Средняя', color: '#facc15', star: '★★☆', bgClass: 'biome-cave'    },
    3: { label: 'Средняя', color: '#facc15', star: '★★☆', bgClass: 'biome-ruins'   },
    4: { label: 'Тяжёлая', color: '#f87171', star: '★★★', bgClass: 'biome-abyss'   },
    5: { label: 'Тяжёлая', color: '#f87171', star: '★★★', bgClass: 'biome-volcano' },
  };
  const diff = difficultyConfig[slot.difficulty] || difficultyConfig[3];
  const chanceClass = !chanceData ? '' :
    chanceData.chance >= 0.6 ? 'chance-high' :
    chanceData.chance >= 0.35 ? 'chance-medium' : 'chance-low';

  const isUsed = slot.is_used;

  return `
    <div class="exp-slot-card ${diff.bgClass} ${isUsed ? 'exp-slot-used' : ''}"
         data-slot-id="${slot.id}">

      <!-- Gradient overlay -->
      <div class="exp-slot-overlay"></div>

      <!-- Top row: difficulty badge + affixes count -->
      <div class="exp-slot-top">
        <span class="exp-diff-badge" style="color:${diff.color};border-color:${diff.color}40;background:${diff.color}18">
          ${diff.star} ${diff.label}
        </span>
        ${slot.affix_count > 0
          ? `<span class="exp-affix-badge">✦ Испытание</span>`
          : ''}
      </div>

      <!-- Center: name -->
      <div class="exp-slot-name">${slot.expedition_name}</div>

      <!-- Meta row: level, rewards -->
      <div class="exp-slot-meta">
        <span>Ур. ${slot.level}</span>
        <span>🪙 ${slot.base_gold_reward}</span>
        <span>✨ ${slot.base_exp_reward}</span>
        ${chanceData
          ? `<span class="exp-chance ${chanceClass}">${chanceData.chance_pct}%</span>`
          : ''}
      </div>

      <!-- Perks needed icons -->
      ${slot.paired_perks?.length
        ? `<div class="exp-slot-perks">
             ${slot.paired_perks.slice(0,4).map(pid =>
               `<span class="exp-perk-icon" title="${PERK_NAMES?.[pid] || pid}">
                  ${PERK_ICONS?.[pid] || '✦'}
                </span>`
             ).join('')}
           </div>`
        : ''}

      <!-- Bottom: action button -->
      <div class="exp-slot-footer">
        ${isUsed
          ? `<div class="exp-slot-sent">✓ Отряд отправлен</div>`
          : `<button class="exp-send-btn" onclick="WaifuApp.openExpeditionStartModal(${slot.id})">
               Отправить отряд
             </button>`
        }
      </div>
    </div>`;
}
```

### CSS: добавить в styles.css

```css
/* ── Expedition slot cards ─────────────────────────────────── */
.expedition-slots-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.exp-slot-card {
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 14px;
  background-size: cover;
  background-position: center;
  border: 1px solid rgba(255,255,255,0.08);
  transition: transform 0.15s, box-shadow 0.15s;
}
.exp-slot-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
.exp-slot-card.exp-slot-used { opacity: 0.5; pointer-events: none; }

/* Biome backgrounds — используем CSS градиенты как fallback,
   в продакшне заменить на background-image: url('/static/biomes/{biome}.webp') */
.biome-forest  { background: linear-gradient(135deg, #1a2e0d 0%, #0d1a08 60%, #0a1506 100%); }
.biome-cave    { background: linear-gradient(135deg, #1e1a10 0%, #12100a 60%, #0a0808 100%); }
.biome-ruins   { background: linear-gradient(135deg, #1a1620 0%, #100d18 60%, #080610 100%); }
.biome-abyss   { background: linear-gradient(135deg, #100818 0%, #08040f 60%, #040208 100%); }
.biome-volcano { background: linear-gradient(135deg, #2e0d00 0%, #1a0800 60%, #100500 100%); }

/* Добавить поверх фотографии затемнение для читаемости текста */
.exp-slot-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(0,0,0,0.15) 0%,
    rgba(0,0,0,0.30) 40%,
    rgba(0,0,0,0.72) 100%
  );
  pointer-events: none;
}

/* All content above overlay */
.exp-slot-top,
.exp-slot-name,
.exp-slot-meta,
.exp-slot-perks,
.exp-slot-footer {
  position: relative;
  z-index: 1;
}

.exp-slot-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.exp-diff-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 20px;
  border: 1px solid;
  letter-spacing: 0.04em;
  backdrop-filter: blur(4px);
}

.exp-affix-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 10px;
  background: rgba(168,85,247,0.2);
  border: 1px solid rgba(168,85,247,0.4);
  color: #c084fc;
}

.exp-slot-name {
  font-size: 18px;
  font-weight: 800;
  color: #fff;
  line-height: 1.2;
  text-shadow: 0 2px 8px rgba(0,0,0,0.8);
  margin: 6px 0;
}

.exp-slot-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: rgba(255,255,255,0.7);
  align-items: center;
}

.exp-chance {
  font-weight: 700;
  font-size: 13px;
  margin-left: auto;
}
.exp-chance.chance-high   { color: #4ade80; }
.exp-chance.chance-medium { color: #facc15; }
.exp-chance.chance-low    { color: #f87171; }

.exp-slot-perks {
  display: flex;
  gap: 4px;
  margin: 4px 0;
}
.exp-perk-icon {
  width: 26px; height: 26px;
  background: rgba(0,0,0,0.5);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
  backdrop-filter: blur(4px);
  cursor: default;
}

.exp-slot-footer { margin-top: 6px; }

.exp-send-btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 10px;
  background: rgba(255,255,255,0.12);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.18);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
  letter-spacing: 0.02em;
}
.exp-send-btn:hover { background: rgba(255,255,255,0.22); }

.exp-slot-sent {
  text-align: center;
  font-size: 13px;
  color: rgba(255,255,255,0.4);
  padding: 8px;
}

/* Активная экспедиция — карточка прогресса */
.exp-active-card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 14px;
  padding: 14px;
  margin-bottom: 10px;
}
.exp-active-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #e8dcc8);
  margin-bottom: 4px;
}
.exp-active-meta {
  font-size: 12px;
  color: var(--text-muted, #8a7a6a);
  margin-bottom: 10px;
}
.exp-active-progress {
  height: 6px;
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}
.exp-active-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #a78bfa, #7c3aed);
  border-radius: 3px;
  transition: width 1s linear;
}
.exp-active-countdown {
  font-size: 13px;
  color: #a78bfa;
  font-weight: 600;
  text-align: center;
  margin-bottom: 10px;
}
.exp-active-squad {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
.exp-active-unit {
  width: 32px; height: 32px;
  background: rgba(255,255,255,0.06);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
  border: 1px solid rgba(255,255,255,0.1);
  cursor: default;
  position: relative;
}
.exp-active-unit-hp {
  position: absolute;
  bottom: -2px; left: 0; right: 0;
  height: 3px;
  background: #ef4444;
  border-radius: 0 0 8px 8px;
}
.exp-active-actions {
  display: flex;
  gap: 8px;
}
.exp-btn-claim {
  flex: 1; padding: 9px;
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  border: none; border-radius: 10px;
  color: #fff; font-size: 13px; font-weight: 700;
  cursor: pointer;
}
.exp-btn-cancel {
  padding: 9px 14px;
  background: rgba(239,68,68,0.12);
  border: 1px solid rgba(239,68,68,0.3);
  border-radius: 10px;
  color: #f87171; font-size: 13px;
  cursor: pointer;
}
```

### Биомные изображения (для продакшна)
Добавить фоновые картинки к карточкам. В nginx уже должна быть директория `/static/biomes/`:
```css
/* Когда изображения будут загружены: */
.biome-forest  { background-image: url('/static/biomes/forest.webp'); }
.biome-cave    { background-image: url('/static/biomes/cave.webp'); }
.biome-ruins   { background-image: url('/static/biomes/ruins.webp'); }
.biome-abyss   { background-image: url('/static/biomes/abyss.webp'); }
.biome-volcano { background-image: url('/static/biomes/volcano.webp'); }
```
Размер: 480×200 px WebP, качество 80%.
Пока изображений нет — CSS градиенты работают как fallback.

---

## ЗАДАЧА 4: Модальное окно результата завершённой экспедиции

### Концепция
При завершении экспедиции — показать полноэкранный модал с:
1. Анимацией загрузки пока генерируется AI-отчёт (заглушка)
2. Готовым результатом с нарративом, наградами, состоянием отряда

### HTML: добавить в dungeons.html

```html
<!-- Expedition Result Modal -->
<div id="expedition-result-modal" class="modal" style="display:none;"
     role="dialog" aria-modal="true" aria-label="Результат экспедиции">
  <div class="exp-result-sheet">
    <div class="modal-handle"></div>

    <!-- ── СОСТОЯНИЕ: ЗАГРУЗКА ── -->
    <div id="exp-result-loading" class="exp-result-loading">
      <div class="exp-result-orb">
        <div class="exp-result-orb-inner"></div>
      </div>
      <div class="exp-result-loading-title">Отряд возвращается...</div>
      <div class="exp-result-loading-sub" id="exp-result-loading-sub">
        Составляем отчёт об экспедиции
      </div>
      <div class="exp-result-loading-bar">
        <div class="exp-result-loading-fill" id="exp-result-loading-fill"></div>
      </div>
      <div class="exp-result-loading-hint">
        Пожалуйста, не закрывайте страницу
      </div>
    </div>

    <!-- ── СОСТОЯНИЕ: РЕЗУЛЬТАТ ── -->
    <div id="exp-result-content" style="display:none;">

      <!-- Outcome header -->
      <div class="exp-result-outcome" id="exp-result-outcome">
        <!-- Заполняется JS: иконка + заголовок + подзаголовок -->
      </div>

      <!-- AI narrative -->
      <div class="exp-result-narrative" id="exp-result-narrative"></div>

      <!-- Rewards -->
      <div class="exp-result-rewards" id="exp-result-rewards">
        <!-- Заполняется JS -->
      </div>

      <!-- Squad state after -->
      <div class="exp-result-squad-title">Состояние отряда после</div>
      <div class="exp-result-squad" id="exp-result-squad">
        <!-- Заполняется JS -->
      </div>

      <!-- Items found -->
      <div id="exp-result-items-wrap" style="display:none;">
        <div class="exp-result-squad-title">Найденные предметы</div>
        <div class="exp-result-items" id="exp-result-items"></div>
      </div>

      <button class="exp-result-close-btn" onclick="WaifuApp.closeExpeditionResult()">
        Забрать награду
      </button>
    </div>

  </div>
</div>
```

### CSS: добавить в styles.css

```css
/* ── Expedition Result Modal ───────────────────────────────── */
#expedition-result-modal .exp-result-sheet {
  background: var(--surface, #1a1410);
  border: 1px solid rgba(167,139,250,0.2);
  border-bottom: none;
  border-radius: 20px 20px 0 0;
  width: 100%; max-width: 480px;
  max-height: 88vh;
  overflow-y: auto;
  padding: 20px 20px 36px;
  position: relative;
}

/* Loading state */
.exp-result-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 0 8px;
}
.exp-result-orb {
  width: 80px; height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #a78bfa, #7c3aed 50%, #3b0764);
  box-shadow: 0 0 40px rgba(124,58,237,0.6), 0 0 80px rgba(124,58,237,0.2);
  animation: result-orb-pulse 2s ease-in-out infinite;
  position: relative;
}
.exp-result-orb-inner {
  position: absolute; inset: -12px;
  border-radius: 50%;
  border: 1px dashed rgba(167,139,250,0.3);
  animation: spin-slow 10s linear infinite;
}
@keyframes result-orb-pulse {
  0%,100% { transform: scale(1); box-shadow: 0 0 40px rgba(124,58,237,0.6); }
  50%      { transform: scale(1.1); box-shadow: 0 0 60px rgba(167,139,250,0.8); }
}
@keyframes spin-slow { to { transform: rotate(360deg); } }

.exp-result-loading-title {
  font-size: 18px; font-weight: 700;
  color: var(--text-primary, #e8dcc8);
  text-align: center;
}
.exp-result-loading-sub {
  font-size: 13px;
  color: var(--text-muted, #8a7a6a);
  text-align: center;
  min-height: 18px;
}
.exp-result-loading-bar {
  width: 200px; height: 4px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px; overflow: hidden;
}
.exp-result-loading-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
  border-radius: 2px;
  transition: width 0.6s ease;
  width: 0%;
}
.exp-result-loading-hint {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
  text-align: center;
  font-style: italic;
}

/* Result content */
.exp-result-outcome {
  text-align: center;
  padding: 16px 0 12px;
}
.exp-result-outcome-icon { font-size: 40px; margin-bottom: 6px; }
.exp-result-outcome-title {
  font-size: 20px; font-weight: 800;
  color: var(--text-primary, #e8dcc8);
}
.exp-result-outcome-sub { font-size: 13px; color: var(--text-muted, #8a7a6a); margin-top: 2px; }

.exp-result-narrative {
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-secondary, #c8b89a);
  font-style: italic;
  background: rgba(255,255,255,0.03);
  border-left: 2px solid rgba(167,139,250,0.4);
  border-radius: 0 8px 8px 0;
  padding: 12px 14px;
  margin: 12px 0;
}

.exp-result-rewards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 12px 0;
}
.exp-result-reward-box {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: center;
}
.exp-result-reward-label { font-size: 10px; color: var(--text-muted, #8a7a6a); text-transform: uppercase; letter-spacing: 0.06em; }
.exp-result-reward-value { font-size: 22px; font-weight: 800; color: var(--text-primary, #e8dcc8); margin-top: 2px; }
.exp-result-reward-mult  { font-size: 10px; color: var(--text-muted, #8a7a6a); margin-top: 1px; }

.exp-result-squad-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted, #8a7a6a);
  margin: 14px 0 6px;
}
.exp-result-squad { display: flex; flex-direction: column; gap: 6px; }
.exp-result-unit {
  display: flex; align-items: center; gap: 10px;
  background: rgba(255,255,255,0.04);
  border-radius: 10px;
  padding: 8px 10px;
}
.exp-result-unit-icon { font-size: 20px; width: 28px; text-align: center; }
.exp-result-unit-info { flex: 1; min-width: 0; }
.exp-result-unit-name  { font-size: 13px; font-weight: 600; color: var(--text-primary, #e8dcc8); }
.exp-result-unit-stats { font-size: 11px; color: var(--text-muted, #8a7a6a); margin-top: 1px; }
.exp-result-unit-bar {
  width: 60px; height: 4px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px; overflow: hidden; flex-shrink: 0;
}
.exp-result-unit-bar-fill { height: 100%; background: #ef4444; border-radius: 2px; }

.exp-result-items {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px;
}
.exp-result-item {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-primary, #e8dcc8);
}

.exp-result-close-btn {
  width: 100%; margin-top: 20px;
  padding: 13px;
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  border: none; border-radius: 12px;
  color: #fff; font-size: 15px; font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s;
}
.exp-result-close-btn:hover { opacity: 0.9; }
```

### JS: добавить в app.js

```javascript
// ── Expedition result modal ─────────────────────────────────

WaifuApp.openExpeditionResult = async function(expeditionId) {
  const modal   = document.getElementById('expedition-result-modal');
  const loading = document.getElementById('exp-result-loading');
  const content = document.getElementById('exp-result-content');
  const fill    = document.getElementById('exp-result-loading-fill');
  const sub     = document.getElementById('exp-result-loading-sub');

  // Показать модал в режиме загрузки
  modal.style.display = 'flex';
  loading.style.display = 'flex';
  content.style.display = 'none';

  // Анимация прогресса пока идёт генерация
  const loadingSteps = [
    [10, 'Отряд возвращается в таверну...'],
    [30, 'Считаем потери и трофеи...'],
    [55, 'Начисляем опыт наёмницам...'],
    [75, 'Рассказчик пишет историю...'],
    [90, 'Почти готово...'],
  ];

  let stepIdx = 0;
  const progressInterval = setInterval(() => {
    if (stepIdx < loadingSteps.length) {
      const [pct, text] = loadingSteps[stepIdx++];
      fill.style.width = pct + '%';
      sub.textContent  = text;
    }
  }, 600);

  try {
    // Запрос результата (backend генерирует нарратив синхронно или по polling)
    const result = await WaifuApp.apiFetch(
      `/api/expeditions/${expeditionId}/claim`,
      { method: 'POST' }
    );

    clearInterval(progressInterval);
    fill.style.width = '100%';
    sub.textContent  = 'Готово!';

    await new Promise(r => setTimeout(r, 400));

    // Заполнить контент
    WaifuApp._fillExpeditionResult(result);

    loading.style.display = 'none';
    content.style.display = 'block';

  } catch (e) {
    clearInterval(progressInterval);
    modal.style.display = 'none';
    WaifuApp.showToast('Ошибка получения наград: ' + e.message, 'error');
  }
};

WaifuApp._fillExpeditionResult = function(result) {
  const OUTCOME_CONFIG = {
    success:         { icon: '✅', title: 'Успешно завершена!',      color: '#4ade80', mult: '×1.0' },
    partial_success: { icon: '⚠️', title: 'Завершена с потерями',    color: '#facc15', mult: '×0.7' },
    failure:         { icon: '❌', title: 'Провал',                  color: '#f87171', mult: '×0.4' },
  };
  const cfg = OUTCOME_CONFIG[result.outcome] || OUTCOME_CONFIG.partial_success;

  // Outcome header
  document.getElementById('exp-result-outcome').innerHTML = `
    <div class="exp-result-outcome-icon">${cfg.icon}</div>
    <div class="exp-result-outcome-title" style="color:${cfg.color}">
      ${result.expedition_name}
    </div>
    <div class="exp-result-outcome-sub">${cfg.title}</div>`;

  // Narrative
  document.getElementById('exp-result-narrative').textContent =
    result.ai_narrative || 'Отряд вернулся из экспедиции.';

  // Rewards
  document.getElementById('exp-result-rewards').innerHTML = `
    <div class="exp-result-reward-box">
      <div class="exp-result-reward-label">Золото</div>
      <div class="exp-result-reward-value">🪙 ${result.gold_earned}</div>
      <div class="exp-result-reward-mult">${cfg.mult}</div>
    </div>
    <div class="exp-result-reward-box">
      <div class="exp-result-reward-label">Опыт наёмниц</div>
      <div class="exp-result-reward-value">✨ ${result.exp_earned}</div>
      <div class="exp-result-reward-mult">${cfg.mult}</div>
    </div>`;

  // Squad state
  document.getElementById('exp-result-squad').innerHTML =
    (result.squad_state || []).map(u => {
      const hpPct = Math.round((u.hp_current / u.hp_max) * 100);
      const needsHeal = u.hp_current < u.hp_max;
      return `
        <div class="exp-result-unit">
          <div class="exp-result-unit-icon">${u.class_icon || '⚔️'}</div>
          <div class="exp-result-unit-info">
            <div class="exp-result-unit-name">${u.name}</div>
            <div class="exp-result-unit-stats">
              ❤ ${u.hp_current}/${u.hp_max}
              ${needsHeal ? ' · <span style="color:#f87171">Нужно лечение</span>' : ' · ✓ Здорова'}
              ${u.leveled_up ? ' · <span style="color:#4ade80">⭐ Новый уровень!</span>' : ''}
            </div>
          </div>
          <div class="exp-result-unit-bar">
            <div class="exp-result-unit-bar-fill" style="width:${hpPct}%"></div>
          </div>
        </div>`;
    }).join('');

  // Items
  const itemsWrap = document.getElementById('exp-result-items-wrap');
  if (result.items_earned?.length > 0) {
    document.getElementById('exp-result-items').innerHTML =
      result.items_earned.map(item =>
        `<div class="exp-result-item">${item.emoji || '🎁'} ${item.name}</div>`
      ).join('');
    itemsWrap.style.display = 'block';
  } else {
    itemsWrap.style.display = 'none';
  }
};

WaifuApp.closeExpeditionResult = function() {
  document.getElementById('expedition-result-modal').style.display = 'none';
  // Перезагрузить вкладку экспедиций
  WaifuApp.loadExpeditionSlots?.();
  WaifuApp.loadActiveExpeditions?.();
};
```

### Где вызывать openExpeditionResult

Заменить текущий вызов при нажатии «Забрать награду» на карточке активной экспедиции:
```javascript
// БЫЛО:
onclick="WaifuApp.claimExpeditionReward(${exp.id})"

// СТАЛО:
onclick="WaifuApp.openExpeditionResult(${exp.id})"
```

---

## ИТОГОВЫЙ ЧЕКЛИСТ

### profile.html
- [ ] Добавить кнопку `tab-levelup admin-only` рядом с `tab-reset`
- [ ] Убедиться что у `tab-reset` тоже есть класс `admin-only`

### app.js
- [ ] Добавить `WaifuApp.adminLevelUpWaifu()` с вызовом POST /api/admin/waifu/levelup
- [ ] Исправить `WaifuApp.adminRefreshExpeditions()` — блокировать кнопку, показывать ошибку
- [ ] Добавить `WaifuApp.openExpeditionResult(id)` — показ модала с анимацией
- [ ] Добавить `WaifuApp._fillExpeditionResult(result)` — заполнение результата
- [ ] Добавить `WaifuApp.closeExpeditionResult()` — закрытие и перезагрузка
- [ ] При загрузке слотов получать шанс через preview API

### dungeons.html
- [ ] Обновить `renderExpeditionSlots()` — новые карточки с фоном
- [ ] Добавить модал `#expedition-result-modal`
- [ ] Кнопку «Забрать награду» направить на `openExpeditionResult(id)`

### styles.css
- [ ] Добавить все стили карточек `.exp-slot-card`
- [ ] Добавить все стили модала `.exp-result-sheet`

### Backend
- [ ] `POST /api/admin/waifu/levelup` — повысить уровень ОВ на 1
- [ ] `POST /api/admin/expeditions/refresh` — пересоздать слоты дня (починить 503)
- [ ] `POST /api/expeditions/{id}/claim` — завершить, начислить награды, вернуть result с ai_narrative
- [ ] Поле `class_icon` в ответе squad_state
- [ ] Поле `leveled_up: bool` в каждом юните squad_state если произошёл лвлап

### nginx (опционально, после готовности)
- [ ] Добавить `/static/biomes/` — WebP-фоны для карточек биомов (480×200 px)
