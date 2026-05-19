# ТЗ для CURSOR: Система навыков ОВ

---

## Два независимых блока

1. **Дерево пассивных навыков** — training_hall.html, очки за левелап
2. **Скрытые навыки** — Morrowind-стиль, открываются/прокачиваются автоматически

---

## БЛОК 1: Дерево пассивных навыков

### БД: таблица passive_skill_nodes

```sql
CREATE TABLE IF NOT EXISTS passive_skill_nodes (
    id          VARCHAR(32) PRIMARY KEY,
    branch      VARCHAR(16) NOT NULL,  -- 'warrior' | 'shadow' | 'sage'
    position    INT NOT NULL,          -- 1-5 в ветке
    name        VARCHAR(64) NOT NULL,
    effect_type VARCHAR(32) NOT NULL,
    effect_value FLOAT NOT NULL,
    cost_points INT NOT NULL DEFAULT 1,
    cost_gold   INT NOT NULL,
    requires_node VARCHAR(32) REFERENCES passive_skill_nodes(id)
);

INSERT INTO passive_skill_nodes VALUES
-- Воин
('war_1','warrior',1,'Грубая сила',   'melee_dmg_pct',   0.08, 1, 200,  NULL),
('war_2','warrior',2,'Закалка',        'armor_pct',        0.10, 1, 400,  'war_1'),
('war_3','warrior',3,'Берсерк',        'low_hp_dmg_pct',   0.20, 1, 700,  'war_2'),
('war_4','warrior',4,'Несокрушимый',   'flat_dmg_reduce',  0.05, 1, 1100, 'war_3'),
('war_5','warrior',5,'Боевой клич',    'once_per_dungeon', 0.50, 2, 1800, 'war_4'),
-- Теневой
('sha_1','shadow', 1,'Острый глаз',   'crit_chance_pct',  0.05, 1, 200,  NULL),
('sha_2','shadow', 2,'Скользкий',      'evade_pct',        0.04, 1, 400,  'sha_1'),
('sha_3','shadow', 3,'Крит. мастерство','crit_mult_add',  0.30, 1, 700,  'sha_2'),
('sha_4','shadow', 4,'Тёмная жатва',   'item_drop_pct',    0.15, 1, 1100, 'sha_3'),
('sha_5','shadow', 5,'Смертельный танец','nth_hit_crit',   5.00, 2, 1800, 'sha_4'),
-- Мудрец
('sag_1','sage',   1,'Знание — сила', 'magic_dmg_pct',    0.08, 1, 200,  NULL),
('sag_2','sage',   2,'Усиление медиа', 'media_dmg_pct',   0.15, 1, 400,  'sag_1'),
('sag_3','sage',   3,'Опытный',        'exp_bonus_pct',    0.10, 1, 700,  'sag_2'),
('sag_4','sage',   4,'Торговая хватка','trade_flat',       20.0, 1, 1100, 'sag_3'),
('sag_5','sage',   5,'Архимаг',        'media_no_charge_pct',0.30,2,1800,'sag_4');
```

### БД: прогресс игрока

```sql
CREATE TABLE IF NOT EXISTS player_passive_skills (
    player_id INT REFERENCES players(id),
    node_id   VARCHAR(32) REFERENCES passive_skill_nodes(id),
    learned_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_id, node_id)
);

-- Счётчик очков навыков (выдаётся за левелап ОВ)
ALTER TABLE players ADD COLUMN IF NOT EXISTS skill_points INT NOT NULL DEFAULT 0;
-- При левелапе: skill_points += 1
```

### Backend: эндпоинты

```
GET  /api/skills/passive/tree
     → все узлы + для игрока: learned: bool, can_learn: bool, missing_prereq: str|null

POST /api/skills/passive/learn
     Body: { "node_id": "war_3" }
     Checks: has prereq learned, has skill_points >= cost_points, has gold >= cost_gold
     → { "ok": true, "new_skill_points": N, "effect_applied": "..." }
```

### Backend: применение эффектов

Найти функцию расчёта статов ОВ (`calc_waifu_stats` или аналог).
Добавить суммирование learned passive nodes:

```python
async def get_passive_bonuses(player_id: int, db) -> dict:
    nodes = await db.execute(
        """SELECT n.effect_type, n.effect_value
           FROM player_passive_skills ps
           JOIN passive_skill_nodes n ON n.id = ps.node_id
           WHERE ps.player_id = :pid""",
        {"pid": player_id}
    )
    bonuses = {}
    for etype, evalue in nodes.fetchall():
        bonuses[etype] = bonuses.get(etype, 0) + evalue
    return bonuses
```

### Frontend: training_hall.html — дерево навыков

Три колонки (по одной на ветку), 5 узлов сверху вниз, соединённые линиями.
Узел: карточка с иконкой, названием, эффектом. Цвет: серый (недоступен), янтарный (можно взять), золотой (изучен).

```javascript
function renderSkillTree(treeData, learnedIds) {
  const branches = { warrior: '⚔️ Воин', shadow: '🗡️ Теневой', sage: '🔮 Мудрец' };
  // treeData: { warrior: [node1..5], shadow: [...], sage: [...] }
  // learnedIds: Set<string>

  return Object.entries(branches).map(([branch, label]) => `
    <div class="skill-branch">
      <div class="branch-title">${label}</div>
      ${treeData[branch].map((node, i) => {
        const learned   = learnedIds.has(node.id);
        const canLearn  = node.can_learn;
        const state     = learned ? 'learned' : canLearn ? 'available' : 'locked';
        return `
          <div class="skill-node skill-node--${state}"
               onclick="WaifuApp.openSkillNode('${node.id}')">
            <div class="skill-node-name">${node.name}</div>
            <div class="skill-node-effect">${node.effect_description}</div>
            ${!learned ? `<div class="skill-node-cost">
              ${node.cost_points} очко · 🪙 ${node.cost_gold}
            </div>` : ''}
          </div>
          ${i < 4 ? '<div class="skill-connector"></div>' : ''}`;
      }).join('')}
    </div>`
  ).join('');
}
```

---

## БЛОК 2: Скрытые навыки (Morrowind-стиль)

### БД: справочник навыков

```sql
CREATE TABLE IF NOT EXISTS hidden_skill_definitions (
    id                 VARCHAR(32) PRIMARY KEY,
    name               VARCHAR(64) NOT NULL,
    icon               VARCHAR(8),
    category           VARCHAR(32),
    description        TEXT,
    unlock_description TEXT,
    counter_type       VARCHAR(32) NOT NULL,
    -- Пороги и эффекты как JSON-массивы из 5 элементов
    thresholds         JSONB NOT NULL,  -- [100, 1000, 2500, 5000, 10000]
    effect_types       JSONB NOT NULL,  -- ["dmg_text_pct", ...]
    effect_values      JSONB NOT NULL   -- [2, 4, 7, 11, 16]
);

CREATE TABLE IF NOT EXISTS player_hidden_skills (
    player_id     INT REFERENCES players(id),
    skill_id      VARCHAR(32) REFERENCES hidden_skill_definitions(id),
    counter       BIGINT NOT NULL DEFAULT 0,
    level         INT NOT NULL DEFAULT 0,
    unlocked_at   TIMESTAMP,
    last_level_up TIMESTAMP,
    PRIMARY KEY (player_id, skill_id)
);

CREATE INDEX ON player_hidden_skills (player_id);
```

### Начальное заполнение справочника

```sql
INSERT INTO hidden_skill_definitions VALUES
('chatterbox','Болтун','💬','Активность','Мастер словесного боя',
 '100 сообщений в подземельях', 'dungeon_messages',
 '[100,1000,2500,5000,10000]','["dmg_text_pct"]','[2,4,7,11,16]'),

('early_bird','Ранняя пташка','🌅','Активность','Бонус за ранний старт',
 'Написать первым в подземелье после 6:00 МСК', 'early_days',
 '[1,7,30,90,365]','["first_hit_per_hour_pct"]','[20,35,55,80,120]'),

('marathon','Марафонец','🏃','Активность','Непрерывная активность',
 '6 часов подряд без пропуска', 'marathon_runs',
 '[1,5,15,30,60]','["hp_regen_per_active_hour"]','[5,12,22,35,50]'),

('night_owl','Ночная сова','🦉','Активность','Ночной охотник',
 'Написать в подземелье 10 раз между 00:00 и 04:00 МСК', 'night_messages',
 '[10,50,150,400,1000]','["gold_night_pct"]','[10,20,35,55,80]'),

('consistent','Постоянство','📅','Активность','Ежедневная активность',
 '7 дней подряд с активностью в подземелье', 'active_days_streak',
 '[7,30,90,180,365]','["exp_bonus_pct"]','[3,8,15,25,40]'),

('speedster','Молния','⚡','Активность','Первый удар — смертельный',
 'Убить монстра за 1-3 сообщения (10 раз)', 'fast_kills',
 '[10,100,500,2000,5000]','["first_hit_crit_pct"]','[5,12,22,35,50]'),

('sticker_master','Стикермастер','🎭','Медиа','Мастер стикеров',
 'Нанести урон стикером 50 раз', 'sticker_hits',
 '[50,300,1000,3000,8000]','["media_sticker_mult"]','[1.0,1.1,1.25,1.45,1.7]'),

('photographer','Фотограф','📸','Медиа','Меткий снимок',
 'Нанести урон фото 30 раз', 'photo_hits',
 '[30,200,700,2000,5000]','["media_photo_mult"]','[1.3,1.5,1.75,2.1,2.6]'),

('audiophile','Меломан','🎵','Медиа','Боевой голос',
 'Нанести урон аудио 20 раз', 'audio_hits',
 '[20,100,400,1200,3000]','["media_audio_mult"]','[2.2,2.5,3.0,3.7,4.5]'),

('director','Режиссёр','🎬','Медиа','Кинематографический удар',
 'Нанести урон видео 10 раз', 'video_hits',
 '[10,60,250,800,2000]','["media_video_mult"]','[2.8,3.3,4.0,5.0,6.5]'),

('gif_fighter','Анимист','🌀','Медиа','Магия анимации',
 'Нанести урон GIF 25 раз', 'gif_hits',
 '[25,150,600,1800,4500]','["media_gif_mult"]','[1.7,2.0,2.5,3.1,4.0]'),

('executioner','Каратель','⚔️','Боевые','Добивание',
 'Убить 50 монстров', 'total_kills',
 '[50,500,2000,7000,20000]','["finisher_dmg_pct"]','[10,20,35,55,80]'),

('boss_slayer','Охотник на боссов','💀','Боевые','Гроза боссов',
 'Убить 5 боссов', 'boss_kills',
 '[5,25,100,300,750]','["boss_reward_pct"]','[10,22,38,60,90]'),

('elite_hunter','Охотник за элитой','🔵','Боевые','Охота на элиту',
 'Убить 20 элитных монстров', 'elite_kills',
 '[20,100,400,1200,3000]','["elite_drop_pct"]','[5,12,22,35,55]'),

('survivor','Выживший','💪','Боевые','Воля к жизни',
 'Получить 50%+ HP урона и выжить (10 раз)', 'near_death_survivals',
 '[10,50,200,600,1500]','["low_hp_dmg_reduce"]','[8,18,30,45,65]'),

('untouchable','Неприкасаемый','🌬️','Боевые','Недосягаемый',
 'Пройти 5 подземелий без урона', 'perfect_clears',
 '[5,20,75,200,500]','["first_hits_evade_pct"]','[10,22,38,58,85]'),

('dungeon_diver','Исследователь','🗺️','Боевые','Картограф данжей',
 'Пройти 10 уникальных подземелий', 'unique_dungeons',
 '[10,30,60,100,150]','["first_clear_exp_pct"]','[20,40,65,100,150]'),

('hoarder','Скряга','💰','Экономика','Бережливость',
 'Накопить 10k золота без трат 3 дня', 'saving_streaks',
 '[1,5,15,30,60]','["gold_drop_pct"]','[5,12,22,35,52]'),

('merchant_friend','Завсегдатай','🏪','Экономика','Постоянный клиент',
 'Купить 10 предметов в магазине', 'shop_purchases',
 '[10,75,300,1000,3000]','["shop_discount_pct"]','[2,5,9,14,20]'),

('gambler','Азартный','🎲','Экономика','Баловень судьбы',
 'Использовать Гембу 5 раз', 'gamble_uses',
 '[5,30,100,300,750]','["gamble_legendary_pct"]','[1,2.5,5,9,15]'),

('team_player','Командный игрок','🤝','Социальные','Сила в единстве',
 'Написать 50 сообщений в групповом подземелье', 'group_messages',
 '[50,300,1200,4000,10000]','["group_dmg_pct"]','[5,12,22,35,52]'),

('expedition_veteran','Ветеран экспедиций','🗺️','Социальные','Опытный командир',
 'Завершить 5 экспедиций', 'completed_expeditions',
 '[5,30,100,300,750]','["expedition_reward_pct"]','[5,12,22,35,52]'),

('loyal_commander','Верный командир','⭐','Социальные','Верность',
 'Одна наёмница участвует в 10 экспедициях', 'loyal_expeditions',
 '[10,50,150,400,1000]','["loyal_unit_success_pct"]','[3,8,15,25,40]'),

('perfectionist','Перфекционист','✨','Особые','Безупречность',
 '3 подземелья подряд без смерти ОВ', 'perfect_series',
 '[3,20,75,200,500]','["perfect_rarity_pct"]','[5,12,22,35,55]'),

('enchanter_soul','Душа кузнеца','🔨','Особые','Мастер заточки',
 'Заточить предмет до +5', 'items_at_5plus',
 '[1,5,15,30,60]','["enchant_cost_pct","enchant_chance_pct"]','[-5,-10,-18,-28,-40]'),

('legend','Легенда','👑','Особые','Вершина мастерства',
 'Иметь 10 навыков на уровне 3+', 'skills_at_5',
 '[1,2,3,4,5]','["all_stats_pct"]','[1,2,3,5,8]');
```

### Backend: сервис hidden_skills.py

```python
# services/hidden_skills.py

COUNTER_EVENTS = {
    # event_name → список skill_id которые нужно инкрементить
    'dungeon_message':     ['chatterbox', 'marathon', 'team_player'],
    'dungeon_kill':        ['executioner'],
    'boss_kill':           ['boss_slayer'],
    'elite_kill':          ['elite_hunter'],
    'fast_kill':           ['speedster'],        # 1-3 сообщения на монстра
    'perfect_dungeon':     ['untouchable', 'perfectionist'],
    'unique_dungeon':      ['dungeon_diver'],
    'near_death_survived': ['survivor'],
    'early_message':       ['early_bird'],       # после 6:00 МСК первым
    'night_message':       ['night_owl'],        # 00:00-04:00 МСК
    'sticker_hit':         ['sticker_master'],
    'photo_hit':           ['photographer'],
    'audio_hit':           ['audiophile'],
    'video_hit':           ['director'],
    'gif_hit':             ['gif_fighter'],
    'shop_purchase':       ['merchant_friend'],
    'gamble_use':          ['gambler'],
    'expedition_complete': ['expedition_veteran'],
    'loyal_expedition':    ['loyal_commander'],
    'saving_period':       ['hoarder'],
    'enchant_5plus':       ['enchanter_soul'],
    'group_message':       ['team_player'],
    # marathon, consistency, legend — отдельные cron-задачи
}

async def increment_skill_counter(
    player_id: int,
    event: str,
    amount: int = 1,
    db: AsyncSession = None,
):
    """
    Вызывается при каждом игровом событии.
    Атомарно обновляет счётчики и проверяет повышение уровня.
    """
    skill_ids = COUNTER_EVENTS.get(event, [])
    if not skill_ids:
        return

    for skill_id in skill_ids:
        # Upsert счётчика
        result = await db.execute("""
            INSERT INTO player_hidden_skills (player_id, skill_id, counter)
            VALUES (:pid, :sid, :amount)
            ON CONFLICT (player_id, skill_id)
            DO UPDATE SET counter = player_hidden_skills.counter + :amount
            RETURNING counter, level
        """, {"pid": player_id, "sid": skill_id, "amount": amount})
        row = result.fetchone()
        if not row:
            continue

        counter, current_level = row.counter, row.level
        await check_level_up(player_id, skill_id, counter, current_level, db)


async def check_level_up(player_id, skill_id, counter, current_level, db):
    """Проверяет и применяет повышение уровня навыка."""
    defn = await db.get(HiddenSkillDefinition, skill_id)
    thresholds = defn.thresholds  # [100, 1000, 2500, 5000, 10000]

    new_level = current_level
    for i, threshold in enumerate(thresholds):
        if counter >= threshold:
            new_level = i + 1

    if new_level > current_level:
        now = datetime.utcnow()
        await db.execute("""
            UPDATE player_hidden_skills
            SET level = :lvl,
                last_level_up = :now,
                unlocked_at = COALESCE(unlocked_at, :now)
            WHERE player_id = :pid AND skill_id = :sid
        """, {"lvl": new_level, "pid": player_id, "sid": skill_id, "now": now})

        # Уведомление
        is_unlock = current_level == 0
        await notify_skill_levelup(player_id, defn, new_level, is_unlock)
```

### Backend: применение эффектов скрытых навыков

```python
async def get_hidden_skill_bonuses(player_id: int, db) -> dict:
    """Суммирует все активные эффекты скрытых навыков игрока."""
    rows = await db.execute("""
        SELECT d.effect_types, d.effect_values, ps.level
        FROM player_hidden_skills ps
        JOIN hidden_skill_definitions d ON d.id = ps.skill_id
        WHERE ps.player_id = :pid AND ps.level > 0
    """, {"pid": player_id})

    bonuses = {}
    for effect_types, effect_values, level in rows.fetchall():
        for etype, evals in zip(effect_types, [effect_values]):
            value = evals[level - 1]  # значение текущего уровня
            bonuses[etype] = bonuses.get(etype, 0) + value
    return bonuses
```

### Где вызывать increment_skill_counter

```python
# services/dungeon.py — при каждом сообщении в подземелье:
await increment_skill_counter(player_id, 'dungeon_message', db=db)

# При групповом подземелье:
await increment_skill_counter(player_id, 'group_message', db=db)

# При убийстве монстра:
await increment_skill_counter(player_id, 'dungeon_kill', db=db)
if monster.is_boss:
    await increment_skill_counter(player_id, 'boss_kill', db=db)
if monster.is_elite:
    await increment_skill_counter(player_id, 'elite_kill', db=db)

# При медиа-ударе (services/dungeon.py или media handler):
media_event_map = {
    'sticker': 'sticker_hit', 'photo': 'photo_hit',
    'audio': 'audio_hit', 'video': 'video_hit', 'gif': 'gif_hit',
}
event = media_event_map.get(media_type)
if event:
    await increment_skill_counter(player_id, event, db=db)

# В shop.py при покупке:
await increment_skill_counter(player_id, 'shop_purchase', db=db)

# В enchanting.py при достижении +5:
if new_enchant_level >= 5:
    await increment_skill_counter(player_id, 'enchant_5plus', db=db)
```

---

## Чеклист

### БД
- [ ] CREATE TABLE passive_skill_nodes + INSERT данных (3 ветки × 5 узлов)
- [ ] ALTER TABLE players ADD skill_points
- [ ] CREATE TABLE player_passive_skills
- [ ] CREATE TABLE hidden_skill_definitions + INSERT 27 навыков
- [ ] CREATE TABLE player_hidden_skills + INDEX по player_id

### Backend
- [ ] GET /api/skills/passive/tree
- [ ] POST /api/skills/passive/learn (проверка prereq + points + gold)
- [ ] services/hidden_skills.py: increment_skill_counter, check_level_up, get_hidden_skill_bonuses
- [ ] Подключить increment_skill_counter в dungeon.py, shop.py, enchanting.py
- [ ] Подключить get_hidden_skill_bonuses в calc_waifu_stats (рядом с пассивным деревом)
- [ ] Telegram-уведомление при открытии/повышении уровня навыка
- [ ] Cron: марафонец (проверять раз в час), постоянство (раз в день), скряга (раз в день)

### Frontend
- [ ] training_hall.html — три ветки с узлами, линии-коннекторы, состояния locked/available/learned
- [ ] Модальное окно узла: эффект, стоимость, кнопка «Изучить»
- [ ] Счётчик очков навыков в атрике или в profile.html
- [ ] Раздел «Достижения» / скрытые навыки в profile.html вкладка 1.3
- [ ] Скрытые навыки показываются только после открытия (level > 0)
- [ ] Прогресс-бар к следующему уровню (counter / threshold_next)
