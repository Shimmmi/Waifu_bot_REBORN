<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  apiGet,
  type PlayerSummary,
  type Achievement,
  type PlayerEventsResponse,
  type ArmoryItem,
} from '../api/client'
import { useAuthStore } from '../stores/auth'
import ItemCard from '../components/ItemCard.vue'
import EventFeed from '../components/EventFeed.vue'
import AchievementList from '../components/AchievementList.vue'
import ProfileHero from '../components/ProfileHero.vue'
import ProfileStatsPanel from '../components/ProfileStatsPanel.vue'
import ProfileTabBar from '../components/ProfileTabBar.vue'
import ItemDetailModal from '../components/ItemDetailModal.vue'

const props = defineProps<{ id: string }>()

const auth = useAuthStore()
const isAdmin = computed(() => !!auth.user?.is_admin)

type ProfileTab = 'stats' | 'achievements' | 'events' | 'dungeons' | 'inventory'

const summary = ref<PlayerSummary | null>(null)
const inventory = ref<ArmoryItem[]>([])
const events = ref<Array<{ id: number; event_type: string; payload: Record<string, unknown>; created_at?: string }>>([])
const achievements = ref<Achievement[]>([])
const dungeons = ref<Array<{ run_id: number; dungeon_name: string; status: string; plus_level: number; finished_at?: string }>>([])
const error = ref('')
const loading = ref(true)
const modalOpen = ref(false)
const modalItem = ref<ArmoryItem | null>(null)
const activeTab = ref<ProfileTab>('stats')

const isOwner = computed(
  () =>
    summary.value?.viewer_access_level === 'owner' ||
    summary.value?.viewer_access_level === 'admin',
)

const tabs = computed(() => {
  const items: Array<{ id: ProfileTab; label: string; count?: number }> = [
    { id: 'stats', label: 'Характеристики' },
    { id: 'achievements', label: 'Достижения', count: achievements.value.length },
    { id: 'events', label: 'История', count: events.value.length },
    { id: 'dungeons', label: 'Данжи', count: dungeons.value.length },
  ]
  if (isOwner.value) {
    items.push({ id: 'inventory', label: 'Инвентарь', count: inventory.value.length })
  }
  return items
})

async function loadSummary() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await apiGet<PlayerSummary>(`/players/${props.id}`)
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

async function loadExtra() {
  if (!summary.value) return
  try {
    const eventsData = await apiGet<PlayerEventsResponse>(`/players/${props.id}/events`)
    achievements.value = eventsData.achievements ?? []
    events.value = eventsData.items
  } catch { /* optional */ }

  try {
    const dungeonsData = await apiGet<{ items: typeof dungeons.value }>(`/players/${props.id}/dungeons`)
    dungeons.value = dungeonsData.items
  } catch { /* optional */ }

  if (isOwner.value) {
    try {
      const invData = await apiGet<{ items: ArmoryItem[] }>(`/players/${props.id}/inventory`)
      inventory.value = invData.items.filter((i) => !i.equipment_slot)
    } catch { /* optional */ }
  }
}

function openModal(item: ArmoryItem) {
  modalItem.value = item
  modalOpen.value = true
}

watch(
  () => tabs.value.map((t) => t.id),
  (ids) => {
    if (!ids.includes(activeTab.value)) activeTab.value = 'stats'
  },
)

watch(() => props.id, () => {
  activeTab.value = 'stats'
  loadSummary().then(loadExtra)
})
onMounted(() => loadSummary().then(loadExtra))
</script>

<template>
  <div v-if="loading" class="loading-hint">Загрузка...</div>
  <div v-else-if="error" class="error">{{ error }}</div>
  <div v-else-if="summary">
    <ProfileHero
      :character="summary.character"
      :equipped="summary.equipped_items"
      :stats-effective="summary.stats_effective"
      :gear-score="summary.gear_score"
      :gold="summary.gold"
      :current-act="summary.current_act"
      :guild="summary.guild"
      :admin-mode="isAdmin"
      @item-click="openModal"
    />

    <p v-if="summary.viewer_access_level === 'public'" class="login-hint card card-compact">
      <a href="/armory/login">Войдите</a>, чтобы видеть полный инвентарь и приватную историю.
    </p>

    <ProfileTabBar v-model="activeTab" :tabs="tabs" />

    <div class="card profile-tab-panel">
      <div v-show="activeTab === 'stats'">
        <ProfileStatsPanel
          v-if="summary.stats_effective"
          :stats="summary.stats_effective"
          :player-id="id"
          :active="activeTab === 'stats'"
        />
        <p v-else class="empty-hint">Нет данных о характеристиках</p>
      </div>

      <div v-show="activeTab === 'achievements'">
        <AchievementList :achievements="achievements" />
      </div>

      <div v-show="activeTab === 'events'">
        <EventFeed :items="events" />
      </div>

      <div v-show="activeTab === 'dungeons'">
        <table v-if="dungeons.length" class="event-table">
          <thead>
            <tr>
              <th>Данж</th>
              <th>Статус</th>
              <th>+</th>
              <th class="col-date">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in dungeons" :key="d.run_id">
              <td>{{ d.dungeon_name }}</td>
              <td>{{ d.status }}</td>
              <td>+{{ d.plus_level }}</td>
              <td class="col-date">{{ d.finished_at?.slice(0, 10) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-hint">Нет прохождений</p>
      </div>

      <div v-show="activeTab === 'inventory'">
        <div v-if="inventory.length" class="inventory-grid">
          <ItemCard
            v-for="item in inventory"
            :key="item.id"
            :item="item"
            :admin-mode="isAdmin"
            @click="openModal"
          />
        </div>
        <p v-else class="empty-hint">Инвентарь пуст</p>
      </div>
    </div>

    <ItemDetailModal v-model="modalOpen" :item="modalItem" :admin-mode="isAdmin" />
  </div>
</template>

<style scoped>
.loading-hint { color: var(--muted); }
.login-hint { margin-bottom: 1rem; font-size: 0.85rem; color: var(--muted); }
.card-compact { padding: 0.65rem 1rem; }
.empty-hint { color: var(--muted); font-size: 0.85rem; }
.profile-tab-panel { margin-top: 0; border-top-left-radius: 0; border-top-right-radius: 0; }
</style>
