<script setup lang="ts">
defineProps<{
  icon?: string
  value?: string | number
  label?: string
  empty?: boolean
}>()
</script>

<template>
  <div class="profile-side-cell" :class="{ 'profile-side-cell--empty': empty }">
    <div v-if="!empty" class="profile-side-cell-value">
      <span v-if="icon" class="profile-side-icon">{{ icon }}</span>
      <span class="profile-side-value">{{ value }}</span>
    </div>
    <div v-if="!empty && label" class="profile-side-cell-label">{{ label }}</div>
  </div>
</template>
