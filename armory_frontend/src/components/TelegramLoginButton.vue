<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api/client'
import {
  openTelegramOidcPopup,
  resolvePageRedirectUri,
  TelegramOidcPopupError,
} from '../utils/telegramOidcPopup'

const clientId = ref('')
const expectedOrigin = ref('')
const suggestedRedirectUri = ref('')
const redirectUriOverride = ref('')
const loading = ref(true)
const loggingIn = ref(false)
const error = ref('')

const botFatherRedirectUri = computed(() => resolveRedirectUri())

function resolveRedirectUri(): string {
  const fromOverride = redirectUriOverride.value.trim()
  if (fromOverride) return fromOverride
  const fromPage = resolvePageRedirectUri().trim()
  if (fromPage) return fromPage
  return suggestedRedirectUri.value.trim()
}

function parseApiError(err: unknown): string {
  const raw = String(err)
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
    if (Array.isArray(parsed.detail)) {
      return parsed.detail.map((item) => String(item)).join('; ')
    }
  } catch {
    // not JSON — fall through
  }
  return raw
}

function formatPopupError(err: unknown): string {
  if (err instanceof TelegramOidcPopupError) {
    if (err.message === 'popup_blocked') {
      return 'Браузер заблокировал всплывающее окно. Разрешите popup для этого сайта.'
    }
    if (err.message === 'popup_closed') {
      return 'Авторизация отменена'
    }
    if (err.message === 'missing redirect_uri') {
      return 'Не удалось определить redirect_uri. Обновите страницу или откройте /armory/login с основного домена.'
    }
    if (err.message === 'malformed id_token') {
      return 'Telegram вернул некорректный токен. Проверьте Trusted Origins в BotFather и откройте страницу по адресу из настроек.'
    }
    if (/redirect_uri/i.test(err.message)) {
      const uri = botFatherRedirectUri.value
      return `Telegram отклонил redirect_uri. Добавьте ${uri} в BotFather → Bot Settings → Web Login → Redirect URIs (Trusted Origins: ${expectedOrigin.value || window.location.origin}).`
    }
    return err.message
  }
  return parseApiError(err)
}

async function handleLogin() {
  if (!clientId.value || loggingIn.value) return

  const effectiveRedirectUri = resolveRedirectUri()
  if (!effectiveRedirectUri) {
    error.value = 'Не удалось определить redirect_uri для входа через Telegram.'
    return
  }

  error.value = ''

  const pageOrigin = window.location.origin.replace(/\/$/, '')
  const expected = expectedOrigin.value.replace(/\/$/, '')
  if (expected && pageOrigin !== expected) {
    error.value = `Откройте Armory по адресу ${expected} (сейчас: ${pageOrigin})`
    return
  }

  loggingIn.value = true
  try {
    const result = await openTelegramOidcPopup({
      clientId: Number(clientId.value),
      redirectUri: effectiveRedirectUri,
      origin: expected || pageOrigin,
      requestAccess: ['write'],
    })
    await apiPost('/auth/telegram', { id_token: result.id_token })
    window.location.href = '/armory/'
  } catch (e) {
    error.value = formatPopupError(e)
  } finally {
    loggingIn.value = false
  }
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  if (params.get('error') === 'deprecated_callback') {
    error.value = 'Старый способ входа больше не поддерживается. Нажмите кнопку ниже.'
  }
  try {
    const data = await apiGet<{
      client_id: string
      origin: string
      suggested_redirect_uri?: string
      redirect_uri?: string
      redirect_uri_override?: string
    }>('/auth/login-url')
    clientId.value = data.client_id
    expectedOrigin.value = data.origin.replace(/\/$/, '')
    suggestedRedirectUri.value = (data.suggested_redirect_uri || data.redirect_uri || '').trim()
    redirectUriOverride.value = (data.redirect_uri_override || '').trim()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="card">
    <h1>Вход через Telegram</h1>
    <p style="color: var(--muted); margin: 1rem 0">
      Авторизуйтесь, чтобы видеть полный инвентарь, историю и приватные данные.
    </p>
    <p v-if="loading" style="color: var(--muted)">Загрузка...</p>
    <template v-else>
      <p v-if="error" class="error">{{ error }}</p>
      <button
        v-if="clientId"
        type="button"
        class="btn"
        :disabled="loggingIn"
        @click="handleLogin"
      >
        {{ loggingIn ? 'Ожидание Telegram...' : 'Войти через Telegram' }}
      </button>
      <p
        v-if="clientId && botFatherRedirectUri"
        style="margin-top: 1rem; font-size: 0.85rem; color: var(--muted)"
      >
        Redirect URI для BotFather (Web Login → Redirect URIs):
        <code style="word-break: break-all">{{ botFatherRedirectUri }}</code>
      </p>
    </template>
    <p style="margin-top: 1rem; font-size: 0.85rem; color: var(--muted)">
      Откроется всплывающее окно Telegram. Если оно не появляется — разрешите popup или попробуйте другую сеть.
    </p>
  </div>
</template>
