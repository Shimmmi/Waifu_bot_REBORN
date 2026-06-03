<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../../api/client'

const q = ref('')
const items = ref<Array<{ telegram_id: number; username?: string; character_name?: string; level?: number; gold: number; banned: boolean; created_at?: string }>>([])
const page = ref(1)

async function load() {
  const data = await apiGet<{ items: typeof items.value; total: number }>(
    `/admin/players?q=${encodeURIComponent(q.value)}&page=${page.value}`
  )
  items.value = data.items
}

onMounted(load)
</script>

<template>
  <div>
    <h1>Игроки</h1>
    <RouterLink to="/admin">← Назад</RouterLink>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>
    <div style="margin: 1rem 0; display: flex; gap: 0.5rem">
      <input v-model="q" type="search" placeholder="Поиск..." @keyup.enter="load" />
      <button class="btn" @click="load">Найти</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Имя</th><th>Персонаж</th><th>Lv</th><th>Gold</th><th>Ban</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in items" :key="p.telegram_id">
          <td>{{ p.telegram_id }}</td>
          <td>{{ p.username || '—' }}</td>
          <td>{{ p.character_name || '—' }}</td>
          <td>{{ p.level ?? '—' }}</td>
          <td>{{ p.gold }}</td>
          <td>{{ p.banned ? 'да' : '' }}</td>
          <td><RouterLink :to="`/admin/players/${p.telegram_id}`">Подробнее</RouterLink></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
