import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { $fetch } from 'ofetch'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<{ id: string; username: string; role: string; force_password_change: boolean } | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const data = await $fetch('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    token.value = data.token
    user.value = data.user
  }

  async function logout() {
    try {
      await $fetch('/api/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.value}` },
      })
    } finally {
      token.value = null
      user.value = null
    }
  }

  function authHeaders() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  return { token, user, isAuthenticated, login, logout, authHeaders }
})
