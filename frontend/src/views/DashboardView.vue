<template>
  <div class="min-h-screen bg-[#0f1117] text-white">
    <!-- Header -->
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center justify-between">
      <h1 class="text-xl font-bold">Androbugger</h1>
      <div class="flex items-center gap-4">
        <RouterLink to="/history" class="text-slate-400 hover:text-white text-sm">History</RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin' || auth.user?.role === 'developer'" to="/plugins" class="text-slate-400 hover:text-white text-sm">Plugins</RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin'" to="/admin" class="text-slate-400 hover:text-white text-sm">Admin</RouterLink>
        <span class="text-slate-500 text-sm">{{ auth.user?.username }}</span>
        <button @click="handleLogout" class="text-sm text-red-400 hover:text-red-300">Logout</button>
      </div>
    </header>

    <main class="p-6 max-w-7xl mx-auto">
      <!-- Connect device -->
      <div class="mb-6 flex gap-3">
        <input
          v-model="connectIP"
          placeholder="Device IP for wireless ADB (e.g. 192.168.1.100)"
          class="flex-1 px-4 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500"
          @keyup.enter="handleConnect"
        />
        <button
          @click="handleConnect"
          :disabled="!connectIP || connecting"
          class="px-5 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm font-medium transition"
        >
          {{ connecting ? 'Connecting…' : 'Connect' }}
        </button>
      </div>

      <!-- Device grid -->
      <div v-if="devicesStore.devices.length" class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <DeviceCard
          v-for="d in devicesStore.devices"
          :key="d.serial"
          :device="d"
          @diagnose="handleDiagnose"
          @disconnect="devicesStore.disconnectDevice"
        />
      </div>

      <div v-else class="text-center text-slate-500 mt-20">
        <p class="text-lg">No devices connected</p>
        <p class="text-sm mt-1">Connect a device via USB or enter an IP address above</p>
      </div>

      <p v-if="connectError" class="mt-3 text-red-400 text-sm">{{ connectError }}</p>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDevicesStore } from '@/stores/devices'
import { useDiagnosticsStore } from '@/stores/diagnostics'
import DeviceCard from '@/components/DeviceCard.vue'

const auth = useAuthStore()
const devicesStore = useDevicesStore()
const diagnostics = useDiagnosticsStore()
const router = useRouter()

const connectIP = ref('')
const connecting = ref(false)
const connectError = ref('')

async function handleConnect() {
  if (!connectIP.value) return
  connecting.value = true
  connectError.value = ''
  try {
    await devicesStore.connectDevice(connectIP.value)
    connectIP.value = ''
  } catch (e: any) {
    connectError.value = e?.data?.detail || 'Connection failed'
  } finally {
    connecting.value = false
  }
}

async function handleDiagnose(serial: string) {
  const sessionId = await diagnostics.startDiagnosis(serial)
  router.push(`/diagnose/${sessionId}`)
}

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>
