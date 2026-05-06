<template>
  <div class="flex flex-col h-full bg-[#161925] border border-[#2a2d3e] rounded-lg overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-[#2a2d3e] flex-shrink-0">
      <div class="flex items-center gap-2">
        <span class="text-blue-400 text-sm">●</span>
        <span class="text-sm font-medium text-slate-200">AI Assistant</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span v-if="connected" class="text-xs text-green-400">Connected</span>
        <span v-else class="text-xs text-slate-500">Disconnected</span>
        <button
          @click="clearChat"
          class="text-xs text-slate-500 hover:text-slate-300 px-1.5 py-0.5 rounded hover:bg-[#2a2d3e] transition-colors"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Messages -->
    <div ref="scrollEl" class="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
      <!-- Welcome message -->
      <div v-if="messages.length === 0" class="text-slate-500 text-xs text-center py-6">
        Ask anything about this diagnostic session. The AI has access to all parsed log data.
      </div>

      <template v-for="msg in messages" :key="msg.id">
        <!-- User message -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="max-w-[80%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-3.5 py-2 text-sm leading-relaxed">
            {{ msg.content }}
          </div>
        </div>

        <!-- Assistant message -->
        <div v-else class="flex gap-2.5">
          <div class="w-6 h-6 rounded-full bg-[#2a2d3e] flex items-center justify-center flex-shrink-0 mt-0.5">
            <span class="text-blue-400 text-xs">AI</span>
          </div>
          <div
            class="max-w-[88%] prose prose-invert prose-sm prose-p:my-1 prose-pre:bg-[#0f1117] prose-pre:text-xs prose-code:text-blue-300 prose-code:bg-[#0f1117] prose-code:px-1 prose-code:rounded"
            v-html="renderMarkdown(msg.content)"
          />
        </div>
      </template>

      <!-- Streaming cursor -->
      <div v-if="streaming" class="flex gap-2.5">
        <div class="w-6 h-6 rounded-full bg-[#2a2d3e] flex items-center justify-center flex-shrink-0 mt-0.5">
          <span class="text-blue-400 text-xs">AI</span>
        </div>
        <div
          v-if="streamBuffer"
          class="max-w-[88%] prose prose-invert prose-sm prose-p:my-1 prose-pre:bg-[#0f1117] prose-code:text-blue-300"
          v-html="renderMarkdown(streamBuffer)"
        />
        <div v-else class="flex gap-1 items-center h-6">
          <span v-for="i in 3" :key="i"
            class="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce"
            :style="{ animationDelay: `${(i - 1) * 0.15}s` }"
          />
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="border-t border-[#2a2d3e] p-3 flex-shrink-0">
      <div class="flex gap-2 items-end">
        <textarea
          ref="inputEl"
          v-model="draft"
          @keydown.enter.exact.prevent="send"
          @keydown.enter.shift.exact="draft += '\n'"
          placeholder="Ask about this session… (Enter to send)"
          rows="1"
          class="flex-1 bg-[#0f1117] border border-[#2a2d3e] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-blue-500 transition-colors leading-relaxed"
          :style="{ minHeight: '38px', maxHeight: '120px' }"
          @input="autoResize"
          :disabled="streaming || !connected"
        />
        <button
          @click="send"
          :disabled="!draft.trim() || streaming || !connected"
          class="flex-shrink-0 w-9 h-9 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-[#2a2d3e] disabled:cursor-not-allowed transition-colors flex items-center justify-center"
        >
          <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>
      <p class="text-xs text-slate-600 mt-1.5">Shift+Enter for new line</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, typographer: true })

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const props = defineProps<{
  sessionId: string
}>()

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const streaming = ref(false)
const streamBuffer = ref('')
const connected = ref(false)
const scrollEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectDelay = 1000

function renderMarkdown(text: string): string {
  return md.render(text || '')
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) {
      scrollEl.value.scrollTop = scrollEl.value.scrollHeight
    }
  })
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function connect() {
  if (ws) {
    ws.close()
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/chat/${props.sessionId}`)

  ws.onopen = () => {
    connected.value = true
    reconnectDelay = 1000
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'chunk') {
        streamBuffer.value += data.content
        scrollToBottom()
      } else if (data.type === 'done') {
        if (streamBuffer.value) {
          messages.value.push({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: streamBuffer.value,
          })
        }
        streamBuffer.value = ''
        streaming.value = false
        scrollToBottom()
      } else if (data.type === 'error') {
        messages.value.push({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `⚠️ Error: ${data.content}`,
        })
        streamBuffer.value = ''
        streaming.value = false
        scrollToBottom()
      }
    } catch {
      // ignore parse errors
    }
  }

  ws.onclose = () => {
    connected.value = false
    streaming.value = false
    streamBuffer.value = ''
    scheduleReconnect()
  }

  ws.onerror = () => {
    connected.value = false
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    reconnectDelay = Math.min(reconnectDelay * 2, 16000)
    connect()
  }, reconnectDelay)
}

function send() {
  if (!draft.value.trim() || streaming.value || !ws || ws.readyState !== WebSocket.OPEN) return
  const content = draft.value.trim()
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content })
  draft.value = ''
  streaming.value = true
  streamBuffer.value = ''
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = '38px'
    }
    scrollToBottom()
  })
  ws.send(JSON.stringify({ type: 'message', content }))
}

function clearChat() {
  messages.value = []
}

watch(() => props.sessionId, (id) => {
  if (id) connect()
}, { immediate: false })

onMounted(() => {
  if (props.sessionId) connect()
})

onUnmounted(() => {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  ws?.close()
})
</script>
