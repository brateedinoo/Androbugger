import { defineStore } from 'pinia'
import { ref } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from './auth'

export interface Session {
  id: string
  device_serial: string
  device_model: string | null
  firmware_version: string | null
  status: 'running' | 'completed' | 'resolved' | 'failed'
  started_at: string
  completed_at: string | null
  deterministic_summary: string | null
  llm_report: string | null
  llm_provider: string | null
  root_cause: string | null
  applied_fix: string | null
}

export const useDiagnosticsStore = defineStore('diagnostics', () => {
  const activeSession = ref<Session | null>(null)
  const polling = ref(false)

  async function startDiagnosis(serial: string): Promise<string> {
    const auth = useAuthStore()
    const data = await $fetch('/api/diagnostics/start', {
      method: 'POST',
      body: { device_serial: serial },
      headers: auth.authHeaders(),
    })
    return data.session_id
  }

  async function fetchSession(id: string): Promise<Session> {
    const auth = useAuthStore()
    const data = await $fetch(`/api/diagnostics/${id}`, { headers: auth.authHeaders() })
    activeSession.value = data.session
    return data.session
  }

  async function pollUntilDone(id: string): Promise<Session> {
    polling.value = true
    try {
      while (true) {
        const s = await fetchSession(id)
        if (s.status !== 'running') return s
        await new Promise(r => setTimeout(r, 3000))
      }
    } finally {
      polling.value = false
    }
  }

  async function resolveSession(id: string, rootCause: string, appliedFix: string, notes: string) {
    const auth = useAuthStore()
    await $fetch(`/api/diagnostics/${id}/resolve`, {
      method: 'POST',
      body: { root_cause: rootCause, applied_fix: appliedFix, notes },
      headers: auth.authHeaders(),
    })
    if (activeSession.value?.id === id) {
      activeSession.value.status = 'resolved'
      activeSession.value.root_cause = rootCause
      activeSession.value.applied_fix = appliedFix
    }
  }

  return { activeSession, polling, startDiagnosis, fetchSession, pollUntilDone, resolveSession }
})
