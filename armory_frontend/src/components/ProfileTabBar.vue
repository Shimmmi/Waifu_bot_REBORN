<script setup lang="ts">
export interface ProfileTabItem {
  id: string
  label: string
  count?: number
}

defineProps<{ tabs: ProfileTabItem[] }>()
const activeTab = defineModel<string>({ required: true })
</script>

<template>
  <div class="tabs profile-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="tab"
      :class="{ active: activeTab === tab.id }"
      @click="activeTab = tab.id"
    >
      {{ tab.label }}<span v-if="tab.count != null" class="tab-count"> ({{ tab.count }})</span>
    </button>
  </div>
</template>

<style scoped>
.tab-count { font-weight: 400; opacity: 0.85; }
.profile-tabs { margin-bottom: 0; flex-wrap: wrap; }
</style>
