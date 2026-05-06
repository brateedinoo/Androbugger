<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Plugin Manager</h1>
      <span class="text-slate-600 text-sm">{{ plugins.length }} plugin(s)</span>
      <button
        @click="refresh"
        :disabled="loading"
        class="ml-auto px-3 py-1.5 rounded-md text-xs bg-[#1e2130] border border-[#2a2d3e] text-slate-300 hover:border-blue-500 transition-colors disabled:opacity-50"
      >
        {{ loading ? 'Loading…' : 'Refresh' }}
      </button>
    </header>

    <div class="p-6 max-w-5xl mx-auto w-full">
      <!-- Error -->
      <div v-if="error" class="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
        {{ error }}
      </div>

      <!-- Plugin cards -->
      <div v-if="plugins.length === 0 && !loading" class="text-slate-500 text-sm text-center py-16">
        No plugins found. Place plugin directories in the <code class="text-slate-400 bg-[#1e2130] px-1 rounded">backend/plugins/</code> folder.
      </div>

      <div class="grid gap-4">
        <div
          v-for="plugin in plugins"
          :key="plugin.id"
          class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-4"
        >
          <!-- Header row -->
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

            <!-- Actions (admin only) -->
            <div v-if="isAdmin" class="flex gap-2 flex-shrink-0">
              <button
                v-if="plugin.status === 'disabled' || plugin.status === 'failed'"
                @click="togglePlugin(plugin, 'enable')"
                :disabled="plugin.status === 'failed'"
                class="px-3 py-1.5 rounded-md text-xs bg-green-800 hover:bg-green-700 disabled:bg-[#2a2d3e] disabled:cursor-not-allowed text-white transition-colors"
              >
                Enable
              </button>
              <button
                v-if="plugin.status === 'enabled'"
                @click="togglePlugin(plugin, 'disable')"
                class="px-3 py-1.5 rounded-md text-xs bg-[#2a2d3e] hover:bg-[#343850] text-slate-300 transition-colors"
              >
                Disable
              </button>
              <button
                @click="reloadPlugin(plugin)"
                class="px-3 py-1.5 rounded-md text-xs border border-[#2a2d3e] hover:border-blue-500 text-slate-400 hover:text-slate-200 transition-colors"
              >
                Reload
              </button>
            </div>
          </div>

          <!-- Validation errors -->
          <div v-if="plugin.validation_errors?.length || plugin.load_error" class="bg-red-950/30 border border-red-900 rounded-lg p-3 text-xs text-red-300 space-y-1">
            <p class="font-medium text-red-200">Validation errors:</p>
            <ul class="list-disc list-inside space-y-0.5">
              <li v-for="err in plugin.validation_errors" :key="err">{{ err }}</li>
              <li v-if="plugin.load_error && !plugin.validation_errors?.includes(plugin.load_error)">{{ plugin.load_error }}</li>
            </ul>
          </div>

          <!-- Capabilities & Permissions -->
          <div class="grid grid-cols-2 gap-4 text-xs">
            <!-- Capabilities -->
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

            <!-- Permissions -->
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

          <!-- Pattern list (expandable) -->
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
  permissions: {
    adb_commands?: string
    network?: boolean
    file_system?: string
  }
  validation_errors?: string[]
  load_error?: string
}

const auth = useAuthStore()
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
    await $fetch(`/api/plugins/${plugin.id}/${action}`, {
      method: 'POST',
      headers: auth.authHeaders(),
    })
    await refresh()
  } catch (e: any) {
    error.value = e.data?.detail || e.message
  }
}

async function reloadPlugin(plugin: Plugin) {
  try {
    await $fetch(`/api/plugins/${plugin.id}/reload`, {
      method: 'POST',
      headers: auth.authHeaders(),
    })
    await refresh()
  } catch (e: any) {
    error.value = e.data?.detail || e.message
  }
}

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
  return {
    read_only: 'bg-green-400',
    state_changing: 'bg-yellow-400',
    destructive: 'bg-red-400',
    none: 'bg-slate-600',
  }[tier || 'none'] || 'bg-slate-600'
}

function severityBadge(severity: string) {
  return {
    critical: 'bg-red-900 text-red-300',
    warning: 'bg-yellow-900 text-yellow-300',
    info: 'bg-blue-900 text-blue-300',
  }[severity] || 'bg-slate-800 text-slate-400'
}

onMounted(refresh)
</script>
