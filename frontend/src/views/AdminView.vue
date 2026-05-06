<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Admin</h1>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar tabs -->
      <nav class="w-48 border-r border-[#2a2d3e] p-3 space-y-1 flex-shrink-0">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="['w-full text-left px-3 py-2 rounded-lg text-sm transition',
            activeTab === tab.id
              ? 'bg-blue-600 text-white font-medium'
              : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e2130]']"
        >
          {{ tab.label }}
        </button>
      </nav>

      <!-- Content area -->
      <div class="flex-1 overflow-y-auto p-6">

        <!-- Stats tab -->
        <div v-if="activeTab === 'stats'" class="space-y-6 max-w-3xl">
          <h2 class="text-base font-semibold">System Overview</h2>
          <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div v-for="s in statCards" :key="s.label" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 text-center">
              <p class="text-2xl font-bold text-blue-400">{{ s.value }}</p>
              <p class="text-slate-500 text-xs mt-0.5">{{ s.label }}</p>
            </div>
          </div>

          <!-- Activity chart (sparkline via bars) -->
          <div v-if="stats?.activity_7d?.length" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5">
            <h3 class="text-sm font-medium text-slate-300 mb-4">Activity (Last 7 Days)</h3>
            <div class="flex items-end gap-1.5 h-20">
              <div
                v-for="day in stats.activity_7d"
                :key="day.day"
                class="flex-1 bg-blue-500 rounded-t"
                :style="{ height: `${Math.max(8, (day.count / maxActivity) * 100)}%` }"
                :title="`${day.day}: ${day.count} events`"
              />
            </div>
            <div class="flex justify-between text-xs text-slate-600 mt-1">
              <span>{{ stats.activity_7d[0]?.day?.slice(5) }}</span>
              <span>{{ stats.activity_7d[stats.activity_7d.length - 1]?.day?.slice(5) }}</span>
            </div>
          </div>
        </div>

        <!-- Users tab -->
        <div v-if="activeTab === 'users'" class="space-y-5 max-w-3xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold">Users</h2>
            <button @click="showCreateUser = !showCreateUser"
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition">
              + New User
            </button>
          </div>

          <!-- Create user form -->
          <div v-if="showCreateUser" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-3">
            <h3 class="text-sm font-medium text-slate-300">Create User</h3>
            <div class="grid grid-cols-3 gap-3">
              <input v-model="newUser.username" placeholder="Username"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              <input v-model="newUser.password" type="password" placeholder="Password"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              <select v-model="newUser.role"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500">
                <option v-for="r in roles" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
            <div class="flex gap-2">
              <button @click="createUser" :disabled="!newUser.username || !newUser.password || userLoading"
                class="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm transition">
                {{ userLoading ? 'Creating…' : 'Create' }}
              </button>
              <button @click="showCreateUser = false" class="px-4 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 text-sm hover:text-slate-200 transition">Cancel</button>
            </div>
            <p v-if="userError" class="text-red-400 text-sm">{{ userError }}</p>
          </div>

          <!-- User table -->
          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl overflow-hidden">
            <table class="w-full text-sm">
              <thead class="border-b border-[#2a2d3e] text-slate-400 text-xs">
                <tr>
                  <th class="px-4 py-3 text-left">Username</th>
                  <th class="px-4 py-3 text-left">Role</th>
                  <th class="px-4 py-3 text-left">Last Login</th>
                  <th class="px-4 py-3 text-left">Created</th>
                  <th class="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in users" :key="u.id" class="border-b border-[#2a2d3e] last:border-0">
                  <td class="px-4 py-3 font-medium">{{ u.username }}</td>
                  <td class="px-4 py-3">
                    <select :value="u.role" @change="changeRole(u.id, ($event.target as HTMLSelectElement).value)"
                      class="bg-transparent border border-[#2a2d3e] rounded px-2 py-0.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500">
                      <option v-for="r in roles" :key="r" :value="r">{{ r }}</option>
                    </select>
                  </td>
                  <td class="px-4 py-3 text-slate-400 text-xs">{{ u.last_login?.slice(0, 16).replace('T', ' ') || '—' }}</td>
                  <td class="px-4 py-3 text-slate-400 text-xs">{{ u.created_at?.slice(0, 10) }}</td>
                  <td class="px-4 py-3 text-right">
                    <button v-if="u.id !== currentUserId" @click="deleteUser(u.id)"
                      class="text-xs text-red-500 hover:text-red-300 transition">Delete</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Audit log tab -->
        <div v-if="activeTab === 'audit'" class="space-y-4 max-w-5xl">
          <div class="flex items-center gap-3 flex-wrap">
            <h2 class="text-base font-semibold">Audit Log</h2>
            <div class="flex gap-2 ml-auto flex-wrap">
              <input v-model="auditFilters.action" @keyup.enter="loadAudit" placeholder="Filter action…"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none focus:border-blue-500 w-36" />
              <select v-model="auditFilters.severity" @change="loadAudit"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none">
                <option value="">All severity</option>
                <option>info</option><option>warning</option><option>error</option>
              </select>
              <select v-model="auditFilters.days" @change="loadAudit"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none">
                <option :value="7">Last 7 days</option>
                <option :value="30">Last 30 days</option>
                <option :value="90">Last 90 days</option>
              </select>
              <button @click="exportAudit"
                class="px-3 py-1.5 rounded-lg border border-[#2a2d3e] text-slate-400 hover:text-slate-200 text-xs transition">
                ↓ CSV
              </button>
              <button @click="pruneAudit"
                class="px-3 py-1.5 rounded-lg border border-red-800 text-red-400 hover:text-red-300 text-xs transition">
                Prune old
              </button>
            </div>
          </div>

          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl overflow-hidden">
            <table class="w-full text-xs font-mono">
              <thead class="border-b border-[#2a2d3e] text-slate-500">
                <tr>
                  <th class="px-3 py-2.5 text-left">Time</th>
                  <th class="px-3 py-2.5 text-left">Action</th>
                  <th class="px-3 py-2.5 text-left">Severity</th>
                  <th class="px-3 py-2.5 text-left">Device</th>
                  <th class="px-3 py-2.5 text-left">Detail</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in auditEntries" :key="e.id" class="border-b border-[#2a2d3e] last:border-0 hover:bg-[#1e2130]">
                  <td class="px-3 py-2 text-slate-500 whitespace-nowrap">{{ e.timestamp?.slice(0, 19).replace('T', ' ') }}</td>
                  <td class="px-3 py-2 text-slate-300">{{ e.action }}</td>
                  <td class="px-3 py-2">
                    <span :class="severityBadge(e.severity)" class="px-1.5 py-0.5 rounded text-[10px]">{{ e.severity }}</span>
                  </td>
                  <td class="px-3 py-2 text-slate-500 max-w-[120px] truncate">{{ e.device_serial || '—' }}</td>
                  <td class="px-3 py-2 text-slate-500 max-w-[240px] truncate">{{ formatDetail(e.detail) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-if="!auditEntries.length && !auditLoading" class="text-slate-500 text-sm text-center py-8">No entries found</p>
          </div>

          <!-- Pagination -->
          <div class="flex items-center justify-between text-xs text-slate-500">
            <span>{{ auditTotal }} total entries</span>
            <div class="flex gap-2">
              <button @click="auditPage = Math.max(1, auditPage - 1); loadAudit()" :disabled="auditPage <= 1"
                class="px-3 py-1 rounded border border-[#2a2d3e] disabled:opacity-40 hover:border-blue-500 transition">← Prev</button>
              <span class="px-3 py-1">Page {{ auditPage }}</span>
              <button @click="auditPage++; loadAudit()" :disabled="auditEntries.length < auditPerPage"
                class="px-3 py-1 rounded border border-[#2a2d3e] disabled:opacity-40 hover:border-blue-500 transition">Next →</button>
            </div>
          </div>
        </div>

        <!-- LLM providers tab -->
        <div v-if="activeTab === 'llm'" class="space-y-5 max-w-2xl">
          <h2 class="text-base font-semibold">LLM Providers</h2>
          <div class="space-y-3">
            <div v-for="p in providers" :key="p.id"
              class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 flex items-center justify-between">
              <div>
                <p class="font-medium text-sm">{{ p.name }}</p>
                <p class="text-slate-500 text-xs mt-0.5">{{ p.type }}</p>
              </div>
              <label class="flex items-center gap-2 cursor-pointer">
                <span class="text-xs text-slate-400">{{ p.enabled ? 'Enabled' : 'Disabled' }}</span>
                <div @click="toggleProvider(p)"
                  :class="['w-10 h-5 rounded-full transition-colors relative cursor-pointer',
                    p.enabled ? 'bg-blue-600' : 'bg-[#2a2d3e]']">
                  <div :class="['w-4 h-4 bg-white rounded-full absolute top-0.5 transition-transform',
                    p.enabled ? 'translate-x-5' : 'translate-x-0.5']" />
                </div>
              </label>
            </div>
            <p v-if="!providers.length" class="text-slate-500 text-sm">No providers configured</p>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const tabs = [
  { id: 'stats', label: 'Overview' },
  { id: 'users', label: 'Users' },
  { id: 'audit', label: 'Audit Log' },
  { id: 'llm', label: 'LLM Providers' },
]
const activeTab = ref('stats')
const currentUserId = computed(() => auth.user?.id)

// ── Stats ──────────────────────────────────────────────────────────────
const stats = ref<any>(null)
const maxActivity = computed(() =>
  Math.max(1, ...((stats.value?.activity_7d || []).map((d: any) => d.count)))
)
const statCards = computed(() => stats.value ? [
  { label: 'Total Users', value: stats.value.user_count },
  { label: 'Diagnostic Sessions', value: stats.value.session_count },
  { label: 'Resolved Sessions', value: stats.value.resolved_count },
  { label: 'Audit Entries', value: stats.value.audit_entry_count },
] : [])

async function loadStats() {
  try {
    stats.value = await $fetch('/api/admin/stats', { headers: auth.authHeaders() })
  } catch { /* ignore */ }
}

// ── Users ──────────────────────────────────────────────────────────────
const users = ref<any[]>([])
const showCreateUser = ref(false)
const userLoading = ref(false)
const userError = ref('')
const newUser = ref({ username: '', password: '', role: 'technician' })
const roles = ['technician', 'qa_engineer', 'developer', 'admin']

async function loadUsers() {
  try {
    const data = await $fetch('/api/admin/users', { headers: auth.authHeaders() })
    users.value = data.users
  } catch { /* ignore */ }
}

async function createUser() {
  userLoading.value = true
  userError.value = ''
  try {
    await $fetch('/api/admin/users', {
      method: 'POST',
      body: newUser.value,
      headers: auth.authHeaders(),
    })
    newUser.value = { username: '', password: '', role: 'technician' }
    showCreateUser.value = false
    await loadUsers()
  } catch (e: any) {
    userError.value = e?.data?.detail || e.message
  } finally {
    userLoading.value = false
  }
}

async function changeRole(userId: string, role: string) {
  try {
    await $fetch(`/api/admin/users/${userId}/role`, {
      method: 'PATCH',
      body: { role },
      headers: auth.authHeaders(),
    })
    await loadUsers()
  } catch { /* ignore */ }
}

async function deleteUser(userId: string) {
  if (!confirm('Delete this user?')) return
  try {
    await $fetch(`/api/admin/users/${userId}`, { method: 'DELETE', headers: auth.authHeaders() })
    await loadUsers()
  } catch { /* ignore */ }
}

// ── Audit ──────────────────────────────────────────────────────────────
const auditEntries = ref<any[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPerPage = 50
const auditLoading = ref(false)
const auditFilters = ref({ action: '', severity: '', days: 30 })

async function loadAudit() {
  auditLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(auditPage.value),
      per_page: String(auditPerPage),
      days: String(auditFilters.value.days),
    })
    if (auditFilters.value.action) params.set('action', auditFilters.value.action)
    if (auditFilters.value.severity) params.set('severity', auditFilters.value.severity)
    const data = await $fetch(`/api/admin/audit?${params}`, { headers: auth.authHeaders() })
    auditEntries.value = data.entries
    auditTotal.value = data.total
  } catch { /* ignore */ } finally {
    auditLoading.value = false
  }
}

async function exportAudit() {
  const url = `/api/admin/audit/export?days=${auditFilters.value.days}`
  const resp = await fetch(url, { headers: auth.authHeaders() as HeadersInit })
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `audit-${auditFilters.value.days}d.csv`
  a.click()
}

async function pruneAudit() {
  if (!confirm('Delete all audit entries beyond the retention period?')) return
  try {
    const data = await $fetch('/api/admin/audit/prune', { method: 'DELETE', headers: auth.authHeaders() })
    alert(`Deleted ${data.deleted} old entries.`)
    await loadAudit()
  } catch { /* ignore */ }
}

function formatDetail(detail: string | null): string {
  if (!detail) return ''
  try { return JSON.stringify(JSON.parse(detail)) } catch { return detail }
}

function severityBadge(s: string) {
  return { info: 'bg-blue-900 text-blue-300', warning: 'bg-yellow-900 text-yellow-300', error: 'bg-red-900 text-red-300' }[s] || 'bg-slate-800 text-slate-400'
}

// ── LLM Providers ──────────────────────────────────────────────────────
const providers = ref<any[]>([])

async function loadProviders() {
  try {
    const data = await $fetch('/api/admin/llm-providers', { headers: auth.authHeaders() })
    providers.value = data.providers
  } catch { /* ignore */ }
}

async function toggleProvider(p: any) {
  try {
    await $fetch(`/api/admin/llm-providers/${p.id}`, {
      method: 'PATCH',
      body: { enabled: !p.enabled },
      headers: auth.authHeaders(),
    })
    p.enabled = !p.enabled
  } catch { /* ignore */ }
}

// ── Lifecycle ──────────────────────────────────────────────────────────
watch(activeTab, (tab) => {
  if (tab === 'stats') loadStats()
  else if (tab === 'users') loadUsers()
  else if (tab === 'audit') loadAudit()
  else if (tab === 'llm') loadProviders()
})

onMounted(loadStats)
</script>
