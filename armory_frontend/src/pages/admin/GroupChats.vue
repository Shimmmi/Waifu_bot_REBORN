<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, apiPost, type AdminGroupChat, type AdminGroupChatsResponse } from '../../api/client'

const statusFilter = ref('all')
const q = ref('')
const page = ref(1)
const items = ref<AdminGroupChat[]>([])
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')

const statusOptions = [
  { value: 'all', label: 'Все' },
  { value: 'active', label: 'Активные' },
  { value: 'left', label: 'Вышел' },
  { value: 'kicked', label: 'Кикнут' },
  { value: 'member', label: 'Участник' },
  { value: 'administrator', label: 'Админ' },
]

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    member: 'участник',
    administrator: 'админ',
    creator: 'создатель',
    left: 'вышел',
    kicked: 'кикнут',
    restricted: 'ограничен',
  }
  return map[s] || s
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiGet<AdminGroupChatsResponse>(
      `/admin/group-chats?status=${encodeURIComponent(statusFilter.value)}&q=${encodeURIComponent(q.value)}&page=${page.value}`
    )
    items.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function refreshPage() {
  refreshing.value = true
  error.value = ''
  try {
    await apiPost('/admin/group-chats/refresh', {
      chat_ids: items.value.map((c) => c.chat_id),
    })
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    refreshing.value = false
  }
}

onMounted(load)
watch(statusFilter, () => {
  page.value = 1
  load()
})
</script>

<template>
  <div>
    <RouterLink to="/admin">← Назад</RouterLink>
    <h1>Групповые чаты</h1>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/tavern-bgm" class="tab">Tavern BGM</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>
    <div style="margin: 1rem 0; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center">
      <select v-model="statusFilter" class="btn" style="padding: 0.4rem 0.6rem">
        <option v-for="o in statusOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <input v-model="q" type="search" placeholder="Название, @username или chat_id..." @keyup.enter="load" />
      <button class="btn" :disabled="loading" @click="load">Найти</button>
      <button class="btn secondary" :disabled="refreshing || !items.length" @click="refreshPage">
        {{ refreshing ? 'Обновление…' : 'Обновить из Telegram' }}
      </button>
      <span v-if="total" style="opacity: 0.75">Всего: {{ total }}</span>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <table v-if="items.length">
      <thead>
        <tr>
          <th>Чат</th>
          <th>chat_id</th>
          <th>Тип</th>
          <th>Статус</th>
          <th>Источник</th>
          <th>Активность</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in items" :key="c.chat_id">
          <td>
            <strong>{{ c.title || '—' }}</strong>
            <span v-if="c.username" style="opacity: 0.75"> @{{ c.username }}</span>
          </td>
          <td><code>{{ c.chat_id }}</code></td>
          <td>{{ c.chat_type }}</td>
          <td>{{ statusLabel(c.status) }}</td>
          <td>{{ c.discovered_via }}</td>
          <td>
            <span v-if="c.last_activity_at" :title="c.last_activity_at">{{ c.last_activity_at.slice(0, 10) }}</span>
            <span v-else style="opacity: 0.75">—</span>
          </td>
          <td>
            <a
              v-if="c.telegram_url"
              :href="c.telegram_url"
              target="_blank"
              rel="noopener noreferrer"
              class="btn"
              style="font-size: 0.85rem"
            >Открыть в Telegram</a>
            <span
              v-else
              style="opacity: 0.75; font-size: 0.85rem"
              title="Нет публичной ссылки: откройте чат в клиенте Telegram, если вы в нём состоите"
            >нет ссылки</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="!loading" style="opacity: 0.75">Чаты не найдены. После деплоя выполните backfill-group-chats на сервере.</p>
  </div>
</template>
