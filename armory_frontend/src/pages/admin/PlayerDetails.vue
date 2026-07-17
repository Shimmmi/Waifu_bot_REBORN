<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, apiPost } from '../../api/client'

const props = defineProps<{ id: string }>()
interface AdminPlayerFull {
  summary: Record<string, unknown>
  target_is_bot_admin: boolean
  stats?: unknown
  inventory?: unknown
  events?: unknown
}

const full = ref<AdminPlayerFull | null>(null)
const message = ref('')

const guildId = computed(() => {
  const g = full.value?.summary?.guild as { id?: number } | undefined
  return g?.id ?? null
})

const character = computed(() => full.value?.summary?.character as Record<string, unknown> | undefined)

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
    <p v-if="full" style="margin: 0.5rem 0">
      <RouterLink :to="`/p/${id}`">Публичный профиль</RouterLink>
      <template v-if="guildId">
        ·
        <RouterLink :to="`/g/${guildId}`">Гильдия</RouterLink>
      </template>
    </p>
    <div v-if="full" class="card" style="margin-top: 1rem">
      <p>
        <strong>Админ бота:</strong>
        {{ full.target_is_bot_admin ? 'да' : 'нет' }}
        <span class="muted">(viewer_access_level в summary — права вашей сессии, не игрока)</span>
      </p>
      <pre style="font-size: 0.75rem; overflow: auto; max-height: 200px">{{ JSON.stringify(full.summary, null, 2) }}</pre>
    </div>
    <div class="card" style="margin-top: 1rem">
      <h3>Действия</h3>
      <p
        v-if="character && 'paperdoll_generations_remaining' in character"
        class="muted"
        style="margin: 0.5rem 0 0"
      >
        Paper-doll: осталось генераций
        {{ character.paperdoll_generations_remaining }}
        (бонус:
        {{ character.paperdoll_bonus_generations ?? 0 }})
      </p>
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem">
        <button class="btn btn-danger" @click="action('wipe')">Вайп</button>
        <button class="btn btn-danger" @click="action('ban', { reason: 'admin' })">Бан</button>
        <button class="btn" @click="action('unban')">Разбан</button>
        <button class="btn" @click="action('grant-gold', { amount: 10000 })">+10k gold</button>
        <button class="btn" @click="action('restore-hp')">Restore HP</button>
        <button class="btn" @click="action('grant-paperdoll-generation')">+1 paper-doll</button>
      </div>
      <p v-if="message" style="margin-top: 0.5rem">{{ message }}</p>
    </div>
  </div>
</template>

<style scoped>
.muted { color: var(--muted); font-size: 0.85rem; }
</style>
