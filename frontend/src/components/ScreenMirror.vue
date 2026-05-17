<template>
  <div class="flex flex-col h-full bg-[#0a0c12]">
    <!-- Controls bar -->
    <div class="flex items-center gap-3 px-3 py-2 border-b border-[#2a2d3e] flex-wrap">
      <!-- Status dot -->
      <div class="flex items-center gap-1.5">
        <span :class="['w-2 h-2 rounded-full', statusDot]" />
        <span class="text-xs text-slate-400">{{ statusLabel }}</span>
      </div>

      <div class="flex items-center gap-2 ml-auto">
        <!-- FPS selector -->
        <label class="text-xs text-slate-500">FPS</label>
        <select v-model.number="fps" @change="reconnect"
          class="px-2 py-1 rounded bg-[#1a1d2e] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none">
          <option :value="1">1</option>
          <option :value="2">2</option>
          <option :value="5">5</option>
        </select>

        <!-- Quality slider -->
        <label class="text-xs text-slate-500">Quality</label>
        <input type="range" v-model.number="quality" min="20" max="90" step="10" @change="reconnect"
          class="w-20 accent-blue-500" />
        <span class="text-xs text-slate-500 w-8">{{ quality }}</span>

        <!-- Screenshot button -->
        <button @click="saveScreenshot" :disabled="!currentFrameUrl"
          class="px-2.5 py-1 rounded border border-[#2a2d3e] text-slate-400 hover:text-slate-200 hover:border-blue-500 text-xs transition disabled:opacity-40">
          Screenshot
        </button>
      </div>
    </div>

    <!-- Frame display -->
    <div class="flex-1 overflow-hidden flex items-center justify-center p-4">
      <div v-if="currentFrameUrl" class="max-h-full max-w-full">
        <img :src="currentFrameUrl" alt="Device screen" class="max-h-full max-w-full object-contain rounded-lg shadow-2xl" />
      </div>

      <div v-else-if="wsState === 'connecting'" class="text-slate-500 text-sm animate-pulse">
        Connecting to device…
      </div>
      <div v-else-if="wsState === 'error'" class="text-center space-y-3">
        <p class="text-red-400 text-sm">{{ errorMsg }}</p>
        <button @click="reconnect" class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm transition">
          Retry
        </button>
      </div>
      <div v-else class="text-slate-600 text-sm">Waiting for first frame…</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ deviceSerial: string }>()

const auth = useAuthStore()

const fps = ref(2)
const quality = ref(75)
const wsState = ref<'connecting' | 'open' | 'closed' | 'error'>('connecting')
const errorMsg = ref('')
const currentFrameUrl = ref<string | null>(null)
let ws: WebSocket | null = null
let prevUrl: string | null = null

const statusDot = computed(() => ({
  connecting: 'bg-yellow-500 animate-pulse',
  open: 'bg-green-500',
  closed: 'bg-slate-600',
  error: 'bg-red-500',
}[wsState.value]))

const statusLabel = computed(() => ({
  connecting: 'Connecting',
  open: 'Live',
  closed: 'Disconnected',
  error: 'Error',
}[wsState.value]))

function connect() {
  if (ws) {
    ws.close()
    ws = null
  }
  wsState.value = 'connecting'
  errorMsg.value = ''

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = encodeURIComponent(auth.token ?? '')
  const url = `${proto}://${location.host}/ws/mirror/${props.deviceSerial}?fps=${fps.value}&quality=${quality.value}&token=${token}`
  ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => { wsState.value = 'open' }

  ws.onmessage = (event) => {
    const blob = new Blob([event.data as ArrayBuffer], { type: 'image/jpeg' })
    const newUrl = URL.createObjectURL(blob)
    if (prevUrl) URL.revokeObjectURL(prevUrl)
    prevUrl = newUrl
    currentFrameUrl.value = newUrl
  }

  ws.onerror = () => {
    wsState.value = 'error'
    errorMsg.value = 'WebSocket error — device may be disconnected'
  }

  ws.onclose = (ev) => {
    if (wsState.value !== 'error') wsState.value = 'closed'
    if (!ev.wasClean) errorMsg.value = `Connection closed (code ${ev.code})`
  }
}

function reconnect() {
  connect()
}

function saveScreenshot() {
  if (!currentFrameUrl.value) return
  const a = document.createElement('a')
  a.href = currentFrameUrl.value
  a.download = `screenshot-${props.deviceSerial}-${Date.now()}.jpg`
  a.click()
}

watch(() => props.deviceSerial, connect)
onMounted(connect)
onUnmounted(() => {
  ws?.close()
  if (prevUrl) URL.revokeObjectURL(prevUrl)
})
</script>
