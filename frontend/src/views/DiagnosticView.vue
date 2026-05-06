<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <!-- Header -->
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Diagnostic Session</h1>
      <span v-if="session" class="text-slate-500 text-xs font-mono">{{ session.id }}</span>
      <span v-if="session"
        :class="['ml-auto px-2.5 py-0.5 rounded-full text-xs font-medium',
          session.status === 'running'   ? 'bg-yellow-900 text-yellow-300 animate-pulse' :
          session.status === 'completed' ? 'bg-blue-900 text-blue-300' :
          session.status === 'resolved'  ? 'bg-green-900 text-green-300' :
          'bg-red-900 text-red-300']">
        {{ session.status }}
      </span>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-slate-400">
      <div class="text-center">
        <div class="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p>Running diagnosis…</p>
        <p class="text-xs text-slate-600 mt-1">Pulling bugreport and analysing logs</p>
      </div>
    </div>

    <div v-else-if="session" class="flex-1 p-6 max-w-6xl mx-auto w-full">
      <DiagnosticReport
        :session="session"
        @resolve="handleResolve"
      />
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
import type { Session } from '@/stores/diagnostics'

const route = useRoute()
const diagnostics = useDiagnosticsStore()
const session = ref<Session | null>(null)
const loading = ref(true)

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
