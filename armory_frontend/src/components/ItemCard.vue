<script setup lang="ts">
import { computed } from 'vue'
import type { ArmoryItem } from '../api/client'
import { itemDisplayName, itemImageUrl, rarityClass, rarityLabel } from '../utils/items'

const props = defineProps<{ item: ArmoryItem }>()
const emit = defineEmits<{ click: [item: ArmoryItem] }>()

const imageUrl = computed(() => itemImageUrl(props.item))
const equipped = computed(() => !!props.item.equipment_slot)
const itemRarity = computed(() => rarityLabel(props.item.rarity))

function onClick() {
  emit('click', props.item)
}

function onImgError(ev: Event) {
  const img = ev.target as HTMLImageElement
  if (props.item.image_key) {
    img.src = `/static/game/items/svg/${encodeURIComponent(props.item.image_key)}.svg`
  }
}
</script>

<template>
  <div class="item-card" :class="rarityClass(item.rarity)" @click="onClick">
    <div class="item-card-art">
      <img v-if="imageUrl" :src="imageUrl" alt="" @error="onImgError" />
      <span v-else>⚔</span>
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
