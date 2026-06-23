<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ArmoryItem } from '../api/client'
import { useItemArtGenerate, itemArtGenerateErrorMessage } from '../composables/useItemArtGenerate'

const props = defineProps<{
  item: ArmoryItem
  adminMode?: boolean
}>()

const emit = defineEmits<{ generated: [url: string] }>()

const loading = ref(false)
const { generateItemArt } = useItemArtGenerate()

const visible = computed(
  () => props.adminMode && !!String(props.item.art_key || '').trim(),
)

async function onGenerate(ev: Event) {
  ev.stopPropagation()
  ev.preventDefault()
  if (loading.value || !visible.value) return
  loading.value = true
  try {
    const url = await generateItemArt(props.item)
    if (url) emit('generated', url)
  } catch (e) {
    window.alert(itemArtGenerateErrorMessage(e) || 'Ошибка генерации')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <button
    v-if="visible"
    type="button"
    class="item-art-generate-btn"
    :class="{ 'is-loading': loading }"
    title="Сгенерировать иконку (admin)"
    aria-label="Сгенерировать иконку"
    :aria-busy="loading || undefined"
    @click="onGenerate"
  >
    🎨
  </button>
</template>
