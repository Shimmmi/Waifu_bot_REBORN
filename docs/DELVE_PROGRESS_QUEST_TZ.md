# ТЗ: Delve Progress Quest (слой 2.3-PQ)

Статус: к реализации.  
Слой силы наёмниц поверх текущего Погружения. Кран игрока и театр колонны остаются.

Связанные документы: [VARIANT_2_2_POGRUZHENIE.md](VARIANT_2_2_POGRUZHENIE.md), [DELVE_ROLEPLAY.md](DELVE_ROLEPLAY.md), [ITEM_SYSTEM_TABLE.md](ITEM_SYSTEM_TABLE.md).

## 0. Границы

Текущий Delve — два слоя:

- кран O(1): золото → `Player.gold`, XP → основная вайфу;
- театр: пила `sawtooth()`, узлы `spine_type()`, лавка — кадр журнала.

`gold_earned` / `xp_earned` на карточке — счётчики доли крана, не кошельки.

Слой **2.3-PQ** живёт на тех же 1–3 `CompanionCard`. Не `HiredWaifu`. Не `inventory_items` основной вайфу. Летопись / flesh / psyche / тинт ветки не меняются.

Снятые законы 2.2: L4 (нет HP на HUD), L7 (сила не влияет на глубину), L10 (лавка = 0 силы).  
Кран игрока (L6, L8, L12) не трогать.

## 1. Законы

| # | Закон |
|---|--------|
| **P1** | Два кошелька. Кран игрока/ОВ без изменений. Наёмницы имеют `gold_wallet` и `xp_unspent`. Это золото не списывается с `Player.gold`. |
| **P2** | Авто. Уровень, покупка, заточка +1…+7, зелья — без клика. |
| **P3** | Покупка всегда сильнее. Витрина не предлагает `ilvl <= current`. После экипа/заточки `power` строго растёт. |
| **P4** | Плоская сила. Нет аффиксов, STR/AGI, брони, legendary, пыли. Только `level` и `ilvl`. |
| **P5** | `d_max = f(party_power)`. Пила живёт, но не глубже `d_max`. При включённом PQ потолок пилы = `d_max` (не время в колонне). |
| **P6** | Пока есть HP — идут вниз. HP = 0 у всего отряда → рестарт спуска. Экип, расходники, уровни, кошельки, сила сохраняются. |
| **P7** | Детерминизм: один сид + те же входы → те же покупки, сток и wipe. Без LLM. |
| **P8** | Предмет колонны нельзя надеть на ОВ. Отдельные таблицы. |

Канон прогрессии — `CompanionCard`. `DelveCompanion` — зеркало на ствол.

## 2. Формулы

```
xp_to_next(L) = 40 + 20*(L-1) + 3*(L-1)^2
power_level   = level
ilvl(item)    = base_ilvl + enchant_level          # enchant 0..7 в v1
power_gear    = sum(ilvl экипированных слотов)     # двуручник считается один раз
power         = power_level + power_gear
hp_max        = 40 + 8 * power
party_power   = sum(power живых в отряде)
d_max         = floor(8 + 0.35 * party_power)
band(d)       = max(1, ceil(d / 20))
gear_price    = round(12 * base_ilvl * 1.12^(band-1))
sharpen_cost  = round(8 * ilvl * 1.35^(N-1))       # N = следующий +
```

Старт: level 1, без экипа, power 1, hp 48, `d_max` ≈ 8.

Авто-левелап: пока `xp_unspent >= xp_to_next(level)` — списать XP, `level += 1`, пересчитать `power` и `hp_max`. Текущее HP от левелапа не восстанавливается.

ID двуручника: слот 1 несёт ilvl, слот 2 пуст и заблокирован.

## 3. Каталог экипировки

Слоты как у ОВ: 1 оружие, 2 оружие/щит, 3 костюм, 4–5 кольца, 6 амулет.

`slot_type`: `weapon_1h`, `weapon_2h`, `offhand`, `costume`, `ring`, `amulet`.

Именные базы — `data/delve_gear.v1.json` (80 строк: 8 семейств × 10 тиров).  
`base_ilvl = tier * 4` (T1=4 … T10=40).

Семейства: `sword`, `dagger`, `axe`, `bow`, `shield`, `costume`, `ring`, `amulet`.

Хвост (`tier > 10`):

```
scaled_plus = tier - 10
base_ilvl   = 40 + 4 * scaled_plus
name        = "{семейство} бездны T{tier}"
```

Заточка v1: только +1…+7, авто. +8…+10 — фаза 2. Смена предмета удаляет старый инстанс (без пыли). Новый всегда `enchant_level=0` и больший `base_ilvl`.

## 4. Лавка и расходники

Узел `SHOP` (`d % 12 == 4`) — авто-резолв.

Порядок наёмницы:

1. Левелап.
2. Купить оффер с максимальным `ilvl` среди доступных по золоту.
3. Если вещь не куплена — заточить слот, если это увеличит силу.
4. Остаток — расходники до капа стака.

Витрина на глубине `d`, `band = ceil(d/20)`:

- 3 оффера экипа, сид `(pq_seed, cycle, d, card_id)`, `tier = band + {-1,0,+1}`;
- 1 заточка, если есть предмет и `enchant < 7`;
- 2 расходника.

Оффер с `ilvl <= current` не генерируется. Если все слоты выше банды — `scaled_plus` или заточка.

| id | Имя | Эффект | Цена | Кап |
|----|-----|--------|------|-----|
| `potion_hp` | Зелье лечения | `+0.35 * hp_max` одной | `6 * band` | 10 |
| `salve_party` | Мазь отряда | `+0.15 * hp_max` каждой | `14 * band` | 5 |

Авто-юз: зелье при `hp% < 40` (цель — наименьший %). Мазь — если двое ниже 40% или перед боссом при среднем HP < 55%.

## 5. HP, сток, wipe

```
threat(d) = d
drain COMBAT = max(1, round(4 + 0.45 * max(0, threat - party_power)))
drain BOSS   = max(2, round(10 + 0.7 * max(0, threat - party_power)))
drain SHOP/REST/SURFACE/LANDMARK/TRAVERSE/BRANCH = 0
REST regen   = 0.10 * hp_max
```

Сток делится по живым пропорционально `power`.

Wipe: все живые `hp_current <= 0`.

При wipe: `run_origin = now`, HP = max, экип/сумка/уровень/кошельки без изменений, `wipe_count += 1`, штамп журнала `wipe`. Кран игрока (`t_origin`) не сбрасывается. Спуск начинается после `T_rest`.

## 6. Кран наёмниц и баланс

Отдельный кран, те же `walk_capped_grant`, свои капы. Делёж по loyalty.

```
merc_gold_cap_day(band) = 80 * band     # band = ceil(pb_depth / 20), минимум 1
merc_xp_cap_day(band)   = 60 * band
```

3 головы не увеличивают кап дня, но носят 3 сета — `party_power` выше.

Ориентир: за день отряд покупает 1 апгрейд слота или 1–2 заточки, не полный сет. Сет T1 — 2–3 дня. Сила: ~30–40% от уровней, 60–70% от ilvl на дистанции недели.

| Банда | Глубина | Кап зол/день | T слота (ilvl) | Цена слота | Зелье |
|------:|--------:|-------------:|----------------|-----------:|------:|
| 1 | 1–20 | 80 | T1 (4) | 48 | 6 |
| 2 | 21–40 | 160 | T2 (8) | 108 | 12 |
| 3 | 41–60 | 240 | T3 (12) | 181 | 18 |
| 4 | 61–80 | 320 | T4 (16) | 270 | 24 |
| 5 | 81–100 | 400 | T5 (20) | 377 | 30 |

Цена: `round(12 * (tier*4) * 1.12^(band-1))` при `tier = band`.

## 7. Catch-up

Кран игрока — `rate × Δt`.

PQ от `last_pq_ts` до `now`:

1. Начислить merc gold/XP одним `walk_capped_grant`.
2. Пройти целочисленные глубины нисходящих фаз пилы с потолком `d_max`.
3. На SHOP — автозакупки. На COMBAT/BOSS — сток (подряд COMBAT можно суммировать). На REST — реген.
4. Wipe внутри сегмента: сбросить `run_origin`, продолжить. Кап wipe за sync = 24.

Первый запуск на старой колонне: `last_pq_ts = now` (историю не переигрывать).

## 8. Данные и API

Новые колонки: `companion_cards` и `delve_companions` — `level`, `xp_unspent`, `gold_wallet`, `power`, `hp_current`, `hp_max`.  
`delve_states` — `last_pq_ts`, `run_origin`, `wipe_count`, `pq_seed`, `pq_gold_today`, `pq_xp_today`, `pq_grant_day_msk`, `pq_last_cycle`, `pq_last_d`.

Таблицы: `delve_gear_templates`, `delve_companion_gear`, `delve_consumable_templates`, `delve_companion_bags`.

Флаг: `delve.pq_enabled` (default true). Новых POST нет.

`GET /delve/sync` добавляет на лицо: `level`, `power`, `gold_wallet`, `xp_unspent`, `hp_*`, `gear[6]`, `bag[]`, `last_shop_buy`; на корень: `party_power`, `d_max`, `wipe_count`, `pq_enabled`, `run_origin`.

## 9. Приёмка

- Покупка и заточка всегда увеличивают `power`.
- Витрина не содержит `ilvl <= current`.
- Wipe сохраняет экип/сумку/level/gold_wallet, сбрасывает глубину, лечит HP.
- `Player.gold` и XP ОВ не зависят от покупок наёмниц.
- Два прогона с одним Δt и сидом совпадают.
- `d` кадра ≤ `d_max`.
- За 24 ч банды B есть покупка и нет тира выше B+1.

## 10. Вне v1

Ручной магазин, разбор, пыль, аффиксы ОВ, заточка +8…+10, перенос в инвентарь ОВ, wipe ≠ смерть карточки, изменение капов крана игрока.
