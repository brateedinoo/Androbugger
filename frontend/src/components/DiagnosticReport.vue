<template>
  <div class="space-y-6">
    <!-- Summary header -->
    <div class="flex items-center gap-3 flex-wrap">
      <span
        :class="[
          'px-3 py-1 rounded-full text-sm font-semibold',
          summary?.severity === 'critical' ? 'bg-red-900 text-red-300' :
          summary?.severity === 'warning'  ? 'bg-yellow-900 text-yellow-300' :
          'bg-green-900 text-green-300'
        ]"
      >{{ (summary?.severity ?? 'unknown').toUpperCase() }}</span>
      <span class="text-slate-400 text-sm">Deterministic summary</span>
      <div class="ml-auto">
        <button
          @click="showExport = true"
          class="px-3 py-1.5 rounded-lg border border-[#2a2d3e] text-slate-400 hover:text-slate-200 hover:border-blue-500 text-xs transition"
        >
          ↓ Export
        </button>
      </div>
    </div>

    <!-- Key metrics -->
    <div v-if="summary" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <MetricBadge label="Tombstones" :value="summary.tombstone_count" :alert="summary.tombstone_count > 0" />
      <MetricBadge label="ANR Events" :value="summary.anr_count" :alert="summary.anr_count > 0" />
      <MetricBadge label="OOM Kills"  :value="summary.oom_count"  :alert="summary.oom_count > 0" />
      <MetricBadge label="Thermal"    :value="summary.thermal_count" :alert="summary.thermal_count > 0" />
    </div>

    <!-- Top errors -->
    <div v-if="summary?.top_errors?.length" class="rounded-lg border border-[#2a2d3e] bg-[#1a1d2e] p-4">
      <h3 class="text-sm font-semibold text-slate-300 mb-3">Top Error Tags</h3>
      <div class="space-y-1.5">
        <div v-for="e in summary.top_errors" :key="e.tag" class="flex items-center gap-3 text-sm">
          <span :class="['w-6 font-bold text-center', levelClass(e.level)]">{{ e.level }}</span>
          <span class="text-slate-200 font-mono w-40 truncate">{{ e.tag }}</span>
          <span class="text-slate-500 text-xs">×{{ e.count }}</span>
          <span class="text-slate-400 text-xs truncate flex-1">{{ e.sample_msg }}</span>
        </div>
      </div>
    </div>

    <!-- LLM report -->
    <div v-if="session.llm_report" class="rounded-lg border border-[#2a2d3e] bg-[#1a1d2e] p-5">
      <div class="flex items-center gap-2 mb-3">
        <span class="text-sm font-semibold text-slate-300">AI Analysis</span>
        <span class="text-xs text-slate-500">{{ session.llm_provider }}</span>
      </div>
      <div class="prose prose-invert prose-sm max-w-none" v-html="renderedReport" />
    </div>

    <div v-else-if="session.status === 'running'" class="text-slate-400 text-sm animate-pulse">
      AI analysis in progress…
    </div>

    <div v-else-if="!session.llm_report" class="text-slate-500 text-sm">
      LLM unavailable — deterministic summary above is the full analysis.
    </div>

    <!-- Hardware check section -->
    <div class="rounded-lg border border-[#2a2d3e] bg-[#1a1d2e]">
      <button @click="toggleHw()"
        class="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-slate-300 hover:text-white transition">
        <span>Hardware Check</span>
        <span class="text-xs text-slate-500">{{ hwOpen ? '▲' : '▼' }}</span>
      </button>
      <div v-if="hwOpen" class="px-4 pb-4 space-y-3">
        <div v-if="hwLoading" class="text-slate-400 text-sm animate-pulse">Loading hardware data…</div>
        <div v-else-if="hwData">
          <div class="flex items-center gap-2 mb-3">
            <span :class="statusDot(hwData.overall_status)" class="w-3 h-3 rounded-full flex-shrink-0" />
            <span class="text-sm font-medium text-slate-200">
              Overall: {{ hwData.overall_status.toUpperCase() }}
            </span>
            <span class="text-xs text-slate-500 ml-auto">{{ hwData.checked_at?.slice(0, 19).replace('T', ' ') }}</span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <div v-for="sub in hwData.results?.subsystems" :key="sub.name"
              class="rounded-lg border p-3 space-y-1"
              :class="sub.status === 'fail' ? 'border-red-800 bg-red-950/30' :
                      sub.status === 'warning' ? 'border-yellow-800 bg-yellow-950/20' :
                      'border-[#2a2d3e] bg-[#0f1117]'">
              <div class="flex items-center gap-2">
                <span :class="statusDot(sub.status)" class="w-2 h-2 rounded-full flex-shrink-0" />
                <span class="text-xs font-semibold capitalize text-slate-200">{{ sub.name }}</span>
              </div>
              <p class="text-[11px] text-slate-400 truncate">{{ sub.details }}</p>
              <div v-if="sub.anomalies?.length" class="space-y-0.5">
                <p v-for="a in sub.anomalies" :key="a" class="text-[10px] text-red-400">⚠ {{ a }}</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="text-slate-500 text-sm">No hardware check for this session.</div>
      </div>
    </div>

    <!-- Resolve form -->
    <div v-if="session.status === 'completed'" class="rounded-lg border border-[#2a2d3e] bg-[#1a1d2e] p-5">
      <h3 class="text-sm font-semibold text-slate-300 mb-3">Mark as Resolved</h3>
      <div class="space-y-3">
        <textarea v-model="rootCause" placeholder="Root cause…" rows="2"
          class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm resize-none focus:outline-none focus:border-blue-500" />
        <textarea v-model="appliedFix" placeholder="Applied fix…" rows="2"
          class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm resize-none focus:outline-none focus:border-blue-500" />
        <textarea v-model="notes" placeholder="Notes (optional)…" rows="1"
          class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm resize-none focus:outline-none focus:border-blue-500" />
        <button @click="$emit('resolve', rootCause, appliedFix, notes)"
          :disabled="!rootCause || !appliedFix"
          class="px-5 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm font-medium transition">
          Mark Resolved
        </button>
      </div>
    </div>

    <div v-if="session.status === 'resolved'" class="rounded-lg border border-green-800 bg-green-950 p-4 text-sm text-green-300">
      <p class="font-semibold">Resolved</p>
      <p class="mt-1 text-green-400">Root cause: {{ session.root_cause }}</p>
      <p class="text-green-400">Fix: {{ session.applied_fix }}</p>
    </div>

    <!-- Export dialog (teleported to body) -->
    <Teleport to="body">
      <ExportDialog v-if="showExport" :session-id="session.id" @close="showExport = false" />
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'
import type { Session } from '@/stores/diagnostics'
import ExportDialog from '@/components/ExportDialog.vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ session: Session }>()
defineEmits<{ resolve: [rootCause: string, appliedFix: string, notes: string] }>()

const auth = useAuthStore()
const md = new MarkdownIt({ html: false, breaks: true })
const showExport = ref(false)

const summary = computed(() => {
  if (!props.session.deterministic_summary) return null
  try { return JSON.parse(props.session.deterministic_summary) } catch { return null }
})

const renderedReport = computed(() =>
  props.session.llm_report ? md.render(props.session.llm_report) : ''
)

const rootCause = ref('')
const appliedFix = ref('')
const notes = ref('')

// Hardware check
const hwOpen = ref(false)
const hwLoading = ref(false)
const hwData = ref<any>(null)

async function loadHardware() {
  if (hwData.value !== null) return
  hwLoading.value = true
  try {
    const resp = await fetch(`/api/diagnostics/${props.session.id}/hardware`, {
      headers: auth.authHeaders() as HeadersInit,
    })
    if (resp.ok) {
      const data = await resp.json()
      hwData.value = data.hardware
    }
  } catch { /* ignore */ } finally {
    hwLoading.value = false
  }
}

// Eagerly load hardware info when component mounts
onMounted(loadHardware)

// Also load when user expands the panel
function toggleHw() {
  hwOpen.value = !hwOpen.value
  if (hwOpen.value) loadHardware()
}

function levelClass(level: string) {
  return { V: 'text-gray-500', D: 'text-blue-400', I: 'text-green-400', W: 'text-yellow-400', E: 'text-red-400', F: 'text-red-500' }[level] ?? 'text-white'
}

function statusDot(status: string) {
  return { pass: 'bg-green-500', warning: 'bg-yellow-500', fail: 'bg-red-500' }[status] ?? 'bg-slate-500'
}
</script>

<script lang="ts">
const MetricBadge = {
  props: ['label', 'value', 'alert'],
  template: `
    <div class="rounded-lg border p-3 text-center"
      :class="alert && value > 0 ? 'border-red-800 bg-red-950' : 'border-[#2a2d3e] bg-[#1a1d2e]'">
      <p class="text-xl font-bold" :class="alert && value > 0 ? 'text-red-300' : 'text-white'">{{ value }}</p>
      <p class="text-xs text-slate-500">{{ label }}</p>
    </div>
  `,
}
</script>
