<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiGet, type PlayerStatistics } from '../api/client'

const props = defineProps<{ playerId: string; active?: boolean }>()

const stats = ref<PlayerStatistics | null>(null)
const loading = ref(false)
const error = ref('')
const loaded = ref(false)

const rows: Array<{ key: keyof PlayerStatistics; label: string; icon: string }> = [
  { key: 'dungeons_completed', label: 'Подземелий', icon: '🏰' },
  { key: 'monsters_killed', label: 'Монстров', icon: '💀' },
  { key: 'damage_dealt', label: 'Урона нанесено', icon: '⚔️' },
  { key: 'hp_lost', label: 'Урона получено', icon: '🩸' },
  { key: 'gold_earned', label: 'Золота', icon: '🪙' },
  { key: 'exp_earned', label: 'Опыта', icon: '✨' },
]

async function load() {
  if (loaded.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    stats.value = await apiGet<PlayerStatistics>(`/players/${props.playerId}/statistics`)
    loaded.value = true
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive) load()
  },
  { immediate: true },
)

watch(
  () => props.playerId,
  () => {
    loaded.value = false
    stats.value = null
    if (props.active) load()
  },
)

function fmt(v: number): string {
  return v.toLocaleString('ru-RU')
}
</script>

<template>
  <div class="player-statistics">
    <h3 class="player-statistics-title">Статистика</h3>
    <div v-if="loading" class="player-statistics-hint">Загрузка...</div>
    <div v-else-if="error" class="error player-statistics-hint">{{ error }}</div>
    <div v-else-if="stats" class="player-statistics-grid">
      <div v-for="row in rows" :key="row.key" class="player-statistics-cell">
        <span class="player-statistics-icon">{{ row.icon }}</span>
        <div class="player-statistics-body">
          <span class="player-statistics-label">{{ row.label }}</span>
          <strong class="player-statistics-value">{{ fmt(stats[row.key]) }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>
