---
name: Caravan tip game facts
overview: Передавать в промпт погонщицы каравана структурированные факты из БД (активные навыки, шаблоны монстров по акту) и жёстко требовать совет только на их основе; доработать эндпоинт и `generate_caravan_driver_tip`.
todos:
  - id: ctx-builder
    content: "build_caravan_driver_game_knowledge(session, act): skills + monster_templates + dominant_trait_ru"
    status: completed
  - id: prompt-api
    content: generate_caravan_driver_tip(..., game_knowledge); обновить промпт и routes.py
    status: completed
isProject: false
---

# Совет погонщицы: только игровые факты

## Проблема

`[generate_caravan_driver_tip](src/waifu_bot/services/expedition_events_ai.py)` сейчас получает только `current_act`, `max_act`, `gold` и просит «общий» совет — модель не опирается на реальные навыки и монстров игры.

## Подход

1. **Собрать контекст из БД** (в том же запросе, где уже есть `AsyncSession` в `[caravan_driver_tip](src/waifu_bot/api/routes.py)`):
  - **Активные навыки**: `select` из `[Skill](src/waifu_bot/db/models/skill.py)` где `skill_type == SkillType.ACTIVE` (или `== 1`), поля `name`, `description` (обрезать `description` до ~200–300 символов на запись, лимит строк ~20–30 чтобы не раздувать токены).
  - **Шаблоны монстров по акту**: `select` из `[MonsterTemplate](src/waifu_bot/db/models/dungeon.py)` с фильтром `act_min <= current_act <= act_max` (или пересечение диапазона акта игрока), случайная выборка или `LIMIT` с `order_by(func.random())` (для SQLite/Postgres уточнить совместимость; при необходимости — загрузить id и выбрать случайные в Python).
  - Для каждого монстра в контекст добавить **вычисляемую строку «доминирующая угроза»** без HP: сравнить пары из `dmg_per_level`, `hp_per_level`, `base_difficulty` (и при желании `tier`) и выбрать одну человекочитаемую метку на русском (например «высокий рост урона», «очень плотный по HP», «высокая базовая сложность») — это заменяет просьбу «самый большой параметр не считая здоровья», т.к. у шаблона нет СИЛ/ЛОВ как у героя.
2. **Расширить сигнатуру** `generate_caravan_driver_tip`: добавить аргумент `game_knowledge: dict` (или отдельные `skills_payload`, `monsters_payload`), сериализовать в JSON и вставить в промпт как отдельный блок `ИГРОВЫЕ_ФАКТЫ (JSON): ...`.
3. **Новый текст промпта** (суть требований):
  - Роль: погонщица, обращение на «вы», 2–4 предложения, без markdown.
  - **Обязательно** опереться на **один** факт из `skills` **или** **одного** монстра из `monsters` из JSON (как в примерах пользователя: «Знал ли ты…», «Встречал ли ты…»).
  - Запрет: не придумывать названий навыков/монстров, которых нет в JSON; не утверждать цифры формул, которых нет в переданных полях; можно перефразировать `description` навыка и использовать переданную метку угрозы для монстра.
4. **Маршрут** `[caravan_driver_tip](src/waifu_bot/api/routes.py)`: перед вызовом генератора вызвать небольшую функцию `async def build_caravan_driver_game_knowledge(session, current_act: int) -> dict` (разместить в `expedition_events_ai.py` рядом с генератором или в `services/caravan_tips.py` если хочется разнести — достаточно одного файла для минимального диффа).
5. **Граничные случаи**: если списки пусты (нет данных в БД) — в промпт явно указать пустые массивы и добавить инструкцию: «если списки пусты — дай общий совет по акту и золоту без выдуманных имён»; либо вернуть короткий статический fallback без LLM (опционально, по желанию — в плане заложить только мягкий fallback в промпте).

## Файлы


| Изменение                           | Файл                                                                                                                                               |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Сбор контекста + обновлённый промпт | `[src/waifu_bot/services/expedition_events_ai.py](src/waifu_bot/services/expedition_events_ai.py)`                                                 |
| Передача контекста из БД            | `[src/waifu_bot/api/routes.py](src/waifu_bot/api/routes.py)` (`caravan_driver_tip`)                                                                |
| При необходимости импорт моделей    | `[src/waifu_bot/db/models/skill.py](src/waifu_bot/db/models/skill.py)`, `[src/waifu_bot/db/models/dungeon.py](src/waifu_bot/db/models/dungeon.py)` |


## Проверка

- После деплоя: несколько запросов `POST /api/player/caravan-driver-tip` — в ответе должны встречаться реальные имена из БД (навык или монстр из выборки по акту).

