<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AdminNav from '../../components/AdminNav.vue'
import { apiGet, type AdminLlmUsage } from '../../api/client'

const report = ref<AdminLlmUsage | null>(null)
const error = ref('')
const loading = ref(false)
const modality = ref('')
const caller = ref('')
const playerId = ref('')

async function load() {
  loading.value = true
  error.value = ''
  const qs = new URLSearchParams()
  if (modality.value) qs.set('modality', modality.value)
  if (caller.value.trim()) qs.set('caller', caller.value.trim())
  if (playerId.value.trim()) qs.set('player_id', playerId.value.trim())
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  try {
    report.value = await apiGet<AdminLlmUsage>(`/admin/llm/usage${suffix}`)
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

function playerLabel(row: AdminLlmUsage['by_player'][number]): string {
  if (row.username) return `@${row.username}`
  if (row.first_name) return `${row.first_name} (${row.player_id ?? '—'})`
  return row.player_id != null ? String(row.player_id) : 'фон / без игрока'
}

onMounted(load)
</script>

<template>
  <div>
    <RouterLink to="/admin">← Назад</RouterLink>
    <h1>LLM — кто тратит</h1>
    <AdminNav />
    <p class="muted" style="margin-bottom: 1rem">
      Каждый POST /chat/completions. Тела промптов не пишутся. Окно по умолчанию — сегодня (UTC+7).
    </p>
    <div style="margin: 1rem 0; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center">
      <select v-model="modality" class="tab">
        <option value="">все modality</option>
        <option value="text">text</option>
        <option value="image">image</option>
      </select>
      <input v-model="caller" type="search" placeholder="caller, напр. delve line" @keyup.enter="load" />
      <input v-model="playerId" type="search" placeholder="player_id" @keyup.enter="load" />
      <button class="btn" :disabled="loading" @click="load">{{ loading ? 'Загрузка…' : 'Обновить' }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-if="report" class="card">
      <div class="stat-grid">
        <div class="stat-item"><div class="label">Sent</div><div class="value">{{ report.totals.sent }}</div></div>
        <div class="stat-item"><div class="label">OK</div><div class="value">{{ report.totals.ok }}</div></div>
        <div class="stat-item"><div class="label">Error</div><div class="value">{{ report.totals.error }}</div></div>
        <div class="stat-item"><div class="label">Игроки</div><div class="value">{{ report.totals.players }}</div></div>
        <div class="stat-item"><div class="label">prompt tokens</div><div class="value">{{ report.totals.prompt_tokens }}</div></div>
        <div class="stat-item"><div class="label">completion tokens</div><div class="value">{{ report.totals.completion_tokens }}</div></div>
      </div>
      <p class="muted" style="margin-top: 0.75rem">{{ report.since }} → {{ report.until }}</p>
    </div>

    <div v-if="report?.by_caller?.length" class="card">
      <h2>Где (caller)</h2>
      <table>
        <thead>
          <tr>
            <th>Caller</th><th>Modality</th><th>Count</th><th>OK</th><th>Err</th><th>avg ms</th><th>tok in/out</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in report.by_caller" :key="`${row.caller}:${row.modality}`">
            <td>{{ row.caller }}</td>
            <td>{{ row.modality }}</td>
            <td>{{ row.count }}</td>
            <td>{{ row.ok }}</td>
            <td>{{ row.error }}</td>
            <td>{{ row.avg_ms }}</td>
            <td>{{ row.prompt_tokens }} / {{ row.completion_tokens }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="report?.by_player?.length" class="card">
      <h2>Кто (игрок)</h2>
      <table>
        <thead>
          <tr><th>Игрок</th><th>Count</th><th>OK</th><th>Err</th><th>tok in/out</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in report.by_player" :key="String(row.player_id)">
            <td>
              <RouterLink v-if="row.player_id" :to="`/admin/players/${row.player_id}`">{{ playerLabel(row) }}</RouterLink>
              <span v-else>{{ playerLabel(row) }}</span>
            </td>
            <td>{{ row.count }}</td>
            <td>{{ row.ok }}</td>
            <td>{{ row.error }}</td>
            <td>{{ row.prompt_tokens }} / {{ row.completion_tokens }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="report?.recent?.length" class="card">
      <h2>Последние запросы</h2>
      <table>
        <thead>
          <tr>
            <th>Time</th><th>Player</th><th>Caller</th><th>Trigger</th><th>Mod</th><th>ms</th><th>HTTP</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in report.recent" :key="row.id">
            <td>{{ row.created_at?.slice(0, 19) }}</td>
            <td>
              <RouterLink v-if="row.player_id" :to="`/admin/players/${row.player_id}`">{{ row.player_id }}</RouterLink>
              <span v-else>—</span>
            </td>
            <td>{{ row.caller }}</td>
            <td>{{ row.trigger || row.source }}</td>
            <td>{{ row.modality }}</td>
            <td>{{ row.latency_ms }}</td>
            <td>{{ row.http_status ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
