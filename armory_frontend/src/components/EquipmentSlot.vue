<script setup lang="ts">
import { computed } from 'vue'
import type { ArmoryItem } from '../api/client'
import { EQUIPMENT_SLOT_NAMES, itemImageUrl, itemDisplayName, rarityClass } from '../utils/items'

const props = defineProps<{
  slot: number
  item?: ArmoryItem | null
}>()

const emit = defineEmits<{ click: [item: ArmoryItem | null, slot: number] }>()

const slotName = computed(() => EQUIPMENT_SLOT_NAMES[props.slot] || `Слот ${props.slot}`)
const rarity = computed(() => (props.item ? rarityClass(props.item.rarity) : 'empty'))
const imageUrl = computed(() => (props.item ? itemImageUrl(props.item) : ''))
const svgFallback = computed(() => {
  if (!props.item?.image_key) return ''
  return `/static/game/items/svg/${encodeURIComponent(props.item.image_key)}.svg`
})

function onClick() {
  if (props.item) emit('click', props.item, props.slot)
}

function onImgError(ev: Event) {
  const img = ev.target as HTMLImageElement
  if (svgFallback.value && img.src !== svgFallback.value) {
    img.src = svgFallback.value
  } else {
    img.style.display = 'none'
  }
}
</script>

<template>
  <button
    type="button"
    class="profile-slot-card"
    :class="[rarity, { empty: !item }]"
    :title="item ? itemDisplayName(item) : `Пусто · ${slotName}`"
    :aria-label="slotName"
    :disabled="!item"
    @click="onClick"
  >
    <div class="profile-slot-media-wrap">
      <div class="profile-slot-media">
        <img v-if="imageUrl" :src="imageUrl" alt="" @error="onImgError" />
        <span v-else class="profile-slot-fallback">⚔</span>
      </div>
      <span v-if="item?.level" class="profile-slot-level">{{ item.level }}</span>
    </div>
    <span class="profile-slot-label">{{ slotName }}</span>
  </button>
</template>
