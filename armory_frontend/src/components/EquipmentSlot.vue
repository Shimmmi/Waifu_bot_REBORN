<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ArmoryItem } from '../api/client'
import { EQUIPMENT_SLOT_NAMES, itemImageUrl, itemDisplayName, rarityClass } from '../utils/items'
import ItemArtGenerateButton from './ItemArtGenerateButton.vue'

const props = defineProps<{
  slot: number
  item?: ArmoryItem | null
  adminMode?: boolean
  /** Hide text label; used in desktop L/R columns */
  compact?: boolean
}>()

const emit = defineEmits<{ click: [item: ArmoryItem | null, slot: number] }>()

const imageSrc = ref('')
const slotName = computed(() => EQUIPMENT_SLOT_NAMES[props.slot] || `Слот ${props.slot}`)
const rarity = computed(() => (props.item ? rarityClass(props.item.rarity) : 'empty'))
const imageUrl = computed(() => (props.item ? itemImageUrl(props.item) : ''))
const svgFallback = computed(() => {
  if (!props.item?.image_key) return ''
  return `/static/game/items/svg/${encodeURIComponent(props.item.image_key)}.svg`
})

watch(
  [() => props.item, imageUrl],
  () => {
    imageSrc.value = imageUrl.value
  },
  { immediate: true },
)

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

function onArtGenerated(url: string) {
  imageSrc.value = url
}
</script>

<template>
  <button
    type="button"
    class="profile-slot-card"
    :class="[rarity, { empty: !item, compact }]"
    :title="item ? itemDisplayName(item) : `Пусто · ${slotName}`"
    :aria-label="slotName"
    :disabled="!item"
    @click="onClick"
  >
    <div class="profile-slot-media-wrap">
      <div class="profile-slot-media">
        <span v-if="item" class="item-art-admin-wrap profile-slot-art-wrap">
          <img v-if="imageSrc" :src="imageSrc" alt="" @error="onImgError" />
          <span v-else class="profile-slot-fallback">⚔</span>
          <ItemArtGenerateButton
            :item="item"
            :admin-mode="adminMode"
            @generated="onArtGenerated"
          />
        </span>
        <span v-else class="profile-slot-fallback">⚔</span>
      </div>
      <span v-if="item?.level" class="profile-slot-level">{{ item.level }}</span>
    </div>
    <span v-if="!compact" class="profile-slot-label">{{ slotName }}</span>
  </button>
</template>
