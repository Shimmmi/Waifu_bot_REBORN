<script setup lang="ts">
import { computed } from 'vue'
import StatsRadar from './StatsRadar.vue'
import PlayerStatisticsGrid from './PlayerStatisticsGrid.vue'
import { statListEntries } from '../utils/items'

const props = defineProps<{
  stats: Record<string, number>
  playerId: string
  active?: boolean
}>()

const entries = computed(() => statListEntries(props.stats))
</script>

<template>
  <div class="stats-panel">
    <div class="stats-panel-body">
      <ul class="stats-list">
        <li v-for="row in entries" :key="row.key" class="stats-list-row">
          <span class="stats-list-label">{{ row.label }}</span>
          <span class="stats-list-value">{{ row.value }}</span>
        </li>
      </ul>
      <StatsRadar :stats="stats" />
    </div>

    <PlayerStatisticsGrid :player-id="playerId" :active="active" />
  </div>
</template>
