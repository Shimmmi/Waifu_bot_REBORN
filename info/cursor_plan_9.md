# ТЗ для CURSOR: Бесконечная система сложности подземелий

## Проблема
Уровни сложности +6, +7, +8 и выше показывают "повышенная сложность" без
конкретных параметров. Нужна детерминированная формула для любого N.

## Формулы масштабирования

```python
import math

def get_difficulty_params(n: int) -> dict:
    hp_dmg_mult  = 1.0 + n * 0.20           # +20% за уровень (линейно)
    reward_mult  = 1.0 + n * 0.15 + math.log1p(n) * 0.10
    rarity_tiers = ["common","uncommon","rare","epic","legendary"]
    rarity       = rarity_tiers[min(n // 2, 4)]
    return {
        "hp_dmg_mult":       round(hp_dmg_mult, 2),
        "reward_mult":       round(reward_mult, 2),
        "item_level_bonus":  n,
        "rarity_floor":      rarity,
        "elite_chance_bonus":round(min(0.40, n * 0.02), 2),
    }
```

## Таблица значений

| N  | HP/DMG | Награды | +уровень предмета | Редкость (мин) | Элиты |
|----|--------|---------|-------------------|----------------|-------|
| 0  | x1.0   | x1.00   | +0                | обычная        | +0%   |
| 1  | x1.2   | x1.22   | +1                | обычная        | +2%   |
| 2  | x1.4   | x1.41   | +2                | необычная      | +4%   |
| 3  | x1.6   | x1.59   | +3                | необычная      | +6%   |
| 4  | x1.8   | x1.76   | +4                | редкая         | +8%   |
| 5  | x2.0   | x1.93   | +5                | редкая         | +10%  |
| 6  | x2.2   | x2.09   | +6                | эпическая      | +12%  |
| 7  | x2.4   | x2.26   | +7                | эпическая      | +14%  |
| 8  | x2.6   | x2.42   | +8                | легендарная    | +16%  |
| 10 | x3.0   | x2.74   | +10               | легендарная    | +20%  |
| 15 | x4.0   | x3.53   | +15               | легендарная    | +30%  |
| 20 | x5.0   | x4.30   | +20               | легендарная    | +40%  |

## Backend

Найти где применяются параметры сложности (plus_level / difficulty_level).
Заменить хардкод/словарь пресетов на функцию get_difficulty_params(n).

Применить:
- hp_dmg_mult к HP и DMG монстров при генерации
- item_level_bonus при генерации лута
- rarity_floor как минимальную редкость лута
- elite_chance_bonus к шансу элитного спавна

## Frontend

Найти функцию рендера боттомшита сложности.
Заменить хардкоженные описания на динамические:

```javascript
function getDifficultyDescription(n) {
    if (n === 0) return "Базовая сложность.";
    const hpDmg   = Math.round(n * 20);
    const reward  = ((1 + n*0.15 + Math.log1p(n)*0.10)).toFixed(2);
    const rarityLabels = ["обычная","необычная","редкая","эпическая","легендарная"];
    const rarity  = rarityLabels[Math.min(Math.floor(n / 2), 4)];
    const elite   = Math.min(40, n * 2);
    return `+${hpDmg}% HP/урон. Награды x${reward}. Предмет +${n} ур. Редкость: ${rarity}. Элиты +${elite}%.`;
}
```

## game_config параметры

| Ключ | Значение | Описание |
|---|---|---|
| difficulty.hp_dmg_step | 0.20 | +% к HP/DMG за уровень сложности |
| difficulty.reward_linear | 0.15 | Линейный коэффициент наград |
| difficulty.reward_log | 0.10 | Логарифмический бонус наград |
| difficulty.rarity_step | 2 | Уровней сложности на шаг редкости |
| difficulty.elite_step | 0.02 | +% к элитам за уровень |
| difficulty.elite_max | 0.40 | Максимальный бонус элитам |
| difficulty.max_plus | 20 | Макс уровень сложности в UI |
