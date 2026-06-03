<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../../api/client'

const stats = ref<Record<string, unknown> | null>(null)

onMounted(async () => {
  stats.value = await apiGet('/admin/stats')
})
</script>

<template>
  <div>
    <h1>Админ-панель</h1>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>
    <div v-if="stats" class="card">
      <div class="stat-grid">
        <div class="stat-item"><div class="label">Всего игроков</div><div class="value">{{ stats.total_players }}</div></div>
        <div class="stat-item"><div class="label">С персонажем</div><div class="value">{{ stats.with_character }}</div></div>
        <div class="stat-item"><div class="label">DAU сегодня</div><div class="value">{{ stats.dau_today }}</div></div>
        <div class="stat-item"><div class="label">Забанено</div><div class="value">{{ stats.banned_count }}</div></div>
      </div>
    </div>
  </div>
</template>
