<template>
  <div class="min-h-screen bg-[#0f1117] text-white p-6">
    <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
    <h1 class="text-2xl font-bold mt-4 mb-6">Diagnostic History</h1>

    <div class="mb-4 flex gap-3">
      <input v-model="query" @keyup.enter="search" placeholder="Search…"
        class="flex-1 px-4 py-2 rounded-lg bg-[#1a1d2e] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
      <button @click="search" class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm">Search</button>
    </div>

    <div class="rounded-xl border border-[#2a2d3e] bg-[#1a1d2e] overflow-hidden">
      <table class="w-full text-sm">
        <thead class="border-b border-[#2a2d3e] text-slate-400">
          <tr>
            <th class="px-4 py-3 text-left">Date</th>
            <th class="px-4 py-3 text-left">Device</th>
            <th class="px-4 py-3 text-left">Firmware</th>
            <th class="px-4 py-3 text-left">Status</th>
            <th class="px-4 py-3 text-left">Root Cause</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id"
            @click="$router.push(`/diagnose/${s.id}`)"
            class="border-b border-[#2a2d3e] hover:bg-[#222540] cursor-pointer">
            <td class="px-4 py-3 text-slate-400 text-xs">{{ s.started_at?.slice(0,16).replace('T',' ') }}</td>
            <td class="px-4 py-3 font-mono text-xs">{{ s.device_serial }}</td>
            <td class="px-4 py-3 text-slate-400 text-xs">{{ s.firmware_version ?? '—' }}</td>
            <td class="px-4 py-3">
              <span :class="statusClass(s.status)" class="px-2 py-0.5 rounded-full text-xs">{{ s.status }}</span>
            </td>
            <td class="px-4 py-3 text-slate-400 text-xs truncate max-w-xs">{{ s.root_cause ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!sessions.length" class="text-slate-500 text-sm text-center py-10">No sessions found</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const sessions = ref<any[]>([])
const query = ref('')

async function fetchHistory() {
  const data = await $fetch('/api/diagnostics/history', { headers: auth.authHeaders() })
  sessions.value = data.sessions
}

async function search() {
  if (!query.value.trim()) return fetchHistory()
  const data = await $fetch(`/api/diagnostics/search?q=${encodeURIComponent(query.value)}`, { headers: auth.authHeaders() })
  sessions.value = data.sessions
}

function statusClass(s: string) {
  return { running: 'bg-yellow-900 text-yellow-300', completed: 'bg-blue-900 text-blue-300',
           resolved: 'bg-green-900 text-green-300', failed: 'bg-red-900 text-red-300' }[s] ?? ''
}

onMounted(fetchHistory)
</script>
