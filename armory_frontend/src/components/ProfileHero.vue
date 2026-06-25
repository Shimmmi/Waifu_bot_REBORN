<script setup lang="ts">
import { computed } from 'vue'
import type { PlayerCharacter, ArmoryItem } from '../api/client'
import EquipmentSlot from './EquipmentSlot.vue'
import ProfileStatSidebar from './ProfileStatSidebar.vue'
import ProfileMetaSidebar from './ProfileMetaSidebar.vue'
import { SLOT_ROW_ORDER } from '../utils/items'

const props = defineProps<{
  character?: PlayerCharacter
  equipped?: ArmoryItem[]
  statsEffective?: Record<string, number>
  gearScore: number
  gold: number
  currentAct: number
  adminMode?: boolean
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

function itemForSlot(slot: number): ArmoryItem | undefined {
  return equippedBySlot.value[slot]
}

function onSlotClick(item: ArmoryItem | null) {
  if (item) emit('itemClick', item)
}
</script>

<template>
  <div class="card profile-card">
    <div class="profile-hero">
      <div class="profile-hero-top">
        <ProfileStatSidebar :stats="statsEffective" />

        <div class="profile-portrait-block">
          <div class="profile-portrait">
            <div class="profile-portrait-media">
              <img v-if="portraitSrc" :src="portraitSrc" :alt="character?.name || 'Портрет'" />
              <span v-else class="profile-portrait-fallback">👤</span>
            </div>
            <div v-if="character" class="profile-portrait-caption">
              <h2>{{ character.name }}</h2>
              <div class="profile-portrait-meta">
                {{ character.race_label }} · {{ character.class_label }}
              </div>
              <div class="profile-portrait-level">Уровень {{ character.level }}</div>
            </div>
            <div v-else class="profile-portrait-caption">
              <h2>Нет персонажа</h2>
            </div>
          </div>
        </div>

        <ProfileMetaSidebar
          :gear-score="gearScore"
          :gold="gold"
          :current-act="currentAct"
          :max-hp="character?.max_hp"
        />
      </div>

      <div class="profile-gear-row">
        <EquipmentSlot
          v-for="slot in SLOT_ROW_ORDER"
          :key="slot"
          :slot="slot"
          :item="itemForSlot(slot)"
          :admin-mode="adminMode"
          @click="onSlotClick"
        />
      </div>
    </div>
  </div>
</template>
