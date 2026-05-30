const API = '/api/armory'

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)armory_csrf=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: 'include' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken(),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface AuthMe {
  authenticated: true
  telegram_id: number
  username?: string
  first_name?: string
  is_admin: boolean
  banned: boolean
}

export interface AuthGuest {
  authenticated: false
}

export type AuthSession = AuthMe | AuthGuest

export interface Achievement {
  kind: 'hidden_skill' | 'story_boss' | 'secret_echo'
  id: string
  name: string
  icon?: string
  level?: number
  max_level?: number
  earned_at?: string
  act?: number
  plus_tier?: number
  category?: string
}

export interface PlayerEventsResponse {
  achievements: Achievement[]
  items: Array<{ id: number; event_type: string; payload: Record<string, unknown>; created_at?: string }>
  next_cursor?: number | null
}

export interface ArmoryAffix {
  name: string
  stat?: string
  value?: string | number
  is_percent?: boolean
  kind?: string
  tier?: number
  description?: string
}

export interface ArmoryItem {
  id: number
  name: string
  display_name?: string
  tier?: number
  rarity?: number
  level?: number
  equipment_slot?: number | null
  art_key?: string
  image_key?: string
  image_url?: string | null
  affixes?: ArmoryAffix[]
  slot_type?: string
  damage_min?: number
  damage_max?: number
  damage_min_effective?: number
  damage_max_effective?: number
  armor_base?: number
  armor_effective?: number
  enchant_level?: number
  is_legendary?: boolean
  base_stat?: string
  base_stat_value?: number
}

export interface PlayerCharacter {
  name: string
  level: number
  race_label: string
  class_label: string
  max_hp: number
  current_hp?: number
  portrait_url?: string
  paperdoll_url?: string
}

export interface PlayerSummary {
  telegram_id: number
  username?: string
  first_name?: string
  viewer_access_level: 'public' | 'owner' | 'admin'
  gear_score: number
  gold: number
  current_act: number
  has_character: boolean
  character?: PlayerCharacter
  equipped_items?: ArmoryItem[]
  stats_effective?: Record<string, number>
  guild?: { name: string; tag: string; level: number }
  recent_dungeons?: Array<{ dungeon_name: string; status: string; plus_level: number }>
}

export interface PlayerStatistics {
  dungeons_completed: number
  monsters_killed: number
  damage_dealt: number
  hp_lost: number
  gold_earned: number
  exp_earned: number
}
