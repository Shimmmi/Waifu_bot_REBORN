<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, apiPost } from '../../api/client'

type AdminStats = {
  total_players?: number
  with_character?: number
  dau_today?: number
  banned_count?: number
  avg_gear_score?: number
  median_gear_score?: number
  guilds_bank_over_5?: number
  abyss_week_start?: string
  abyss_top?: Array<{ telegram_id: number; character_name?: string; max_floor: number }>
}

const stats = ref<AdminStats | null>(null)
const message = ref('')
const recomputing = ref(false)

async function load() {
  stats.value = await apiGet('/admin/stats')
}

async function recomputeGs() {
  recomputing.value = true
  message.value = ''
  try {
    const res = await apiPost<{ success: boolean; updated: number }>('/admin/gear-score/recompute')
    message.value = `GS пересчитан для ${res.updated} игроков`
    await load()
  } catch (e) {
    message.value = String(e)
  } finally {
    recomputing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>Админ-панель</h1>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/tavern-bgm" class="tab">Tavern BGM</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>

    <div v-if="stats" class="card">
      <div class="stat-grid">
        <div class="stat-item"><div class="label">Всего игроков</div><div class="value">{{ stats.total_players }}</div></div>
        <div class="stat-item"><div class="label">С персонажем</div><div class="value">{{ stats.with_character }}</div></div>
        <div class="stat-item"><div class="label">DAU сегодня</div><div class="value">{{ stats.dau_today }}</div></div>
        <div class="stat-item"><div class="label">Забанено</div><div class="value">{{ stats.banned_count }}</div></div>
        <div class="stat-item"><div class="label">Средний GS</div><div class="value">{{ stats.avg_gear_score ?? '—' }}</div></div>
        <div class="stat-item"><div class="label">Медиана GS</div><div class="value">{{ stats.median_gear_score ?? '—' }}</div></div>
        <div class="stat-item"><div class="label">Гильдии bank&gt;5</div><div class="value">{{ stats.guilds_bank_over_5 ?? 0 }}</div></div>
      </div>
      <div style="margin-top: 1rem">
        <button class="btn" :disabled="recomputing" @click="recomputeGs">
          {{ recomputing ? 'Пересчёт…' : 'Пересчитать gear_score' }}
        </button>
        <p v-if="message" style="margin-top: 0.5rem; color: var(--muted)">{{ message }}</p>
      </div>
    </div>

    <div v-if="stats?.abyss_top?.length" class="card">
      <h2>Бездна (неделя {{ stats.abyss_week_start }})</h2>
      <table>
        <thead>
          <tr><th>#</th><th>Игрок</th><th>Этаж</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in stats.abyss_top" :key="row.telegram_id">
            <td>{{ i + 1 }}</td>
            <td>
              <RouterLink :to="`/p/${row.telegram_id}`">{{ row.character_name || row.telegram_id }}</RouterLink>
              ·
              <RouterLink :to="`/admin/players/${row.telegram_id}`">admin</RouterLink>
            </td>
            <td>{{ row.max_floor }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
