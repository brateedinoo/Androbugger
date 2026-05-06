<template>
  <div class="min-h-screen bg-[#0f1117] text-white">
    <!-- Header -->
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center justify-between">
      <h1 class="text-xl font-bold">Androbugger</h1>
      <div class="flex items-center gap-4">
        <RouterLink to="/history" class="text-slate-400 hover:text-white text-sm">History</RouterLink>
        <RouterLink to="/compare" class="text-slate-400 hover:text-white text-sm">Compare</RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin' || auth.user?.role === 'developer'" to="/plugins" class="text-slate-400 hover:text-white text-sm">Plugins</RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin'" to="/admin" class="text-slate-400 hover:text-white text-sm">Admin</RouterLink>
        <span class="text-slate-500 text-sm">{{ auth.user?.username }}</span>
        <button @click="handleLogout" class="text-sm text-red-400 hover:text-red-300">Logout</button>
      </div>
    </header>

    <main class="p-6 max-w-7xl mx-auto space-y-6">

      <!-- Fleet stats bar -->
      <div v-if="devicesStore.devices.length" class="grid grid-cols-4 gap-3">
        <div v-for="stat in fleetStats" :key="stat.label"
          class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4">
          <p class="text-2xl font-bold" :class="stat.color">{{ stat.value }}</p>
          <p class="text-slate-500 text-xs mt-0.5">{{ stat.label }}</p>
        </div>
      </div>

      <!-- Connect + actions bar -->
      <div class="flex gap-3 flex-wrap">
        <input
          v-model="connectIP"
          placeholder="Device IP for wireless ADB (e.g. 192.168.1.100)"
          class="flex-1 min-w-0 px-4 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500"
          @keyup.enter="handleConnect"
        />
        <button
          @click="handleConnect"
          :disabled="!connectIP || connecting"
          class="px-5 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm font-medium transition"
        >
          {{ connecting ? 'Connecting…' : 'Connect' }}
        </button>

        <!-- Batch actions (shown when devices are selected) -->
        <template v-if="selectedSerials.length">
          <button
            @click="handleBatchDiagnose"
            :disabled="batchLoading"
            class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition"
          >
            {{ batchLoading ? 'Starting…' : `Diagnose ${selectedSerials.length} device(s)` }}
          </button>
          <button
            @click="selectedSerials = []"
            class="px-4 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 hover:text-slate-200 text-sm transition"
          >
            Deselect all
          </button>
        </template>
      </div>

      <p v-if="connectError" class="text-red-400 text-sm">{{ connectError }}</p>

      <!-- Outlier alert -->
      <div v-if="outlierDevices.length" class="bg-red-950/30 border border-red-800 rounded-xl p-4 flex items-start gap-3">
        <span class="text-red-400 text-lg flex-shrink-0">⚠</span>
        <div>
          <p class="text-red-300 text-sm font-medium">High failure rate detected</p>
          <p class="text-red-400 text-xs mt-0.5">
            {{ outlierDevices.map(s => devicesStore.deviceMap[s]?.model || s).join(', ') }}
            — showing above-average failure rates vs fleet baseline.
          </p>
        </div>
      </div>

      <!-- No devices -->
      <div v-if="!devicesStore.devices.length" class="text-center text-slate-500 mt-20">
        <p class="text-lg">No devices connected</p>
        <p class="text-sm mt-1">Connect a device via USB or enter an IP address above</p>
      </div>

      <!-- Firmware groups view -->
      <div v-else>
        <!-- View toggle -->
        <div class="flex items-center gap-3 mb-4">
          <span class="text-slate-500 text-sm">Group by:</span>
          <button
            v-for="v in views"
            :key="v.id"
            @click="groupView = v.id"
            :class="['px-3 py-1 rounded-md text-xs font-medium transition-colors border',
              groupView === v.id
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-[#1e2130] border-[#2a2d3e] text-slate-400 hover:border-blue-500']"
          >
            {{ v.label }}
          </button>
          <button
            v-if="devicesStore.devices.length > 1"
            @click="toggleSelectAll"
            class="ml-auto text-xs text-slate-500 hover:text-slate-300 transition"
          >
            {{ selectedSerials.length === devicesStore.devices.length ? 'Deselect all' : 'Select all' }}
          </button>
        </div>

        <!-- Flat grid -->
        <div v-if="groupView === 'none'" class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <DeviceCard
            v-for="d in devicesStore.devices"
            :key="d.serial"
            :device="d"
            :health="healthMap[d.serial]"
            :health-loading="healthLoading"
            :selected="selectedSerials.includes(d.serial)"
            @diagnose="handleDiagnose"
            @disconnect="devicesStore.disconnectDevice"
            @select="toggleSelect"
          />
        </div>

        <!-- Grouped by firmware -->
        <div v-else class="space-y-6">
          <div v-for="(group, fw) in firmwareGroups" :key="fw">
            <div class="flex items-center gap-3 mb-3">
              <h2 class="text-sm font-semibold text-slate-300">FW {{ fw }}</h2>
              <span class="text-xs text-slate-600">{{ group.length }} device(s)</span>
              <div v-if="outlierCountForFw(String(fw))" class="text-xs px-1.5 py-0.5 rounded bg-red-900 text-red-300">
                {{ outlierCountForFw(String(fw)) }} outlier(s)
              </div>
            </div>
            <div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <DeviceCard
                v-for="d in group"
                :key="d.serial"
                :device="d"
                :health="healthMap[d.serial]"
                :health-loading="healthLoading"
                :selected="selectedSerials.includes(d.serial)"
                @diagnose="handleDiagnose"
                @disconnect="devicesStore.disconnectDevice"
                @select="toggleSelect"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Batch results toast -->
      <div v-if="batchResults.length" class="fixed bottom-6 right-6 bg-[#1e2130] border border-[#2a2d3e] rounded-xl p-4 max-w-sm shadow-xl">
        <p class="text-sm font-medium mb-2">Batch diagnosis started</p>
        <ul class="space-y-1">
          <li v-for="r in batchResults" :key="r.serial" class="text-xs flex justify-between gap-4">
            <span class="text-slate-400 font-mono">{{ r.serial }}</span>
            <RouterLink v-if="r.session_id" :to="`/diagnose/${r.session_id}`" class="text-blue-400 hover:underline">View →</RouterLink>
            <span v-else class="text-red-400">{{ r.error }}</span>
          </li>
        </ul>
        <button @click="batchResults = []" class="mt-3 text-xs text-slate-500 hover:text-slate-300">Dismiss</button>
      </div>

    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { $fetch } from 'ofetch'
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
const selectedSerials = ref<string[]>([])
const batchLoading = ref(false)
const batchResults = ref<Array<{ serial: string; session_id?: string; error?: string }>>([])
const healthMap = ref<Record<string, any>>({})
const healthLoading = ref(false)
const groupView = ref<'none' | 'firmware'>('none')

const views = [
  { id: 'none', label: 'All Devices' },
  { id: 'firmware', label: 'Firmware' },
]

const firmwareGroups = computed(() => {
  const groups: Record<string, typeof devicesStore.devices> = {}
  for (const d of devicesStore.devices) {
    const fw = d.firmware_version || 'Unknown'
    groups[fw] = groups[fw] || []
    groups[fw].push(d)
  }
  return groups
})

const outlierDevices = computed(() =>
  Object.entries(healthMap.value)
    .filter(([, h]) => h?.is_outlier)
    .map(([serial]) => serial)
)

const fleetStats = computed(() => {
  const total = devicesStore.devices.length
  const outliers = outlierDevices.value.length
  const health = Object.values(healthMap.value)
  const failures7d = health.reduce((s: number, h: any) => s + (h?.failures_7d || 0), 0)
  const sessions7d = health.reduce((s: number, h: any) => s + (h?.sessions_7d || 0), 0)
  return [
    { label: 'Connected Devices', value: total, color: 'text-white' },
    { label: '7d Diagnoses', value: sessions7d, color: 'text-blue-400' },
    { label: '7d Failures', value: failures7d, color: failures7d ? 'text-red-400' : 'text-slate-400' },
    { label: 'Outliers', value: outliers, color: outliers ? 'text-yellow-400' : 'text-slate-400' },
  ]
})

function outlierCountForFw(fw: string) {
  return devicesStore.devices
    .filter(d => (d.firmware_version || 'Unknown') === fw)
    .filter(d => healthMap.value[d.serial]?.is_outlier).length
}

function toggleSelect(serial: string) {
  const idx = selectedSerials.value.indexOf(serial)
  if (idx >= 0) selectedSerials.value.splice(idx, 1)
  else selectedSerials.value.push(serial)
}

function toggleSelectAll() {
  if (selectedSerials.value.length === devicesStore.devices.length) {
    selectedSerials.value = []
  } else {
    selectedSerials.value = devicesStore.devices.map(d => d.serial)
  }
}

async function loadHealth() {
  if (!devicesStore.devices.length) return
  healthLoading.value = true
  try {
    const data = await $fetch('/api/devices/health', { headers: auth.authHeaders() })
    healthMap.value = data.health
  } catch {
    // best-effort
  } finally {
    healthLoading.value = false
  }
}

async function handleConnect() {
  if (!connectIP.value) return
  connecting.value = true
  connectError.value = ''
  try {
    await devicesStore.connectDevice(connectIP.value)
    connectIP.value = ''
    await loadHealth()
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

async function handleBatchDiagnose() {
  if (!selectedSerials.value.length) return
  batchLoading.value = true
  try {
    const data = await $fetch('/api/diagnostics/batch', {
      method: 'POST',
      body: { device_serials: selectedSerials.value },
      headers: auth.authHeaders(),
    })
    batchResults.value = data.sessions
    selectedSerials.value = []
  } catch (e: any) {
    connectError.value = e?.data?.detail || 'Batch diagnose failed'
  } finally {
    batchLoading.value = false
  }
}

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

onMounted(async () => {
  await loadHealth()
})
</script>
