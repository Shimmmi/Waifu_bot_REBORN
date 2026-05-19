# Пассивные навыки (тренировочный зал)

Иконки узлов дерева пассивок: **`webp/<node_id>.webp`**, где `node_id` совпадает с `passive_skill_nodes.id` в БД и с ключами `PASSIVE_NODE_ICONS` в `src/waifu_bot/webapp/app.js`.

| Ветка | Префикс id | Пример URL |
|-------|--------------|------------|
| Воин | `w_` | `/static/game/passive-skills/webp/w_bash.webp` |
| Тень | `s_` | `/static/game/passive-skills/webp/s_keen.webp` |
| Мудрец | `m_` | `/static/game/passive-skills/webp/m_arcane.webp` |

Сейчас в `webp/` лежат **заглушки** одного стиля (96×96); их можно заменить финальными артами без смены имён файлов.
