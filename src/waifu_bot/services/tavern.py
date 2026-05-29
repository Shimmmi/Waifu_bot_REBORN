"""Tavern service for hiring waifus and managing squad."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload
from sqlalchemy.exc import SQLAlchemyError

from waifu_bot.db.models import (
    HiredWaifu,
    Player,
    TavernHireSlot,
    TavernState,
    WaifuClass,
    WaifuRace,
    WaifuRarity,
)
from waifu_bot.game.constants import (
    HIRED_HP_REGEN_MINUTES_PER_HP,
    HIRED_WAIFU_POOL_MAX,
    RESERVE_SIZE,
    SQUAD_SIZE,
    TAVERN_HEAL_GOLD_PER_HP,
    TAVERN_HIRE_COST,
    TAVERN_SLOTS_PER_DAY,
)
from waifu_bot.game.expedition_redesign import pick_perk_id_for_class
from waifu_bot.game.expedition_data import PERK_BY_ID, PERKS
from waifu_bot.services.expedition_events_ai import (
    generate_hire_waifu_name_and_bio,
    generate_hire_waifu_image,
)
from waifu_bot.services.passive_skills import (
    apply_passive_hire_cost,
    compute_tavern_hire_price,
)


async def is_first_hire_free(session: AsyncSession, player_id: int) -> bool:
    """True if the player has never successfully hired a mercenary before."""
    hired_waifus = int(
        await session.scalar(
            select(func.count()).select_from(HiredWaifu).where(HiredWaifu.player_id == player_id)
        )
        or 0
    )
    if hired_waifus > 0:
        return False
    used_slots = int(
        await session.scalar(
            select(func.count())
            .select_from(TavernHireSlot)
            .where(
                TavernHireSlot.player_id == player_id,
                TavernHireSlot.hired_at.isnot(None),
            )
        )
        or 0
    )
    return used_slots == 0


async def compute_effective_tavern_hire_price(session: AsyncSession, player_id: int) -> int:
    """First mercenary hire is free; subsequent hires use the normal discount formula."""
    if await is_first_hire_free(session, player_id):
        return 0
    cost = await compute_tavern_hire_price(session, player_id, TAVERN_HIRE_COST)
    try:
        from waifu_bot.services.guild_skill_effects import apply_price_discount_pct, effect_values_for_player

        gfx = await effect_values_for_player(session, player_id)
        cost = apply_price_discount_pct(cost, float(gfx.get("tavern_hire_discount_pct", 0) or 0))
    except Exception:
        pass
    return int(cost)

# Русские названия для шаблонной биографии (без OpenRouter)
_RACE_NAMES_RU = {
    1: "человек",
    2: "эльфийка",
    3: "зверолюдка",
    4: "ангел",
    5: "вампирша",
    6: "демоница",
    7: "фея",
}
_CLASS_NAMES_RU = {
    1: "рыцарь",
    2: "воин",
    3: "лучник",
    4: "маг",
    5: "ассасин",
    6: "целительница",
    7: "торговка",
}

# Запасные имена по расе, если ИИ недоступен (без Waifu_xxxx)
_FALLBACK_NAMES_BY_RACE: dict[int, list[str]] = {
    1: ["Мира", "Лена", "Ада", "Соль", "Дарья", "Иволга", "Снежана", "Власта", "Млада", "Заряна", "Берёзка", "Радмила"],
    2: ["Аэль", "Нэли", "Сиэль", "Ирэн", "Элестрин", "Фейлинн", "Аэвенир", "Лютиэль", "Сильвэ", "Тинувэль", "Эовин", "Карасэль"],
    3: ["Рэй", "Кора", "Яра", "Тэйн", "Грюнхильда", "Брунн", "Хельга", "Тордис", "Сигрид", "Рагна", "Ульфхильд", "Боргильда"],
    4: ["Лира", "Аэра", "Нэль", "Сия", "Мейлин", "Сакура-но", "Цзинь", "Юкико", "Ханами", "Аои", "Рэйка", "Цубаки"],
    5: ["Вэра", "Нокс", "Дэйн", "Рива", "Мортисса", "Лилит", "Карна", "Эреш", "Морриган", "Невея", "Тенебра", "Сумрана"],
    6: ["Зэль", "Кира", "Асха", "Вэл", "Шаррхан", "Зафира", "Лейла-дюн", "Самира", "Назиля", "Раксана", "Джамиля", "Аиша-кан"],
    7: ["Пик", "Дэви", "Нии", "Фэй", "Тильда", "Бузина", "Чубрик", "Пеппа", "Мармора", "Глюк", "Финтик", "Кнопа"],
}


def _fallback_name_by_race(race_id: int) -> str:
    import random
    pool = _FALLBACK_NAMES_BY_RACE.get(
        race_id, ["Аира", "Мика", "Нэли", "Ки", "Орла", "Вестра", "Лумина", "Тэсса"]
    )
    return random.choice(pool)


def _template_bio(waifu: HiredWaifu) -> str:
    """Генерирует короткую биографию наёмницы по шаблону (без внешнего AI)."""
    name = waifu.name or "Наёмница"
    race_id = int(waifu.race or 1)
    class_id = int(waifu.class_ or 1)
    race_ru = _RACE_NAMES_RU.get(race_id, "путница")
    class_ru = _CLASS_NAMES_RU.get(class_id, "искательница приключений")
    perk_ids = waifu.perks or []
    perk_names = []
    for pid in perk_ids[:4]:
        p_id = pid if isinstance(pid, str) else str(pid)
        if p_id in PERK_BY_ID:
            perk_names.append(PERK_BY_ID[p_id].name)
    skills_str = ", ".join(perk_names) if perk_names else "опыт в походах"
    return (
        f"{name} — {race_ru} и {class_ru} по призванию. "
        f"Отличается умениями: {skills_str}. "
        "Готова присоединиться к отряду и делить тяготы пути."
    )

try:
    from zoneinfo import ZoneInfo

    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover
    MOSCOW_TZ = timezone.utc


class TavernService:
    """Service for tavern operations."""

    async def get_available_waifus(
        self, session: AsyncSession, player_id: int
    ) -> List[TavernHireSlot]:
        """
        Get today's tavern hire slots for a player (4 per Moscow day).

        NOTE: These are NOT hired waifus; they are "hooded figures" / opportunities to hire.
        """
        today = self._moscow_today()
        return await self._ensure_day_slots(session, player_id, today)

    async def hire_waifu(
        self,
        session: AsyncSession,
        player_id: int,
        slot: Optional[int] = None,
    ) -> dict:
        """Hire a waifu from tavern using one daily slot."""
        # Get player
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        hire_cost = await compute_effective_tavern_hire_price(session, player_id)
        first_hire_free = hire_cost == 0
        # Check gold (skip for the first free hire)
        if hire_cost > 0 and player.gold < hire_cost:
            return {
                "error": "insufficient_gold",
                "required": hire_cost,
                "have": player.gold,
            }

        # Единый пул наёмниц (ТЗ v1.3)
        total_hired = int(
            await session.scalar(
                select(func.count()).select_from(HiredWaifu).where(HiredWaifu.player_id == player_id)
            )
            or 0
        )
        if total_hired >= HIRED_WAIFU_POOL_MAX:
            return {"error": "reserve_full"}

        # Consume a daily hire slot
        today = self._moscow_today()
        slots = await self._ensure_day_slots(session, player_id, today)
        chosen: TavernHireSlot | None = None

        if slot is not None:
            try:
                s = int(slot)
            except Exception:
                return {"error": "invalid_slot"}
            chosen = next((x for x in slots if int(x.slot) == s), None)
        else:
            chosen = next((x for x in slots if x.hired_at is None), None)

        if not chosen:
            return {"error": "slot_not_found"}
        if chosen.hired_at is not None:
            return {"error": "slot_taken", "slot": int(chosen.slot)}

        waifu = await self._generate_waifu(session, player_id)
        chosen.hired_waifu_id = waifu.id
        chosen.hired_at = datetime.now(tz=timezone.utc)

        # Deduct gold (first hire is free)
        if hire_cost > 0:
            player.gold -= hire_cost

        # Имя и био: OpenRouter возвращает JSON {name, bio}; при недоступности — fallback по расе + шаблон
        _, race_ru, class_ru, level, perk_names = self._waifu_bio_inputs(waifu)
        name_bio = await generate_hire_waifu_name_and_bio(race_ru, class_ru, level, perk_names)
        if name_bio:
            waifu.name = name_bio[0]
            bio = name_bio[1]
        else:
            waifu.name = _fallback_name_by_race(int(waifu.race or 1))
            bio = _template_bio(waifu)
        waifu.bio = bio

        # Портрет через OpenRouter image API (cursor_plan_7): modalities ["image"], ответ в message.images[]
        image_b64 = await generate_hire_waifu_image(
            race_ru, class_ru, bio, waifu.name, perk_ids=waifu.perks
        )
        if image_b64:
            waifu.image_data = image_b64
            waifu.image_mime = "image/webp"
            waifu.image_generated_at = datetime.now(tz=timezone.utc)

        from waifu_bot.services.event_log import log_event

        await log_event(
            session,
            player_id,
            "tavern_hired",
            {"waifu_name": waifu.name, "rarity": waifu.rarity},
        )
        await session.commit()
        image_url = None
        if getattr(waifu, "image_data", None):
            mime = getattr(waifu, "image_mime", None) or "image/webp"
            image_url = f"data:{mime};base64,{waifu.image_data}"
        out = {
            "success": True,
            "waifu_id": waifu.id,
            "waifu_name": waifu.name,
            "waifu_rarity": waifu.rarity,
            "gold_remaining": player.gold,
            "slot": int(chosen.slot),
            "bio": bio,
            "image_url": image_url,
            "hire_cost": hire_cost,
            "first_hire_free": first_hire_free,
        }
        if not first_hire_free:
            try:
                from waifu_bot.services.guild_skill_effects import (
                    effect_values_for_player,
                    guild_skill_contributions,
                    pct_bonus_lines_ru,
                )

                gfx = await effect_values_for_player(session, player_id)
                if float(gfx.get("tavern_hire_discount_pct", 0) or 0) > 0:
                    lines = pct_bonus_lines_ru(
                        await guild_skill_contributions(
                            session, player_id, params={"tavern_hire_discount_pct"}
                        )
                    )
                    if lines:
                        out["guild_bonus_hint"] = lines[0]
            except Exception:
                pass
        return out

    def _apply_hired_regen(self, waifu: HiredWaifu, now: datetime) -> None:
        """Применить реген HP со временем (на месте)."""
        max_hp = getattr(waifu, "max_hp", 65) or 65
        current = getattr(waifu, "current_hp", max_hp)
        if current >= max_hp:
            return
        if current <= 0:
            return
        updated_at = getattr(waifu, "hp_updated_at", None)
        if not updated_at:
            waifu.hp_updated_at = now
            return
        minutes = (now - updated_at).total_seconds() / 60.0
        add_hp = int(minutes / HIRED_HP_REGEN_MINUTES_PER_HP)
        if add_hp <= 0:
            return
        waifu.current_hp = min(max_hp, current + add_hp)
        waifu.hp_updated_at = now

    async def get_squad(self, session: AsyncSession, player_id: int) -> List[HiredWaifu]:
        """Get player's squad (6 slots). Реген HP применяется при загрузке."""
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                HiredWaifu.squad_position.isnot(None),
                HiredWaifu.squad_position >= 1,
                HiredWaifu.squad_position <= SQUAD_SIZE,
            )
        ).order_by(HiredWaifu.squad_position)
        result = await session.execute(stmt)
        squad = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        for w in squad:
            self._apply_hired_regen(w, now)
        if squad:
            await session.flush()
        return squad

    async def get_reserve(self, session: AsyncSession, player_id: int) -> List[HiredWaifu]:
        """Get player's reserve waifus (not in squad slots 1..SQUAD_SIZE).

        Includes NULL and legacy 0: DB allows squad_position 0, but get_squad only uses 1..6,
        so 0 was invisible to both squad and reserve before this filter.
        """
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                or_(
                    HiredWaifu.squad_position.is_(None),
                    HiredWaifu.squad_position == 0,
                ),
            )
        )
        result = await session.execute(stmt)
        reserve = list(result.scalars().all())
        now = datetime.now(timezone.utc)
        for w in reserve:
            if w.squad_position == 0:
                w.squad_position = None
            self._apply_hired_regen(w, now)
        if reserve:
            await session.flush()
        return reserve

    async def heal_waifu(
        self, session: AsyncSession, player_id: int, hired_waifu_id: int
    ) -> dict:
        """Лечение наёмницы за золото. При 0 HP (обморок) стоимость ×2."""
        waifu = await session.get(HiredWaifu, hired_waifu_id)
        if not waifu or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}
        if getattr(waifu, "expedition_id", None) is not None:
            return {
                "error": "waifu_on_expedition",
                "hint": "Дождитесь возвращения из экспедиции.",
            }
        max_hp = getattr(waifu, "max_hp", 65) or 65
        current_hp = getattr(waifu, "current_hp", max_hp)
        need_heal = max(0, max_hp - current_hp)
        if need_heal == 0:
            return {"error": "full_hp", "current_hp": current_hp, "max_hp": max_hp}
        mult = 2 if current_hp == 0 else 1
        cost = need_heal * TAVERN_HEAL_GOLD_PER_HP * mult
        cost = await apply_passive_hire_cost(session, player_id, int(cost))
        guild_heal_hint: str | None = None
        try:
            from waifu_bot.services.guild_skill_effects import (
                apply_price_discount_pct,
                effect_values_for_player,
                pct_bonus_lines_ru,
                guild_skill_contributions,
            )

            gfx = await effect_values_for_player(session, player_id)
            disc = float(gfx.get("tavern_heal_discount_pct", 0) or 0)
            if disc > 0:
                before = int(cost)
                cost = apply_price_discount_pct(before, disc)
                lines = pct_bonus_lines_ru(
                    await guild_skill_contributions(
                        session, player_id, params={"tavern_heal_discount_pct"}
                    )
                )
                if lines:
                    guild_heal_hint = lines[0]
        except Exception:
            pass
        if player.gold < cost:
            return {"error": "not_enough_gold", "required": cost, "gold": player.gold}
        player.gold -= cost
        waifu.current_hp = max_hp
        waifu.hp_updated_at = datetime.now(timezone.utc)
        await session.commit()
        out = {
            "success": True,
            "gold_spent": cost,
            "gold_total": player.gold,
            "current_hp": max_hp,
            "max_hp": max_hp,
        }
        if guild_heal_hint:
            out["guild_bonus_hint"] = guild_heal_hint
        return out

    async def add_to_squad(
        self, session: AsyncSession, player_id: int, waifu_id: int, slot: Optional[int] = None
    ) -> dict:
        """Add waifu to squad."""
        waifu = await session.get(HiredWaifu, waifu_id)
        if not waifu or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}
        if getattr(waifu, "expedition_id", None) is not None:
            return {"error": "waifu_on_expedition"}

        # Find free slot if not specified
        if slot is None:
            squad = await self.get_squad(session, player_id)
            occupied_slots = {w.squad_position for w in squad}
            for s in range(1, SQUAD_SIZE + 1):
                if s not in occupied_slots:
                    slot = s
                    break

        if slot is None:
            return {"error": "squad_full"}

        # If slot is occupied, move existing waifu to reserve
        if slot:
            existing_stmt = select(HiredWaifu).where(
                and_(
                    HiredWaifu.player_id == player_id,
                    HiredWaifu.squad_position == slot,
                )
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                existing.squad_position = None  # Move to reserve

        waifu.squad_position = slot
        await session.commit()

        return {"success": True, "waifu_id": waifu_id, "slot": slot}

    async def remove_from_squad(
        self, session: AsyncSession, player_id: int, waifu_id: int
    ) -> dict:
        """Remove waifu from squad (move to reserve)."""
        waifu = await session.get(HiredWaifu, waifu_id)
        if not waifu or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}

        waifu.squad_position = None
        await session.commit()

        return {"success": True, "waifu_id": waifu_id}

    async def dismiss_waifu(
        self, session: AsyncSession, player_id: int, waifu_id: int
    ) -> dict:
        """
        Уволить наёмницу (удалить навсегда). Доступно из отряда или запаса; не в экспедиции.
        Уровень уволенной сохраняется в TavernState; следующая нанятая вайфу получит его (ТЗ).
        Используется узкий SELECT (без power/perks), чтобы не падать на старых БД без этих колонок.
        """
        stmt = select(
            HiredWaifu.id,
            HiredWaifu.player_id,
            HiredWaifu.squad_position,
            HiredWaifu.level,
            HiredWaifu.expedition_id,
        ).where(HiredWaifu.id == waifu_id)
        row = (await session.execute(stmt)).one_or_none()
        if not row or row.player_id != player_id:
            return {"error": "waifu_not_found"}
        if getattr(row, "expedition_id", None) is not None:
            return {"error": "waifu_on_expedition", "hint": "Дождитесь возвращения из экспедиции."}

        level_to_transfer = max(1, int(row.level or 1))

        # Обнулить ссылки в слотах найма, иначе FK блокирует удаление
        await session.execute(
            update(TavernHireSlot)
            .where(TavernHireSlot.hired_waifu_id == waifu_id)
            .values(hired_waifu_id=None)
        )
        await session.execute(
            delete(HiredWaifu).where(
                and_(HiredWaifu.id == waifu_id, HiredWaifu.player_id == player_id)
            )
        )

        try:
            state = await self._get_or_create_tavern_state(session, player_id)
            state.last_dismissed_level = level_to_transfer
        except SQLAlchemyError:
            pass

        await session.commit()
        return {
            "success": True,
            "waifu_id": waifu_id,
            "level_saved": level_to_transfer,
            "hint": "Следующая нанятая в таверне вайфу получит этот уровень.",
        }

    async def _get_or_create_tavern_state(
        self, session: AsyncSession, player_id: int
    ) -> TavernState:
        stmt = select(TavernState).where(TavernState.player_id == player_id)
        state = (await session.execute(stmt)).scalar_one_or_none()
        if not state:
            state = TavernState(player_id=player_id)
            session.add(state)
            await session.flush()
        return state

    async def _generate_waifu(
        self, session: AsyncSession, player_id: int
    ) -> HiredWaifu:
        """Generate a random hired waifu. Level = 1 or last_dismissed_level (ТЗ)."""
        import random

        start_level = 1
        state = await self._get_or_create_tavern_state(session, player_id)
        if getattr(state, "last_dismissed_level", None) is not None:
            start_level = max(1, int(state.last_dismissed_level))
            state.last_dismissed_level = None  # один раз передаём уровень

        # Roll rarity (weights: Common 50%, Uncommon 30%, Rare 15%, Epic 5%)
        rarity_roll = random.random()
        if rarity_roll < 0.5:
            rarity = WaifuRarity.COMMON
        elif rarity_roll < 0.8:
            rarity = WaifuRarity.UNCOMMON
        elif rarity_roll < 0.95:
            rarity = WaifuRarity.RARE
        else:
            rarity = WaifuRarity.EPIC

        # Random race and class
        race = WaifuRace(random.randint(1, 7))
        class_ = WaifuClass(random.randint(1, 7))

        power_base = {WaifuRarity.COMMON: 40, WaifuRarity.UNCOMMON: 55, WaifuRarity.RARE: 75, WaifuRarity.EPIC: 95, WaifuRarity.LEGENDARY: 120}
        base_power = power_base.get(rarity, 40)
        power = base_power + random.randint(0, 10) + (start_level - 1) * 2  # slight power scaling by level
        perk_count = {WaifuRarity.COMMON: 1, WaifuRarity.UNCOMMON: 2, WaifuRarity.RARE: 2, WaifuRarity.EPIC: 3, WaifuRarity.LEGENDARY: 4}
        max_perks = perk_count.get(rarity, 1)
        perk_ids: list[str] = []
        tries = 0
        while len(perk_ids) < max_perks and tries < 80:
            tries += 1
            pid = pick_perk_id_for_class(int(class_.value))
            if pid not in perk_ids:
                perk_ids.append(pid)

        max_hp = 50 + start_level * 15
        now_utc = datetime.now(timezone.utc)
        waifu = HiredWaifu(
            player_id=player_id,
            name="Наёмница",  # будет заменено на имя от ИИ или fallback по расе
            race=race.value,
            class_=class_.value,
            rarity=rarity.value,
            level=start_level,
            power=power,
            perks=perk_ids,
            squad_position=None,
            max_hp=max_hp,
            current_hp=max_hp,
            hp_updated_at=now_utc,
        )

        session.add(waifu)
        await session.flush()
        return waifu

    def _waifu_bio_inputs(self, waifu: HiredWaifu) -> tuple[str, str, str, int, list[str]]:
        """Имя, раса (RU), класс (RU), уровень, список названий перков для промпта OpenRouter."""
        name = waifu.name or "Наёмница"
        race_ru = _RACE_NAMES_RU.get(int(waifu.race or 1), "путница")
        class_ru = _CLASS_NAMES_RU.get(int(waifu.class_ or 1), "искательница приключений")
        level = max(1, int(waifu.level or 1))
        perk_ids = waifu.perks or []
        perk_names = []
        for pid in perk_ids:
            p_id = pid if isinstance(pid, str) else str(pid)
            if p_id in PERK_BY_ID:
                perk_names.append(PERK_BY_ID[p_id].name)
        return name, race_ru, class_ru, level, perk_names

    async def _get_reserve_count(self, session: AsyncSession, player_id: int) -> int:
        """Get count of waifus in reserve (same semantics as get_reserve)."""
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                or_(
                    HiredWaifu.squad_position.is_(None),
                    HiredWaifu.squad_position == 0,
                ),
            )
        )
        result = await session.execute(stmt)
        return len(list(result.scalars().all()))

    def _moscow_today(self):
        return datetime.now(tz=MOSCOW_TZ).date()

    async def _ensure_day_slots(
        self,
        session: AsyncSession,
        player_id: int,
        day,
    ) -> list[TavernHireSlot]:
        stmt = (
            select(TavernHireSlot)
            .where(and_(TavernHireSlot.player_id == player_id, TavernHireSlot.day == day))
            .order_by(TavernHireSlot.slot)
            .options(noload(TavernHireSlot.hired_waifu))
        )
        existing = (await session.execute(stmt)).scalars().all()
        have = {int(s.slot) for s in existing}
        if len(have) < TAVERN_SLOTS_PER_DAY:
            for s in range(1, TAVERN_SLOTS_PER_DAY + 1):
                if s in have:
                    continue
                session.add(TavernHireSlot(player_id=player_id, day=day, slot=s))
            await session.flush()
            existing = (await session.execute(stmt)).scalars().all()
        return list(existing)

    async def admin_refresh_today(self, session: AsyncSession, player_id: int) -> list[TavernHireSlot]:
        """
        Admin-only helper: reset today's hire slots back to full availability.
        Does NOT delete any hired waifus; only resets the opportunities to hire.
        """
        today = self._moscow_today()
        await session.execute(
            delete(TavernHireSlot).where(and_(TavernHireSlot.player_id == player_id, TavernHireSlot.day == today))
        )
        await session.flush()
        slots = await self._ensure_day_slots(session, player_id, today)
        await session.commit()
        return slots

    async def upgrade_perk(
        self,
        session: AsyncSession,
        player_id: int,
        waifu_id: int,
        perk_id: str,
    ) -> dict:
        """Spend perk_upgrade_points to raise a perk level by 1.

        Cost formula: current_level points (1→2 costs 1 pt, 2→3 costs 2 pts, ...).
        Maximum perk level is 5.
        """
        waifu = await session.get(HiredWaifu, waifu_id)
        if waifu is None or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}

        perks = list(waifu.perks or [])
        perk_id_str = str(perk_id)
        if perk_id_str not in perks:
            return {"error": "perk_not_owned"}

        if perk_id_str not in PERK_BY_ID:
            return {"error": "perk_unknown"}

        perk_levels: dict = dict(getattr(waifu, "perk_levels", None) or {})
        current_level = int(perk_levels.get(perk_id_str, 1))
        max_perk_level = 5
        if current_level >= max_perk_level:
            return {"error": "perk_max_level", "level": current_level}

        cost = current_level  # points cost to go current_level → current_level + 1
        available_points = int(getattr(waifu, "perk_upgrade_points", 0) or 0)
        if available_points < cost:
            return {
                "error": "insufficient_points",
                "have": available_points,
                "need": cost,
            }

        perk_levels[perk_id_str] = current_level + 1
        waifu.perk_levels = perk_levels
        waifu.perk_upgrade_points = available_points - cost
        await session.flush()
        await session.commit()
        return {
            "ok": True,
            "perk_id": perk_id_str,
            "new_level": current_level + 1,
            "points_remaining": waifu.perk_upgrade_points,
        }
