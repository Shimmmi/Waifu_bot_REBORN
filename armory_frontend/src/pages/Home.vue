<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'

type PlayerRow = {
  telegram_id?: number
  character_name?: string
  username?: string
  level?: number | null
  value?: number
}

type GuildRow = {
  guild_id?: number
  name?: string
  tag?: string
  level?: number
  member_count?: number
  trophies?: number
  value?: number
}

type BoardState<T> = {
  items: T[]
  loading: boolean
  error: string
}

const query = ref('')
const searchResults = ref<
  Array<{ telegram_id: number; username?: string; character_name?: string; level?: number }>
>([])
const searchError = ref('')

const boards = reactive({
  level: { items: [] as PlayerRow[], loading: true as boolean, error: '' },
  gear_score: { items: [] as PlayerRow[], loading: true as boolean, error: '' },
  dungeon_plus: { items: [] as PlayerRow[], loading: true as boolean, error: '' },
  gold: { items: [] as PlayerRow[], loading: true as boolean, error: '' },
  guild: { items: [] as GuildRow[], loading: true as boolean, error: '' },
})

const PLAYER_BOARDS = [
  { kind: 'level' as const, title: 'Уровень', metric: 'Ур.' },
  { kind: 'gear_score' as const, title: 'Снаряжение', metric: 'GS' },
  { kind: 'dungeon_plus' as const, title: 'Данж+', metric: '+' },
  { kind: 'gold' as const, title: 'Золото', metric: 'Золото' },
]

async function search() {
  if (!query.value.trim()) return
  searchError.value = ''
  try {
    const data = await apiGet<{ items: typeof searchResults.value }>(
      `/players/search?q=${encodeURIComponent(query.value)}`,
    )
    searchResults.value = data.items
  } catch (e) {
    searchError.value = String(e)
    searchResults.value = []
  }
}

async function loadBoard(kind: keyof typeof boards) {
  const board = boards[kind]
  board.loading = true
  board.error = ''
  try {
    const data = await apiGet<{ items: typeof board.items }>(`/leaderboards/${kind}?limit=10`)
    board.items = data.items ?? []
  } catch (e) {
    board.error = String(e)
    board.items = []
  } finally {
    board.loading = false
  }
}

function formatValue(kind: string, value?: number): string {
  if (value == null) return '—'
  if (kind === 'gold') return value.toLocaleString('ru-RU')
  if (kind === 'dungeon_plus') return `+${value}`
  return String(value)
}

onMounted(() => {
  void Promise.all([
    loadBoard('level'),
    loadBoard('gear_score'),
    loadBoard('dungeon_plus'),
    loadBoard('gold'),
    loadBoard('guild'),
  ])
})
</script>

<template>
  <div class="home-hub">
    <h1>Waifu_HUB</h1>
    <p class="home-lead">
      Публичные профили персонажей, рейтинги и история прогресса.
    </p>

    <div class="card">
      <h2>Поиск игрока</h2>
      <div class="search-row">
        <input
          v-model="query"
          type="search"
          placeholder="Username или Telegram ID"
          @keyup.enter="search"
        />
        <button class="btn" @click="search">Найти</button>
      </div>
      <ul v-if="searchResults.length" class="search-results">
        <li v-for="p in searchResults" :key="p.telegram_id">
          <RouterLink :to="`/p/${p.telegram_id}`">
            {{ p.character_name || p.username || p.telegram_id }}
            <span v-if="p.level" class="badge">Ур. {{ p.level }}</span>
          </RouterLink>
        </li>
      </ul>
      <p v-if="searchError" class="error">{{ searchError }}</p>
    </div>

    <h2 class="section-title">Рейтинги</h2>
    <div class="ladder-grid">
      <section
        v-for="board in PLAYER_BOARDS"
        :key="board.kind"
        class="card ladder-card"
      >
        <h3>{{ board.title }}</h3>
        <p v-if="boards[board.kind].loading" class="empty-hint">Загрузка…</p>
        <p v-else-if="boards[board.kind].error" class="error board-error">
          {{ boards[board.kind].error }}
        </p>
        <p v-else-if="!boards[board.kind].items.length" class="empty-hint">Нет данных</p>
        <table v-else class="ladder-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Имя</th>
              <th v-if="board.kind !== 'level'">Ур.</th>
              <th>{{ board.metric }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in boards[board.kind].items" :key="row.telegram_id ?? i">
              <td>{{ i + 1 }}</td>
              <td>
                <RouterLink v-if="row.telegram_id" :to="`/p/${row.telegram_id}`">
                  {{ row.character_name || row.username || row.telegram_id }}
                </RouterLink>
                <span v-else>—</span>
              </td>
              <td v-if="board.kind !== 'level'">{{ row.level ?? '—' }}</td>
              <td>{{ formatValue(board.kind, row.value) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card ladder-card">
        <h3>Гильдии</h3>
        <p v-if="boards.guild.loading" class="empty-hint">Загрузка…</p>
        <p v-else-if="boards.guild.error" class="error board-error">{{ boards.guild.error }}</p>
        <p v-else-if="!boards.guild.items.length" class="empty-hint">Нет данных</p>
        <table v-else class="ladder-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Гильдия</th>
              <th>Ур.</th>
              <th>Участники</th>
              <th>Трофеи</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in boards.guild.items" :key="row.guild_id ?? i">
              <td>{{ i + 1 }}</td>
              <td>
                <RouterLink v-if="row.guild_id" :to="`/g/${row.guild_id}`">
                  [{{ row.tag }}] {{ row.name }}
                </RouterLink>
                <span v-else>[{{ row.tag }}] {{ row.name }}</span>
              </td>
              <td>{{ row.level ?? '—' }}</td>
              <td>{{ row.member_count ?? '—' }}</td>
              <td>{{ row.trophies ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home-lead {
  color: var(--muted);
  margin-bottom: 1.5rem;
}
.search-row {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.search-results {
  margin-top: 1rem;
  list-style: none;
}
.search-results li {
  padding: 0.4rem 0;
}
.section-title {
  margin: 1.5rem 0 0.75rem;
  font-size: 1.15rem;
}
.ladder-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.ladder-card h3 {
  margin-bottom: 0.75rem;
  font-size: 1rem;
}
.ladder-table {
  width: 100%;
  font-size: 0.9rem;
}
.board-error {
  font-size: 0.8rem;
  word-break: break-word;
}
.empty-hint {
  color: var(--muted);
  font-size: 0.85rem;
}
@media (max-width: 720px) {
  .ladder-grid {
    grid-template-columns: 1fr;
  }
}
</style>
