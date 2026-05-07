<template>
  <div class="min-h-screen bg-[#0f1117] text-white">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-xl font-bold">Analytics</h1>
    </header>

    <main class="p-6 max-w-6xl mx-auto space-y-8">
      <!-- Overview cards -->
      <section>
        <h2 class="text-lg font-semibold mb-4">Overview</h2>
        <div v-if="overviewLoading" class="text-slate-500">Loading…</div>
        <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-[#1a1d2e] rounded-xl p-4">
            <p class="text-slate-400 text-sm">Total Sessions</p>
            <p class="text-2xl font-bold mt-1">{{ overview.total_sessions ?? 0 }}</p>
          </div>
          <div class="bg-[#1a1d2e] rounded-xl p-4">
            <p class="text-slate-400 text-sm">Resolved %</p>
            <p class="text-2xl font-bold mt-1 text-green-400">{{ overview.resolved_pct ?? 0 }}%</p>
          </div>
          <div class="bg-[#1a1d2e] rounded-xl p-4">
            <p class="text-slate-400 text-sm">Avg TTR</p>
            <p class="text-2xl font-bold mt-1">{{ fmtTtr(overview.avg_ttr_seconds) }}</p>
          </div>
          <div class="bg-[#1a1d2e] rounded-xl p-4">
            <p class="text-slate-400 text-sm">Top Failure</p>
            <p class="text-sm font-semibold mt-1 text-amber-400 truncate" :title="overview.top_root_causes?.[0]?.root_cause">
              {{ overview.top_root_causes?.[0]?.root_cause ?? 'None' }}
            </p>
          </div>
        </div>
      </section>

      <!-- Trend chart -->
      <section>
        <div class="flex items-center gap-4 mb-4">
          <h2 class="text-lg font-semibold">Daily Trend</h2>
          <select v-model="trendDays" @change="loadTrends"
            class="bg-[#1a1d2e] border border-[#2a2d3e] rounded px-2 py-1 text-sm">
            <option :value="7">7 days</option>
            <option :value="30">30 days</option>
            <option :value="90">90 days</option>
          </select>
        </div>
        <div v-if="trendsLoading" class="text-slate-500">Loading…</div>
        <div v-else-if="trends.length === 0" class="text-slate-500 text-sm">No data yet.</div>
        <div v-else class="bg-[#1a1d2e] rounded-xl p-4 overflow-x-auto">
          <div class="flex items-end gap-1 h-32 min-w-max">
            <div
              v-for="d in trends"
              :key="d.date"
              class="flex flex-col items-center gap-1 w-8"
              :title="`${d.date}: ${d.total} sessions, ${d.failed} failed`"
            >
              <div class="w-6 rounded-t"
                :style="`height: ${barHeight(d.total)}px; background: ${d.fail_rate > 50 ? '#ef4444' : d.fail_rate > 20 ? '#f59e0b' : '#22c55e'}`">
              </div>
              <span class="text-[9px] text-slate-500 rotate-90 origin-left w-6">{{ d.date.slice(5) }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Failure patterns -->
      <section>
        <h2 class="text-lg font-semibold mb-4">Recurring Failure Patterns</h2>
        <div v-if="patternsLoading" class="text-slate-500">Loading…</div>
        <div v-else-if="patterns.length === 0" class="text-slate-500 text-sm">No patterns detected yet.</div>
        <div v-else class="bg-[#1a1d2e] rounded-xl overflow-hidden">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-[#2a2d3e] text-slate-400">
                <th class="text-left px-4 py-2">Root Cause</th>
                <th class="text-right px-4 py-2">Count</th>
                <th class="text-right px-4 py-2">Devices</th>
                <th class="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in patterns" :key="p.example_session_id"
                class="border-b border-[#2a2d3e] hover:bg-[#22253a]">
                <td class="px-4 py-2 max-w-xs truncate" :title="p.root_cause">{{ p.root_cause }}</td>
                <td class="px-4 py-2 text-right">
                  <span class="bg-red-900/40 text-red-400 px-2 py-0.5 rounded text-xs">{{ p.count }}</span>
                </td>
                <td class="px-4 py-2 text-right text-slate-400">{{ p.device_count }}</td>
                <td class="px-4 py-2 text-right">
                  <RouterLink v-if="p.example_session_id" :to="`/diagnose/${p.example_session_id}`"
                    class="text-blue-400 hover:underline text-xs">Example →</RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Top root causes from overview -->
      <section>
        <h2 class="text-lg font-semibold mb-4">Top Root Causes</h2>
        <div v-if="overviewLoading" class="text-slate-500">Loading…</div>
        <div v-else-if="!overview.top_root_causes?.length" class="text-slate-500 text-sm">No data yet.</div>
        <div v-else class="space-y-2">
          <div v-for="rc in overview.top_root_causes" :key="rc.root_cause" class="flex items-center gap-3">
            <div class="flex-1 bg-[#1a1d2e] rounded-full h-3 overflow-hidden">
              <div class="h-3 bg-blue-500 rounded-full"
                :style="`width: ${(rc.count / overview.top_root_causes[0].count) * 100}%`">
              </div>
            </div>
            <span class="text-sm text-slate-300 truncate max-w-xs" :title="rc.root_cause">{{ rc.root_cause }}</span>
            <span class="text-slate-500 text-sm w-8 text-right">{{ rc.count }}</span>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const overview = ref<any>({})
const overviewLoading = ref(true)
const trends = ref<any[]>([])
const trendsLoading = ref(true)
const trendDays = ref(30)
const patterns = ref<any[]>([])
const patternsLoading = ref(true)

async function apiFetch(path: string) {
  const res = await fetch(path, {
    headers: { Authorization: `Bearer ${auth.token}` },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function loadOverview() {
  overviewLoading.value = true
  try {
    overview.value = await apiFetch('/api/analytics/overview')
  } catch { overview.value = {} }
  finally { overviewLoading.value = false }
}

async function loadTrends() {
  trendsLoading.value = true
  try {
    const data = await apiFetch(`/api/analytics/trends?days=${trendDays.value}`)
    trends.value = data.data ?? []
  } catch { trends.value = [] }
  finally { trendsLoading.value = false }
}

async function loadPatterns() {
  patternsLoading.value = true
  try {
    const data = await apiFetch('/api/analytics/failure-patterns')
    patterns.value = data.patterns ?? []
  } catch { patterns.value = [] }
  finally { patternsLoading.value = false }
}

function fmtTtr(seconds: number): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

function barHeight(count: number): number {
  const maxCount = Math.max(...trends.value.map((d: any) => d.total), 1)
  return Math.max(4, Math.round((count / maxCount) * 100))
}

onMounted(() => {
  loadOverview()
  loadTrends()
  loadPatterns()
})
</script>
