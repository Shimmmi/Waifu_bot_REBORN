# Скрытые навыки (зал тренировок, вкладка «?»)

Иконки: **`webp/<skill_id>.webp`**, где `skill_id` = `hidden_skill_definitions.id` в БД.

| Пример URL |
|------------|
| `/static/game/hidden-skills/webp/marathon.webp` |

Соотношение сторон **1:1**. В WebApp при отсутствии файла показывается emoji из поля `icon` в БД.

Сейчас в `webp/` лежат **заглушки** одного стиля; их можно заменить финальными артами без смены имён файлов.

## Список id (29)

`chatterbox`, `early_bird`, `marathon`, `night_owl`, `consistent`, `speedster`, `stoic`,
`sticker_master`, `photographer`, `audiophile`, `director`, `gif_fighter`,
`executioner`, `boss_slayer`, `elite_hunter`, `survivor`, `untouchable`, `dungeon_diver`,
`hoarder`, `merchant_friend`, `gambler`, `team_player`, `expedition_veteran`, `loyal_commander`,
`perfectionist`, `enchanter_soul`, `legend`, `echo_atlas`, `echo_catalog`
