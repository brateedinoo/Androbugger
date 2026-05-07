<template>
  <!-- Backdrop -->
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
    <div class="bg-[#161925] border border-[#2a2d3e] rounded-2xl p-6 w-full max-w-sm space-y-5 shadow-2xl">
      <div class="flex items-center justify-between">
        <h2 class="font-semibold text-base">Export Report</h2>
        <button @click="$emit('close')" class="text-slate-500 hover:text-slate-300 text-lg leading-none">✕</button>
      </div>

      <!-- Format selection -->
      <div class="space-y-2">
        <p class="text-xs text-slate-500">Format</p>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="fmt in formats"
            :key="fmt.id"
            @click="selectedFormat = fmt.id"
            :class="['flex flex-col items-center gap-2 p-4 rounded-xl border text-sm transition',
              selectedFormat === fmt.id
                ? 'border-blue-500 bg-blue-950/30 text-blue-300'
                : 'border-[#2a2d3e] text-slate-400 hover:border-[#3a3d5e]']"
          >
            <span class="text-2xl">{{ fmt.icon }}</span>
            <span class="font-medium">{{ fmt.label }}</span>
            <span class="text-xs text-slate-600">{{ fmt.desc }}</span>
          </button>
        </div>
      </div>

      <p v-if="selectedFormat === 'pdf'" class="text-xs text-slate-500 bg-[#0f1117] rounded-lg p-3">
        PDF export requires <code class="text-slate-400">weasyprint</code> and <code class="text-slate-400">markdown</code> on the server. Falls back to a notice if unavailable.
      </p>

      <!-- Error -->
      <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>

      <!-- Actions -->
      <div class="flex gap-2">
        <button
          @click="$emit('close')"
          class="flex-1 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 hover:text-slate-200 text-sm transition"
        >
          Cancel
        </button>
        <button
          @click="doExport"
          :disabled="loading"
          class="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition"
        >
          {{ loading ? 'Generating…' : 'Download' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ sessionId: string }>()
const emit = defineEmits<{ close: [] }>()

const auth = useAuthStore()
const selectedFormat = ref('markdown')
const loading = ref(false)
const error = ref('')

const formats = [
  { id: 'markdown', label: 'Markdown', icon: '📄', desc: '.md file' },
  { id: 'pdf', label: 'PDF', icon: '📋', desc: 'Formatted PDF' },
]

async function doExport() {
  loading.value = true
  error.value = ''
  try {
    const url = `/api/diagnostics/${props.sessionId}/export?format=${selectedFormat.value}`
    const resp = await fetch(url, { headers: auth.authHeaders() as HeadersInit })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: resp.statusText }))
      error.value = body.detail || 'Export failed'
      return
    }
    const blob = await resp.blob()
    const ext = selectedFormat.value === 'pdf' ? 'pdf' : 'md'
    const filename = `androbugger-${props.sessionId.slice(0, 8)}.${ext}`
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
    emit('close')
  } catch (e: any) {
    error.value = e.message || 'Export failed'
  } finally {
    loading.value = false
  }
}
</script>
