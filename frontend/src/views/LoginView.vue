<template>
  <div class="min-h-screen flex items-center justify-center bg-[#0f1117]">
    <div class="w-full max-w-md p-8 rounded-2xl border border-[#2a2d3e] bg-[#1a1d2e] shadow-2xl">
      <div class="mb-8 text-center">
        <h1 class="text-3xl font-bold text-white tracking-tight">Androbugger</h1>
        <p class="text-slate-400 mt-1 text-sm">IFP Diagnostic Platform</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm text-slate-300 mb-1">Username</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            class="w-full px-4 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white focus:outline-none focus:border-blue-500"
            required
          />
        </div>
        <div>
          <label class="block text-sm text-slate-300 mb-1">Password</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            class="w-full px-4 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white focus:outline-none focus:border-blue-500"
            required
          />
        </div>

        <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold transition"
        >
          {{ loading ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDevicesStore } from '@/stores/devices'

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()
const devicesStore = useDevicesStore()

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    devicesStore.connectWebSocket()
    router.push('/')
  } catch {
    error.value = 'Invalid credentials'
  } finally {
    loading.value = false
  }
}
</script>
