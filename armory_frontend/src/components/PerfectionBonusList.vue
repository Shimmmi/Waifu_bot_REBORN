<script setup lang="ts">
import type { PerfectionBonusSummary } from '../api/client'

defineProps<{
  perfectionLevel: number
  bonuses: PerfectionBonusSummary[]
}>()
</script>

<template>
  <div class="perfection-panel">
    <p v-if="perfectionLevel <= 0" class="empty-hint">
      Откроется на 60 уровне
    </p>
    <template v-else>
      <div class="perfection-panel-level">Уровень совершенствования: {{ perfectionLevel }}</div>
      <ul v-if="bonuses.length" class="perfection-bonus-list">
        <li v-for="b in bonuses" :key="b.bonus_id">
          <span class="perfection-bonus-title">{{ b.title_ru }}</span>
          <strong class="perfection-bonus-value">{{ b.display_value }}</strong>
          <em class="perfection-bonus-tag">{{ b.label || 'Навсегда' }}</em>
        </li>
      </ul>
      <p v-else class="empty-hint">Пока нет постоянных бонусов</p>
    </template>
  </div>
</template>
