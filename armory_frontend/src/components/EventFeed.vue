<script setup lang="ts">
import { formatEvent, formatEventDate } from '../utils/items'

defineProps<{
  items: Array<{ id: number; event_type: string; payload: Record<string, unknown>; created_at?: string }>
}>()
</script>

<template>
  <table v-if="items.length" class="event-table">
    <thead>
      <tr>
        <th class="col-num">№</th>
        <th>Активность</th>
        <th class="col-date">Дата</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(e, idx) in items" :key="e.id">
        <td class="col-num">{{ idx + 1 }}</td>
        <td class="col-type">{{ formatEvent(e.event_type, e.payload) }}</td>
        <td class="col-date">{{ formatEventDate(e.created_at) }}</td>
      </tr>
    </tbody>
  </table>
  <p v-else class="empty-hint">Нет событий</p>
</template>

<style scoped>
.empty-hint { color: var(--muted); font-size: 0.85rem; }
</style>
