<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Firmware Comparison</h1>
    </header>

    <div class="p-6 max-w-6xl mx-auto w-full space-y-6">

      <!-- Input row -->
      <div class="flex gap-3 items-end flex-wrap">
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs text-slate-500 mb-1">Firmware A</label>
          <input v-model="fwA" placeholder="e.g. 2.4.1"
            class="w-full px-3 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs text-slate-500 mb-1">Firmware B</label>
          <input v-model="fwB" placeholder="e.g. 2.5.0"
            class="w-full px-3 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div class="flex-shrink-0">
          <label class="block text-xs text-slate-500 mb-1">Sessions</label>
          <select v-model="limit" class="px-3 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none">
            <option :value="10">Last 10</option>
            <option :value="20">Last 20</option>
            <option :value="50">Last 50</option>
          </select>
        </div>
        <button
          @click="compare"
          :disabled="!fwA.trim() || !fwB.trim() || loading"
          class="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition"
        >
          {{ loading ? 'Comparing…' : 'Compare' }}
        </button>
      </div>

      <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>

      <!-- Results -->
      <div v-if="result" class="space-y-6">

        <!-- Summary cards -->
        <div class="grid grid-cols-2 gap-6">
          <div v-for="stats in [result.firmware_a, result.firmware_b]" :key="stats.firmware"
            class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-4">
            <div class="flex items-center justify-between">
              <h2 class="font-semibold text-lg">FW {{ stats.firmware }}</h2>
              <span class="text-slate-500 text-sm">{{ stats.session_count }} session(s)</span>
            </div>

            <!-- Metrics -->
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="bg-[#0f1117] rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-blue-400">{{ stats.session_count }}</p>
                <p class="text-slate-500 text-xs mt-0.5">Total Sessions</p>
              </div>
              <div class="bg-[#0f1117] rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-green-400">{{ stats.resolved_count }}</p>
                <p class="text-slate-500 text-xs mt-0.5">Resolved</p>
              </div>
              <div class="bg-[#0f1117] rounded-lg p-3 text-center col-span-2">
                <p class="text-2xl font-bold"
                  :class="resolveRate(stats) > 0.7 ? 'text-green-400' : resolveRate(stats) > 0.4 ? 'text-yellow-400' : 'text-red-400'">
                  {{ (resolveRate(stats) * 100).toFixed(0) }}%
                </p>
                <p class="text-slate-500 text-xs mt-0.5">Resolution Rate</p>
              </div>
            </div>

            <!-- Top root causes -->
            <div>
              <p class="text-xs text-slate-500 font-medium mb-2 uppercase tracking-wider">Top Root Causes</p>
              <div v-if="stats.top_root_causes.length" class="space-y-2">
                <div v-for="rc in stats.top_root_causes" :key="rc.cause" class="flex items-center gap-2">
                  <div class="flex-1 min-w-0">
                    <div class="flex justify-between text-xs mb-0.5">
                      <span class="text-slate-300 truncate">{{ rc.cause || '(unknown)' }}</span>
                      <span class="text-slate-500 flex-shrink-0 ml-2">{{ rc.count }}</span>
                    </div>
                    <div class="h-1.5 bg-[#2a2d3e] rounded-full overflow-hidden">
                      <div class="h-full bg-blue-500 rounded-full"
                        :style="{ width: `${(rc.count / stats.session_count) * 100}%` }" />
                    </div>
                  </div>
                </div>
              </div>
              <p v-else class="text-slate-600 text-xs">No resolved sessions to compare</p>
            </div>
          </div>
        </div>

        <!-- Delta analysis -->
        <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5">
          <h3 class="font-semibold mb-4">Delta Analysis</h3>
          <div class="grid grid-cols-3 gap-4 text-sm">
            <!-- Session volume delta -->
            <div class="bg-[#0f1117] rounded-lg p-4 text-center">
              <p class="text-xs text-slate-500 mb-1">Session Volume</p>
              <p class="text-xl font-bold" :class="volumeDelta >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ volumeDelta >= 0 ? '+' : '' }}{{ volumeDelta }}
              </p>
              <p class="text-xs text-slate-600 mt-0.5">{{ result.firmware_a.firmware }} → {{ result.firmware_b.firmware }}</p>
            </div>
            <!-- Resolution rate delta -->
            <div class="bg-[#0f1117] rounded-lg p-4 text-center">
              <p class="text-xs text-slate-500 mb-1">Resolution Rate Δ</p>
              <p class="text-xl font-bold" :class="resolveDelta >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ resolveDelta >= 0 ? '+' : '' }}{{ (resolveDelta * 100).toFixed(1) }}%
              </p>
              <p class="text-xs text-slate-600 mt-0.5">vs previous firmware</p>
            </div>
            <!-- New vs disappeared causes -->
            <div class="bg-[#0f1117] rounded-lg p-4 text-center">
              <p class="text-xs text-slate-500 mb-1">New Root Causes</p>
              <p class="text-xl font-bold text-yellow-400">{{ newCauses.length }}</p>
              <p class="text-xs text-slate-600 mt-0.5">appeared in {{ result.firmware_b.firmware }}</p>
            </div>
          </div>

          <!-- New causes list -->
          <div v-if="newCauses.length" class="mt-4">
            <p class="text-xs text-slate-500 font-medium mb-2">New root causes in {{ result.firmware_b.firmware }}:</p>
            <div class="flex flex-wrap gap-2">
              <span v-for="c in newCauses" :key="c"
                class="px-2 py-0.5 rounded-full text-xs bg-yellow-900 text-yellow-300">
                {{ c }}
              </span>
            </div>
          </div>

          <div v-if="fixedCauses.length" class="mt-3">
            <p class="text-xs text-slate-500 font-medium mb-2">Root causes resolved in {{ result.firmware_b.firmware }}:</p>
            <div class="flex flex-wrap gap-2">
              <span v-for="c in fixedCauses" :key="c"
                class="px-2 py-0.5 rounded-full text-xs bg-green-900 text-green-300">
                {{ c }}
              </span>
            </div>
          </div>
        </div>

        <!-- Sample sessions -->
        <div class="grid grid-cols-2 gap-6">
          <div v-for="stats in [result.firmware_a, result.firmware_b]" :key="`sample-${stats.firmware}`">
            <p class="text-xs text-slate-500 font-medium mb-2 uppercase tracking-wider">
              Recent Sessions — FW {{ stats.firmware }}
            </p>
            <div class="space-y-2">
              <RouterLink
                v-for="s in stats.sessions"
                :key="s.id"
                :to="`/diagnose/${s.id}`"
                class="block bg-[#161925] border border-[#2a2d3e] rounded-lg p-3 hover:border-blue-500 transition text-xs"
              >
                <div class="flex justify-between">
                  <span :class="statusClass(s.status)" class="px-1.5 py-0.5 rounded-full text-[10px]">{{ s.status }}</span>
                  <span class="text-slate-600 font-mono">{{ s.id?.slice(0, 8) }}</span>
                </div>
                <p class="text-slate-400 mt-1 truncate">{{ s.root_cause || '(no root cause)' }}</p>
              </RouterLink>
              <p v-if="!stats.sessions.length" class="text-slate-600 text-xs text-center py-4">No sessions found</p>
            </div>
          </div>
        </div>

      </div>

      <!-- Empty state -->
      <div v-else-if="!loading" class="text-center py-20 text-slate-500">
        <p class="text-lg">Enter two firmware versions above to compare diagnostic data.</p>
        <p class="text-sm mt-1">The comparison includes session volume, resolution rates, and root cause distribution.</p>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const fwA = ref('')
const fwB = ref('')
const limit = ref(20)
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)

async function compare() {
  if (!fwA.value.trim() || !fwB.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await $fetch(
      `/api/diagnostics/compare?firmware_a=${encodeURIComponent(fwA.value)}&firmware_b=${encodeURIComponent(fwB.value)}&limit=${limit.value}`,
      { headers: auth.authHeaders() }
    )
  } catch (e: any) {
    error.value = e?.data?.detail || e.message || 'Comparison failed'
  } finally {
    loading.value = false
  }
}

function resolveRate(stats: any): number {
  if (!stats.session_count) return 0
  return stats.resolved_count / stats.session_count
}

const volumeDelta = computed(() => {
  if (!result.value) return 0
  return result.value.firmware_b.session_count - result.value.firmware_a.session_count
})

const resolveDelta = computed(() => {
  if (!result.value) return 0
  return resolveRate(result.value.firmware_b) - resolveRate(result.value.firmware_a)
})

const newCauses = computed(() => {
  if (!result.value) return []
  const causesA = new Set(result.value.firmware_a.top_root_causes.map((c: any) => c.cause))
  return result.value.firmware_b.top_root_causes
    .map((c: any) => c.cause)
    .filter((c: string) => !causesA.has(c) && c)
})

const fixedCauses = computed(() => {
  if (!result.value) return []
  const causesB = new Set(result.value.firmware_b.top_root_causes.map((c: any) => c.cause))
  return result.value.firmware_a.top_root_causes
    .map((c: any) => c.cause)
    .filter((c: string) => !causesB.has(c) && c)
})

function statusClass(status: string) {
  return {
    running: 'bg-yellow-900 text-yellow-300',
    completed: 'bg-blue-900 text-blue-300',
    resolved: 'bg-green-900 text-green-300',
    failed: 'bg-red-900 text-red-300',
  }[status] || ''
}
</script>
