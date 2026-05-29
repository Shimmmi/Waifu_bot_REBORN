<script setup lang="ts">
import { computed } from 'vue'
import { STAT_ICONS, STAT_FULL_LABELS, STAT_ORDER } from '../utils/items'
import ProfileSideCell from './ProfileSideCell.vue'

const props = defineProps<{ stats?: Record<string, number> }>()

const rows = computed(() =>
  STAT_ORDER.map((key) => ({
    key,
    icon: STAT_ICONS[key] || '•',
    label: (STAT_FULL_LABELS[key] || key).toLowerCase(),
    value: props.stats?.[key] ?? 0,
  })),
)
</script>

<template>
  <div class="profile-stat-sidebar">
    <ProfileSideCell
      v-for="row in rows"
      :key="row.key"
      :icon="row.icon"
      :value="row.value"
      :label="row.label"
    />
  </div>
</template>
