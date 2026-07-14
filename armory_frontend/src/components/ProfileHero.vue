<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { PlayerCharacter, ArmoryItem } from '../api/client'
import EquipmentSlot from './EquipmentSlot.vue'
import {
  META_ICONS,
  SLOT_LAYOUT,
  SLOT_ROW_ORDER,
  STAT_FULL_LABELS,
  STAT_ICONS,
  STAT_ORDER,
} from '../utils/items'

const props = defineProps<{
  character?: PlayerCharacter
  equipped?: ArmoryItem[]
  statsEffective?: Record<string, number>
  gearScore: number
  gold: number
  currentAct: number
  adminMode?: boolean
  guild?: { id?: number; name: string; tag: string; level: number } | null
}>()

const emit = defineEmits<{ itemClick: [item: ArmoryItem] }>()

const equippedBySlot = computed(() => {
  const map: Record<number, ArmoryItem> = {}
  for (const item of props.equipped ?? []) {
    if (item.equipment_slot) map[item.equipment_slot] = item
  }
  return map
})

const portraitSrc = computed(() => {
  const c = props.character
  if (!c) return ''
  return c.paperdoll_url || c.portrait_url || ''
})

const statRows = computed(() =>
  STAT_ORDER.map((key) => ({
    key,
    icon: STAT_ICONS[key] || '•',
    label: STAT_FULL_LABELS[key] || key,
    value: props.statsEffective?.[key] ?? 0,
  })),
)

const metaRows = computed(() => {
  const rows = [
    { key: 'gear_score', icon: META_ICONS.gear_score, label: 'Снаряжение', value: fmt(props.gearScore) },
    {
      key: 'max_hp',
      icon: META_ICONS.max_hp,
      label: 'Здоровье',
      value: props.character?.max_hp != null ? fmt(props.character.max_hp) : '—',
    },
    { key: 'gold', icon: META_ICONS.gold, label: 'Золото', value: fmt(props.gold) },
    { key: 'act', icon: META_ICONS.act, label: 'Акт', value: String(props.currentAct) },
  ]
  return rows
})

function itemForSlot(slot: number): ArmoryItem | undefined {
  return equippedBySlot.value[slot]
}

function onSlotClick(item: ArmoryItem | null) {
  if (item) emit('itemClick', item)
}

function fmt(n: number): string {
  return n.toLocaleString('ru-RU')
}
</script>

<template>
  <div class="card profile-card">
    <div class="profile-hero">
      <div class="profile-paperdoll">
        <div class="profile-paperdoll-row">
          <div class="profile-slot-col profile-slot-col--left">
            <EquipmentSlot
              v-for="slot in SLOT_LAYOUT.left"
              :key="`l-${slot}`"
              :slot="slot"
              :item="itemForSlot(slot)"
              :admin-mode="adminMode"
              compact
              @click="onSlotClick"
            />
          </div>

          <div class="profile-portrait-block">
            <div class="profile-portrait">
              <div class="profile-portrait-media">
                <img v-if="portraitSrc" :src="portraitSrc" :alt="character?.name || 'Портрет'" />
                <span v-else class="profile-portrait-fallback">👤</span>
              </div>
            </div>
          </div>

          <div class="profile-slot-col profile-slot-col--right">
            <EquipmentSlot
              v-for="slot in SLOT_LAYOUT.right"
              :key="`r-${slot}`"
              :slot="slot"
              :item="itemForSlot(slot)"
              :admin-mode="adminMode"
              compact
              @click="onSlotClick"
            />
          </div>
        </div>

        <div v-if="character" class="profile-portrait-caption">
          <h2>{{ character.name }}</h2>
          <div class="profile-portrait-meta">
            {{ character.race_label }} · {{ character.class_label }}
          </div>
          <div class="profile-portrait-level">Уровень {{ character.level }}</div>
          <div v-if="guild" class="profile-portrait-guild">
            <RouterLink v-if="guild.id" :to="`/g/${guild.id}`">
              {{ META_ICONS.guild }} [{{ guild.tag }}] {{ guild.name }}
            </RouterLink>
            <span v-else>{{ META_ICONS.guild }} [{{ guild.tag }}] {{ guild.name }}</span>
            <span class="badge">Ур. {{ guild.level }}</span>
          </div>
        </div>
        <div v-else class="profile-portrait-caption">
          <h2>Нет персонажа</h2>
        </div>
      </div>

      <div class="profile-gear-row profile-gear-row--mobile">
        <EquipmentSlot
          v-for="slot in SLOT_ROW_ORDER"
          :key="`m-${slot}`"
          :slot="slot"
          :item="itemForSlot(slot)"
          :admin-mode="adminMode"
          @click="onSlotClick"
        />
      </div>

      <div class="profile-stats-strip">
        <div class="profile-stats-grid">
          <div v-for="row in statRows" :key="row.key" class="profile-strip-cell">
            <span class="profile-side-icon">{{ row.icon }}</span>
            <span class="profile-side-value">{{ row.value }}</span>
            <span class="profile-side-cell-label">{{ row.label }}</span>
          </div>
        </div>
        <div class="profile-meta-grid-strip">
          <div v-for="row in metaRows" :key="row.key" class="profile-strip-cell">
            <span class="profile-side-icon">{{ row.icon }}</span>
            <span class="profile-side-value">{{ row.value }}</span>
            <span class="profile-side-cell-label">{{ row.label }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
