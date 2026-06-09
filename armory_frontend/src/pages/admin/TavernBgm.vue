<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import {
  apiGet,
  apiPost,
  type AdminTavernBgmChat,
  type AdminTavernBgmChatsResponse,
  type AdminTavernBgmEventsResponse,
  type AdminTavernBgmOverview,
  type AdminTavernBgmPendingItem,
  type AdminTavernBgmPendingResponse,
  type AdminTavernBgmPlayerPreview,
  type AdminTavernBgmTrack,
  type AdminTavernBgmTracksResponse,
} from '../../api/client'

const overview = ref<AdminTavernBgmOverview | null>(null)
const events = ref<AdminTavernBgmEventsResponse['events']>([])
const pending = ref<AdminTavernBgmPendingItem[]>([])
const chats = ref<AdminTavernBgmChat[]>([])
const chatTotal = ref(0)
const chatQ = ref('')
const chatPage = ref(1)
const selectedChatId = ref<number | null>(null)
const tracks = ref<AdminTavernBgmTrack[]>([])
const playerIdInput = ref('')
const playerPreview = ref<AdminTavernBgmPlayerPreview | null>(null)
const loading = ref(false)
const retryingUid = ref<string | null>(null)
const error = ref('')

const pendingByUid = computed(() => new Set(pending.value.map((p) => p.file_unique_id)))

function parseUidFromDetail(detail: string): string | null {
  const m = detail.match(/uid=(\S+)/)
  return m ? m[1] : null
}

function canRetryEvent(ev: { event: string; detail: string }): boolean {
  if (ev.event !== 'failed') return false
  const uid = parseUidFromDetail(ev.detail)
  return uid != null && pendingByUid.value.has(uid)
}

async function loadOverview() {
  overview.value = await apiGet<AdminTavernBgmOverview>('/admin/tavern-bgm/overview')
}

async function loadEvents() {
  const data = await apiGet<AdminTavernBgmEventsResponse>('/admin/tavern-bgm/events?limit=100')
  events.value = data.events
}

async function loadPending() {
  const data = await apiGet<AdminTavernBgmPendingResponse>('/admin/tavern-bgm/pending?status=failed&limit=100')
  pending.value = data.items
}

async function loadChats() {
  const data = await apiGet<AdminTavernBgmChatsResponse>(
    `/admin/tavern-bgm/chats?q=${encodeURIComponent(chatQ.value)}&page=${chatPage.value}`
  )
  chats.value = data.items
  chatTotal.value = data.total
}

async function loadTracks(chatId: number) {
  selectedChatId.value = chatId
  const data = await apiGet<AdminTavernBgmTracksResponse>(`/admin/tavern-bgm/chats/${chatId}/tracks`)
  tracks.value = data.tracks
}

async function loadPlayerPreview() {
  const pid = Number(playerIdInput.value)
  if (!Number.isFinite(pid) || pid <= 0) {
    error.value = 'Укажите корректный Telegram ID'
    return
  }
  playerPreview.value = await apiGet<AdminTavernBgmPlayerPreview>(
    `/admin/tavern-bgm/player-preview?player_id=${encodeURIComponent(String(pid))}`
  )
}

async function retryCapture(fileUniqueId: string) {
  retryingUid.value = fileUniqueId
  error.value = ''
  try {
    const result = await apiPost<{ ok: boolean; status: string; error?: string; events?: AdminTavernBgmEventsResponse['events'] }>(
      '/admin/tavern-bgm/pending/retry',
      { file_unique_id: fileUniqueId }
    )
    if (result.events) {
      events.value = result.events
    }
    await Promise.all([loadOverview(), loadPending(), loadEvents()])
    if (selectedChatId.value != null) {
      await loadTracks(selectedChatId.value)
    }
    if (!result.ok) {
      error.value = result.error || `Retry failed: ${result.status}`
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    retryingUid.value = null
  }
}

async function refreshAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadOverview(), loadEvents(), loadPending(), loadChats()])
    if (selectedChatId.value != null) {
      await loadTracks(selectedChatId.value)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(refreshAll)
</script>

<template>
  <div>
    <RouterLink to="/admin">← Назад</RouterLink>
    <h1>Tavern BGM — диагностика</h1>
    <nav class="tabs" style="margin: 1rem 0">
      <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
      <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
      <RouterLink to="/admin/tavern-bgm" class="tab">Tavern BGM</RouterLink>
      <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
    </nav>

    <div style="margin: 1rem 0; display: flex; gap: 0.5rem; flex-wrap: wrap">
      <button class="btn" :disabled="loading" @click="refreshAll">{{ loading ? 'Загрузка…' : 'Обновить' }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="overview" class="card" style="margin-bottom: 1rem">
      <h2 style="margin-top: 0">Сводка</h2>
      <div class="stat-grid">
        <div class="stat-item"><div class="label">Треков в БД</div><div class="value">{{ overview.total_tracks }}</div></div>
        <div class="stat-item"><div class="label">Чатов с треками</div><div class="value">{{ overview.chats_with_tracks }}</div></div>
        <div class="stat-item"><div class="label">За 24 ч</div><div class="value">{{ overview.tracks_last_24h }}</div></div>
        <div class="stat-item"><div class="label">Не загружены</div><div class="value">{{ overview.pending_failed_count }}</div></div>
        <div class="stat-item"><div class="label">Файлов нет на диске</div><div class="value">{{ overview.missing_files }}</div></div>
        <div class="stat-item"><div class="label">Событий за час</div><div class="value">{{ overview.events_last_hour }}</div></div>
        <div class="stat-item"><div class="label">Буфер событий</div><div class="value">{{ overview.events_buffer_size }}</div></div>
      </div>
    </section>

    <section class="card" style="margin-bottom: 1rem">
      <h2 style="margin-top: 0">Не загружены</h2>
      <p style="opacity: 0.75; font-size: 0.9rem">
        Записи с failed-захватом. «Повторить» использует сохранённый <code>file_id</code> — re-send в чат не нужен.
        Ссылка Telegram действует ~1 час; позже только повторная отправка MP3.
      </p>
      <table v-if="pending.length">
        <thead>
          <tr>
            <th>uid</th>
            <th>Название</th>
            <th>chat_id</th>
            <th>Размер</th>
            <th>Retry</th>
            <th>Ошибка</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in pending" :key="p.file_unique_id">
            <td><code>{{ p.file_unique_id }}</code></td>
            <td>{{ p.title || p.performer || '—' }}</td>
            <td>{{ p.chat_id }}</td>
            <td>{{ p.file_size ?? '—' }}</td>
            <td>{{ p.retry_count }}</td>
            <td style="max-width: 280px; word-break: break-word">{{ p.last_error || '—' }}</td>
            <td>
              <button
                class="btn secondary"
                type="button"
                :disabled="retryingUid === p.file_unique_id"
                @click="retryCapture(p.file_unique_id)"
              >
                {{ retryingUid === p.file_unique_id ? '…' : 'Повторить' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else style="opacity: 0.75">Нет failed-захватов.</p>
    </section>

    <section class="card" style="margin-bottom: 1rem">
      <h2 style="margin-top: 0">Журнал захвата</h2>
      <p style="opacity: 0.75; font-size: 0.9rem">
        Отправьте MP3 в групповой чат и нажмите «Обновить».
        Нет <code>enqueue</code> — апдейт не дошёл до handler.
        <code>failed</code> с <code>received=0</code> — прокси/Worker не отдаёт body.
        <code>received&gt;0</code> — канал медленный; streaming-download может занять несколько минут.
        Ожидайте цепочку: <code>enqueue</code> → <code>start</code> → <code>download</code> → <code>cached</code>.
      </p>
      <table v-if="events.length">
        <thead>
          <tr>
            <th>Время</th>
            <th>Событие</th>
            <th>chat_id</th>
            <th>player_id</th>
            <th>Детали</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(ev, idx) in events" :key="`${ev.ts}-${idx}`">
            <td><code>{{ ev.ts.slice(11, 19) }}</code></td>
            <td><strong>{{ ev.event }}</strong></td>
            <td>{{ ev.chat_id ?? '—' }}</td>
            <td>{{ ev.player_id ?? '—' }}</td>
            <td style="max-width: 420px; word-break: break-word">{{ ev.detail }}</td>
            <td>
              <button
                v-if="canRetryEvent(ev)"
                class="btn secondary"
                type="button"
                :disabled="retryingUid === parseUidFromDetail(ev.detail)"
                @click="retryCapture(parseUidFromDetail(ev.detail)!)"
              >
                Повторить
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else style="opacity: 0.75">Событий пока нет (отправьте аудио в чат после деплоя).</p>
    </section>

    <section class="card" style="margin-bottom: 1rem">
      <h2 style="margin-top: 0">Чаты</h2>
      <div style="display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap">
        <input v-model="chatQ" type="search" placeholder="Название или chat_id..." @keyup.enter="loadChats()" />
        <button class="btn" @click="loadChats()">Найти</button>
        <span v-if="chatTotal" style="opacity: 0.75">Всего: {{ chatTotal }}</span>
      </div>
      <table v-if="chats.length">
        <thead>
          <tr>
            <th>Чат</th>
            <th>chat_id</th>
            <th>Статус</th>
            <th>Треков</th>
            <th>Последний трек</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in chats" :key="c.chat_id">
            <td>{{ c.title || '—' }}</td>
            <td><code>{{ c.chat_id }}</code></td>
            <td>{{ c.status }}</td>
            <td><strong>{{ c.track_count }}</strong></td>
            <td>{{ c.last_track_at ? c.last_track_at.slice(0, 19) : '—' }}</td>
            <td><button class="btn secondary" type="button" @click="loadTracks(c.chat_id)">Треки</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="selectedChatId != null" class="card" style="margin-bottom: 1rem">
      <h2 style="margin-top: 0">Треки чата {{ selectedChatId }}</h2>
      <table v-if="tracks.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>Название</th>
            <th>Файл</th>
            <th>На диске</th>
            <th>Загружен</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tracks" :key="t.id">
            <td>{{ t.id }}</td>
            <td>{{ t.title || t.performer || '—' }}</td>
            <td><a :href="t.url" target="_blank" rel="noopener">{{ t.relative_path }}</a></td>
            <td>{{ t.file_exists ? 'да' : 'нет' }}</td>
            <td>{{ t.created_at ? t.created_at.slice(0, 19) : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else style="opacity: 0.75">В этом чате нет записей в chat_audio_tracks.</p>
    </section>

    <section class="card">
      <h2 style="margin-top: 0">Player preview</h2>
      <p style="opacity: 0.75; font-size: 0.9rem">Что видит игрок в плеере таверны (пересечение чатов игрока и бота).</p>
      <div style="display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap">
        <input v-model="playerIdInput" type="number" placeholder="Telegram ID игрока" />
        <button class="btn" @click="loadPlayerPreview()">Показать</button>
      </div>
      <div v-if="playerPreview">
        <p><strong>Чаты игрока (raw):</strong> {{ playerPreview.player_group_chats.join(', ') || '—' }}</p>
        <p><strong>∩ активный бот:</strong> {{ playerPreview.bot_active_intersection.join(', ') || '—' }}</p>
        <table v-if="playerPreview.player_view.chats.length">
          <thead>
            <tr><th>Чат</th><th>chat_id</th><th>track_count</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in playerPreview.player_view.chats" :key="c.chat_id">
              <td>{{ c.title }}</td>
              <td><code>{{ c.chat_id }}</code></td>
              <td>{{ c.track_count }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else style="opacity: 0.75">{{ playerPreview.player_view.hint || 'Нет доступных чатов' }}</p>
      </div>
    </section>
  </div>
</template>
