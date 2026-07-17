"""GD v1: absurd narrative event seeds + anti-repeat fingerprints."""
from __future__ import annotations

import hashlib
import random
import re
from typing import Any

# Biome-agnostic + themed absurd beat cards. Pick 0–1 unused seed per round.
GD_ABSURD_EVENT_SEEDS: list[dict[str, str]] = [
    {"id": "echo_bargain", "biome": "*", "beat": "эхо предлагает сделку: половина урона за мемный комплимент монстру"},
    {"id": "sock_golem", "biome": "*", "beat": "из кучи тряпья встаёт голем из потерянных носков и требует дуэль взглядом"},
    {"id": "tax_imp", "biome": "*", "beat": "налоговый бес выписывает штраф за «несанкционированный героизм»"},
    {"id": "mirror_selfie", "biome": "*", "beat": "зеркало показывает прошлый провал отряда и требует селфи для искупления"},
    {"id": "hungry_chest", "biome": "*", "beat": "сундук с зубами просит покормить его стикером, иначе укусит сапог"},
    {"id": "wrong_dungeon", "biome": "*", "beat": "таблица «Вы здесь» утверждает, что отряд в спа-салоне, а не в подземелье"},
    {"id": "gossip_rats", "biome": "*", "beat": "крысы сплетничают о билде самой слабой вайфу громче боя"},
    {"id": "polite_trap", "biome": "*", "beat": "ловушка вежливо извиняется и просит отойти на полшага"},
    {"id": "karaoke_curse", "biome": "*", "beat": "проклятие караоке: следующий удар должен быть «в ритме»"},
    {"id": "lost_tourist", "biome": "*", "beat": "потерявшийся турист просит сфоткать его на фоне босса"},
    {"id": "slime_recipe", "biome": "swamp", "beat": "слизь диктует рецепт супа и обижается на отклонение"},
    {"id": "fog_password", "biome": "swamp", "beat": "туман требует пароль — любой стикер считается ответом"},
    {"id": "bone_queue", "biome": "crypt", "beat": "скелеты стоят в очереди за автографом целителя"},
    {"id": "coffin_wifi", "biome": "crypt", "beat": "в саркофаге ловится Wi‑Fi «Dungeon_Guest» без пароля"},
    {"id": "lava_spa", "biome": "volcano", "beat": "лава предлагает спа-процедуру «обжиг пят» со скидкой героям"},
    {"id": "ash_influencer", "biome": "volcano", "beat": "пепельный инфлюенсер стримит бой и просит реакцию"},
    {"id": "ice_contract", "biome": "ice", "beat": "ледяной контракт: кто молчит — получает иней на реплику"},
    {"id": "penguin_ref", "biome": "ice", "beat": "пингвин-рефери свистит фол за «слишком серьёзный» удар"},
    {"id": "forest_hr", "biome": "forest", "beat": "лесной HR проводит performance review вайфу mid-fight"},
    {"id": "mushroom_standup", "biome": "forest", "beat": "грибы устраивают стендап про класс лучницы"},
    {"id": "desert_mirage_cafe", "biome": "desert", "beat": "мираж открывает кафе с меню из миражей и счётом из песка"},
    {"id": "cactus_coach", "biome": "desert", "beat": "кактус-тренер орёт мотивационные цитаты в спину танку"},
    {"id": "ruin_tour", "biome": "ruins", "beat": "руина-гид проводит экскурсию и просит не бить экспонаты"},
    {"id": "ghost_ticket", "biome": "ruins", "beat": "призрак продаёт билеты «на финал», хотя босс ещё жив"},
    {"id": "abyss_meme", "biome": "abyss", "beat": "из бездны всплывает мем трёхлетней давности и требует реакции"},
    {"id": "void_unsubscribe", "biome": "abyss", "beat": "пустота предлагает отписаться от страданий одним кликом"},
    {"id": "castle_butler", "biome": "castle", "beat": "дворецкий монстров сервирует чай и оценивает манеры отряда"},
    {"id": "armor_fashion", "biome": "castle", "beat": "рыцарские доспехи устраивают модный показ под ударными"},
    {"id": "cave_echo_roast", "biome": "cave", "beat": "эхо в пещере роастит инициативу молчавших"},
    {"id": "bat_accountant", "biome": "cave", "beat": "летучая мышь-бухгалтер считает урон и спорит с округлением"},
]


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{4,}")


def narrative_fingerprint(text: str, *, max_tokens: int = 12) -> str:
    """Stable short fingerprint from distinctive tokens in narrative text."""
    raw = re.sub(r"<[^>]+>", " ", text or "")
    tokens = [t.lower() for t in _WORD_RE.findall(raw)]
    # Drop ultra-common filler
    stop = {
        "этот",
        "этой",
        "эта",
        "они",
        "она",
        "его",
        "её",
        "как",
        "что",
        "это",
        "для",
        "было",
        "были",
        "раунд",
        "отряд",
        "бой",
        "монстр",
        "подземелье",
    }
    picked = [t for t in tokens if t not in stop][:max_tokens]
    blob = "|".join(picked) if picked else (raw.strip()[:80] or "empty")
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def pick_absurd_event_seed(
    *,
    biome_tag: str | None,
    used_seed_ids: list[str] | None,
    rng: random.Random | None = None,
) -> dict[str, str] | None:
    """Pick one unused seed matching biome (or *) ; ~70% chance to return a seed."""
    r = rng or random.Random()
    if r.random() > 0.70:
        return None
    used = {str(x) for x in (used_seed_ids or [])}
    biome = (biome_tag or "").strip().lower()
    candidates = [
        s
        for s in GD_ABSURD_EVENT_SEEDS
        if s["id"] not in used
        and (s["biome"] == "*" or (biome and s["biome"] in biome))
    ]
    if not candidates:
        candidates = [s for s in GD_ABSURD_EVENT_SEEDS if s["id"] not in used]
    if not candidates:
        return None
    return dict(r.choice(candidates))


def recent_fingerprints_from_rounds(
    rounds: list[Any],
    *,
    limit: int = 8,
) -> list[str]:
    """Extract fingerprints from recent GDRound-like objects (ai_narrative field)."""
    out: list[str] = []
    for rnd in rounds[:limit]:
        narr = getattr(rnd, "ai_narrative", None)
        if not narr and isinstance(rnd, dict):
            narr = rnd.get("ai_narrative")
        if narr:
            out.append(narrative_fingerprint(str(narr)))
    return out


def format_seed_and_fingerprint_prompt_block(
    seed: dict[str, str] | None,
    fingerprints: list[str] | None,
) -> str:
    lines = ["УНИКАЛЬНОСТЬ НАРРАТИВА:"]
    if seed:
        lines.append(
            f"Обязательный beat этого раунда (id={seed.get('id')}): {seed.get('beat')}. "
            "Обыграй коротко и с лёгким юмором, без гротеска, не повторяя дословно."
        )
    else:
        lines.append("Отдельного event-seed нет — всё равно избегай шаблонных фраз.")
    fps = [f for f in (fingerprints or []) if f]
    if fps:
        lines.append(
            "Не повторяй шутки/сцены, похожие на недавние нарративы этого чата "
            f"(fingerprints: {', '.join(fps[:8])}). Придумай новый угол."
        )
    return "\n".join(lines)


def merge_used_seed_ids(state: dict[str, Any], seed_id: str | None) -> None:
    if not seed_id:
        return
    used = list(state.get("used_narrative_seed_ids") or [])
    if seed_id not in used:
        used.append(seed_id)
    state["used_narrative_seed_ids"] = used[-40:]
