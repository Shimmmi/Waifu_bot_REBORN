"""Static data for expeditions (affixes, perks, base locations)."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ExpeditionAffix:
    id: str
    name: str
    penalty: int
    counter: str
    category: str


@dataclass(frozen=True)
class ExpeditionPerk:
    id: str
    name: str
    counters: tuple[str, ...]
    category: str
    flavor_ru: str
    effect_ru: str


def format_perk_effect_ru(counters: tuple[str, ...], affix_by_id: dict[str, ExpeditionAffix] | None = None) -> str:
    """Снижает штраф + точные RU-названия препятствий (как в AFFIXES.name)."""
    lookup = affix_by_id if affix_by_id is not None else AFFIX_BY_ID
    names = [lookup[c].name for c in counters if c in lookup]
    if not names:
        return "Снижает штраф"
    return "Снижает штраф: " + ", ".join(names)


AFFIXES: list[ExpeditionAffix] = [
    # environment
    ExpeditionAffix(id="smelly", name="Вонючий", penalty=15, counter="gas_mask", category="environment"),
    ExpeditionAffix(id="flooded", name="Затопленный", penalty=15, counter="diver", category="environment"),
    ExpeditionAffix(id="hot", name="Жаркий", penalty=15, counter="fireproof", category="environment"),
    ExpeditionAffix(id="icy", name="Ледяной", penalty=15, counter="frostproof", category="environment"),
    ExpeditionAffix(id="foggy", name="Туманный", penalty=15, counter="navigator", category="environment"),
    ExpeditionAffix(id="stormy", name="Штормовой", penalty=15, counter="navigator", category="environment"),
    ExpeditionAffix(id="dusty", name="Пыльный", penalty=15, counter="desert_walker", category="environment"),
    ExpeditionAffix(id="poisonous_air", name="Ядовитый воздух", penalty=15, counter="gas_filter", category="environment"),
    ExpeditionAffix(id="snowstorm", name="Снежная буря", penalty=15, counter="snow_warrior", category="environment"),
    ExpeditionAffix(id="acid_rain", name="Кислотный дождь", penalty=15, counter="acid_proof", category="environment"),
    # creatures
    ExpeditionAffix(id="evil_elves", name="Злые эльфы", penalty=15, counter="elf_slayer", category="creatures"),
    ExpeditionAffix(id="orc_berserkers", name="Орки-берсеркеры", penalty=15, counter="orc_hunter", category="creatures"),
    ExpeditionAffix(id="undead", name="Нежить", penalty=15, counter="priest", category="creatures"),
    ExpeditionAffix(id="demons", name="Демоны", penalty=15, counter="demon_slayer", category="creatures"),
    ExpeditionAffix(id="dragons", name="Драконы", penalty=15, counter="dragonslayer", category="creatures"),
    ExpeditionAffix(id="goblins", name="Гоблины", penalty=15, counter="goblin_shaker", category="creatures"),
    ExpeditionAffix(id="trolls", name="Тролли", penalty=15, counter="troll_slayer", category="creatures"),
    ExpeditionAffix(id="vampires", name="Вампиры", penalty=15, counter="vampire_hunter", category="creatures"),
    ExpeditionAffix(id="giant_insects", name="Гигантские насекомые", penalty=15, counter="entomologist", category="creatures"),
    ExpeditionAffix(id="bats", name="Летучие мыши", penalty=15, counter="bat_hunter", category="creatures"),
    # location
    ExpeditionAffix(id="poisonous_mushrooms", name="Ядовитые грибы", penalty=15, counter="mushroom_expert", category="location"),
    ExpeditionAffix(id="traps", name="Ловушки", penalty=15, counter="scout", category="location"),
    ExpeditionAffix(id="cursed_artifacts", name="Проклятые артефакты", penalty=15, counter="archaeologist", category="location"),
    ExpeditionAffix(id="quicksand", name="Зыбучие пески", penalty=15, counter="desert_walker", category="location"),
    ExpeditionAffix(id="spiderwebs", name="Паутина", penalty=15, counter="spider_hunter", category="location"),
    ExpeditionAffix(id="acid_pools", name="Кислотные лужи", penalty=15, counter="chemist", category="location"),
    ExpeditionAffix(id="magical_anomalies", name="Магические аномалии", penalty=15, counter="magic_researcher", category="location"),
    ExpeditionAffix(id="ghostly_phenomena", name="Призрачные явления", penalty=15, counter="exorcist", category="location"),
    ExpeditionAffix(id="cave_ins", name="Обвалы", penalty=15, counter="mountain_engineer", category="location"),
    ExpeditionAffix(id="magnetic_anomalies", name="Магнитные аномалии", penalty=15, counter="anti_magnet", category="location"),
    # magical
    ExpeditionAffix(id="cursed", name="Проклятый", penalty=15, counter="curse_removal", category="magical"),
    ExpeditionAffix(id="enchanted", name="Зачарованный", penalty=15, counter="anti_mage", category="magical"),
    ExpeditionAffix(id="distorted", name="Искаженный", penalty=15, counter="spatial_mage", category="magical"),
    ExpeditionAffix(id="blinding", name="Ослепляющий", penalty=15, counter="light_protection", category="magical"),
    ExpeditionAffix(id="paralyzing", name="Парализующий", penalty=15, counter="magic_resistance", category="magical"),
    ExpeditionAffix(id="time_slow", name="Замедление времени", penalty=15, counter="chronomancer", category="magical"),
    ExpeditionAffix(id="time_fast", name="Ускорение времени", penalty=15, counter="accelerator", category="magical"),
    ExpeditionAffix(id="space_distortion", name="Искажение пространства", penalty=15, counter="spatial_navigator", category="magical"),
    ExpeditionAffix(id="mana_drain", name="Магическое истощение", penalty=15, counter="mana_shield", category="magical"),
    ExpeditionAffix(id="luck_curse", name="Проклятие удачи", penalty=15, counter="lucky", category="magical"),
    # psychological
    ExpeditionAffix(id="mental_attacks", name="Ментальные атаки", penalty=15, counter="mental_shield", category="psychological"),
    ExpeditionAffix(id="phobias", name="Навязчивые страхи", penalty=15, counter="strong_spirit", category="psychological"),
    ExpeditionAffix(id="hallucinations", name="Галлюцинации", penalty=15, counter="mental_clarity", category="psychological"),
    ExpeditionAffix(id="magic_sleep", name="Магический сон", penalty=15, counter="sleepless", category="psychological"),
    ExpeditionAffix(id="paranoia", name="Паранойя", penalty=15, counter="trusting", category="psychological"),
    ExpeditionAffix(id="amnesia", name="Амнезия", penalty=15, counter="photographic_memory", category="psychological"),
    ExpeditionAffix(id="persecution_complex", name="Мания преследования", penalty=15, counter="calm", category="psychological"),
    ExpeditionAffix(id="depression", name="Депрессия", penalty=15, counter="optimist", category="psychological"),
    ExpeditionAffix(id="aggression", name="Агрессия", penalty=15, counter="anger_control", category="psychological"),
    ExpeditionAffix(id="apathy", name="Апатия", penalty=15, counter="passionate", category="psychological"),
]


PERKS: list[ExpeditionPerk] = [
    # environment
    ExpeditionPerk(
        id="gas_mask",
        name="Газовая маска",
        counters=("smelly", "poisonous_air"),
        category="environment",
        flavor_ru="Дышит через фильтр «Премиум-Капуста» и называет вони «сложным букетом».",
        effect_ru="Снижает штраф от вони и ядовитого воздуха",
    ),
    ExpeditionPerk(
        id="diver",
        name="Водолаз",
        counters=("flooded",),
        category="environment",
        flavor_ru="Ныряет с важным видом, будто так и надо было начинать квест с лужи.",
        effect_ru="Снижает штраф в затопленных локациях",
    ),
    ExpeditionPerk(
        id="fireproof",
        name="Огнестойкий",
        counters=("hot",),
        category="environment",
        flavor_ru="Жарит маршмеллоу на лаве и жалуется, что «слабо подсолили».",
        effect_ru="Снижает штраф в жарких локациях",
    ),
    ExpeditionPerk(
        id="frostproof",
        name="Морозостойкий",
        counters=("icy",),
        category="environment",
        flavor_ru="Лижет сосульку ради науки и утверждает, что это «ледяной смузи».",
        effect_ru="Снижает штраф в ледяных локациях",
    ),
    ExpeditionPerk(
        id="navigator",
        name="Штурман",
        counters=("foggy", "stormy"),
        category="environment",
        flavor_ru="Ведёт отряд по компасу, который показывает «куда-нибудь не сюда».",
        effect_ru="Снижает штраф в тумане и шторме",
    ),
    ExpeditionPerk(
        id="desert_walker",
        name="Пустынник",
        counters=("dusty", "quicksand"),
        category="environment",
        flavor_ru="Считает песок личным врагом и ведёт с ним долгие переговоры.",
        effect_ru="Снижает штраф в пыли и зыбучих песках",
    ),
    ExpeditionPerk(
        id="gas_filter",
        name="Газовый фильтр",
        counters=("poisonous_air",),
        category="environment",
        flavor_ru="Носит запасной фильтр «на удачу» и иногда дышит им в качестве ароматерапии.",
        effect_ru="Снижает штраф от ядовитого воздуха",
    ),
    ExpeditionPerk(
        id="snow_warrior",
        name="Снежный воин",
        counters=("snowstorm",),
        category="environment",
        flavor_ru="Строит снежную крепость быстрее, чем отряд успевает замёрзнуть морально.",
        effect_ru="Снижает штраф в снежной буре",
    ),
    ExpeditionPerk(
        id="acid_proof",
        name="Кислотостойкий",
        counters=("acid_rain",),
        category="environment",
        flavor_ru="Под кислотным дождём распускает зонтик и шепчет: «погода — это настроение».",
        effect_ru="Снижает штраф от кислотного дождя",
    ),
    ExpeditionPerk(
        id="wind_walker",
        name="Ветроход",
        counters=("stormy",),
        category="environment",
        flavor_ru="Ловит ураган как попутку и просит не ронять причёску истории.",
        effect_ru="Снижает штраф в штормовых локациях",
    ),
    # creatures
    ExpeditionPerk(
        id="elf_slayer",
        name="Убийца эльфов",
        counters=("evil_elves",),
        category="creatures",
        flavor_ru="Специализируется на высокомерных ушастых и их токсичных комментариях о моде.",
        effect_ru="Бонус против злых эльфов",
    ),
    ExpeditionPerk(
        id="orc_hunter",
        name="Охотник на орков",
        counters=("orc_berserkers",),
        category="creatures",
        flavor_ru="Знает семнадцать способов сказать «спокойно, зелёный» до того, как начнётся драка.",
        effect_ru="Бонус против орков-берсеркеров",
    ),
    ExpeditionPerk(
        id="priest",
        name="Священник",
        counters=("undead",),
        category="creatures",
        flavor_ru="Кропит нежить святой водой и спрашивает, не записались ли они на отпевание.",
        effect_ru="Бонус против нежити",
    ),
    ExpeditionPerk(
        id="demon_slayer",
        name="Демоноборец",
        counters=("demons",),
        category="creatures",
        flavor_ru="Говорит демонам «не сегодня» таким тоном, будто отменяет подписку.",
        effect_ru="Бонус против демонов",
    ),
    ExpeditionPerk(
        id="dragonslayer",
        name="Драконоборец",
        counters=("dragons",),
        category="creatures",
        flavor_ru="Коллекционирует чешую как стикеры и мечтает о полном альбоме.",
        effect_ru="Бонус против драконов",
    ),
    ExpeditionPerk(
        id="goblin_shaker",
        name="Гоблинотряс",
        counters=("goblins",),
        category="creatures",
        flavor_ru="Трясёт гоблинов за уши, пока не выпадет мелочь и самооценка.",
        effect_ru="Бонус против гоблинов",
    ),
    ExpeditionPerk(
        id="troll_slayer",
        name="Троллеубийца",
        counters=("trolls",),
        category="creatures",
        flavor_ru="Бьёт троллей дубиной и мемами — что окажется больнее, неизвестно.",
        effect_ru="Бонус против троллей",
    ),
    ExpeditionPerk(
        id="vampire_hunter",
        name="Охотник на вампиров",
        counters=("vampires",),
        category="creatures",
        flavor_ru="Носит колья как зубочистки и предлагает вампирам «дневной спа».",
        effect_ru="Бонус против вампиров",
    ),
    ExpeditionPerk(
        id="entomologist",
        name="Энтомолог",
        counters=("giant_insects",),
        category="creatures",
        flavor_ru="Любит жуков professionally и лично — особенно когда они размером с диван.",
        effect_ru="Бонус против гигантских насекомых",
    ),
    ExpeditionPerk(
        id="bat_hunter",
        name="Охотник на летучих мышей",
        counters=("bats",),
        category="creatures",
        flavor_ru="Свистит ультразвуком и спорит с летучими мышами о расписании.",
        effect_ru="Бонус против летучих мышей",
    ),
    # location
    ExpeditionPerk(
        id="mushroom_expert",
        name="Грибник-знаток",
        counters=("poisonous_mushrooms",),
        category="location",
        flavor_ru="Различает «можно» и «похороны» по запаху и уровню самоуверенности.",
        effect_ru="Снижает штраф от ядовитых грибов",
    ),
    ExpeditionPerk(
        id="scout",
        name="Разведчик",
        counters=("traps",),
        category="location",
        flavor_ru="Находит ловушки взглядом «я же говорил» ещё до того, как кто-то наступит.",
        effect_ru="Снижает штраф от ловушек",
    ),
    ExpeditionPerk(
        id="archaeologist",
        name="Археолог",
        counters=("cursed_artifacts",),
        category="location",
        flavor_ru="Гладит проклятый кубок тряпочкой и шепчет: «ты просто недопонятый».",
        effect_ru="Снижает штраф от проклятых артефактов",
    ),
    ExpeditionPerk(
        id="swamp_walker",
        name="Болотный ходок",
        counters=("quicksand",),
        category="location",
        flavor_ru="Идёт по трясине так, будто это красная дорожка на болотном балу.",
        effect_ru="Снижает штраф от зыбучих песков",
    ),
    ExpeditionPerk(
        id="spider_hunter",
        name="Охотник на пауков",
        counters=("spiderwebs",),
        category="location",
        flavor_ru="Снимает паутину с лица как шарф и делает вид, что так и задумано.",
        effect_ru="Снижает штраф от паутины",
    ),
    ExpeditionPerk(
        id="chemist",
        name="Химик",
        counters=("acid_pools",),
        category="location",
        flavor_ru="Нюхает кислотные лужи «для пробы» и записывает рецепт в блокнот ужасов.",
        effect_ru="Снижает штраф от кислотных луж",
    ),
    ExpeditionPerk(
        id="magic_researcher",
        name="Маг-исследователь",
        counters=("magical_anomalies",),
        category="location",
        flavor_ru="Тыкает аномалию палочкой и говорит «интересный баг» вместо «беги».",
        effect_ru="Снижает штраф от магических аномалий",
    ),
    ExpeditionPerk(
        id="exorcist",
        name="Экзорцист",
        counters=("ghostly_phenomena",),
        category="location",
        flavor_ru="Выгоняет призраков вежливо, как незваных родственников с дивана.",
        effect_ru="Снижает штраф от призрачных явлений",
    ),
    ExpeditionPerk(
        id="mountain_engineer",
        name="Горный инженер",
        counters=("cave_ins",),
        category="location",
        flavor_ru="Подпирает потолок киркой и обещает, что «это временно, как ремонт».",
        effect_ru="Снижает штраф от обвалов",
    ),
    ExpeditionPerk(
        id="anti_magnet",
        name="Анти-магнит",
        counters=("magnetic_anomalies",),
        category="location",
        flavor_ru="Отталкивает аномалии харизмой и медью — наука пока не разобралась чем именно.",
        effect_ru="Снижает штраф от магнитных аномалий",
    ),
    # magical
    ExpeditionPerk(
        id="curse_removal",
        name="Снятие проклятий",
        counters=("cursed",),
        category="magical",
        flavor_ru="Снимает проклятия как старые стикеры: с характерным звуком и лёгким «упс».",
        effect_ru="Снижает штраф от проклятий",
    ),
    ExpeditionPerk(
        id="anti_mage",
        name="Антимаг",
        counters=("enchanted",),
        category="magical",
        flavor_ru="Гасит чужие чары взглядом «я не в настроении для спецэффектов».",
        effect_ru="Снижает штраф от зачарований",
    ),
    ExpeditionPerk(
        id="spatial_mage",
        name="Пространственный маг",
        counters=("distorted",),
        category="magical",
        flavor_ru="Складывает пространство оригами и теряет ключи в соседнем измерении.",
        effect_ru="Снижает штраф от искажений",
    ),
    ExpeditionPerk(
        id="light_protection",
        name="Защита от света",
        counters=("blinding",),
        category="magical",
        flavor_ru="Носит очки «от судьбы» и считает блики личным оскорблением.",
        effect_ru="Снижает штраф от ослепления",
    ),
    ExpeditionPerk(
        id="magic_resistance",
        name="Сопротивление магии",
        counters=("paralyzing",),
        category="magical",
        flavor_ru="Паралич обходит стороной: слишком занята спором с заклинанием.",
        effect_ru="Снижает штраф от паралича",
    ),
    ExpeditionPerk(
        id="chronomancer",
        name="Хрономант",
        counters=("time_slow",),
        category="magical",
        flavor_ru="Замедляет время, чтобы успеть допить чай до конца кат-сцены.",
        effect_ru="Снижает штраф от замедления времени",
    ),
    ExpeditionPerk(
        id="accelerator",
        name="Ускоритель",
        counters=("time_fast",),
        category="magical",
        flavor_ru="Ускоряет всё вокруг, кроме очереди за лутом — там свои законы.",
        effect_ru="Снижает штраф от ускорения времени",
    ),
    ExpeditionPerk(
        id="spatial_navigator",
        name="Пространственный навигатор",
        counters=("space_distortion",),
        category="magical",
        flavor_ru="Читает карту вселенной вверх ногами и всё равно приходит первой.",
        effect_ru="Снижает штраф от искажения пространства",
    ),
    ExpeditionPerk(
        id="mana_shield",
        name="Мана-щит",
        counters=("mana_drain",),
        category="magical",
        flavor_ru="Держит щит из маны и мемов; истощение стучится — не пускаем.",
        effect_ru="Снижает штраф от магического истощения",
    ),
    ExpeditionPerk(
        id="lucky",
        name="Удачливый",
        counters=("luck_curse",),
        category="magical",
        flavor_ru="Роняет клевер и всё равно выигрывает — вселенная устала спорить.",
        effect_ru="Снижает штраф от проклятия удачи",
    ),
    # psychological
    ExpeditionPerk(
        id="mental_shield",
        name="Ментальный щит",
        counters=("mental_attacks",),
        category="psychological",
        flavor_ru="В голове стоит «не беспокоить» — ментальные атаки оставляют визитку.",
        effect_ru="Снижает штраф от ментальных атак",
    ),
    ExpeditionPerk(
        id="strong_spirit",
        name="Стойкий дух",
        counters=("phobias",),
        category="psychological",
        flavor_ru="Боится только недосыпа и пустого инвентаря — остальное по расписанию.",
        effect_ru="Снижает штраф от навязчивых страхов",
    ),
    ExpeditionPerk(
        id="mental_clarity",
        name="Ясность разума",
        counters=("hallucinations",),
        category="psychological",
        flavor_ru="Видит галлюцинации, но вежливо просит их подождать в очереди.",
        effect_ru="Снижает штраф от галлюцинаций",
    ),
    ExpeditionPerk(
        id="sleepless",
        name="Бессонный",
        counters=("magic_sleep",),
        category="psychological",
        flavor_ru="Не спит принципиально: вдруг сон окажется платным DLC.",
        effect_ru="Снижает штраф от магического сна",
    ),
    ExpeditionPerk(
        id="trusting",
        name="Доверчивый",
        counters=("paranoia",),
        category="psychological",
        flavor_ru="Доверяет всем, включая подозрительный куст — и как-то это работает.",
        effect_ru="Снижает штраф от паранойи",
    ),
    ExpeditionPerk(
        id="photographic_memory",
        name="Фотографическая память",
        counters=("amnesia",),
        category="psychological",
        flavor_ru="Помнит всё, кроме где оставила ключи от подземелья — это нормально.",
        effect_ru="Снижает штраф от амнезии",
    ),
    ExpeditionPerk(
        id="calm",
        name="Спокойствие",
        counters=("persecution_complex",),
        category="psychological",
        flavor_ru="Даже если за ней гонятся, она делает вид, что это флешмоб.",
        effect_ru="Снижает штраф от мании преследования",
    ),
    ExpeditionPerk(
        id="optimist",
        name="Оптимист",
        counters=("depression",),
        category="psychological",
        flavor_ru="В любой яме видит «углублённый уровень» и бонус к характеру.",
        effect_ru="Снижает штраф от депрессии",
    ),
    ExpeditionPerk(
        id="anger_control",
        name="Контроль гнева",
        counters=("aggression",),
        category="psychological",
        flavor_ru="Считает до десяти… на драконьем, чтобы злость успела устать.",
        effect_ru="Снижает штраф от агрессии",
    ),
    ExpeditionPerk(
        id="passionate",
        name="Страстный",
        counters=("apathy",),
        category="psychological",
        flavor_ru="Горит энтузиазмом так ярко, что апатия просит огнетушитель.",
        effect_ru="Снижает штраф от апатии",
    ),
]


BASE_LOCATIONS: list[str] = [
    "Темный Лес",
    "Потерянные Руины",
    "Затопленный Храм",
    "Кристальные Пещеры",
    "Пустыня Забвения",
    "Часовня Времени",
    "Лабиринт Зеркал",
    "Глубинный Риф",
    "Воздушная Крепость",
    "Плачущие Болота",
]


AFFIX_BY_ID = {affix.id: affix for affix in AFFIXES}
# effect_ru всегда из точных имён препятствий (AFFIXES.name), не из ручных формулировок.
PERKS = [replace(p, effect_ru=format_perk_effect_ru(p.counters, AFFIX_BY_ID)) for p in PERKS]
PERK_BY_ID = {perk.id: perk for perk in PERKS}
