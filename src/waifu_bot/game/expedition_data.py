"""Static data for expeditions (affixes, perks, base locations)."""

from __future__ import annotations

from dataclasses import dataclass


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
    ExpeditionAffix(id="giant_insects", name="Насекомые-гиганты", penalty=15, counter="entomologist", category="creatures"),
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
    # environment counters
    ExpeditionPerk(id="gas_mask", name="Газовая маска", counters=("smelly", "poisonous_air"), category="environment"),
    ExpeditionPerk(id="diver", name="Водолаз", counters=("flooded",), category="environment"),
    ExpeditionPerk(id="fireproof", name="Огнестойкий", counters=("hot",), category="environment"),
    ExpeditionPerk(id="frostproof", name="Морозостойкий", counters=("icy",), category="environment"),
    ExpeditionPerk(id="navigator", name="Штурман", counters=("foggy", "stormy"), category="environment"),
    ExpeditionPerk(id="desert_walker", name="Пустынник", counters=("dusty", "quicksand"), category="environment"),
    ExpeditionPerk(id="gas_filter", name="Газовый фильтр", counters=("poisonous_air",), category="environment"),
    ExpeditionPerk(id="snow_warrior", name="Снежный воин", counters=("snowstorm",), category="environment"),
    ExpeditionPerk(id="acid_proof", name="Кислотостойкий", counters=("acid_rain",), category="environment"),
    ExpeditionPerk(id="wind_walker", name="Ветроход", counters=("stormy",), category="environment"),
    # creature counters
    ExpeditionPerk(id="elf_slayer", name="Убийца эльфов", counters=("evil_elves",), category="creatures"),
    ExpeditionPerk(id="orc_hunter", name="Охотник на орков", counters=("orc_berserkers",), category="creatures"),
    ExpeditionPerk(id="priest", name="Священник", counters=("undead",), category="creatures"),
    ExpeditionPerk(id="demon_slayer", name="Демоноборец", counters=("demons",), category="creatures"),
    ExpeditionPerk(id="dragonslayer", name="Драконоборец", counters=("dragons",), category="creatures"),
    ExpeditionPerk(id="goblin_shaker", name="Гоблинотряс", counters=("goblins",), category="creatures"),
    ExpeditionPerk(id="troll_slayer", name="Троллеубийца", counters=("trolls",), category="creatures"),
    ExpeditionPerk(id="vampire_hunter", name="Охотник на вампиров", counters=("vampires",), category="creatures"),
    ExpeditionPerk(id="entomologist", name="Энтомолог", counters=("giant_insects",), category="creatures"),
    ExpeditionPerk(id="bat_hunter", name="Охотник на летучих мышей", counters=("bats",), category="creatures"),
    # location counters
    ExpeditionPerk(id="mushroom_expert", name="Грибник-знаток", counters=("poisonous_mushrooms",), category="location"),
    ExpeditionPerk(id="scout", name="Разведчик", counters=("traps",), category="location"),
    ExpeditionPerk(id="archaeologist", name="Археолог", counters=("cursed_artifacts",), category="location"),
    ExpeditionPerk(id="swamp_walker", name="Болотный ходок", counters=("quicksand",), category="location"),
    ExpeditionPerk(id="spider_hunter", name="Охотник на пауков", counters=("spiderwebs",), category="location"),
    ExpeditionPerk(id="chemist", name="Химик", counters=("acid_pools",), category="location"),
    ExpeditionPerk(id="magic_researcher", name="Маг-исследователь", counters=("magical_anomalies",), category="location"),
    ExpeditionPerk(id="exorcist", name="Экзорцист", counters=("ghostly_phenomena",), category="location"),
    ExpeditionPerk(id="mountain_engineer", name="Горный инженер", counters=("cave_ins",), category="location"),
    ExpeditionPerk(id="anti_magnet", name="Анти-магнит", counters=("magnetic_anomalies",), category="location"),
    # magical counters
    ExpeditionPerk(id="curse_removal", name="Снятие проклятий", counters=("cursed",), category="magical"),
    ExpeditionPerk(id="anti_mage", name="Антимаг", counters=("enchanted",), category="magical"),
    ExpeditionPerk(id="spatial_mage", name="Пространственный маг", counters=("distorted",), category="magical"),
    ExpeditionPerk(id="light_protection", name="Защита от света", counters=("blinding",), category="magical"),
    ExpeditionPerk(id="magic_resistance", name="Сопротивление магии", counters=("paralyzing",), category="magical"),
    ExpeditionPerk(id="chronomancer", name="Хрономант", counters=("time_slow",), category="magical"),
    ExpeditionPerk(id="accelerator", name="Ускоритель", counters=("time_fast",), category="magical"),
    ExpeditionPerk(id="spatial_navigator", name="Пространственный навигатор", counters=("space_distortion",), category="magical"),
    ExpeditionPerk(id="mana_shield", name="Мана-щит", counters=("mana_drain",), category="magical"),
    ExpeditionPerk(id="lucky", name="Удачливый", counters=("luck_curse",), category="magical"),
    # psychological counters
    ExpeditionPerk(id="mental_shield", name="Ментальный щит", counters=("mental_attacks",), category="psychological"),
    ExpeditionPerk(id="strong_spirit", name="Стойкий дух", counters=("phobias",), category="psychological"),
    ExpeditionPerk(id="mental_clarity", name="Ясность разума", counters=("hallucinations",), category="psychological"),
    ExpeditionPerk(id="sleepless", name="Бессонный", counters=("magic_sleep",), category="psychological"),
    ExpeditionPerk(id="trusting", name="Доверчивый", counters=("paranoia",), category="psychological"),
    ExpeditionPerk(id="photographic_memory", name="Фотографическая память", counters=("amnesia",), category="psychological"),
    ExpeditionPerk(id="calm", name="Спокойствие", counters=("persecution_complex",), category="psychological"),
    ExpeditionPerk(id="optimist", name="Оптимист", counters=("depression",), category="psychological"),
    ExpeditionPerk(id="anger_control", name="Контроль гнева", counters=("aggression",), category="psychological"),
    ExpeditionPerk(id="passionate", name="Страстный", counters=("apathy",), category="psychological"),
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
PERK_BY_ID = {perk.id: perk for perk in PERKS}

