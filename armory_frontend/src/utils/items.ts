import type { ArmoryAffix, ArmoryItem } from '../api/client'

export const GAME_STATIC_BASE = '/static/game'

export const EQUIPMENT_SLOT_NAMES: Record<number, string> = {
  1: 'Оружие 1',
  2: 'Оружие 2',
  3: 'Костюм',
  4: 'Кольцо 1',
  5: 'Кольцо 2',
  6: 'Амулет',
}

export const SLOT_LAYOUT = {
  left: [1, 3, 4],
  right: [2, 6, 5],
} as const

export const SLOT_ROW_ORDER = [1, 2, 3, 4, 5, 6] as const

export const STAT_LABELS: Record<string, string> = {
  strength: 'СИЛ',
  agility: 'ЛОВ',
  intelligence: 'ИНТ',
  endurance: 'ВЫН',
  charm: 'ОБА',
  luck: 'УДЧ',
}

export const STAT_FULL_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Выносливость',
  charm: 'Обаяние',
  luck: 'Удача',
}

export const STAT_ORDER = [
  'strength',
  'agility',
  'intelligence',
  'endurance',
  'charm',
  'luck',
] as const

export const STAT_ICONS: Record<string, string> = {
  strength: '💪',
  agility: '🎯',
  intelligence: '🧠',
  endurance: '🛡️',
  charm: '🎭',
  luck: '🍀',
}

export const META_ICONS = {
  gear_score: '⚔️',
  max_hp: '❤️',
  gold: '🪙',
  act: '🗺️',
  guild: '🏰',
} as const

export const RARITY_NAMES: Record<number, string> = {
  1: 'common',
  2: 'uncommon',
  3: 'rare',
  4: 'epic',
  5: 'legendary',
}

export const RARITY_LABELS_RU: Record<number, string> = {
  1: 'Обычный',
  2: 'Необычный',
  3: 'Редкий',
  4: 'Эпический',
  5: 'Легендарный',
}

export const SECONDARY_STAT_LABELS: Record<string, string> = {
  hp_flat: 'Здоровье',
  hp_percent: 'Здоровье',
  defense_flat: 'Защита',
  defense_percent: 'Защита',
  crit_chance_flat: 'Крит',
  crit_chance_percent: 'Крит',
  merchant_discount_flat: 'Скидка',
  merchant_discount_percent: 'Скидка',
  melee_damage_flat: 'Урон в ближнем бою',
  ranged_damage_flat: 'Урон в дальнем бою',
  magic_damage_flat: 'Урон магией',
  damage_flat: 'Доп. урон',
  damage_percent: 'Доп. урон %',
}

export function statLabel(key?: string | null): string {
  if (!key) return '—'
  const low = key.toLowerCase()
  return STAT_FULL_LABELS[low] ?? SECONDARY_STAT_LABELS[low] ?? key
}

export function rarityLabel(r?: number | null): string {
  const v = Number(r ?? 1)
  return RARITY_LABELS_RU[v] ?? `Редкость ${v || '—'}`
}

export function formatAffixLine(a: ArmoryAffix): string {
  const name = a.name || statLabel(a.stat)
  if (a.stat && a.value != null) {
    const label = statLabel(a.stat)
    const suffix = a.is_percent ? '%' : ''
    return `${name}: ${label} +${a.value}${suffix}`
  }
  return name
}

export function rarityClass(rarity?: number | null): string {
  const key = RARITY_NAMES[rarity ?? 1] ?? 'common'
  return `rarity-${key}`
}

export function itemArtTierNormalized(item: Pick<ArmoryItem, 'tier'>): number {
  const t = Number(item?.tier ?? 1)
  return Number.isFinite(t) && t > 0 ? Math.min(5, Math.floor(t)) : 1
}

export function encodeArtKeyPath(artKey: string): string {
  return artKey.split('/').map(encodeURIComponent).join('/')
}

export function itemImageUrl(item: Pick<ArmoryItem, 'image_url' | 'art_key' | 'image_key' | 'tier'>): string {
  const direct = String(item?.image_url || '').trim()
  if (direct) return direct

  const tier = itemArtTierNormalized(item)
  const artKey = String(item?.art_key || '').trim()
  if (artKey) {
    return `${GAME_STATIC_BASE}/items/webp/${encodeArtKeyPath(artKey)}/t${tier}.webp`
  }

  const key = String(item?.image_key || '').trim()
  if (!key) return ''
  return `${GAME_STATIC_BASE}/items/svg/${encodeURIComponent(key)}.svg`
}

export function itemDisplayName(item: Pick<ArmoryItem, 'display_name' | 'name'>): string {
  return String(item.display_name || item.name || 'Предмет')
}

export function formatEventDate(iso?: string): string {
  if (!iso) return '—'
  return iso.slice(0, 19).replace('T', ' ')
}

export function formatEvent(type: string, payload: Record<string, unknown>): string {
  switch (type) {
    case 'level_up':
      return `Уровень ${payload.level}`
    case 'dungeon_completed':
      return `Данж: ${payload.dungeon_name} (+${payload.plus_level ?? 0})`
    case 'dungeon_failed':
      return `Провал: ${payload.dungeon_name}`
    case 'expedition_completed':
      return `Экспедиция: ${payload.name} — ${payload.outcome}`
    case 'item_equipped':
      return `Экипировка: ${payload.item_name}`
    case 'item_unequipped':
      return `Снято: ${payload.item_name}`
    case 'tavern_hired':
      return `Найм: ${payload.waifu_name}`
    case 'account_created':
      return `Создан персонаж: ${payload.character_name}`
    case 'account_wiped':
      return 'Сброс прогресса'
    case 'account_banned':
      return 'Аккаунт заблокирован'
    case 'hidden_skill_unlock':
      return `Открыт навык: ${payload.name}`
    case 'hidden_skill_level_up':
      return `${payload.name} — уровень ${payload.level}`
    case 'boss_first_kill':
      return `Первое убийство: ${payload.boss_name} (акт ${payload.act}, +${payload.plus_tier})`
    case 'secret_echo_unlocked':
      return 'Эхо пробуждено'
    case 'secret_echo_defeated':
      return 'Победа над эхом'
    default:
      return type
  }
}

export function radarStats(stats: Record<string, number>): Array<[string, number]> {
  return STAT_ORDER.map((key) => [STAT_FULL_LABELS[key] || key, Number(stats[key] ?? 0)])
}

export function statListEntries(stats: Record<string, number>): Array<{ key: string; label: string; value: number }> {
  return STAT_ORDER.map((key) => ({
    key,
    label: STAT_FULL_LABELS[key] || key,
    value: Number(stats[key] ?? 0),
  }))
}
