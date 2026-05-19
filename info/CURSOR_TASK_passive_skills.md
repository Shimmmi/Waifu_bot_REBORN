# Cursor Task: Пассивные навыки рас и классов — Вайфу-бот (Telegram IDLE RPG)

## Контекст проекта

Telegram IDLE RPG бот. Игрок управляет Основной Вайфу (ОВ), которая проходит подземелья через активность в групповом Telegram-чате:
- **Текстовое сообщение** = атака по монстру (базовый урон)
- **Медиа-сообщение** = активный навык (усиленный урон)
- **Вторичные статы** (HP, урон, крит, уклонение, Торговля, EXP, золото) рассчитываются через основные характеристики: СИЛ, ЛОВ, ИНТ, ВЫН, ОБА, УДЧ

---

## Задача

Реализовать систему пассивных навыков рас и классов. Каждый навык работает постоянно (без ручной активации) и влияет на формулы вторичных статов персонажа.

---

## Архитектура: таблица настроек в БД

Все коэффициенты навыков хранятся в таблице `skill_config`:

```sql
CREATE TABLE IF NOT EXISTS skill_config (
    key VARCHAR(64) PRIMARY KEY,
    value FLOAT NOT NULL,
    description TEXT
);
```

Начальные значения (INSERT OR IGNORE при старте бота):

```sql
-- Расовые коэффициенты
INSERT OR IGNORE INTO skill_config VALUES ('race_human_exp_bonus', 0.05, 'Человек: +5% EXP');
INSERT OR IGNORE INTO skill_config VALUES ('race_human_gold_bonus', 0.05, 'Человек: +5% золота');
INSERT OR IGNORE INTO skill_config VALUES ('race_elf_crit_flat', 0.05, 'Эльф: +5% к шансу крита');
INSERT OR IGNORE INTO skill_config VALUES ('race_elf_hp_penalty', 0.05, 'Эльф: -5% макс HP');
INSERT OR IGNORE INTO skill_config VALUES ('race_beast_nth_msg_base', 10.0, 'Зверолюд: базовое N для хищного инстинкта');
INSERT OR IGNORE INTO skill_config VALUES ('race_beast_dmg_flat', 3.0, 'Зверолюд: +плоский бонус к урону ближнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('race_beast_dodge_bonus', 0.03, 'Зверолюд: +3% к уклонению');
INSERT OR IGNORE INTO skill_config VALUES ('race_beast_sell_penalty', 0.05, 'Зверолюд: -5% к цене продажи');
INSERT OR IGNORE INTO skill_config VALUES ('race_angel_regen_mult', 1.5, 'Ангел: множитель регенерации HP');
INSERT OR IGNORE INTO skill_config VALUES ('race_angel_exp_bonus', 0.1, 'Ангел: +10% EXP');
INSERT OR IGNORE INTO skill_config VALUES ('race_angel_crit_dmg_penalty', 0.1, 'Ангел: -10% к урону крита');
INSERT OR IGNORE INTO skill_config VALUES ('race_vampire_k', 0.003, 'Вампир: K_vampir для формулы вампиризма');
INSERT OR IGNORE INTO skill_config VALUES ('race_vampire_crit_bonus', 0.05, 'Вампир: +5% к шансу крита');
INSERT OR IGNORE INTO skill_config VALUES ('race_vampire_trade_penalty', 0.1, 'Вампир: -10% к Торговле');
INSERT OR IGNORE INTO skill_config VALUES ('race_demon_skill_flat', 0.1, 'Демон: +10% к урону навыков');
INSERT OR IGNORE INTO skill_config VALUES ('race_demon_trade_penalty', 0.15, 'Демон: -15% к Торговле');
INSERT OR IGNORE INTO skill_config VALUES ('race_fairy_sell_bonus', 0.15, 'Фея: +15% к цене продажи');
INSERT OR IGNORE INTO skill_config VALUES ('race_fairy_melee_penalty', 0.1, 'Фея: -10% к урону ближнего боя');

-- Классовые коэффициенты
INSERT OR IGNORE INTO skill_config VALUES ('K_zhv', 0.3, 'Рыцарь: коэфф. снижения урона от ВЫН');
INSERT OR IGNORE INTO skill_config VALUES ('K_zhv_hp_bonus', 10.0, 'Рыцарь: +HP плоский бонус');
INSERT OR IGNORE INTO skill_config VALUES ('K_zhv_ranged_penalty', 0.15, 'Рыцарь: -% к урону дальнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('K_brs', 0.5, 'Воин: коэфф. берсерка от СИЛ');
INSERT OR IGNORE INTO skill_config VALUES ('K_brs_crit_flat', 5.0, 'Воин: +плоский бонус к крит. урону');
INSERT OR IGNORE INTO skill_config VALUES ('K_brs_magic_penalty', 0.2, 'Воин: -% к магическому урону');
INSERT OR IGNORE INTO skill_config VALUES ('K_met', 0.4, 'Лучник: коэфф. крита от ЛОВ');
INSERT OR IGNORE INTO skill_config VALUES ('K_met_ranged_bonus', 0.1, 'Лучник: +% к урону дальнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('K_met_melee_penalty', 0.15, 'Лучник: -% к урону ближнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('K_ark', 0.6, 'Маг: коэфф. урона навыков от ИНТ');
INSERT OR IGNORE INTO skill_config VALUES ('K_ark_exp_bonus', 0.1, 'Маг: +% EXP');
INSERT OR IGNORE INTO skill_config VALUES ('K_ark_melee_penalty', 0.2, 'Маг: -% к урону ближнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('K_ten', 0.5, 'Ассассин: коэфф. уклонения от ЛОВ');
INSERT OR IGNORE INTO skill_config VALUES ('K_ten_hp_penalty', 15.0, 'Ассассин: -HP плоский штраф');
INSERT OR IGNORE INTO skill_config VALUES ('K_reg', 1.5, 'Лекарь: коэфф. восстановления HP от ВЫН');
INSERT OR IGNORE INTO skill_config VALUES ('K_n', 10.0, 'Лекарь: делитель ВЫН для расчёта N');
INSERT OR IGNORE INTO skill_config VALUES ('K_reg_regen_bonus', 0.1, 'Лекарь: +% к пассивной регенерации');
INSERT OR IGNORE INTO skill_config VALUES ('K_reg_melee_penalty', 0.1, 'Лекарь: -% к урону ближнего боя');
INSERT OR IGNORE INTO skill_config VALUES ('K_chut', 0.4, 'Торговец: коэфф. золота от УДЧ+ОБА');
INSERT OR IGNORE INTO skill_config VALUES ('K_hire', 0.3, 'Торговец: коэфф. скидки найма от ОБА');
INSERT OR IGNORE INTO skill_config VALUES ('K_chut_trade_bonus', 5.0, 'Торговец: +плоский бонус к Торговле');
INSERT OR IGNORE INTO skill_config VALUES ('K_chut_combat_penalty', 0.2, 'Торговец: -% к урону в бою');
```

---

## Модуль: `passive_skills.py`

Создать файл `passive_skills.py` со следующими функциями:

### 1. Загрузка конфига

```python
def load_skill_config(db_conn) -> dict:
    """Загружает все значения из skill_config в словарь {key: value}."""
```

### 2. Расчёт модификаторов персонажа

Функция принимает базовые характеристики персонажа и возвращает словарь модификаторов, которые применяются поверх стандартных формул:

```python
def get_passive_modifiers(race: str, class_name: str, stats: dict, config: dict) -> dict:
    """
    Возвращает словарь модификаторов от пассивных навыков расы и класса.
    
    Args:
        race: название расы ('human', 'elf', 'beast', 'angel', 'vampire', 'demon', 'fairy')
        class_name: название класса ('knight', 'warrior', 'archer', 'mage', 'assassin', 'healer', 'merchant')
        stats: {'sil': int, 'lov': int, 'int': int, 'vyn': int, 'oba': int, 'uch': int}
        config: словарь из load_skill_config()
    
    Returns:
        {
            'exp_bonus_mult': float,        # множитель к EXP (1.0 = без бонуса)
            'gold_bonus_mult': float,        # множитель к золоту с монстров
            'crit_chance_add': float,        # прибавка к шансу крита (абсолютная, 0.05 = +5%)
            'crit_chance_mult_lov': float,   # множитель к коэффициенту крита от ЛОВ (1.0 = стандарт)
            'crit_dmg_mult': float,          # множитель к урону крит. атак
            'dodge_add': float,              # прибавка к шансу уклонения
            'melee_dmg_mult': float,         # множитель к урону ближнего боя
            'ranged_dmg_mult': float,        # множитель к урону дальнего боя
            'skill_dmg_mult': float,         # множитель к урону активных навыков (медиа)
            'skill_dmg_mult_int': float,     # множитель к коэффициенту урона навыков от ИНТ
            'hp_max_add': float,             # плоский бонус к макс. HP
            'hp_max_mult': float,            # множитель к макс. HP
            'regen_mult': float,             # множитель к формуле регенерации HP
            'trade_add': float,              # плоский бонус к навыку Торговля
            'trade_mult_oba': float,         # множитель к коэффициенту Торговли от ОБА
            'trade_penalty_mult': float,     # штраф к навыку Торговля (множитель, < 1.0)
            'sell_price_mult': float,        # множитель к цене продажи предметов
            'hire_cost_mult': float,         # множитель к стоимости найма вайфу (< 1.0 = дешевле)
            'damage_in_mult': float,         # множитель к получаемому урону (< 1.0 = танк)
            'nth_message_attack': int | None, # каждое N-е сообщение = усиленная атака (None = выкл.)
            'nth_message_mult': float,       # множитель урона для N-го сообщения
            'berserker_hp_threshold': float, # порог HP для берсерка (0.0 = выкл.)
            'berserker_dmg_mult': float,     # бонус урона берсерка
            'dodge_bonus_mult': float,       # бонус к следующей атаке после уклонения
            'heal_per_n_messages': int | None, # каждые N сообщений = исцеление (None = выкл.)
            'heal_amount': float,            # сколько HP восстанавливать
            'vampirism_rate': float,         # % восстановления HP от нанесённого урона (0.0 = выкл.)
            'every_5th_crit_double': bool,   # каждый 5-й крит = двойной урон (Лучник)
        }
    """
```

### 3. Применение вампиризма (вызывается из обработчика атаки)

```python
def apply_vampirism(damage_dealt: int, vampirism_rate: float, current_hp: int, max_hp: int) -> int:
    """Возвращает новое значение HP после вампиризма. Не превышает max_hp."""
```

### 4. Проверка хищного инстинкта зверолюда

```python
def check_nth_message_attack(message_count: int, nth: int) -> bool:
    """Возвращает True если это N-е сообщение в подземелье (message_count % nth == 0)."""
```

### 5. Расчёт исцеления лекаря

```python
def check_healer_heal(message_count: int, heal_every_n: int, heal_amount: float) -> float:
    """Возвращает heal_amount если пора лечиться, иначе 0."""
```

---

## Интеграция в обработчик сообщения-атаки

В функции, которая обрабатывает текстовое сообщение пользователя в подземелье, добавить:

```python
# Получаем модификаторы один раз при входе в подземелье (или при левелапе)
# и кешируем в сессии игрока

config = load_skill_config(db)
mods = get_passive_modifiers(player.race, player.class_name, player.stats, config)

# При каждом сообщении:
session.message_count += 1

# 1. Базовый урон (уже рассчитан по формулам характеристик)
base_damage = calculate_base_damage(player)  # существующая функция

# 2. Применяем мультипликатор ближнего боя
damage = base_damage * mods['melee_dmg_mult']

# 3. Берсерк воина
if mods['berserker_hp_threshold'] > 0 and player.hp / player.hp_max < mods['berserker_hp_threshold']:
    damage *= mods['berserker_dmg_mult']

# 4. Хищный инстинкт зверолюда
if mods['nth_message_attack'] and check_nth_message_attack(session.message_count, mods['nth_message_attack']):
    damage *= mods['nth_message_mult']

# 5. Бонус после уклонения (ассассин)
if session.dodge_bonus_active:
    damage *= mods['dodge_bonus_mult']
    session.dodge_bonus_active = False

# 6. Крит
if roll_crit(player, mods):  # учитывает mods['crit_chance_add'] и mods['crit_chance_mult_lov']
    damage *= crit_damage_multiplier(player) * mods['crit_dmg_mult']
    session.crit_count += 1
    if mods['every_5th_crit_double'] and session.crit_count % 5 == 0:
        damage *= 2

# 7. Золото с монстра
gold = base_gold * mods['gold_bonus_mult']

# 8. Вампиризм
if mods['vampirism_rate'] > 0:
    player.hp = apply_vampirism(damage, mods['vampirism_rate'], player.hp, player.hp_max)

# 9. Исцеление лекаря
heal = check_healer_heal(session.message_count, mods['heal_per_n_messages'], mods['heal_amount'])
if heal > 0:
    player.hp = min(player.hp + heal, player.hp_max)

# 10. Получаемый урон от монстра
incoming_damage = monster.damage * mods['damage_in_mult']

# 11. Уклонение ассассина
if roll_dodge(player, mods):  # учитывает mods['dodge_add']
    session.dodge_bonus_active = True
    incoming_damage = 0
```

---

## Интеграция в обработчик медиа-сообщения

```python
# Урон активного навыка (медиа)
skill_damage = calculate_skill_damage(player)  # существующая функция
skill_damage *= mods['skill_dmg_mult']
# (mods['skill_dmg_mult_int'] уже учтён внутри calculate_skill_damage через ИНТ-коэффициент)
```

---

## Интеграция в формулы вторичных статов

В функции пересчёта вторичных статов персонажа:

```python
def recalculate_secondary_stats(player, mods):
    # EXP бонус
    player.exp_bonus = base_exp_bonus(player) * mods['exp_bonus_mult']
    
    # Торговля
    trade_base = player.oba * trade_k_oba * mods['trade_mult_oba']  
    # trade_k_oba берётся из БД; для Феи mods['trade_mult_oba'] = 2.0
    player.trade = trade_base * mods['trade_penalty_mult'] + mods['trade_add']
    
    # Цена продажи (в функции расчёта цены из раздела Характеристик)
    sell_price = base_sell_price * mods['sell_price_mult']
    
    # Стоимость найма
    hire_cost = base_hire_cost * mods['hire_cost_mult']
    
    # Регенерация HP
    regen_pct = player.hp_max * (1 - math.exp(-player.vyn / 100)) * mods['regen_mult']
    
    # Максимальное HP
    player.hp_max = base_hp_max(player) * mods['hp_max_mult'] + mods['hp_max_add']
```

---

## Хранение сессионного состояния подземелья

Добавить в объект/таблицу сессии подземелья:

```python
dungeon_session = {
    'message_count': 0,     # счётчик сообщений в этом подземелье
    'crit_count': 0,         # счётчик критических ударов (для правила каждого 5-го)
    'dodge_bonus_active': False,  # флаг бонуса ассассина после уклонения
}
```

---

## Переменная «Каждые N уровней» (Человек)

```python
def get_human_bonus_stat_points(player_level: int) -> int:
    """Возвращает количество бонусных очков характеристик от расы Человек."""
    return player_level // 10
```

При левелапе проверять: если `player.race == 'human'` и `new_level % 10 == 0` — отправить уведомление игроку о новом свободном очке и добавить его в `player.free_stat_points`.

---

## Отображение в профиле (profile.html, вкладка «Подробная информация»)

В блоке «Источники» для каждой характеристики уже есть строки:
`База + Раса + Класс + Экипировка + Навыки = Итого`

Добавить раздел **«Пассивный навык»** под каждым аккордеоном характеристики — показывать, какой пассивный навык и как влияет на производные именно этой характеристики. Пример для ЛОВ у эльфа-лучника:

```
Шанс крита: +5% (расовый) + ЛОВ×0.4×2 (Лесное чутьё + Меткий глаз) = X%
```

---

## Проверка (unit-тесты)

Написать `test_passive_skills.py` с тест-кейсами:

```python
# Фея-торговец: Торговля должна считаться с двойным коэффициентом ОБА + классовым бонусом
# Вампир: check что vampirism_rate > 0 и HP растёт после атаки
# Лучник-эльф: crit_chance_mult_lov == 2.0, every_5th_crit_double == True
# Воин при HP < 50%: berserker_dmg_mult применяется
# Ассассин: после уклонения dodge_bonus_active = True, следующая атака × 1.3
# Лекарь на 8-м сообщении при ВЫН=10: heal_amount > 0
```

---

## Не трогать

- Формулы основных характеристик из раздела «Характеристики» ТЗ (СИЛ → HP, ЛОВ → крит и т.д.)
- Формулы Торговли (уравнения с e^(−T/100))
- Логику стартовой экипировки классов
- Существующие обработчики сообщений — только добавлять вызовы новых функций
