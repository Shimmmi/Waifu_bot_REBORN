<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../../api/client'

const items = ref<Array<{ id: number; action: string; admin_tg_id: number; target_tg_id?: number; created_at?: string }>>([])

onMounted(async () => {
  const data = await apiGet<{ items: typeof items.value }>('/admin/actions')
  items.value = data.items
})
</script>

<template>
  <div>
    <RouterLink to="/admin">← Назад</RouterLink>
    <h1>Журнал админ-действий</h1>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/tavern-bgm" class="tab">Tavern BGM</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>
    <table>
      <thead><tr><th>ID</th><th>Admin</th><th>Target</th><th>Action</th><th>Time</th></tr></thead>
      <tbody>
        <tr v-for="a in items" :key="a.id">
          <td>{{ a.id }}</td>
          <td>{{ a.admin_tg_id }}</td>
          <td>{{ a.target_tg_id ?? '—' }}</td>
          <td>{{ a.action }}</td>
          <td>{{ a.created_at?.slice(0, 19) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
