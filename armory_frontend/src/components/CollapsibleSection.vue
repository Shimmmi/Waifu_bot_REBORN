<script setup lang="ts">
defineProps<{ title: string; count?: number }>()
</script>

<template>
  <details class="collapsible">
    <summary>
      <span>{{ title }}<span v-if="count != null" class="muted-inline"> ({{ count }})</span></span>
    </summary>
    <div class="collapsible-body">
      <slot />
    </div>
  </details>
</template>

<style scoped>
.muted-inline { color: var(--muted); font-weight: 400; }
</style>
