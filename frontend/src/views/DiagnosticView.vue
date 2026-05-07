<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <!-- Header -->
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4 flex-shrink-0">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Diagnostic Session</h1>
      <span v-if="session" class="text-slate-500 text-xs font-mono">{{ session.id }}</span>
      <span v-if="session"
        :class="['px-2.5 py-0.5 rounded-full text-xs font-medium',
          session.status === 'running'   ? 'bg-yellow-900 text-yellow-300 animate-pulse' :
          session.status === 'completed' ? 'bg-blue-900 text-blue-300' :
          session.status === 'resolved'  ? 'bg-green-900 text-green-300' :
          'bg-red-900 text-red-300']">
        {{ session.status }}
      </span>

      <!-- Side panel buttons -->
      <div v-if="session && session.status !== 'running'" class="ml-auto flex gap-2">
        <button
          v-for="panel in sidePanels"
          :key="panel.id"
          @click="togglePanel(panel.id)"
          :class="['px-3 py-1 rounded-md text-xs font-medium transition-colors border',
            activePanel === panel.id
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'bg-[#1e2130] border-[#2a2d3e] text-slate-300 hover:border-blue-500']"
        >
          {{ panel.label }}
        </button>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-slate-400">
      <div class="text-center">
        <div class="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p>Running diagnosis…</p>
        <p class="text-xs text-slate-600 mt-1">Pulling bugreport and analysing logs</p>
      </div>
    </div>

    <!-- Main split layout -->
    <div v-else-if="session" class="flex-1 flex overflow-hidden">
      <!-- Report pane -->
      <div :class="['overflow-y-auto transition-all duration-300', activePanel ? 'w-[55%]' : 'w-full']">
        <div class="p-6 max-w-4xl">
          <DiagnosticReport
            :session="session"
            @resolve="handleResolve"
          />
        </div>
      </div>

      <!-- Side panel -->
      <div v-if="activePanel" class="w-[45%] border-l border-[#2a2d3e] flex flex-col overflow-hidden">
        <ChatPanel
          v-if="activePanel === 'chat'"
          :session-id="session.id"
        />
        <CommandInput
          v-if="activePanel === 'commands'"
          :device-serial="session.device_serial"
        />
        <LogcatViewer
          v-if="activePanel === 'logcat'"
          :device-serial="session.device_serial"
        />
        <ScreenMirror
          v-if="activePanel === 'mirror'"
          :device-serial="session.device_serial"
        />
      </div>
    </div>

    <div v-else class="flex-1 flex items-center justify-center text-red-400">
      Session not found
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useDiagnosticsStore } from '@/stores/diagnostics'
import DiagnosticReport from '@/components/DiagnosticReport.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import CommandInput from '@/components/CommandInput.vue'
import LogcatViewer from '@/components/LogcatViewer.vue'
import ScreenMirror from '@/components/ScreenMirror.vue'
import type { Session } from '@/stores/diagnostics'

const route = useRoute()
const diagnostics = useDiagnosticsStore()
const session = ref<Session | null>(null)
const loading = ref(true)
const activePanel = ref<string | null>(null)

const sidePanels = [
  { id: 'chat', label: 'AI Chat' },
  { id: 'commands', label: 'ADB Commands' },
  { id: 'logcat', label: 'Live Logcat' },
  { id: 'mirror', label: 'Screen Mirror' },
]

function togglePanel(id: string) {
  activePanel.value = activePanel.value === id ? null : id
}

onMounted(async () => {
  const id = route.params.sessionId as string
  session.value = await diagnostics.pollUntilDone(id)
  loading.value = false
})

async function handleResolve(rootCause: string, appliedFix: string, notes: string) {
  if (!session.value) return
  await diagnostics.resolveSession(session.value.id, rootCause, appliedFix, notes)
  session.value = await diagnostics.fetchSession(session.value.id)
}
</script>
