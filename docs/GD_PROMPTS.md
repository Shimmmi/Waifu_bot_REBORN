# GD prompts — снимок для анализа

Актуальные LLM / image-промпты групповых подземелий (daily + classic GD v1).  
Снимок кода на `HEAD` (`4b595c6` и новее на ветке `feature/merc-overhaul`).  
Без предложений по улучшению — только as-is + пути к исходникам.

Динамические подстановки помечены как `{name}`, `{title}` и т.п.

---

## 1. Карта вызовов

```text
Daily GD (04:30 start / 04:00 finale)
  gd_daily_worker
    ├─ generate_gd_daily_start_narrative     → text LLM (caller=gd-start)
    ├─ analyze_day_word_stats                → text LLM (caller=gd-daily-words)
    └─ generate_gd_daily_podium_png          → Pillow race board (no image LLM)
         └─ gate: should_generate_podium (≥1 active msg_total>0)
         └─ title «Итоги дня»; no group text finale / empty photo caption

Classic GD v1 (раунды)
  gd_v1_worker / gd_cycle_service
    ├─ generate_gd_start_narrative           → text LLM (caller=gd-start)
    ├─ generate_gd_round_narrative           → text LLM (caller=gd-round)
    └─ generate_gd_finale_narrative          → text LLM (caller=gd-finale)

Общий system для всех text-нарративов GD:
  GD_SYSTEM_PROMPT  (gd_narrative_ai.py)
```

Файлы:

| Область | Файл |
|---|---|
| System + user builders + generate_* | [`src/waifu_bot/services/gd_narrative_ai.py`](../src/waifu_bot/services/gd_narrative_ai.py) |
| HTML-вёрстка (вставка в system) | [`src/waifu_bot/game/constants.py`](../src/waifu_bot/game/constants.py) (`GD_NARRATIVE_FORMATTING_RU`) |
| Absurd seeds / fingerprints | [`src/waifu_bot/services/gd_narrative_seeds.py`](../src/waifu_bot/services/gd_narrative_seeds.py) |
| Пьедестал (image) | [`src/waifu_bot/services/gd_podium_art.py`](../src/waifu_bot/services/gd_podium_art.py) |
| Топ-слова дня | [`src/waifu_bot/services/gd_daily_word_ai.py`](../src/waifu_bot/services/gd_daily_word_ai.py) |
| Legacy pie (image) | [`src/waifu_bot/services/gd_pie_chart.py`](../src/waifu_bot/services/gd_pie_chart.py) |
| Оркестрация daily | [`src/waifu_bot/services/gd_daily_worker.py`](../src/waifu_bot/services/gd_daily_worker.py) |

---

## 2. Общий system prompt

### 2.1 `GD_NARRATIVE_FORMATTING_RU`

Источник: `waifu_bot.game.constants.GD_NARRATIVE_FORMATTING_RU`

```text
Вёрстка ответа (обязательно): имена вайфу из состава — каждый раз в <b>Имя</b>; придуманное название навыка — <b>Название навыка</b> (краткий эффект в скобках: урон / дебафф / лечение / бафф); имена монстров при ударе можно в <b>...</b>. Разрешены только теги <b> и </b>. Текст разбей на 2–3 абзаца с пустой строкой между ними — не одной стеной. Не выводи числа HP/урона; эффекты — словами. Пример: <b>Путютя</b> с диким рыком обрушивает <b>Раскол Панциря</b> (урон), сдирая с <b>Паучка</b> липкую защиту.
```

### 2.2 `GD_SYSTEM_PROMPT`

Источник: `gd_narrative_ai.GD_SYSTEM_PROMPT`  
(внутри f-string подставляется блок из §2.1)

```text
Ты рассказчик в фэнтезийной RPG-игре про вайфу.
Пишешь о событиях групповых походов в Telegram-группе.
Стиль: ярко, с характером персонажей. Юмор — высокий приоритет: лёгкий, ситуативный, ироничный RPG-тон.
Без гротеска, телесного ужаса, жести и оскорблений игроков. Без «хрюканья» и нишевого трэша.
3–5 предложений на раунд, 2–3 абзаца с пустой строкой между ними.
{GD_NARRATIVE_FORMATTING_RU}
Язык: русский. Без markdown (#, *, списки). Без чисел и игровых механик в тексте.
Персонажи — девушки с именами и характерами.
Состав отряда и правила, кого упоминать, заданы в user-сообщении — следуй им строго.
Если дана «Хроника похода» — продолжи историю, не повторяй те же шутки и образы.
Для каждого применённого навыка придумай органичное название (1–3 слова),
соответствующее классу: маг — магия/стихии, воин — сила/ярость,
ассассин — скрытность/яд, лекарь — исцеление/свет,
рыцарь — защита/команда, лучник — точность/скорость, торговец — хитрость/алхимия.
Статус раунда определяет тон:
victory — финальный удар, гибель монстра, ощущение завершённости.
ongoing — стычка не закончена. НЕ убивай монстра. Намёк на продолжение.
party_wiped — монстр торжествует, отряд без сознания, намёк на возвращение.
```

Используется как `system=` для: daily start/finale, classic start/round/finale.  
Топ-слова дня используют **свой** system (см. §3.4).

---

## 3. Daily GD

### 3.1 Старт дня — `generate_gd_daily_start_narrative`

Файл: `gd_narrative_ai.py` · caller: `gd-start` · system: `GD_SYSTEM_PROMPT`  
`dungeon_name` / `party` намеренно **не** передаются в модель.

**User prompt (дословно):**

```text
Сгенерируй РОВНО один короткий абзац (1–2 предложения) на русском для Telegram (HTML: только <b> при необходимости).

Юмористическое обращение к ИГРОКАМ про дневной групповой поход, в духе «В опасное путешествие отправился наш бравый отряд домохозяек в составе:». Абзац ОБЯЗАН заканчиваться на «в составе:» (с двоеточием). Не перечисляй игроков и вайфу — список состава добавит код сразу после этой фразы.

ЗАПРЕЩЕНО: второй абзац, концовка про активность/экипировку, описание локации/атмосферы подземелья, лор, внешность/класс/раса вайфу, имена персонажей, цифры, списки.
```

**Stub (fallback без LLM):**

```text
В опасное путешествие отправился наш бравый отряд домохозяек в составе:
```

Список состава (вайфу, уровни) подставляется кодом в HTML-сообщение сразу после интро (`format_daily_start_roster_html`). Итоговый текст: `{intro}\n{roster}` — без второго абзаца.

---

### 3.2 Финал дня (в чат)

Текстовый HTML/AI-финал в групповой чат **не отправляется**. Итог дня — только картинка таблицы забега (§3.3) + ЛС с наградами.

Промпт `generate_gd_daily_finale_narrative` и хелперы `build_daily_finale_html_chunks` остаются в коде (тесты / legacy), но daily worker их в чат не шлёт.

---

### 3.3 Таблица забега (image) — `render_race_leaderboard_pillow`

Файл: `gd_podium_art.py` · **без image-LLM** (Pillow).  
Gate: `MIN_PODIUM_ACTIVE = 1` — skip только если никто не писал (`msg_total > 0`).

Daily-путь (`generate_gd_daily_podium_png`) рендерит Uma Musume–style race results board:

- место (`1st`/`2nd`/…), цветные waku-badges, кроп лица с paperdoll→portrait;
- имя основной вайфу (размер шрифта фиксирован);
- слова дня: до 6 чипов в 2 ряда × 3 ячейки (flex-ширина) между именем и pills;
- pills: `% чата`, `текст N`, `медиа N`, `симв. N`.

Макет/референсы: `info/race_leaderboard_editable.html`, `info/photo_2026-08-04_11-14-29.jpg`, `info/photo_2026-08-04_11-14-33.jpg`.

`{title}` на проде: **`Итоги дня`**. Caption под фото: пустой (не передаётся). Source в логах: `race_board`.  
Legacy RouterAI `_podium_prompt` / `generate_podium_routerai` остаются в файле, но **не** вызываются из daily-финала.

---

### 3.4 Топ-слова дня — `analyze_day_word_stats`

Файл: `gd_daily_word_ai.py` · caller: `gd-daily-words`

**System:**

```text
Ты аналитик частоты слов. Отвечай только JSON. Не цитируй сообщения целиком, не добавляй комментарии.
```

**User (`_build_prompt`):**

```text
Проанализируй тексты сообщений игроков за день. Для каждого user_id верни топ-5 самых частых слов.
Правила:
- Исключи предлоги, союзы, частицы и служебные слова.
- Приведи слова к именительному падежу (лемма), нижний регистр.
- Если ни одно слово не встречалось более 1 раза: no_word_repeated=true и top_words=[].
- Иначе no_word_repeated=false и top_words: до 5 элементов {"word","count"}, по убыванию count.
- Ответ ТОЛЬКО валидный JSON без markdown:
{"users":[{"user_id":123,"top_words":[{"word":"игра","count":5}],"no_word_repeated":false}]}
Данные:
{json: user_id → [messages…]}
```

При ошибке LLM — локальный fallback `local_word_stats`.

---

## 4. Classic GD v1

Все generate_* ниже: system = `GD_SYSTEM_PROMPT`.

### 4.1 Старт похода — `build_user_prompt_start` / `generate_gd_start_narrative`

Caller: `gd-start`

**Шаблон user prompt:**

```text
Этап: СТАРТ ПОХОДА (ещё нет боя, только вход в зону).
Подземелье: {dungeon_name}
Краткий антураж/биом: {biome_tag}.
СОСТАВ ОТРЯДА. Строго соблюдай класс и расу по строкам ниже; не приписывай меч или ярость воина магу, лучнику, лекарю и т.д.
В ответе не перечисляй сухие числа статов, но отрази уровень каждой намёком (опыт, новичок, бывалая, ветеран) согласно указанному уровню.
- Имя: {name}[, telegram user_id={uid}]. Класс (роль в бою): {class_ru} [внутр. id класса: {cid}]. Раса: {race_ru} [внутр. id расы: {rid}]. Уровень персонажа: {lvl}. {attack_style_hint}.
… (строка на каждого участника)
{build_gd_composition_instructions(phase="start")}
{GD_NARRATIVE_FORMATTING_RU}
Напиши 4–6 предложений на русском в 2 абзаца: отряд собирается у входа, настрой, короткие реплики или мысли в духе персонажей, ощущение угрозы впереди. Не повторяй дословно системные фразы про «15 минут».
```

**Stub:**

```text
Отряд собирается у входа в «{dungeon_name}». Впереди тёмные коридоры — пора действовать.
```

---

### 4.2 Раунд — `build_user_prompt_round` / `generate_gd_round_narrative`

Caller: `gd-round`

**Структура user prompt (блоки по порядку):**

```text
Подземелье: {dungeon} (биом: {biome})
Раунд {n} из ~{total_est}, следующий через 15 мин.
Статус раунда: {outcome}   # victory | ongoing | party_wiped

{folding_chronicle}         # если есть — build_gd_folding_chronicle

СОСТАВ ОТРЯДА:
Класс и раса каждой указаны словами и id — не подменяй архетип (маг ≠ воин с мечом).
- … format_gd_party_member_line(for_start=False) + HP% …

{build_gd_composition_instructions(phase="round")}

ПРОТИВНИКИ:
- {monster_name} Lv{level}, HP: {pct}%

ДЕЙСТВИЯ ЗА РАУНД:
- … _format_gd_action_line …

{build_gd_actions_format_block}

# если outcome == victory:
ПОБЕДА: все монстры повержены — это финальный, победный раунд. Заверши сцену триумфально, опиши добивающий удар и гибель противника. [Отдельно отметь MVP похода — <b>{mvp_name}</b> …]

# flags:
Особое: воскрешение — целей не было, обыграй.   # revive_no_target
Особое: лечение не нашло раненых, обыграй.     # heal_no_target

ИСХОД (для тона, не выводи числа в ответе):
{json outcomes_summary}

СЫРОЙ СБОР СООБЩЕНИЙ (telegram user_id → длина текста, медиа-типы, молчание):
{json raw_buffer_users}

СВОДКА УДАРОВ/ЭФФЕКТОВ (до 50 записей, для тона):
{json outcomes_hits}

ИСЦЕЛЕНИЯ:
{json outcomes_heals}

{format_seed_and_fingerprint_prompt_block}

Намёк на силу билда (без цифр): {power_hint}.   # если есть
```

**Stub:**

```text
[Раунд {n}. Бой продолжается...]
```

**Хроника (`build_gd_folding_chronicle`):**

```text
ХРОНИКА ПОХОДА (продолжи, не повторяй те же шутки/образы):
Факты: волна={wave}; раунд={round}; нокауты_отряда={wipe_count}; прошлый_исход={last_outcome}; недавно_падали: …
• Ранее (1): {stripped_narrative_≤280}
• Ранее (2): …
# или:
• Предыдущих сцен ещё нет — задай тон похода.
```

---

### 4.3 Финал похода — `build_user_prompt_finale` / `generate_gd_finale_narrative`

Caller: `gd-finale`

```text
Этап: ФИНАЛ ПОХОДА (победа, выход из подземелья).
Подземелье: {dungeon}
СОСТАВ ОТРЯДА (только эти участники существовали в походе):
- … format_gd_party_member_line(for_start=True) …
{build_gd_composition_instructions(phase="finale", contributions=…)}
ВКЛАД УЧАСТНИКОВ (для MVP и аутсайдера, не выводи числа в ответе):
- {name} (user {uid}): относительный вклад {score}
{GD_NARRATIVE_FORMATTING_RU}
Два героя финала (если разные): MVP силы/вклада в бой — {mvp_power}; MVP присутствия в чате — {mvp_presence}.
{format_seed_and_fingerprint_prompt_block}
Напиши эпичный короткий итог похода (4–6 предложений, 2 абзаца). Выдели MVP и одного с наименьшим вкладом — шутливо, без оскорблений. Если указаны два MVP (сила и присутствие) — обыграй обоих. Без цифр.
```

**Stub:**

```text
Герои вышли из подземелья — впереди новые приключения.
```

---

### 4.4 Вспомогательные блоки

#### `build_gd_composition_instructions`

Всегда начинается с:

```text
ПРАВИЛА СОСТАВА (обязательны):
В походе ровно {N} участник(ов). Упоминай в тексте ТОЛЬКО персонажей из блока СОСТАВ ОТРЯДА: {names}.
ЗАПРЕЩЕНО придумывать дополнительных союзников, «остальных в отряде», рыцарей, целительниц и любых NPC, которых нет в списке.
```

Далее по размеру отряда:

| Режим | Условие | Текст |
|---|---|---|
| solo | ≤1 | `Режим: одиночный поход. Единственный боец — {name}. Не пиши про «остальных»…` |
| small | 2–4 | `Режим: небольшой отряд ({N} чел.). Можешь кратко затронуть каждого…` |
| large | ≥5 | `Режим: большой отряд ({N} чел.). В фокусе … до 3 наиболее активных: {focus}. Остальных … не более одной-двух коротких фраз…` |

Фазовые добавки:

- **round:** шутка про молчавших по классу/расе *или* запрет выдумывать бездействующих.
- **start:** настрой одиночки / всего состава.
- **finale:** MVP и наименьший вклад только из списка + данные вклада.

#### `build_gd_actions_format_block`

```text
НАВЫКИ И ЭФФЕКТЫ (для вёрстки):
- {who}: придумай название навыка (1–3 слова) → <b>Название</b> ({effect_label}[, урон/лечение N]); имя вайфу в <b>{who}</b>
- {who}: текстовая атака → имя в <b>{who}</b>[, серия ударов,] эффект (урон {dmg})
# или:
- Нет навыков и текстовых атак — опиши общий ход боя.
```

#### `format_seed_and_fingerprint_prompt_block`

Источник: `gd_narrative_seeds.py`

```text
УНИКАЛЬНОСТЬ НАРРАТИВА:
Обязательный beat этого раунда (id={seed_id}): {beat}. Обыграй коротко и с лёгким юмором, без гротеска, не повторяя дословно.
# или без seed:
Отдельного event-seed нет — всё равно избегай шаблонных фраз.
Не повторяй шутки/сцены, похожие на недавние нарративы этого чата (fingerprints: {fp1}, …). Придумай новый угол.
```

---

### 4.5 Absurd event seeds

Источник: `GD_ABSURD_EVENT_SEEDS` в `gd_narrative_seeds.py` (biome `*` = любой).

| id | biome | beat |
|---|---|---|
| echo_bargain | * | эхо предлагает сделку: половина урона за мемный комплимент монстру |
| sock_golem | * | из кучи тряпья встаёт голем из потерянных носков и требует дуэль взглядом |
| tax_imp | * | налоговый бес выписывает штраф за «несанкционированный героизм» |
| mirror_selfie | * | зеркало показывает прошлый провал отряда и требует селфи для искупления |
| hungry_chest | * | сундук с зубами просит покормить его стикером, иначе укусит сапог |
| wrong_dungeon | * | таблица «Вы здесь» утверждает, что отряд в спа-салоне, а не в подземелье |
| gossip_rats | * | крысы сплетничают о билде самой слабой вайфу громче боя |
| polite_trap | * | ловушка вежливо извиняется и просит отойти на полшага |
| karaoke_curse | * | проклятие караоке: следующий удар должен быть «в ритме» |
| lost_tourist | * | потерявшийся турист просит сфоткать его на фоне босса |
| slime_recipe | swamp | слизь диктует рецепт супа и обижается на отклонение |
| fog_password | swamp | туман требует пароль — любой стикер считается ответом |
| bone_queue | crypt | скелеты стоят в очереди за автографом целителя |
| coffin_wifi | crypt | в саркофаге ловится Wi‑Fi «Dungeon_Guest» без пароля |
| lava_spa | volcano | лава предлагает спа-процедуру «обжиг пят» со скидкой героям |
| ash_influencer | volcano | пепельный инфлюенсер стримит бой и просит реакцию |
| ice_contract | ice | ледяной контракт: кто молчит — получает иней на реплику |
| penguin_ref | ice | пингвин-рефери свистит фол за «слишком серьёзный» удар |
| forest_hr | forest | лесной HR проводит performance review вайфу mid-fight |
| mushroom_standup | forest | грибы устраивают стендап про класс лучницы |
| desert_mirage_cafe | desert | мираж открывает кафе с меню из миражей и счётом из песка |
| cactus_coach | desert | кактус-тренер орёт мотивационные цитаты в спину танку |
| ruin_tour | ruins | руина-гид проводит экскурсию и просит не бить экспонаты |
| ghost_ticket | ruins | призрак продаёт билеты «на финал», хотя босс ещё жив |
| abyss_meme | abyss | из бездны всплывает мем трёхлетней давности и требует реакции |
| void_unsubscribe | abyss | пустота предлагает отписаться от страданий одним кликом |
| castle_butler | castle | дворецкий монстров сервирует чай и оценивает манеры отряда |
| armor_fashion | castle | рыцарские доспехи устраивают модный показ под ударными |
| cave_echo_roast | cave | эхо в пещере роастит инициативу молчавших |
| bat_accountant | cave | летучая мышь-бухгалтер считает урон и спорит с округлением |

---

## 5. Legacy: pie chart (не daily-финал)

Daily-финал переключён на podium (§3.3). Код pie остаётся в `gd_pie_chart.py`.

**`_pie_prompt`:**

```text
Create a clean circular pie chart infographic for a Telegram game summary. Title at top: «{title}». Dark navy background (#1A1F2B), warm accent colors, high contrast white labels. Show a clear legend with EXACT percentages from the data — do not invent or round differently. No people, no anime characters, no logos, no watermarks, no UI chrome. Flat modern data visualization only.

DATA (must match exactly):
{label}: {pct}% ({msgs} msgs)
…
```

---

## 6. Метаданные для правок

| Промпт | Файл | Функция / константа | Channel | caller / model |
|---|---|---|---|---|
| System narrative | `gd_narrative_ai.py` | `GD_SYSTEM_PROMPT` | text system | — |
| HTML formatting | `constants.py` | `GD_NARRATIVE_FORMATTING_RU` | вставка в system | — |
| Daily start | `gd_narrative_ai.py` | `generate_gd_daily_start_narrative` | text user | `gd-start` |
| Daily finale | `gd_narrative_ai.py` | `generate_gd_daily_finale_narrative` | text user | `gd-finale` |
| Daily words system | `gd_daily_word_ai.py` | `analyze_day_word_stats` | text system | `gd-daily-words` |
| Daily words user | `gd_daily_word_ai.py` | `_build_prompt` | text user | `gd-daily-words` |
| Podium main | `gd_podium_art.py` | `_podium_prompt` | image text | `get_image_model()` |
| Podium ref caption | `gd_podium_art.py` | `generate_podium_routerai` | image text+image | `get_image_model()` |
| Classic start | `gd_narrative_ai.py` | `build_user_prompt_start` | text user | `gd-start` |
| Classic round | `gd_narrative_ai.py` | `build_user_prompt_round` | text user | `gd-round` |
| Classic finale | `gd_narrative_ai.py` | `build_user_prompt_finale` | text user | `gd-finale` |
| Composition rules | `gd_narrative_ai.py` | `build_gd_composition_instructions` | text block | — |
| Actions format | `gd_narrative_ai.py` | `build_gd_actions_format_block` | text block | — |
| Seeds / fingerprints | `gd_narrative_seeds.py` | `format_seed_and_fingerprint_prompt_block` | text block | — |
| Legacy pie | `gd_pie_chart.py` | `_pie_prompt` | image text | `get_image_model()` |

Preset текста: `settings.ai_preset_gd`.
