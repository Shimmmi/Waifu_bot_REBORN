<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ArmoryItem } from '../api/client'
import { itemDisplayName, itemImageUrl, rarityClass, rarityLabel } from '../utils/items'
import ItemArtGenerateButton from './ItemArtGenerateButton.vue'

const props = defineProps<{ item: ArmoryItem; adminMode?: boolean }>()
const emit = defineEmits<{ click: [item: ArmoryItem] }>()

const imageSrc = ref('')
const imageUrl = computed(() => itemImageUrl(props.item))
const equipped = computed(() => !!props.item.equipment_slot)
const itemRarity = computed(() => rarityLabel(props.item.rarity))

watch(
  [() => props.item, imageUrl],
  () => {
    imageSrc.value = imageUrl.value
  },
  { immediate: true },
)

function onClick() {
  emit('click', props.item)
}

function onImgError(ev: Event) {
  const img = ev.target as HTMLImageElement
  if (props.item.image_key) {
    img.src = `/static/game/items/svg/${encodeURIComponent(props.item.image_key)}.svg`
  }
}

function onArtGenerated(url: string) {
  imageSrc.value = url
}
</script>

<template>
  <div class="item-card" :class="rarityClass(item.rarity)" @click="onClick">
    <div class="item-card-art">
      <span class="item-art-admin-wrap">
        <img v-if="imageSrc" :src="imageSrc" alt="" @error="onImgError" />
        <span v-else>⚔</span>
        <ItemArtGenerateButton
          :item="item"
          :admin-mode="adminMode"
          @generated="onArtGenerated"
        />
      </span>
    </div>
    <div class="item-card-body">
      <div class="item-card-name">{{ itemDisplayName(item) }}</div>
      <div class="item-card-meta">
        Уровень {{ item.tier ?? 1 }} · {{ itemRarity }}
        <span v-if="equipped" class="badge badge-gold">Надето</span>
      </div>
    </div>
  </div>
</template>
