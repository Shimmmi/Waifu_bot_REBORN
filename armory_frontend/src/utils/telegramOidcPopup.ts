const OIDC_ORIGIN = 'https://oauth.telegram.org'
const OIDC_AUTH_URL = `${OIDC_ORIGIN}/auth`

export interface TelegramOidcPopupOptions {
  clientId: number
  redirectUri: string
  origin: string
  requestAccess?: Array<'write' | 'phone'>
  lang?: string
}

export interface TelegramOidcPopupResult {
  id_token: string
}

export class TelegramOidcPopupError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TelegramOidcPopupError'
  }
}

/** Same as official telegram-login.js: current page URL without query/hash. */
export function resolvePageRedirectUri(): string {
  return window.location.origin + window.location.pathname
}

interface AuthResultMessage {
  event?: string
  error?: string
  result?: unknown
  id_token?: string
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    let payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = payload.length % 4
    if (pad) payload += '='.repeat(4 - pad)
    return JSON.parse(atob(payload)) as Record<string, unknown>
  } catch {
    return null
  }
}

function looksLikeJwt(token: string): boolean {
  const parts = token.split('.')
  return parts.length === 3 && parts[0].startsWith('eyJ')
}

function extractIdToken(data: AuthResultMessage): string | null {
  const { result } = data
  if (typeof result === 'string') return result
  if (result && typeof result === 'object' && 'id_token' in result) {
    const nested = (result as { id_token?: unknown }).id_token
    if (typeof nested === 'string') return nested
  }
  if (typeof data.id_token === 'string') return data.id_token
  return null
}

function buildResult(data: AuthResultMessage): TelegramOidcPopupResult {
  if (data.error) {
    throw new TelegramOidcPopupError(String(data.error))
  }
  const idToken = extractIdToken(data)
  if (!idToken) {
    throw new TelegramOidcPopupError('missing id_token')
  }
  if (!looksLikeJwt(idToken)) {
    throw new TelegramOidcPopupError('malformed id_token')
  }
  if (!decodeJwtPayload(idToken)) {
    throw new TelegramOidcPopupError('malformed id_token')
  }
  return { id_token: idToken }
}

function buildScope(requestAccess?: Array<'write' | 'phone'>): string {
  const scope = ['openid', 'profile']
  for (const access of requestAccess ?? ['write']) {
    if (access === 'phone') {
      scope.push('phone')
    } else if (access === 'write') {
      scope.push('telegram:bot_access')
    }
  }
  return scope.join(' ')
}

function buildAuthUrl(options: TelegramOidcPopupOptions): string {
  const params = new URLSearchParams({
    response_type: 'post_message',
    client_id: String(options.clientId),
    redirect_uri: options.redirectUri,
    origin: options.origin,
    scope: buildScope(options.requestAccess),
  })
  if (options.lang) {
    params.set('lang', options.lang)
  }
  return `${OIDC_AUTH_URL}?${params.toString()}`
}

export function openTelegramOidcPopup(options: TelegramOidcPopupOptions): Promise<TelegramOidcPopupResult> {
  const redirectUri = (options.redirectUri || '').trim()
  if (!redirectUri) {
    return Promise.reject(new TelegramOidcPopupError('missing redirect_uri'))
  }

  return new Promise((resolve, reject) => {
    const authUrl = buildAuthUrl({ ...options, redirectUri })
    if (import.meta.env.DEV) {
      console.debug('[Telegram OIDC] auth URL:', authUrl)
    }
    const width = 550
    const height = 650
    const left = Math.max(0, (screen.width - width) / 2) + ((screen as Screen & { availLeft?: number }).availLeft ?? 0)
    const top = Math.max(0, (screen.height - height) / 2) + ((screen as Screen & { availTop?: number }).availTop ?? 0)
    const features = `width=${width},height=${height},left=${left},top=${top},status=0,location=0,menubar=0,toolbar=0`

    let finished = false
    let popup: Window | null = null

    const cleanup = () => {
      window.removeEventListener('message', onMessage)
      if (pollTimer !== null) {
        clearTimeout(pollTimer)
      }
    }

    const finish = (fn: () => void) => {
      if (finished) return
      finished = true
      cleanup()
      fn()
    }

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== OIDC_ORIGIN) return
      if (popup && event.source !== popup) return

      let data: AuthResultMessage
      try {
        data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data
      } catch {
        return
      }

      if (!data || data.event !== 'auth_result') return

      try {
        finish(() => resolve(buildResult(data)))
      } catch (err) {
        finish(() => reject(err))
      }
    }

    window.addEventListener('message', onMessage)

    popup = window.open(authUrl, 'telegram_oidc_login', features)
    if (!popup) {
      cleanup()
      reject(new TelegramOidcPopupError('popup_blocked'))
      return
    }
    popup.focus()

    let pollTimer: ReturnType<typeof setTimeout> | null = null
    const pollClosed = () => {
      if (finished) return
      if (!popup || popup.closed) {
        finish(() => reject(new TelegramOidcPopupError('popup_closed')))
        return
      }
      pollTimer = setTimeout(pollClosed, 200)
    }
    pollClosed()
  })
}
