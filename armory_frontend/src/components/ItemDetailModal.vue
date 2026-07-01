<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ArmoryItem } from '../api/client'
import {
  itemDisplayName,
  itemImageUrl,
  rarityClass,
  rarityLabel,
  statLabel,
  formatAffixLine,
} from '../utils/items'
import ItemArtGenerateButton from './ItemArtGenerateButton.vue'

const props = defineProps<{ item: ArmoryItem | null; adminMode?: boolean }>()
const open = defineModel<boolean>({ default: false })

const imageSrc = ref('')
const imageUrl = computed(() => (props.item ? itemImageUrl(props.item) : ''))
const itemRarity = computed(() => rarityLabel(props.item?.rarity))

watch(
  [() => props.item, imageUrl],
  () => {
    imageSrc.value = imageUrl.value
  },
  { immediate: true },
)

const statRows = computed(() => {
  const item = props.item
  if (!item) return []
  const rows: Array<{ label: string; value: string }> = []
  if (item.damage_min_effective != null || item.damage_max_effective != null) {
    rows.push({
      label: 'Урон',
      value: `${item.damage_min_effective ?? item.damage_min ?? '—'} – ${item.damage_max_effective ?? item.damage_max ?? '—'}`,
    })
  } else if (item.damage_min != null) {
    rows.push({ label: 'Урон', value: `${item.damage_min} – ${item.damage_max ?? '—'}` })
  }
  if (item.armor_effective != null || item.armor_base != null) {
    rows.push({ label: 'Броня', value: String(item.armor_effective ?? item.armor_base) })
  }
  if (item.base_stat && item.base_stat_value != null) {
    rows.push({ label: statLabel(item.base_stat), value: String(item.base_stat_value) })
  }
  if (item.enchant_level) {
    rows.push({ label: 'Зачарование', value: `+${item.enchant_level}` })
  }
  return rows
})

const affixLines = computed(() => props.item?.affixes?.map(formatAffixLine) ?? [])

function close() {
  open.value = false
}

function onOverlayClick(ev: MouseEvent) {
  if (ev.target === ev.currentTarget) close()
}

function onImgError(ev: Event) {
  const img = ev.target as HTMLImageElement
  if (props.item?.image_key) {
    img.src = `/static/game/items/svg/${encodeURIComponent(props.item.image_key)}.svg`
  }
}

function onArtGenerated(url: string) {
  imageSrc.value = url
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open && item" class="item-modal-overlay" @click="onOverlayClick">
      <div class="item-modal" :class="rarityClass(item.rarity)" @click.stop>
        <div class="item-modal-header">
          <div>
            <div class="item-modal-title">{{ itemDisplayName(item) }}</div>
            <div class="item-modal-sub">
              Уровень {{ item.tier ?? 1 }} · {{ itemRarity }}
              <span v-if="item.level"> · Ур. {{ item.level }}</span>
            </div>
          </div>
          <button type="button" class="item-modal-close" aria-label="Закрыть" @click="close">×</button>
        </div>
        <div class="item-modal-art-wrap">
          <div class="item-modal-art">
            <span class="item-art-admin-wrap">
              <img v-if="imageSrc" :src="imageSrc" alt="" @error="onImgError" />
              <span v-else>⚔</span>
              <ItemArtGenerateButton
                v-if="item"
                :item="item"
                :admin-mode="adminMode"
                @generated="onArtGenerated"
              />
            </span>
          </div>
        </div>
        <div v-if="statRows.length" class="item-modal-stats">
          <div v-for="row in statRows" :key="row.label" class="item-modal-stat-row">
            <span>{{ row.label }}</span>
            <span>{{ row.value }}</span>
          </div>
        </div>
        <div v-if="affixLines.length" class="item-modal-affixes">
          <strong>Аффиксы</strong>
          <ul>
            <li v-for="(line, i) in affixLines" :key="i">{{ line }}</li>
          </ul>
        </div>
      </div>
    </div>
  </Teleport>
</template>
