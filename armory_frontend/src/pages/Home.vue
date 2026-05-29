<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, type PlayerSummary } from '../api/client'

const query = ref('')
const searchResults = ref<Array<{ telegram_id: number; username?: string; character_name?: string; level?: number }>>([])
const leaderboard = ref<Array<{ telegram_id?: number; character_name?: string; username?: string; value?: number; name?: string; tag?: string; level?: number }>>([])
const lbKind = ref('level')
const error = ref('')

async function search() {
  if (!query.value.trim()) return
  try {
    const data = await apiGet<{ items: typeof searchResults.value }>(`/players/search?q=${encodeURIComponent(query.value)}`)
    searchResults.value = data.items
  } catch (e) {
    error.value = String(e)
  }
}

async function loadLeaderboard() {
  try {
    const data = await apiGet<{ items: typeof leaderboard.value }>(`/leaderboards/${lbKind.value}`)
    leaderboard.value = data.items
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(loadLeaderboard)
</script>

<template>
  <div>
    <h1>Waifu_HUB</h1>
    <p style="color: var(--muted); margin-bottom: 1.5rem">
      Публичные профили персонажей, рейтинги и история прогресса.
    </p>

    <div class="card">
      <h2>Поиск игрока</h2>
      <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem">
        <input v-model="query" type="search" placeholder="Username или Telegram ID" @keyup.enter="search" />
        <button class="btn" @click="search">Найти</button>
      </div>
      <ul v-if="searchResults.length" style="margin-top: 1rem; list-style: none">
        <li v-for="p in searchResults" :key="p.telegram_id" style="padding: 0.4rem 0">
          <RouterLink :to="`/p/${p.telegram_id}`">
            {{ p.character_name || p.username || p.telegram_id }}
            <span v-if="p.level" class="badge">Ур. {{ p.level }}</span>
          </RouterLink>
        </li>
      </ul>
    </div>

    <div class="card">
      <h2>Рейтинг</h2>
      <div class="tabs">
        <button v-for="k in ['level', 'gold', 'dungeon_plus', 'guild']" :key="k"
          class="tab" :class="{ active: lbKind === k }"
          @click="lbKind = k; loadLeaderboard()">
          {{ { level: 'Уровень', gold: 'Золото', dungeon_plus: 'Данж+', guild: 'Гильдии' }[k] }}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Имя</th>
            <th v-if="lbKind !== 'guild'">Значение</th>
            <th v-else>Уровень</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in leaderboard" :key="i">
            <td>{{ i + 1 }}</td>
            <td>
              <RouterLink v-if="row.telegram_id" :to="`/p/${row.telegram_id}`">
                {{ row.character_name || row.username || row.telegram_id }}
              </RouterLink>
              <span v-else>[{{ row.tag }}] {{ row.name }}</span>
            </td>
            <td>{{ row.value ?? row.level }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>
