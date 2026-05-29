<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, apiPost } from '../../api/client'

const props = defineProps<{ id: string }>()
const full = ref<Record<string, unknown> | null>(null)
const message = ref('')

async function load() {
  full.value = await apiGet(`/admin/players/${props.id}/full`)
}

async function action(name: string, body?: unknown) {
  message.value = ''
  try {
    await apiPost(`/admin/players/${props.id}/${name}`, body)
    message.value = `OK: ${name}`
    await load()
  } catch (e) {
    message.value = String(e)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <RouterLink to="/admin/players">← К списку</RouterLink>
    <h1 v-if="full">Игрок {{ id }}</h1>
    <div v-if="full" class="card" style="margin-top: 1rem">
      <pre style="font-size: 0.75rem; overflow: auto; max-height: 200px">{{ JSON.stringify(full.summary, null, 2) }}</pre>
    </div>
    <div class="card" style="margin-top: 1rem">
      <h3>Действия</h3>
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem">
        <button class="btn btn-danger" @click="action('wipe')">Вайп</button>
        <button class="btn btn-danger" @click="action('ban', { reason: 'admin' })">Бан</button>
        <button class="btn" @click="action('unban')">Разбан</button>
        <button class="btn" @click="action('grant-gold', { amount: 10000 })">+10k gold</button>
        <button class="btn" @click="action('restore-hp')">Restore HP</button>
      </div>
      <p v-if="message" style="margin-top: 0.5rem">{{ message }}</p>
    </div>
  </div>
</template>
