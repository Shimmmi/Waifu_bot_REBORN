import { ref } from 'vue'
import { apiPostQuery, type ArmoryItem, type ItemArtGenerateResponse } from '../api/client'
import { itemArtTierNormalized, itemDisplayName } from '../utils/items'

const busy = ref(false)

const ERROR_MESSAGES: Record<string, string> = {
  item_art_pillow_unavailable: 'Генерация недоступна (Pillow)',
  item_art_generation_failed: 'Не удалось сгенерировать иконку',
  item_art_write_failed: 'Не удалось сохранить файл',
  item_art_db_failed: 'Ошибка записи в БД',
  invalid_art_key: 'Некорректный art_key',
  invalid_weapon_type: 'Некорректный тип оружия',
}

function parseErrorDetail(err: unknown): string {
  const raw = String(err)
  try {
    const parsed = JSON.parse(raw) as { detail?: string | { msg?: string }[] }
    const detail = parsed.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  } catch {
    /* not JSON */
  }
  return raw
}

export function itemArtGenerateErrorMessage(err: unknown): string {
  const detail = parseErrorDetail(err)
  return ERROR_MESSAGES[detail] ?? detail
}

export function cacheBustUrl(url: string): string {
  const base = String(url || '').trim()
  if (!base) return ''
  try {
    const u = new URL(base, window.location.origin)
    u.searchParams.set('v', String(Date.now()))
    return u.pathname + u.search + u.hash
  } catch {
    const clean = base.split('?')[0]
    return `${clean}?v=${Date.now()}`
  }
}

export function useItemArtGenerate() {
  async function generateItemArt(item: ArmoryItem): Promise<string | null> {
    const artKey = String(item.art_key || '').trim()
    if (!artKey || busy.value) return null

    busy.value = true
    document.body.classList.add('item-art-gen-busy')
    try {
      const tier = itemArtTierNormalized(item)
      const payload = await apiPostQuery<ItemArtGenerateResponse>('/admin/item-art/generate', {
        art_key: artKey,
        tier,
        weapon_type: item.weapon_type,
        display_label: itemDisplayName(item),
      })
      const url = String(payload?.image_url || '').trim()
      return url ? cacheBustUrl(url) : null
    } finally {
      busy.value = false
      document.body.classList.remove('item-art-gen-busy')
    }
  }

  return { busy, generateItemArt, cacheBustUrl, itemArtGenerateErrorMessage }
}
