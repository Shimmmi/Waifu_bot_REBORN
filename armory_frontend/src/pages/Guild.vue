<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, type ArmoryItem } from '../api/client'
import ProfileTabBar from '../components/ProfileTabBar.vue'
import ItemCard from '../components/ItemCard.vue'
import ItemDetailModal from '../components/ItemDetailModal.vue'

const props = defineProps<{ id: string }>()

type GuildTab = 'members' | 'raids' | 'wars' | 'achievements' | 'bank'

type GuildSummary = {
  guild_id: number
  name: string
  tag: string
  description?: string | null
  level: number
  experience: number
  trophies: number
  member_count: number
  is_recruiting: boolean
  min_level_requirement?: number | null
  icon_url?: string | null
  banner_url?: string | null
  title_badge?: string | null
  war_status?: string
  active_war?: {
    status: string
    score: number
    enemy_score: number
    ends_at?: string | null
    opponent?: { guild_id: number; name: string; tag: string } | null
  } | null
  active_raid?: {
    raid_id: number
    status: string
    current_stage?: number
    stages_count?: number | null
    name?: string | null
    tier?: number | null
  } | null
  raid_wins: number
  raid_losses: number
  war_wins: number
  war_losses: number
}

type GuildMember = {
  telegram_id: number
  username?: string
  character_name?: string
  level?: number | null
  role: string
  joined_at?: string | null
}

type RaidItem = {
  raid_id: number
  name?: string | null
  tier?: number | null
  status: string
  current_stage?: number
  stages_count?: number | null
  gxp_reward?: number
  started_at?: string | null
  ends_at?: string | null
  top_participants?: Array<{ telegram_id: number; character_name?: string; damage_dealt: number }>
}

type WarItem = {
  war_id: number
  status: string
  our_score: number
  their_score: number
  stake_gold: number
  winner_guild_id?: number | null
  we_won?: boolean | null
  opponent?: { guild_id?: number; name?: string; tag?: string }
  declared_at?: string | null
  ends_at?: string | null
}

type GuildAchievement = {
  id: string
  kind: string
  name: string
  value?: number
  threshold?: number
  earned: boolean
  tier?: number
  level?: number
  until?: string | null
}

const summary = ref<GuildSummary | null>(null)
const members = ref<GuildMember[]>([])
const raids = ref<{
  wins: number
  losses: number
  winrate: number
  active: RaidItem | null
  items: RaidItem[]
} | null>(null)
const wars = ref<{
  wins: number
  losses: number
  trophies: number
  active: GuildSummary['active_war']
  items: WarItem[]
} | null>(null)
const achievements = ref<GuildAchievement[]>([])
const bank = ref<{
  gold: number
  item_count: number
  max_items: number
  can_view_items: boolean
  items: ArmoryItem[]
} | null>(null)
const loading = ref(true)
const error = ref('')
const activeTab = ref<GuildTab>('members')
const modalOpen = ref(false)
const modalItem = ref<ArmoryItem | null>(null)

const ROLE_LABELS: Record<string, string> = {
  leader: 'Лидер',
  officer: 'Офицер',
  member: 'Участник',
}

const tabs = computed(() => [
  { id: 'members' as const, label: 'Состав', count: members.value.length },
  { id: 'raids' as const, label: 'Рейды', count: raids.value?.items.length },
  { id: 'wars' as const, label: 'Войны', count: wars.value?.items.length },
  {
    id: 'achievements' as const,
    label: 'Достижения',
    count: achievements.value.filter((a) => a.earned).length,
  },
  {
    id: 'bank' as const,
    label: 'Банк',
    count: bank.value?.item_count,
  },
])

async function loadAll() {
  loading.value = true
  error.value = ''
  summary.value = null
  try {
    summary.value = await apiGet<GuildSummary>(`/guilds/${props.id}`)
  } catch (e) {
    error.value = String(e)
    loading.value = false
    return
  }

  const [membersRes, raidsRes, warsRes, achRes, bankRes] = await Promise.allSettled([
    apiGet<{ items: GuildMember[] }>(`/guilds/${props.id}/members`),
    apiGet<NonNullable<typeof raids.value>>(`/guilds/${props.id}/raids`),
    apiGet<NonNullable<typeof wars.value>>(`/guilds/${props.id}/wars`),
    apiGet<{ items: GuildAchievement[] }>(`/guilds/${props.id}/achievements`),
    apiGet<NonNullable<typeof bank.value>>(`/guilds/${props.id}/bank`),
  ])

  members.value = membersRes.status === 'fulfilled' ? membersRes.value.items : []
  raids.value = raidsRes.status === 'fulfilled' ? raidsRes.value : null
  wars.value = warsRes.status === 'fulfilled' ? warsRes.value : null
  achievements.value = achRes.status === 'fulfilled' ? achRes.value.items : []
  bank.value = bankRes.status === 'fulfilled' ? bankRes.value : null
  loading.value = false
}

function openBankItem(item: ArmoryItem) {
  modalItem.value = item
  modalOpen.value = true
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    victory: 'Победа',
    defeat: 'Поражение',
    active: 'Активен',
    preparation: 'Подготовка',
    pending: 'Ожидание',
    ended: 'Завершена',
    none: 'Нет',
  }
  return map[status] || status
}

watch(
  () => props.id,
  () => {
    activeTab.value = 'members'
    void loadAll()
  },
)
onMounted(() => void loadAll())
</script>

<template>
  <div v-if="loading" class="loading-hint">Загрузка…</div>
  <div v-else-if="error" class="error">{{ error }}</div>
  <div v-else-if="summary" class="guild-page">
    <div class="card guild-header">
      <div class="guild-header-main">
        <img
          v-if="summary.icon_url"
          class="guild-icon"
          :src="summary.icon_url"
          :alt="summary.name"
        />
        <div>
          <h1>[{{ summary.tag }}] {{ summary.name }}</h1>
          <p class="guild-meta">
            Уровень {{ summary.level }}
            · {{ summary.member_count }} уч.
            · Трофеи {{ summary.trophies }}
            <span v-if="summary.title_badge" class="badge">{{ summary.title_badge }}</span>
          </p>
          <p v-if="summary.description" class="guild-desc">{{ summary.description }}</p>
          <p class="guild-recruit">
            {{ summary.is_recruiting ? 'Набор открыт' : 'Набор закрыт' }}
            <span v-if="summary.min_level_requirement">
              · мин. ур. {{ summary.min_level_requirement }}
            </span>
          </p>
        </div>
      </div>

      <div class="guild-kpi">
        <div class="kpi-cell">
          <strong>{{ summary.raid_wins }}</strong>
          <span>Рейды W</span>
        </div>
        <div class="kpi-cell">
          <strong>{{ summary.raid_losses }}</strong>
          <span>Рейды L</span>
        </div>
        <div class="kpi-cell">
          <strong>{{ summary.war_wins }}</strong>
          <span>Войны W</span>
        </div>
        <div class="kpi-cell">
          <strong>{{ summary.war_losses }}</strong>
          <span>Войны L</span>
        </div>
      </div>

      <div v-if="summary.active_war?.opponent" class="banner-card">
        <strong>Активная война</strong>
        vs
        <RouterLink :to="`/g/${summary.active_war.opponent.guild_id}`">
          [{{ summary.active_war.opponent.tag }}] {{ summary.active_war.opponent.name }}
        </RouterLink>
        — {{ summary.active_war.score }} : {{ summary.active_war.enemy_score }}
        <span v-if="summary.active_war.ends_at" class="muted">
          до {{ summary.active_war.ends_at.slice(0, 16).replace('T', ' ') }}
        </span>
      </div>

      <div v-if="summary.active_raid" class="banner-card">
        <strong>Активный рейд</strong>
        {{ summary.active_raid.name || 'Рейд' }}
        <span v-if="summary.active_raid.tier">T{{ summary.active_raid.tier }}</span>
        — {{ statusLabel(summary.active_raid.status) }}
        <span v-if="summary.active_raid.stages_count">
          · стадия {{ summary.active_raid.current_stage }}/{{ summary.active_raid.stages_count }}
        </span>
      </div>
    </div>

    <ProfileTabBar v-model="activeTab" :tabs="tabs" />

    <div class="card profile-tab-panel">
      <div v-show="activeTab === 'members'">
        <table v-if="members.length" class="event-table">
          <thead>
            <tr>
              <th>Игрок</th>
              <th>Роль</th>
              <th>Ур.</th>
              <th class="col-date">Вступил</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in members" :key="m.telegram_id">
              <td>
                <RouterLink :to="`/p/${m.telegram_id}`">
                  {{ m.character_name || m.username || m.telegram_id }}
                </RouterLink>
              </td>
              <td>
                <span class="badge">{{ ROLE_LABELS[m.role] || m.role }}</span>
              </td>
              <td>{{ m.level ?? '—' }}</td>
              <td class="col-date">{{ m.joined_at?.slice(0, 10) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-hint">Нет участников</p>
      </div>

      <div v-show="activeTab === 'raids'">
        <p v-if="raids" class="kpi-line">
          Побед: {{ raids.wins }} · Поражений: {{ raids.losses }} · Winrate: {{ raids.winrate }}%
        </p>
        <div v-if="raids?.active" class="banner-card">
          Сейчас: {{ raids.active.name || 'Рейд' }} — {{ statusLabel(raids.active.status) }}
        </div>
        <table v-if="raids?.items.length" class="event-table">
          <thead>
            <tr>
              <th>Рейд</th>
              <th>Tier</th>
              <th>Статус</th>
              <th>GXP</th>
              <th>Топ урон</th>
              <th class="col-date">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in raids.items" :key="r.raid_id">
              <td>{{ r.name || `Рейд #${r.raid_id}` }}</td>
              <td>{{ r.tier ?? '—' }}</td>
              <td>{{ statusLabel(r.status) }}</td>
              <td>{{ r.gxp_reward ?? '—' }}</td>
              <td>
                <span
                  v-for="(p, i) in r.top_participants || []"
                  :key="p.telegram_id"
                  class="top-chip"
                >
                  <RouterLink :to="`/p/${p.telegram_id}`">{{ p.character_name }}</RouterLink>
                  ({{ p.damage_dealt.toLocaleString('ru-RU') }})<span v-if="i < (r.top_participants?.length || 0) - 1">, </span>
                </span>
                <span v-if="!(r.top_participants && r.top_participants.length)">—</span>
              </td>
              <td class="col-date">{{ (r.ends_at || r.started_at)?.slice(0, 10) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-hint">Нет завершённых рейдов</p>
      </div>

      <div v-show="activeTab === 'wars'">
        <p v-if="wars" class="kpi-line">
          Побед: {{ wars.wins }} · Поражений: {{ wars.losses }} · Трофеи: {{ wars.trophies }}
        </p>
        <table v-if="wars?.items.length" class="event-table">
          <thead>
            <tr>
              <th>Противник</th>
              <th>Счёт</th>
              <th>Статус</th>
              <th>Ставка</th>
              <th class="col-date">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in wars.items" :key="w.war_id">
              <td>
                <RouterLink v-if="w.opponent?.guild_id" :to="`/g/${w.opponent.guild_id}`">
                  [{{ w.opponent.tag }}] {{ w.opponent.name }}
                </RouterLink>
                <span v-else>—</span>
              </td>
              <td>{{ w.our_score }} : {{ w.their_score }}</td>
              <td>
                {{ statusLabel(w.status) }}
                <span v-if="w.we_won === true" class="badge">W</span>
                <span v-else-if="w.we_won === false" class="badge">L</span>
              </td>
              <td>{{ w.stake_gold.toLocaleString('ru-RU') }}</td>
              <td class="col-date">{{ (w.ends_at || w.declared_at)?.slice(0, 10) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-hint">Нет войн</p>
      </div>

      <div v-show="activeTab === 'achievements'">
        <div v-if="achievements.length" class="ach-grid">
          <div
            v-for="a in achievements"
            :key="a.id"
            class="ach-card"
            :class="{ earned: a.earned, locked: !a.earned }"
          >
            <strong>{{ a.name }}</strong>
            <p v-if="a.threshold != null" class="muted">
              {{ a.value ?? 0 }} / {{ a.threshold }}
            </p>
            <p v-else-if="a.kind === 'trophy'" class="muted">{{ a.value ?? 0 }}</p>
            <p v-else-if="a.kind === 'skill'" class="muted">
              Tier {{ a.tier }} · ур. {{ a.level }}
            </p>
          </div>
        </div>
        <p v-else class="empty-hint">Нет достижений</p>
      </div>

      <div v-show="activeTab === 'bank'">
        <p v-if="bank" class="kpi-line">
          Золото: {{ bank.gold.toLocaleString('ru-RU') }}
          · Предметы: {{ bank.item_count }} / {{ bank.max_items }}
        </p>
        <template v-if="bank?.can_view_items">
          <div v-if="bank.items.length" class="inventory-grid">
            <ItemCard
              v-for="(item, idx) in bank.items"
              :key="item.bank_item_id ?? item.id ?? idx"
              :item="item"
              @click="openBankItem"
            />
          </div>
          <p v-else class="empty-hint">Банк пуст</p>
        </template>
        <p v-else class="empty-hint">Состав банка виден только участникам гильдии</p>
      </div>
    </div>

    <ItemDetailModal v-model="modalOpen" :item="modalItem" />
  </div>
</template>

<style scoped>
.loading-hint { color: var(--muted); }
.empty-hint { color: var(--muted); font-size: 0.85rem; }
.muted { color: var(--muted); font-size: 0.85rem; }
.guild-header-main {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1rem;
}
.guild-icon {
  width: 72px;
  height: 72px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.guild-meta { color: var(--muted); margin-top: 0.35rem; }
.guild-desc { margin-top: 0.5rem; font-size: 0.9rem; }
.guild-recruit { margin-top: 0.35rem; font-size: 0.85rem; color: var(--muted); }
.guild-kpi {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.kpi-cell {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  padding: 0.5rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.8rem;
  color: var(--muted);
}
.kpi-cell strong {
  color: var(--text);
  font-size: 1.1rem;
}
.banner-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.55rem 0.75rem;
  margin-bottom: 0.5rem;
  background: var(--bg);
  font-size: 0.9rem;
}
.kpi-line {
  margin-bottom: 0.75rem;
  color: var(--muted);
  font-size: 0.9rem;
}
.profile-tab-panel {
  margin-top: 0;
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}
.ach-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.5rem;
}
.ach-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem;
  background: var(--bg);
}
.ach-card.locked { opacity: 0.55; }
.ach-card.earned { border-color: var(--gold); }
.top-chip { font-size: 0.85rem; }
@media (max-width: 720px) {
  .guild-kpi { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
