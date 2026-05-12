<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Plugin Manager</h1>

      <!-- Tab switcher -->
      <div class="flex gap-1 ml-4 bg-[#1a1d2e] rounded-lg p-0.5">
        <button v-for="tab in tabs" :key="tab.id" @click="activeTab = tab.id"
          :class="['px-4 py-1.5 rounded-md text-sm transition', activeTab === tab.id
            ? 'bg-blue-600 text-white font-medium'
            : 'text-slate-400 hover:text-slate-200']">
          {{ tab.label }}
          <span v-if="tab.id === 'installed'" class="ml-1.5 text-xs opacity-60">{{ plugins.length }}</span>
        </button>
      </div>

      <button v-if="activeTab === 'installed'" @click="refresh" :disabled="loading"
        class="ml-auto px-3 py-1.5 rounded-md text-xs bg-[#1e2130] border border-[#2a2d3e] text-slate-300 hover:border-blue-500 transition-colors disabled:opacity-50">
        {{ loading ? 'Loading…' : 'Refresh' }}
      </button>
    </header>

    <div class="p-6 max-w-5xl mx-auto w-full">

      <!-- ── Installed tab ─────────────────────────────────────────── -->
      <div v-if="activeTab === 'installed'">
        <div v-if="error" class="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">{{ error }}</div>

        <div v-if="plugins.length === 0 && !loading" class="text-slate-500 text-sm text-center py-16">
          No plugins found. Place plugin directories in <code class="text-slate-400 bg-[#1e2130] px-1 rounded">backend/plugins/</code>.
        </div>

        <div class="grid gap-4">
          <div v-for="plugin in plugins" :key="plugin.id"
            class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-4">
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-3 flex-wrap">
                  <h2 class="font-semibold text-base">{{ plugin.name }}</h2>
                  <span class="text-slate-500 text-xs font-mono">v{{ plugin.version }}</span>
                  <span :class="statusBadge(plugin.status)">{{ plugin.status }}</span>
                </div>
                <p class="text-slate-400 text-sm mt-1">{{ plugin.description }}</p>
                <p class="text-slate-600 text-xs mt-0.5">by {{ plugin.author }}</p>
              </div>
              <div v-if="isAdmin" class="flex gap-2 flex-shrink-0 flex-wrap">
                <button v-if="plugin.status === 'disabled' || plugin.status === 'failed'"
                  @click="togglePlugin(plugin, 'enable')" :disabled="plugin.status === 'failed'"
                  class="px-3 py-1.5 rounded-md text-xs bg-green-800 hover:bg-green-700 disabled:bg-[#2a2d3e] disabled:cursor-not-allowed text-white transition-colors">
                  Enable
                </button>
                <button v-if="plugin.status === 'enabled'" @click="togglePlugin(plugin, 'disable')"
                  class="px-3 py-1.5 rounded-md text-xs bg-[#2a2d3e] hover:bg-[#343850] text-slate-300 transition-colors">
                  Disable
                </button>
                <button @click="reloadPlugin(plugin)"
                  class="px-3 py-1.5 rounded-md text-xs border border-[#2a2d3e] hover:border-blue-500 text-slate-400 hover:text-slate-200 transition-colors">
                  Reload
                </button>
                <button @click="toggleConfig(plugin)"
                  class="px-3 py-1.5 rounded-md text-xs border border-[#2a2d3e] hover:border-purple-500 text-slate-400 hover:text-slate-200 transition-colors">
                  Config
                </button>
                <button @click="updatePlugin(plugin)" :disabled="updatingPlugin === plugin.id"
                  class="px-3 py-1.5 rounded-md text-xs border border-[#2a2d3e] hover:border-green-500 text-slate-400 hover:text-green-300 transition-colors disabled:opacity-50">
                  {{ updatingPlugin === plugin.id ? 'Updating…' : 'Update' }}
                </button>
              </div>
            </div>

            <div v-if="plugin.validation_errors?.length || plugin.load_error"
              class="bg-red-950/30 border border-red-900 rounded-lg p-3 text-xs text-red-300 space-y-1">
              <p class="font-medium text-red-200">Validation errors:</p>
              <ul class="list-disc list-inside space-y-0.5">
                <li v-for="err in plugin.validation_errors" :key="err">{{ err }}</li>
                <li v-if="plugin.load_error && !plugin.validation_errors?.includes(plugin.load_error)">{{ plugin.load_error }}</li>
              </ul>
            </div>

            <div class="grid grid-cols-2 gap-4 text-xs">
              <div>
                <p class="text-slate-500 font-medium mb-2 uppercase tracking-wider text-[10px]">Capabilities</p>
                <div class="space-y-1">
                  <div v-if="plugin.capabilities?.diagnostic_patterns?.length" class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0" />
                    <span class="text-slate-300">{{ plugin.capabilities.diagnostic_patterns.length }} diagnostic pattern(s)</span>
                  </div>
                  <div v-if="plugin.capabilities?.fix_routines?.length" class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-green-400 flex-shrink-0" />
                    <span class="text-slate-300">{{ plugin.capabilities.fix_routines.length }} fix routine(s)</span>
                  </div>
                  <div v-if="plugin.capabilities?.custom_parsers?.length" class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-purple-400 flex-shrink-0" />
                    <span class="text-slate-300">{{ plugin.capabilities.custom_parsers.length }} custom parser(s)</span>
                  </div>
                  <div v-if="!hasCapabilities(plugin)" class="text-slate-600">No capabilities declared</div>
                </div>
              </div>
              <div>
                <p class="text-slate-500 font-medium mb-2 uppercase tracking-wider text-[10px]">Permissions</p>
                <div class="space-y-1">
                  <div class="flex items-center gap-2">
                    <span :class="['w-2 h-2 rounded-full flex-shrink-0', adbTierColor(plugin.permissions?.adb_commands)]" />
                    <span class="text-slate-300">ADB: {{ plugin.permissions?.adb_commands || 'none' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span :class="['w-2 h-2 rounded-full flex-shrink-0', plugin.permissions?.network ? 'bg-yellow-400' : 'bg-slate-600']" />
                    <span class="text-slate-300">Network: {{ plugin.permissions?.network ? 'allowed' : 'blocked' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-slate-500 flex-shrink-0" />
                    <span class="text-slate-300">FS: {{ plugin.permissions?.file_system || 'none' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Config panel -->
            <div v-if="configOpenId === plugin.id && configData[plugin.id]"
              class="bg-[#0f1117] border border-[#2a2d3e] rounded-lg p-4 text-sm space-y-3">
              <p class="text-slate-400 font-medium text-xs uppercase tracking-wider">Runtime Config</p>
              <div v-for="(val, key) in configData[plugin.id].config" :key="key" class="flex items-center gap-3">
                <label class="text-slate-400 text-xs w-40 shrink-0">{{ key }}</label>
                <input
                  v-model="configEdits[plugin.id][key]"
                  class="flex-1 bg-[#1a1d2e] border border-[#2a2d3e] rounded px-2 py-1 text-xs"
                />
              </div>
              <div class="flex gap-2">
                <button @click="saveConfig(plugin)"
                  class="bg-blue-600 hover:bg-blue-700 text-white text-xs px-3 py-1.5 rounded">Save</button>
                <button @click="configOpenId = null"
                  class="text-slate-400 hover:text-white text-xs px-3 py-1.5 rounded">Cancel</button>
              </div>
            </div>

            <details v-if="plugin.capabilities?.diagnostic_patterns?.length" class="text-xs">
              <summary class="text-slate-500 cursor-pointer hover:text-slate-300 select-none">
                Diagnostic patterns ({{ plugin.capabilities.diagnostic_patterns.length }})
              </summary>
              <div class="mt-2 space-y-1.5 pl-3 border-l border-[#2a2d3e]">
                <div v-for="p in plugin.capabilities.diagnostic_patterns" :key="p.id" class="text-slate-400">
                  <span class="text-slate-200 font-medium">{{ p.name }}</span>
                  <span :class="['ml-2 px-1.5 py-0.5 rounded text-[10px]', severityBadge(p.severity)]">{{ p.severity }}</span>
                  <p class="text-slate-600 mt-0.5">{{ p.description }}</p>
                </div>
              </div>
            </details>
          </div>
        </div>
      </div>

      <!-- ── Marketplace tab ──────────────────────────────────────── -->
      <div v-if="activeTab === 'marketplace'" class="space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-slate-400 text-sm">Community plugins tagged <code class="bg-[#1e2130] px-1 rounded text-slate-300">androbugger-plugin</code> on GitHub.</p>
          <button @click="loadMarketplace" :disabled="mktLoading"
            class="px-3 py-1.5 rounded-md text-xs bg-[#1e2130] border border-[#2a2d3e] text-slate-300 hover:border-blue-500 transition-colors disabled:opacity-50">
            {{ mktLoading ? 'Loading…' : 'Refresh' }}
          </button>
        </div>

        <p v-if="mktError" class="text-red-400 text-sm">{{ mktError }}</p>

        <div v-if="mktRepos.length === 0 && !mktLoading" class="text-slate-500 text-sm text-center py-16">
          No community plugins found yet. Be the first to publish one!
        </div>

        <!-- Install URL input (admin only) -->
        <div v-if="isAdmin" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 space-y-3">
          <p class="text-xs text-slate-500 font-medium">Install from GitHub URL</p>
          <div class="flex gap-2">
            <input v-model="installUrl" placeholder="https://github.com/author/my-androbugger-plugin"
              class="flex-1 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
            <button @click="doInstall(installUrl)" :disabled="!installUrl || installLoading"
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition">
              {{ installLoading ? 'Installing…' : 'Install' }}
            </button>
          </div>
          <p v-if="installResult" class="text-green-400 text-sm">✓ {{ installResult }}</p>
          <p v-if="installError" class="text-red-400 text-sm">{{ installError }}</p>
        </div>

        <!-- Repo cards -->
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-for="repo in mktRepos" :key="repo.url"
            class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 space-y-3">
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <h3 class="font-medium text-sm text-white truncate">{{ repo.name }}</h3>
                <p class="text-slate-400 text-xs mt-0.5 line-clamp-2">{{ repo.description || '(no description)' }}</p>
              </div>
              <div class="flex-shrink-0 text-right">
                <p class="text-xs text-slate-500">⭐ {{ repo.stars }}</p>
                <p class="text-xs text-slate-600 mt-0.5">{{ repo.updated_at?.slice(0, 10) }}</p>
              </div>
            </div>
            <div class="flex gap-2">
              <a :href="repo.url" target="_blank" rel="noopener"
                class="px-3 py-1.5 rounded-md text-xs border border-[#2a2d3e] text-slate-400 hover:text-slate-200 hover:border-blue-500 transition">
                View on GitHub
              </a>
              <button v-if="isAdmin" @click="doInstall(repo.clone_url)"
                :disabled="installLoading"
                class="px-3 py-1.5 rounded-md text-xs bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white transition">
                {{ installLoading ? '…' : 'Install' }}
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

interface Plugin {
  id: string
  name: string
  version: string
  author: string
  description: string
  status: 'enabled' | 'disabled' | 'failed' | 'validating'
  capabilities: {
    diagnostic_patterns?: Array<{ id: string; name: string; description: string; severity: string }>
    fix_routines?: Array<{ id: string; name: string }>
    custom_parsers?: Array<unknown>
  }
  permissions: { adb_commands?: string; network?: boolean; file_system?: string }
  validation_errors?: string[]
  load_error?: string
}

const auth = useAuthStore()
const activeTab = ref<'installed' | 'marketplace'>('installed')
const tabs: { id: 'installed' | 'marketplace'; label: string }[] = [
  { id: 'installed', label: 'Installed' },
  { id: 'marketplace', label: 'Marketplace' },
]

// ── Installed ──────────────────────────────────────────────────────────
const plugins = ref<Plugin[]>([])
const loading = ref(false)
const error = ref('')
const isAdmin = computed(() => auth.user?.role === 'admin')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await $fetch('/api/plugins', { headers: auth.authHeaders() })
    plugins.value = data.plugins
  } catch (e: any) {
    error.value = e.data?.detail || e.message || 'Failed to load plugins'
  } finally {
    loading.value = false
  }
}

async function togglePlugin(plugin: Plugin, action: 'enable' | 'disable') {
  try {
    await $fetch(`/api/plugins/${plugin.id}/${action}`, { method: 'POST', headers: auth.authHeaders() })
    await refresh()
  } catch (e: any) { error.value = e.data?.detail || e.message }
}

async function reloadPlugin(plugin: Plugin) {
  try {
    await $fetch(`/api/plugins/${plugin.id}/reload`, { method: 'POST', headers: auth.authHeaders() })
    await refresh()
  } catch (e: any) { error.value = e.data?.detail || e.message }
}

// ── Plugin config & update ─────────────────────────────────────────────
const configOpenId = ref<string | null>(null)
const configData = ref<Record<string, any>>({})
const configEdits = ref<Record<string, Record<string, any>>>({})
const updatingPlugin = ref<string | null>(null)

async function toggleConfig(plugin: Plugin) {
  if (configOpenId.value === plugin.id) {
    configOpenId.value = null
    return
  }
  try {
    const data = await $fetch(`/api/plugins/${plugin.id}/config`, { headers: auth.authHeaders() })
    configData.value[plugin.id] = data
    configEdits.value[plugin.id] = { ...data.config }
    configOpenId.value = plugin.id
  } catch (e: any) { error.value = e.data?.detail || e.message }
}

async function saveConfig(plugin: Plugin) {
  try {
    await $fetch(`/api/plugins/${plugin.id}/config`, {
      method: 'PUT',
      headers: auth.authHeaders(),
      body: { config: configEdits.value[plugin.id] },
    })
    configOpenId.value = null
    await refresh()
  } catch (e: any) { error.value = e.data?.detail || e.message }
}

async function updatePlugin(plugin: Plugin) {
  updatingPlugin.value = plugin.id
  try {
    const result = await $fetch(`/api/plugins/${plugin.id}/update`, {
      method: 'POST', headers: auth.authHeaders()
    })
    if (result.changed) {
      error.value = ''
      await refresh()
      alert(`Updated ${plugin.name} from v${result.old_version} → v${result.new_version}`)
    } else {
      alert(`${plugin.name} is already up to date (v${result.new_version})`)
    }
  } catch (e: any) { error.value = e.data?.detail || e.message }
  finally { updatingPlugin.value = null }
}

// ── Marketplace ────────────────────────────────────────────────────────
const mktRepos = ref<any[]>([])
const mktLoading = ref(false)
const mktError = ref('')
const installUrl = ref('')
const installLoading = ref(false)
const installResult = ref('')
const installError = ref('')

async function loadMarketplace() {
  mktLoading.value = true
  mktError.value = ''
  try {
    const data = await $fetch('/api/plugins/marketplace', { headers: auth.authHeaders() })
    mktRepos.value = data.repos
  } catch (e: any) {
    mktError.value = e.data?.detail || e.message || 'Failed to load marketplace'
  } finally {
    mktLoading.value = false
  }
}

async function doInstall(url: string) {
  if (!url) return
  installLoading.value = true
  installResult.value = ''
  installError.value = ''
  try {
    const data = await $fetch('/api/plugins/install', {
      method: 'POST',
      body: { github_url: url },
      headers: auth.authHeaders(),
    })
    installResult.value = `Installed ${data.name} v${data.version} (${data.status})`
    installUrl.value = ''
    await refresh()
  } catch (e: any) {
    installError.value = e.data?.detail || e.message || 'Installation failed'
  } finally {
    installLoading.value = false
  }
}

// ── Helpers ────────────────────────────────────────────────────────────
function hasCapabilities(plugin: Plugin) {
  return (
    (plugin.capabilities?.diagnostic_patterns?.length ?? 0) > 0 ||
    (plugin.capabilities?.fix_routines?.length ?? 0) > 0 ||
    (plugin.capabilities?.custom_parsers?.length ?? 0) > 0
  )
}

function statusBadge(status: string) {
  return {
    'px-2 py-0.5 rounded-full text-xs font-medium': true,
    'bg-green-900 text-green-300': status === 'enabled',
    'bg-slate-800 text-slate-400': status === 'disabled',
    'bg-red-900 text-red-300': status === 'failed',
    'bg-yellow-900 text-yellow-300': status === 'validating',
  }
}

function adbTierColor(tier?: string) {
  return { read_only: 'bg-green-400', state_changing: 'bg-yellow-400', destructive: 'bg-red-400' }[tier || ''] || 'bg-slate-600'
}

function severityBadge(severity: string) {
  return { critical: 'bg-red-900 text-red-300', warning: 'bg-yellow-900 text-yellow-300', info: 'bg-blue-900 text-blue-300' }[severity] || 'bg-slate-800 text-slate-400'
}

onMounted(refresh)
</script>
