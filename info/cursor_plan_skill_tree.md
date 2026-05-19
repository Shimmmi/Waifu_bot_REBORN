# ТЗ для CURSOR: Дерево навыков ОВ (training_hall.html)

---

## БД

### Таблица passive_skill_nodes (справочник — уже описана в cursor_plan_skills.md)

Дополнить данными всех 33 навыков (3 ветки × 11 навыков):

```sql
TRUNCATE passive_skill_nodes CASCADE;
INSERT INTO passive_skill_nodes
  (id, branch, tier, position, name, max_level,
   waifu_level_req, branch_points_req,
   effect_type, effect_values, cost_gold, description) VALUES

-- ── ВОИН ──────────────────────────────────────────────────────
('w_bash',    'warrior',1,1,'Удар',           3,1, 0, 'melee_dmg_pct',    '[0.06,0.13,0.22]',      200,'Урон ближнего боя'),
('w_tough',   'warrior',1,2,'Закалка',        3,1, 0, 'armor_pct',         '[0.04,0.09,0.15]',      200,'Броня от снаряжения'),
('w_cry',     'warrior',1,3,'Боевой дух',     3,1, 0, 'hp_max_pct',        '[0.03,0.07,0.12]',      200,'Максимум HP'),
('w_heavy',   'warrior',2,1,'Тяжёлый удар',   4,10,5, 'stun_chance',       '[0.08,0.17,0.28,0.42]', 400,'Шанс оглушить монстра'),
('w_iron',    'warrior',2,2,'Железная кожа',  4,10,5, 'dmg_reduce_pct',    '[0.03,0.07,0.12,0.18]', 400,'Снижение получаемого урона'),
('w_blood',   'warrior',2,3,'Кров. ярость',   4,10,5, 'low_hp_dmg_pct',    '[0.10,0.22,0.36,0.54]', 400,'Урон при HP < 50%'),
('w_berserk', 'warrior',3,1,'Берсерк',        4,25,15,'hp_loss_dmg_pct',   '[0.15,0.32,0.52,0.78]', 700,'Урон за каждые 10% потер. HP'),
('w_fort',    'warrior',3,2,'Крепость',       4,25,15,'armor_and_reduce',  '[0.05,0.11,0.18,0.27]', 700,'Броня + снижение урона'),
('w_last',    'warrior',3,3,'Последний рубеж',4,25,15,'survive_chance',    '[0.15,0.25,0.38,0.55]', 700,'Выжить с 1 HP (1р/данж)'),
('w_wrath',   'warrior',4,1,'Гнев героя',     5,40,30,'crit_dmg_melee_pct','[0.20,0.38,0.60,0.88,1.25]',1800,'Крит урон ближнего боя'),
('w_imm',     'warrior',4,2,'Бессмертный',    5,40,30,'hp_on_kill_pct',    '[0.08,0.15,0.23,0.33,0.45]',1800,'HP при убийстве монстра'),

-- ── ТЕНЕВОЙ ───────────────────────────────────────────────────
('s_keen',    'shadow', 1,1,'Острый глаз',    3,1, 0, 'crit_chance_pct',   '[0.04,0.09,0.15]',      200,'Шанс крита'),
('s_nimble',  'shadow', 1,2,'Проворство',     3,1, 0, 'evade_pct',          '[0.03,0.07,0.12]',      200,'Шанс уклонения'),
('s_media',   'shadow', 1,3,'Чутьё',          3,1, 0, 'media_dmg_pct',      '[0.08,0.17,0.28]',      200,'Урон медиа-атак'),
('s_crit_m',  'shadow', 2,1,'Мастер крита',   4,10,5, 'crit_mult_add',      '[0.2,0.4,0.7,1.1]',     400,'Множитель крита'),
('s_shadow',  'shadow', 2,2,'Шаг тени',       4,10,5, 'full_evade_chance',  '[0.10,0.20,0.33,0.50]', 400,'Иммунитет к удару монстра'),
('s_exploit', 'shadow', 2,3,'Уязвимость',     4,10,5, 'debuff_dmg_pct',     '[0.12,0.26,0.43,0.65]', 400,'Урон по монстрам с аффиксами'),
('s_nth',     'shadow', 3,1,'Серия смерти',   4,25,15,'nth_hit_crit',       '[4,3,3,2]',              700,'Каждый N-й удар — крит'),
('s_ghost',   'shadow', 3,2,'Призрак',        4,25,15,'revive_chance',      '[0.15,0.28,0.44,0.65]', 700,'Ожить с 10% HP при смерти'),
('s_amp',     'shadow', 3,3,'Усил. медиа',    4,25,15,'media_mult_bonus',   '[0.15,0.32,0.52,0.78]', 700,'Урон медиа × (поверх коэф.)'),
('s_lethal',  'shadow', 4,1,'Смерт. удар',    5,40,30,'instakill_chance',   '[0.05,0.10,0.17,0.26,0.38]',1800,'Мгнов. убийство (не боссы)'),
('s_phantom', 'shadow', 4,2,'Фантом',         5,40,30,'first_hit_dmg_pct',  '[0.25,0.48,0.75,1.10,1.55]',1800,'Урон 1-го удара по монстру'),

-- ── МУДРЕЦ ────────────────────────────────────────────────────
('m_arcane',  'sage',   1,1,'Аркана',         3,1, 0, 'magic_dmg_pct',      '[0.06,0.13,0.22]',      200,'Урон магических атак'),
('m_wisdom',  'sage',   1,2,'Мудрость',       3,1, 0, 'exp_bonus_pct',       '[0.04,0.09,0.15]',      200,'Получаемый опыт'),
('m_trade',   'sage',   1,3,'Торговец',       3,1, 0, 'trade_flat',          '[8,18,30]',              200,'Навык Торговли (плоско)'),
('m_media_m', 'sage',   2,1,'Медиамаг',       4,10,5, 'media_no_charge_pct','[0.30,0.55,0.90,1.25]', 400,'Медиа без расхода заряда'),
('m_lore',    'sage',   2,2,'Знания',         4,10,5, 'boss_reward_pct',     '[0.06,0.13,0.22,0.33]', 400,'Опыт и золото с боссов'),
('m_bargain', 'sage',   2,3,'Сделка',         4,10,5, 'shop_discount_pct',   '[0.04,0.09,0.15,0.22]', 400,'Скидка магазин/найм'),
('m_surge',   'sage',   3,1,'Маг. всплеск',   4,25,15,'media_after_text_pct','[0.20,0.38,0.60,0.88]', 700,'Медиа после 3 текст. ударов'),
('m_cmd',     'sage',   3,2,'Командование',   4,25,15,'expedition_bonus_pct','[0.08,0.17,0.28,0.42]', 700,'Шанс/награды экспедиций'),
('m_rune',    'sage',   3,3,'Рун. броня',     4,25,15,'int_dmg_reduce',      '[0.05,0.10,0.16,0.24]', 700,'Снижение урона от ИНТ'),
('m_trans',   'sage',   4,1,'Трансценд.',     5,40,30,'all_stats_pct',       '[0.12,0.22,0.34,0.50,0.70]',1800,'Все параметры ОВ'),
('m_arch',    'sage',   4,2,'Архимаг',        5,40,30,'active_skill_dmg_pct','[0.30,0.58,0.90,1.30,1.80]',1800,'Урон активных навыков');
```

### Прогресс игрока (уже описана, дополнение):

```sql
-- Убедиться что есть поле skill_points в players
ALTER TABLE players ADD COLUMN IF NOT EXISTS skill_points INT NOT NULL DEFAULT 0;

-- При левелапе ОВ: skill_points += 1
-- При сбросе ветки: вернуть потраченные очки
```

---

## Backend

### GET /api/skills/passive/tree

```python
@router.get("/api/skills/passive/tree")
async def get_skill_tree(player_id: int = Depends(get_current_player), db = Depends(get_db)):
    # Все узлы
    all_nodes = await db.execute("SELECT * FROM passive_skill_nodes ORDER BY branch, tier, position")

    # Что изучено
    learned = await db.execute(
        "SELECT node_id, level FROM player_passive_skills WHERE player_id = :pid",
        {"pid": player_id}
    )
    learned_map = {r.node_id: r.level for r in learned.fetchall()}

    # Потрачено в каждую ветку
    branch_pts = {"warrior":0,"shadow":0,"sage":0}
    for node_id, lvl in learned_map.items():
        node = next((n for n in all_nodes if n.id == node_id), None)
        if node:
            branch_pts[node.branch] += lvl

    # Уровень ОВ
    player = await db.get(Player, player_id)

    result = {}
    for node in all_nodes:
        current_level  = learned_map.get(node.id, 0)
        bp             = branch_pts[node.branch]
        can_learn      = (
            player.level >= node.waifu_level_req
            and bp >= node.branch_points_req
            and current_level < node.max_level
            and player.skill_points > 0
        )
        result.setdefault(node.branch, []).append({
            "id":             node.id,
            "name":           node.name,
            "tier":           node.tier,
            "position":       node.position,
            "max_level":      node.max_level,
            "current_level":  current_level,
            "waifu_level_req":node.waifu_level_req,
            "branch_pts_req": node.branch_points_req,
            "effect_type":    node.effect_type,
            "effect_values":  node.effect_values,
            "cost_gold":      node.cost_gold,
            "description":    node.description,
            "can_learn":      can_learn,
            "is_locked":      player.level < node.waifu_level_req or bp < node.branch_points_req,
        })

    return {
        "branches": result,
        "skill_points": player.skill_points,
        "branch_points": branch_pts,
    }
```

### POST /api/skills/passive/learn

```python
@router.post("/api/skills/passive/learn")
async def learn_skill(body: LearnSkillRequest, player_id: int = Depends(...), db = Depends(...)):
    node  = await db.get(PassiveSkillNode, body.node_id)
    if not node:
        raise HTTPException(404)

    player = await db.get(Player, player_id)

    # Потрачено в ветку
    bp = await get_branch_points(player_id, node.branch, db)

    if player.level < node.waifu_level_req:
        raise HTTPException(400, "insufficient_waifu_level")
    if bp < node.branch_points_req:
        raise HTTPException(400, "insufficient_branch_points")
    if player.skill_points < 1:
        raise HTTPException(400, "no_skill_points")

    # Текущий уровень
    existing = await db.execute(
        "SELECT level FROM player_passive_skills WHERE player_id=:pid AND node_id=:nid",
        {"pid": player_id, "nid": node.id}
    )
    row = existing.fetchone()
    current_lvl = row.level if row else 0

    if current_lvl >= node.max_level:
        raise HTTPException(400, "skill_already_maxed")

    # Проверка золота
    if player.gold < node.cost_gold:
        raise HTTPException(400, "insufficient_gold")

    # Применить
    new_lvl = current_lvl + 1
    await db.execute("""
        INSERT INTO player_passive_skills (player_id, node_id, level)
        VALUES (:pid, :nid, 1)
        ON CONFLICT (player_id, node_id)
        DO UPDATE SET level = player_passive_skills.level + 1
    """, {"pid": player_id, "nid": node.id})

    player.skill_points -= 1
    player.gold -= node.cost_gold
    await db.commit()

    return {"ok": True, "new_level": new_lvl, "skill_points_left": player.skill_points}
```

### POST /api/skills/passive/reset/{branch}

```python
@router.post("/api/skills/passive/reset/{branch}")
async def reset_branch(branch: str, player_id: int = Depends(...), db = Depends(...)):
    # Найти все изученные навыки в ветке
    rows = await db.execute("""
        SELECT ps.node_id, ps.level, n.cost_gold
        FROM player_passive_skills ps
        JOIN passive_skill_nodes n ON n.id = ps.node_id
        WHERE ps.player_id = :pid AND n.branch = :branch
    """, {"pid": player_id, "branch": branch})

    total_points = 0
    for row in rows.fetchall():
        total_points += row.level

    cfg = await get_game_config()
    reset_cost = round(total_points * float(cfg.get('skill.reset_cost_per_point', 500)))

    player = await db.get(Player, player_id)
    if player.gold < reset_cost:
        raise HTTPException(400, "insufficient_gold")

    # Сброс
    await db.execute("""
        DELETE FROM player_passive_skills
        WHERE player_id = :pid
          AND node_id IN (SELECT id FROM passive_skill_nodes WHERE branch = :branch)
    """, {"pid": player_id, "branch": branch})

    player.skill_points += total_points
    player.gold -= reset_cost
    await db.commit()

    return {"ok": True, "points_refunded": total_points, "gold_spent": reset_cost}
```

### Применение эффектов

Добавить в функцию расчёта статов ОВ:

```python
async def get_passive_tree_bonuses(player_id: int, db) -> dict:
    rows = await db.execute("""
        SELECT n.effect_type, n.effect_values, ps.level
        FROM player_passive_skills ps
        JOIN passive_skill_nodes n ON n.id = ps.node_id
        WHERE ps.player_id = :pid AND ps.level > 0
    """, {"pid": player_id})

    bonuses = {}
    for effect_type, effect_values, level in rows.fetchall():
        value = effect_values[level - 1]  # 0-indexed
        bonuses[effect_type] = bonuses.get(effect_type, 0) + value
    return bonuses
```

Добавить в game_config:
```sql
INSERT INTO game_config VALUES
  ('skill.reset_cost_per_point', '500', 'Стоимость сброса 1 очка навыка'),
  ('skill.points_per_level', '1', 'Очков навыков за левелап ОВ');
```

---

## Frontend (training_hall.html)

Структура страницы:
1. Три вкладки: Воин / Теневой / Мудрец
2. Строка статуса: ур.ОВ, свободных очков, потрачено W/S/M
3. Дерево: 4 ряда сверху вниз, коннекторы между рядами
4. Кнопка сброса ветки (с ценой)

### Состояния узла

| Состояние | CSS-класс | Условие |
|---|---|---|
| Заблокирован | `skill-node--locked` | level < reqLvl или branch_pts < reqPts |
| Доступен | `skill-node--available` | Можно взять, level = 0 |
| Частично | `skill-node--partial` | 0 < level < max_level |
| Максимум | `skill-node--maxed` | level = max_level |

### Узел содержит

- Бейджи требований (ур.ОВ, очки в ветке) — верхний правый угол
- Название навыка
- Краткое описание
- Эффект текущего уровня (или «— (макс: X)» если не изучен)
- Pip-индикатор: N полосочек по числу max_level, заполненные — изучены
- Кнопка «+» (только если can_learn = true)

### Клик на узел

- Если can_learn = true → вызвать POST /api/skills/passive/learn
- Если locked → показать тултип «Требуется: ур.ОВ N, X очков в ветке»
- Если maxed → показать тултип «Навык максимально прокачан»

---

## Чеклист

### БД
- [ ] INSERT 33 навыков в passive_skill_nodes (SQL выше)
- [ ] ALTER TABLE players ADD skill_points
- [ ] При левелапе ОВ: skill_points += 1

### Backend
- [ ] GET /api/skills/passive/tree
- [ ] POST /api/skills/passive/learn
- [ ] POST /api/skills/passive/reset/{branch}
- [ ] get_passive_tree_bonuses() → подключить к calc_waifu_stats
- [ ] game_config: skill.reset_cost_per_point, skill.points_per_level

### Frontend
- [ ] Три вкладки в training_hall.html
- [ ] Рендер дерева: 4 ряда × 2-3 узла с CSS-коннекторами
- [ ] Состояния узлов: locked / available / partial / maxed
- [ ] Кнопка + → POST learn → перерисовать дерево
- [ ] Кнопка сброса с ценой → POST reset → перерисовать
- [ ] Строка статуса: очки ОВ/потрачено по веткам
