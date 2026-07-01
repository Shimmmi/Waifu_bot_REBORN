<script setup lang="ts">
import { computed } from 'vue'
import { META_ICONS } from '../utils/items'
import ProfileSideCell from './ProfileSideCell.vue'

const props = defineProps<{
  gearScore: number
  gold: number
  currentAct: number
  maxHp?: number
}>()

const META_LABELS: Record<string, string> = {
  gear_score: 'уровень предметов',
  max_hp: 'здоровье',
  gold: 'золото',
  act: 'акт',
}

type MetaCell = {
  key: string
  icon: string
  value: string
  label: string
  empty?: boolean
}

const cells = computed((): MetaCell[] => {
  const filled: MetaCell[] = [
    {
      key: 'gear_score',
      icon: META_ICONS.gear_score,
      value: fmt(props.gearScore),
      label: META_LABELS.gear_score,
    },
    {
      key: 'max_hp',
      icon: META_ICONS.max_hp,
      value: props.maxHp != null ? fmt(props.maxHp) : '—',
      label: META_LABELS.max_hp,
    },
    {
      key: 'gold',
      icon: META_ICONS.gold,
      value: fmt(props.gold),
      label: META_LABELS.gold,
    },
    {
      key: 'act',
      icon: META_ICONS.act,
      value: String(props.currentAct),
      label: META_LABELS.act,
    },
  ]
  const placeholders: MetaCell[] = [
    { key: 'empty_5', icon: '', value: '', label: '', empty: true },
    { key: 'empty_6', icon: '', value: '', label: '', empty: true },
  ]
  return [...filled, ...placeholders]
})

function fmt(n: number): string {
  return n.toLocaleString('ru-RU')
}
</script>

<template>
  <div class="profile-meta-sidebar">
    <ProfileSideCell
      v-for="cell in cells"
      :key="cell.key"
      :icon="cell.icon"
      :value="cell.value"
      :label="cell.label"
      :empty="cell.empty"
    />
  </div>
</template>
