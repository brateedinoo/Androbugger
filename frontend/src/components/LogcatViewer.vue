<template>
  <div class="flex flex-col h-full bg-[#0d0f14] border border-[#2a2d3e] rounded-lg overflow-hidden text-xs font-mono">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 px-3 py-2 border-b border-[#2a2d3e] bg-[#161925] flex-shrink-0 flex-wrap">
      <!-- Connection indicator -->
      <div class="flex items-center gap-1.5 flex-shrink-0">
        <div :class="['w-2 h-2 rounded-full', connected ? 'bg-green-400 animate-pulse' : streamError ? 'bg-red-500' : 'bg-slate-600']" />
        <span :class="['text-xs', streamError ? 'text-red-400' : 'text-slate-400']">{{ connected ? 'Live' : streamError ? 'Error' : 'Paused' }}</span>
      </div>

      <!-- Level filter -->
      <select
        v-model="levelFilter"
        class="bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-blue-500"
      >
        <option value="">All levels</option>
        <option v-for="lvl in ['V','D','I','W','E','F']" :key="lvl" :value="lvl">{{ levelLabel(lvl) }}</option>
      </select>

      <!-- Tag filter -->
      <input
        v-model="tagFilter"
        placeholder="Filter tag…"
        class="bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-blue-500 w-28"
      />

      <!-- Text search -->
      <input
        v-model="textFilter"
        placeholder="Search message…"
        class="bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-blue-500 flex-1 min-w-0"
      />

      <!-- Controls -->
      <div class="flex items-center gap-2 flex-shrink-0 ml-auto">
        <span class="text-slate-600">{{ filteredLines.length }} / {{ lines.length }}</span>

        <button
          @click="autoScroll = !autoScroll"
          :class="['px-2 py-1 rounded text-xs transition-colors border',
            autoScroll
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'bg-[#1e2130] border-[#2a2d3e] text-slate-400 hover:border-blue-500']"
        >
          {{ autoScroll ? 'Auto↓' : 'Locked' }}
        </button>

        <button
          v-if="selectedLines.length"
          @click="explainSelected"
          :disabled="explaining"
          class="px-2 py-1 rounded text-xs bg-purple-700 hover:bg-purple-600 disabled:bg-[#2a2d3e] text-white transition-colors border border-purple-600"
        >
          {{ explaining ? 'Explaining…' : `Explain (${selectedLines.length})` }}
        </button>

        <button
          v-if="selectedLines.length"
          @click="selectedLines = []"
          class="px-2 py-1 rounded text-xs text-slate-500 hover:text-slate-300 border border-[#2a2d3e] hover:border-slate-500 transition-colors"
        >
          Clear sel.
        </button>

        <button
          @click="clearLines"
          class="px-2 py-1 rounded text-xs text-slate-500 hover:text-red-400 border border-[#2a2d3e] transition-colors"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Stream error banner -->
    <div v-if="streamError" class="bg-red-950/60 border-b border-red-800 px-3 py-2 text-xs text-red-300 flex gap-2 items-center flex-shrink-0">
      <span class="font-sans flex-1">ADB error: {{ streamError }}</span>
      <button @click="streamError = ''; scheduleReconnect()" class="text-red-400 hover:text-red-200 flex-shrink-0">Retry</button>
    </div>

    <!-- Explanation popup -->
    <div v-if="explanation" class="bg-purple-950/50 border-b border-purple-800 px-3 py-2 text-xs text-purple-200 flex gap-2 flex-shrink-0">
      <span class="font-sans leading-relaxed flex-1">{{ explanation }}</span>
      <button @click="explanation = ''" class="text-purple-400 hover:text-purple-200 flex-shrink-0">✕</button>
    </div>

    <!-- Virtual scroll viewport -->
    <div
      ref="viewportEl"
      class="flex-1 overflow-y-auto"
      @scroll="onScroll"
    >
      <!-- Spacer for lines above visible window -->
      <div :style="{ height: topSpacerHeight + 'px' }" />

      <!-- Visible rows -->
      <div
        v-for="line in visibleLines"
        :key="line.line_number"
        @click="toggleSelect(line)"
        :class="['flex gap-2 px-2 py-px cursor-pointer select-none leading-5 hover:bg-[#1a1d27] transition-colors',
          isSelected(line) ? 'bg-[#1a1d27] ring-1 ring-inset ring-blue-700' : '',
          levelBg(line.level)]"
      >
        <!-- Level badge -->
        <span :class="['flex-shrink-0 w-3 text-center font-bold', levelColor(line.level)]">
          {{ line.level || '·' }}
        </span>
        <!-- Timestamp -->
        <span class="flex-shrink-0 text-slate-600 w-24 truncate">{{ shortTs(line.ts) }}</span>
        <!-- PID/TID -->
        <span class="flex-shrink-0 text-slate-700 w-16 truncate">{{ line.pid }}/{{ line.tid }}</span>
        <!-- Tag -->
        <span class="flex-shrink-0 text-cyan-700 w-32 truncate">{{ line.tag }}</span>
        <!-- Message -->
        <span :class="['flex-1 break-all', levelColor(line.level) || 'text-slate-300']">{{ line.msg || line.raw }}</span>
      </div>

      <!-- Spacer for lines below visible window -->
      <div :style="{ height: bottomSpacerHeight + 'px' }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

interface LogLine {
  line_number: number
  ts?: string
  pid?: number
  tid?: number
  level?: string
  tag?: string
  msg?: string
  raw?: string
}

const props = defineProps<{
  deviceSerial: string
}>()

const auth = useAuthStore()

// State
const lines = ref<LogLine[]>([])
const levelFilter = ref('')
const tagFilter = ref('')
const textFilter = ref('')
const autoScroll = ref(true)
const connected = ref(false)
const streamError = ref('')
const selectedLines = ref<LogLine[]>([])
const explaining = ref(false)
const explanation = ref('')
const viewportEl = ref<HTMLElement | null>(null)

// Virtual scroll config
const ROW_HEIGHT = 20  // px per row (matches leading-5 = 20px at text-xs)
const OVERSCAN = 20    // extra rows to render above/below visible area
const MAX_LINES = 10000

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectDelay = 1000
const scrollTop = ref(0)
const viewportHeight = ref(600)

// Filtering
const filteredLines = computed(() => {
  let result = lines.value
  if (levelFilter.value) {
    const levels = ['V', 'D', 'I', 'W', 'E', 'F']
    const minIdx = levels.indexOf(levelFilter.value)
    result = result.filter(l => levels.indexOf(l.level || 'V') >= minIdx)
  }
  if (tagFilter.value) {
    const q = tagFilter.value.toLowerCase()
    result = result.filter(l => (l.tag || '').toLowerCase().includes(q))
  }
  if (textFilter.value) {
    const q = textFilter.value.toLowerCase()
    result = result.filter(l => (l.msg || l.raw || '').toLowerCase().includes(q))
  }
  return result
})

// Virtual scroll math
const totalHeight = computed(() => filteredLines.value.length * ROW_HEIGHT)
const firstVisibleIdx = computed(() => Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT) - OVERSCAN))
const lastVisibleIdx = computed(() => Math.min(
  filteredLines.value.length,
  Math.ceil((scrollTop.value + viewportHeight.value) / ROW_HEIGHT) + OVERSCAN
))
const visibleLines = computed(() => filteredLines.value.slice(firstVisibleIdx.value, lastVisibleIdx.value))
const topSpacerHeight = computed(() => firstVisibleIdx.value * ROW_HEIGHT)
const bottomSpacerHeight = computed(() => Math.max(0, (filteredLines.value.length - lastVisibleIdx.value) * ROW_HEIGHT))

function onScroll(e: Event) {
  const el = e.target as HTMLElement
  scrollTop.value = el.scrollTop
  // If user scrolls up, disable auto-scroll
  if (el.scrollTop + el.clientHeight < el.scrollHeight - 40) {
    autoScroll.value = false
  }
}

function scrollToBottom() {
  if (!viewportEl.value) return
  viewportEl.value.scrollTop = viewportEl.value.scrollHeight
}

watch(filteredLines, () => {
  if (autoScroll.value) {
    nextTick(scrollToBottom)
  }
})

// WebSocket
function connect() {
  if (ws) ws.close()
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/logcat/${props.deviceSerial}`)

  ws.onopen = () => {
    connected.value = true
    streamError.value = ''
    reconnectDelay = 1000
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.error) {
        streamError.value = msg.error
        return
      }
      const line = msg as LogLine
      lines.value.push(line)
      if (lines.value.length > MAX_LINES) {
        lines.value = lines.value.slice(-MAX_LINES)
      }
    } catch {
      // ignore
    }
  }

  ws.onclose = () => {
    connected.value = false
    if (!streamError.value) scheduleReconnect()
  }

  ws.onerror = () => { connected.value = false }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    reconnectDelay = Math.min(reconnectDelay * 2, 16000)
    connect()
  }, reconnectDelay)
}

// Selection
function toggleSelect(line: LogLine) {
  const idx = selectedLines.value.findIndex(l => l.line_number === line.line_number)
  if (idx >= 0) {
    selectedLines.value.splice(idx, 1)
  } else {
    selectedLines.value.push(line)
  }
}

function isSelected(line: LogLine) {
  return selectedLines.value.some(l => l.line_number === line.line_number)
}

// Explain this
async function explainSelected() {
  if (!selectedLines.value.length || explaining.value) return
  explaining.value = true
  explanation.value = ''
  try {
    const data = await $fetch('/api/chat/explain', {
      method: 'POST',
      body: {
        device_serial: props.deviceSerial,
        selected_lines: selectedLines.value.map(l => ({
          line_number: l.line_number,
          text: l.msg || l.raw || '',
        })),
      },
      headers: auth.authHeaders(),
    })
    explanation.value = data.explanation || 'No explanation returned.'
  } catch (e: any) {
    explanation.value = `Error: ${e.message}`
  } finally {
    explaining.value = false
  }
}

function clearLines() {
  lines.value = []
  selectedLines.value = []
  explanation.value = ''
}

// Styling helpers
function levelColor(level?: string) {
  return {
    V: 'text-slate-500',
    D: 'text-slate-400',
    I: 'text-blue-400',
    W: 'text-yellow-400',
    E: 'text-red-400',
    F: 'text-red-300',
  }[level || ''] || 'text-slate-300'
}

function levelBg(level?: string) {
  return {
    E: 'bg-red-950/20',
    F: 'bg-red-950/40',
    W: 'bg-yellow-950/20',
  }[level || ''] || ''
}

function levelLabel(l: string) {
  return { V: 'Verbose', D: 'Debug', I: 'Info', W: 'Warning', E: 'Error', F: 'Fatal' }[l] || l
}

function shortTs(ts?: string) {
  if (!ts) return ''
  // "MM-DD HH:MM:SS.mmm" → "HH:MM:SS.mmm"
  return ts.slice(6) || ts
}

// Resize observer for viewport height
let ro: ResizeObserver | null = null

onMounted(() => {
  connect()
  if (viewportEl.value) {
    viewportHeight.value = viewportEl.value.clientHeight
    ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        viewportHeight.value = e.contentRect.height
      }
    })
    ro.observe(viewportEl.value)
  }
})

onUnmounted(() => {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  ws?.close()
  ro?.disconnect()
})
</script>
