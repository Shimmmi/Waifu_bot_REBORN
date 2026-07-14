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

export async function apiPostQuery<T>(
  path: string,
  params: Record<string, string | number | undefined | null>,
): Promise<T> {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== '') qs.set(key, String(value))
  }
  const query = qs.toString()
  const url = query ? `${API}${path}?${query}` : `${API}${path}`
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRF-Token': csrfToken() },
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface ItemArtGenerateResponse {
  success: boolean
  art_key: string
  tier: number
  image_url: string
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
  weapon_type?: string
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
  guild?: { id: number; name: string; tag: string; level: number; is_leader?: boolean; is_officer?: boolean }
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

export interface AdminGroupChat {
  chat_id: number
  chat_type: string
  title?: string | null
  username?: string | null
  status: string
  joined_at?: string | null
  left_at?: string | null
  last_activity_at?: string | null
  discovered_via: string
  telegram_url?: string | null
}

export interface AdminGroupChatsResponse {
  total: number
  page: number
  page_size: number
  items: AdminGroupChat[]
}

export interface AdminTavernBgmOverview {
  total_tracks: number
  chats_with_tracks: number
  tracks_last_24h: number
  missing_files: number
  pending_failed_count: number
  events_last_hour: number
  events_buffer_size: number
}

export interface AdminTavernBgmChat {
  chat_id: number
  title?: string | null
  username?: string | null
  status: string
  track_count: number
  last_track_at?: string | null
}

export interface AdminTavernBgmChatsResponse {
  total: number
  page: number
  page_size: number
  items: AdminTavernBgmChat[]
}

export interface AdminTavernBgmTrack {
  id: number
  chat_id: number
  url: string
  title?: string | null
  performer?: string | null
  duration?: number | null
  relative_path: string
  file_exists: boolean
  created_at?: string | null
  uploader_player_id?: number | null
  mime_type?: string | null
  file_size?: number | null
}

export interface AdminTavernBgmTracksResponse {
  chat_id: number
  tracks: AdminTavernBgmTrack[]
}

export interface AdminTavernBgmEvent {
  ts: string
  event: string
  chat_id?: number | null
  player_id?: number | null
  detail: string
}

export interface AdminTavernBgmEventsResponse {
  events: AdminTavernBgmEvent[]
}

export interface AdminTavernBgmPlayerPreview {
  player_id: number
  player_group_chats: number[]
  bot_active_intersection: number[]
  player_view: {
    chats: Array<{ chat_id: number; title: string; track_count: number }>
    hint?: string
  }
}

export interface AdminTavernBgmPendingItem {
  id: number
  chat_id: number
  file_unique_id: string
  file_id: string
  title?: string | null
  performer?: string | null
  file_size?: number | null
  mime_type?: string | null
  uploader_player_id?: number | null
  status: string
  last_error?: string | null
  retry_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminTavernBgmPendingResponse {
  items: AdminTavernBgmPendingItem[]
}

export interface AdminTavernBgmRetryResponse {
  ok: boolean
  status: string
  track_id?: number
  error?: string
  events: AdminTavernBgmEvent[]
}
