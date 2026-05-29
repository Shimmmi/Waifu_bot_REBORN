import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost, type AuthMe, type AuthSession } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthMe | null>(null)
  const loading = ref(false)

  async function fetchMe() {
    loading.value = true
    try {
      const data = await apiGet<AuthSession>('/auth/me')
      user.value = data.authenticated ? data : null
    } catch {
      user.value = null
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    await apiPost('/auth/logout')
    user.value = null
  }

  return { user, loading, fetchMe, logout }
})
