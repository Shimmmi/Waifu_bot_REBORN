# Аффиксы элитных монстров

Каталог свойств элиты соло-подземелий (и связанных флагов Бездны). Числа и формулы — **как в коде**, не из устаревшего ТЗ.

Источники: [`alembic/versions/0018_monster_affixes.py`](../alembic/versions/0018_monster_affixes.py), [`0087_abyss_core.py`](../alembic/versions/0087_abyss_core.py), [`0154_elite_reflect_max_hp.py`](../alembic/versions/0154_elite_reflect_max_hp.py), [`elite_affix_combat.py`](../src/waifu_bot/services/elite_affix_combat.py), [`combat.py`](../src/waifu_bot/services/combat.py).

Имя элиты: `[префиксы] База[-суффиксы]`. Пример: `Толстый Могучий Крыс-берсерк`.

---

## Спавн элиты (соло)

Шанс не зависит от удачи и `elite_chance` шаблона:

`p = 0.06 + min(0.40, plus_level × 0.02)`  
(`ELITE_SPAWN_*` в [`constants.py`](../src/waifu_bot/game/constants.py)).

Если бросок прошёл:

| Вероятность | Аффиксов | Цвет |
|------------:|---------:|------|
| 60% | 1 | синий |
| 28% | 2 | синий |
| 10% | 3 | золото |
| 2% | 4 | красный |

Число режется `monster_templates.max_affixes` (обычно 4). Итоговый уровень монстра: база + сумма `level_add`. HP/урон/золото/опыт перемножаются по выбранным аффиксам **на спавне**.

Правила набора ([`_pick_monster_affixes`](../src/waifu_bot/services/combat.py)):

- не больше **одного** поведенческого суффикса (`type=suffix`, `category=behavior`);
- не больше **одного** аффикса на `affix_group` (нельзя два тира одной группы);
- пары из `incompatible_with` не ставятся вместе;
- `allowed_families` / `forbidden_families` фильтруют пул по семейству монстра.

Челлендж задаёт список id заранее (`apply_monster_affix_ids`); чёрный список пар включает `REFLECT`+`STONE_SKIN`.

Бездна: тир 2 с этажа 21, тир 3 и эксклюзивные флаги — с этажа 51. Рантайм эксклюзивов есть только в [`abyss_combat.py`](../src/waifu_bot/services/abyss_combat.py).

---

## Пайплайн исходящего урона (соло)

Порядок после базового урона и бонусного пула:

1. `CURSE` — множитель урона игрока (сохраняется в `elite_state`).
2. `STONE_SKIN` — снижение пропорционально оставшемуся HP монстра.
3. `MEDIA_IMMUNE` / `TEXT_IMMUNE` — урон этого типа = 0.
4. `MEDIA_BLOCK` — каждое N-е медиа-сообщение = 0.
5. Крит (шанс режется `ANTI_CRIT`: `chance × (1 − сумма)`, сумма capped 0.95).
6. Уклонение монстра (`evade_add`), затем `defense_add` (−% входящего в монстра).
7. Слабость / добивание / инстакилл.
8. **`REFLECT`** — см. ниже; затем HP монстра.
9. `UNDYING` / `SPLIT` при смерти.
10. `BERSERK` — флаг `berserk_active` при HP ≤ порога; множитель на **реторс** при убийстве.
11. `REGEN` после удара (не с 1 HP и не с 0 HP).

---

## Рефлект (актуально)

Раньше отражалась **доля урона удара** (20%/35%) — на высоких Dungeon+ один прок убивал вайфу.

Теперь при успешном ударе (урон > 0, монстр не уклонился):

```
if random() < chance:
    taken = max(1, round(waifu.max_hp × reflect_pct))
    waifu.current_hp = max(0, current − taken)
```

Это **истинный % макс. HP**: броня, ВЫН и `dmg_reduce` **не** применяются. Размер удара на величину не влияет.

Ключ в `behavior_params` по-прежнему `reflect_pct` (теперь доля макс. HP, не доля урона).

| Тир | Имя | Шанс | Урон | `level_add` |
|----:|-----|-----:|------|------------:|
| 1 | -отражатель | 15% | 25% макс. HP | +2 |
| 2 | -зеркальный | 25% | 50% макс. HP | +3 |
| 3 | -призма | 35% | 75% макс. HP | +4 |

Не путать с механикой босса Бездны `REFLECT`, аффиксом `ABYSS_MIRROR` (доля урона удара) и скиллом ГД `REFLECT`.

---

## Префиксы

| Группа | Тир | Имя | Категория | `level_add` | Эффект | Семьи / несовместимость |
|--------|----:|-----|-----------|------------:|--------|-------------------------|
| `hp_bulk` | 1 | Толстый | stat | +1 | HP ×1.5 | — |
| `hp_bulk` | 2 | Жирнючий | stat | +2 | HP ×2.0 | — |
| `hp_bulk` | 3 | Мегакабанистый | stat | +3 | HP ×2.5 | — |
| `dmg_power` | 1 | Могучий | stat | +1 | DMG ×1.4 | — |
| `dmg_power` | 2 | Сокрушительный | stat | +2 | DMG ×1.8 | — |
| `dmg_power` | 3 | Опустошительный | stat | +3 | DMG ×2.3 | — |
| `defense` | 1 | Бронированный | stat | +1 | входящий в монстра −10% | несовм. `stone_skin` |
| `defense` | 2 | Закалённый | stat | +2 | −20% | несовм. `stone_skin` |
| `defense` | 3 | Неприступный | stat | +3 | −30% | несовм. `stone_skin` |
| `evade` | 1 | Удачливый | stat | +1 | уклон монстра 10% | — |
| `evade` | 2 | Увёртливый | stat | +2 | 20% | — |
| `evade` | 3 | Неуловимый | stat | +3 | 30% | — |
| `stone_skin` | 1 | Каменный | stat | +3 | `STONE_SKIN` max_reduction 50% | construct, beast; несовм. `defense` |
| `stone_skin` | 2 | Гранитный | stat | +4 | max_reduction 70% | construct, beast; несовм. `defense` |
| `ancient` | 1 | Древний | reward | +1 | EXP ×2, золото ×2 | несовм. `miser` |
| `ancient` | 2 | Реликтовый | reward | +2 | EXP ×3, золото ×3, `drop_rarity_bonus=1` | несовм. `miser` |

Каменная кожа: `снижение = max_reduction × (текущий_HP / макс_HP)`, затем `урон × (1 − снижение)`. На полном HP максимум, у нуля — ноль.

---

## Суффиксы

| Группа | Тир | Имя | Категория | Flag | `level_add` | Параметры / формула | Семьи / несовместимость |
|--------|----:|-----|-----------|------|------------:|---------------------|-------------------------|
| `berserk` | 1 | -берсерк | behavior | `BERSERK` | +2 | порог 40% HP, реторс ×1.5 | несовм. `buff_next` |
| `berserk` | 2 | -неистовый | behavior | `BERSERK` | +3 | 60%, ×1.8 | несовм. `buff_next` |
| `berserk` | 3 | -одержимый | behavior | `BERSERK` | +4 | 75%, ×2.2 | несовм. `buff_next` |
| `regen` | 1 | -регенератор | behavior | `REGEN` | +2 | +3% макс. HP каждые 5 сообщ. | несовм. `undying` |
| `regen` | 2 | -живучий | behavior | `REGEN` | +3 | +6% / 4 | несовм. `undying` |
| `regen` | 3 | -бессмертный | behavior | `REGEN` | +4 | +10% / 3 | несовм. `undying` |
| `reflect` | 1 | -отражатель | behavior | `REFLECT` | +2 | 15% шанс, 25% макс. HP вайфу, без брони | — |
| `reflect` | 2 | -зеркальный | behavior | `REFLECT` | +3 | 25% / 50% | — |
| `reflect` | 3 | -призма | behavior | `REFLECT` | +4 | 35% / 75% | — |
| `split` | 1 | -делитель | behavior | `SPLIT` | +3 | 2 копии, 40% HP и DMG | несовм. `undying` |
| `split` | 2 | -роевой | behavior | `SPLIT` | +4 | 3 копии, 50% HP и DMG | несовм. `undying` |
| `undying` | 1 | -нежить | behavior | `UNDYING` | +3 | воскреснуть один раз с 10% HP | undead, demon; несовм. `split`, `regen` |
| `undying` | 2 | -феникс | behavior | `UNDYING` | +4 | 20% HP | undead, demon; несовм. `split`, `regen` |
| `undying` | 3 | -вечный | behavior | `UNDYING` | +5 | 30% HP | undead, demon; несовм. `split`, `regen` |
| `media_block` | 1 | -поглотитель | behavior | `MEDIA_BLOCK` | +2 | каждое 3-е медиа = 0 урона | запрет construct; несовм. `text_immune` |
| `media_block` | 2 | -пожиратель | behavior | `MEDIA_BLOCK` | +3 | каждое 2-е медиа | запрет construct; несовм. `text_immune` |
| `media_block` | 3 | -аннигилятор | behavior | `MEDIA_BLOCK` | +4 | каждое медиа | запрет construct; несовм. `text_immune` |
| `media_immune_audio` | — | -игнорирующий аудио | behavior | `MEDIA_IMMUNE` | +1 | иммунитет к audio/voice | — |
| `media_immune_url` | — | -игнорирующий ссылки | behavior | `MEDIA_IMMUNE` | +2 | иммунитет к LINK | — |
| `media_immune_video` | — | -игнорирующий видео | behavior | `MEDIA_IMMUNE` | +2 | иммунитет к video | — |
| `media_immune_photo` | — | -игнорирующий фото | behavior | `MEDIA_IMMUNE` | +3 | иммунитет к photo | — |
| `media_immune_sticker` | — | -игнорирующий стикеры | behavior | `MEDIA_IMMUNE` | +4 | иммунитет к sticker | — |
| `text_immune` | — | -неосязаемый | behavior | `TEXT_IMMUNE` | +5 | текст не наносит урон | undead, elemental, demon; несовм. `media_block` |
| `curse` | 1 | -проклинатель | debuff | `CURSE` | +2 | урон игрока −15% (множитель, стакается) | — |
| `curse` | 2 | -порченый | debuff | `CURSE` | +3 | −25% | — |
| `curse` | 3 | -осквернитель | debuff | `CURSE` | +4 | −40% | — |
| `anti_crit` | 1 | -скользкий | debuff | `ANTI_CRIT` | +1 | шанс крита × (1 − 0.15) | — |
| `anti_crit` | 2 | -туманный | debuff | `ANTI_CRIT` | +2 | × (1 − 0.30) | — |
| `miser` | 1 | -жадина | reward | `MISER` | +1 | золото ×0.70, `drop_chance_mult=0.70` | несовм. `ancient` |
| `miser` | 2 | -скряга | reward | `MISER` | +2 | золото ×0.50, EXP ×0.80, `drop_chance_mult=0.50` | несовм. `ancient` |
| `buff_next` | 1 | -воевода | behavior | `BUFF_NEXT` | +2 | следующие монстры HP ×1.20, пока жив | запрет slime; несовм. `berserk` |
| `buff_next` | 2 | -полководец | behavior | `BUFF_NEXT` | +3 | HP ×1.20, DMG ×1.15 | запрет slime; несовм. `berserk` |
| `buff_next` | 3 | -повелитель | behavior | `BUFF_NEXT` | +5 | HP ×1.30, DMG ×1.20, `player_dmg_mult=0.90` | запрет slime; несовм. `berserk` |

`MEDIA_BLOCK` считает только медиа (не TEXT/LINK). Реген: `heal = max(1, max_hp × regen_pct / 100)` каждые `every_n` сообщений после удара с уроном > 0.

Берсерк в коде — не отдельный удар из ТЗ, а постоянный множитель реторса, пока `berserk_active`.

`BUFF_NEXT` применяется к монстрам с большим `position`, пока воевода жив (`buff_next_multipliers_for_new_monster`). Поле `player_dmg_mult` в сиде **не читается** боем.

---

## Эксклюзивы Бездны (этаж ≥ 51)

| Имя | Группа | Flag | `level_add` | Эффект | Семьи |
|-----|--------|------|------------:|--------|-------|
| похититель | `grace_steal` | `GRACE_STEAL` | +5 | активная Грация отключена на этот бой (`duration_messages: 10` в параметрах) | все |
| зеркало Бездны | `abyss_mirror` | `ABYSS_MIRROR` | +4 | каждый 7-й попавший удар: `round(урон × 0.3)` вайфу | elemental, construct |
| иссушающий | `anti_regen` | `ANTI_REGEN` | +3 | нет регена HP между монстрами | все |
| хаотичный | `chaos_damage` | `CHAOS_DMG` | +3 | исходящий урон × `uniform(0.7, 1.3)` | запрет construct |

`ABYSS_MIRROR` по-прежнему отражает **долю урона удара**, не % макс. HP.

Соло-ролл элиты **не исключает** эти четыре флага из пула; обработчиков в соло-бою нет.

---

## Совместимость (сводка)

Не на одном монстре:

- `undying` + `split`
- `undying` + `regen`
- `text_immune` + `media_block`
- `berserk` + `buff_next`
- `stone_skin` + `defense`
- `ancient` + `miser`

По семейству:

- `text_immune`: только undead, elemental, demon
- `undying`: только undead, demon
- `stone_skin`: только construct, beast
- `media_block` / `media_immune`: запрет construct (в сиде `forbidden_families` есть у `media_block`; у `media_immune_*` фильтра нет)
- `buff_next`: запрет slime

---

## Как в коде, но не в луте / не в бою

- `drop_chance_mult` и `drop_rarity_bonus` пишутся в карточку элиты и в UI; **ролл лута их не умножает**. На спавне применяются только `gold_mult` / `exp_mult`.
- `BUFF_NEXT.player_dmg_mult` у «-повелитель» в сиде есть, в `buff_next_multipliers_for_new_monster` нет.
- Соло может выбросить аффиксы Бездны; флаги `GRACE_STEAL` / `ABYSS_MIRROR` / `ANTI_REGEN` / `CHAOS_DMG` в соло не исполняются.

Связанные формулы входящего урона (реторс, броня): [`COMBAT_FORMULAS.md`](COMBAT_FORMULAS.md).
