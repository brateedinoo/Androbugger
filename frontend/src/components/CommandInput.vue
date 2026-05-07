<template>
  <div class="flex flex-col h-full bg-[#161925] border border-[#2a2d3e] rounded-lg overflow-hidden">
    <!-- Tabs -->
    <div class="flex border-b border-[#2a2d3e] flex-shrink-0">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        :class="['px-4 py-2.5 text-xs font-medium transition-colors border-b-2',
          activeTab === tab.id
            ? 'border-blue-500 text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-200']"
      >
        {{ tab.label }}
      </button>
      <div class="ml-auto flex items-center pr-3">
        <span class="text-xs text-slate-600 font-mono truncate max-w-[160px]">{{ deviceSerial }}</span>
      </div>
    </div>

    <!-- Natural Language tab -->
    <div v-if="activeTab === 'nl'" class="flex-1 flex flex-col overflow-hidden">
      <!-- Input -->
      <div class="p-3 border-b border-[#2a2d3e] flex-shrink-0">
        <div class="flex gap-2">
          <input
            v-model="nlQuery"
            @keydown.enter="translateCommand"
            placeholder="e.g. 'show last 50 crashes' or 'clear app cache for com.example'"
            class="flex-1 bg-[#0f1117] border border-[#2a2d3e] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
            :disabled="nlLoading"
          />
          <button
            @click="translateCommand"
            :disabled="!nlQuery.trim() || nlLoading"
            class="px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-[#2a2d3e] disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
          >
            {{ nlLoading ? '…' : 'Translate' }}
          </button>
        </div>
      </div>

      <!-- Translated commands -->
      <div class="flex-1 overflow-y-auto p-3 space-y-3 text-sm">
        <div v-if="!nlResult && !nlLoading" class="text-slate-600 text-xs text-center py-8">
          Describe what you want to do in plain English. The AI will translate it to ADB commands.
        </div>

        <div v-if="nlResult" class="space-y-2">
          <!-- Blocked commands warning -->
          <div v-if="nlResult.blocked_commands?.length" class="bg-red-900/30 border border-red-800 rounded-lg p-2 text-xs text-red-300">
            Blocked (insufficient role): {{ nlResult.blocked_commands.join(', ') }}
          </div>

          <!-- Command cards -->
          <div
            v-for="(cmd, i) in nlResult.commands"
            :key="i"
            class="bg-[#0f1117] border border-[#2a2d3e] rounded-lg p-3 space-y-2"
          >
            <div class="flex items-start justify-between gap-2">
              <code class="text-blue-300 text-xs break-all">$ {{ cmd.cmd }}</code>
              <span :class="['px-1.5 py-0.5 rounded text-xs flex-shrink-0',
                cmd.tier === 'read_only'    ? 'bg-green-900 text-green-300' :
                cmd.tier === 'state_changing' ? 'bg-yellow-900 text-yellow-300' :
                'bg-red-900 text-red-300']">
                {{ cmd.tier }}
              </span>
            </div>
            <p class="text-slate-400 text-xs">{{ cmd.explanation }}</p>
          </div>

          <!-- Confirmation gate -->
          <div v-if="nlResult.needs_confirmation && !execConfirmed" class="bg-yellow-900/20 border border-yellow-700 rounded-lg p-3 text-xs text-yellow-300 space-y-2">
            <p>⚠ Some commands modify device state. Review and confirm to proceed.</p>
            <button
              @click="execConfirmed = true; executeCommands()"
              class="px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 rounded text-white text-xs font-medium transition-colors"
            >
              Confirm &amp; Execute
            </button>
          </div>

          <!-- Execute button (no confirmation needed) -->
          <button
            v-if="!nlResult.needs_confirmation && nlResult.commands.length"
            @click="executeCommands"
            :disabled="execLoading"
            class="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-[#2a2d3e] rounded-lg text-sm font-medium transition-colors"
          >
            {{ execLoading ? 'Running…' : 'Run Commands' }}
          </button>
        </div>

        <!-- Execution results -->
        <div v-if="execResult" class="space-y-2">
          <div
            v-for="(r, i) in execResult.results"
            :key="i"
            class="bg-[#0f1117] border border-[#2a2d3e] rounded-lg p-3"
          >
            <p class="text-blue-300 text-xs font-mono mb-2">$ {{ r.command }}</p>
            <pre v-if="r.output" class="text-slate-300 text-xs whitespace-pre-wrap break-all">{{ r.output }}</pre>
            <p v-if="r.error" class="text-red-400 text-xs">Error: {{ r.error }}</p>
          </div>

          <!-- LLM interpretation -->
          <div v-if="execResult.interpretation" class="bg-blue-950/30 border border-blue-800 rounded-lg p-3">
            <p class="text-xs text-blue-400 font-medium mb-1">AI Interpretation</p>
            <p class="text-sm text-slate-300 leading-relaxed">{{ execResult.interpretation }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Raw Shell tab -->
    <div v-if="activeTab === 'raw'" class="flex-1 flex flex-col overflow-hidden">
      <div ref="terminalEl" class="flex-1 bg-[#0d0f14] p-2 overflow-hidden" />
      <div class="border-t border-[#2a2d3e] p-2 flex gap-2 flex-shrink-0">
        <span class="text-green-400 text-xs font-mono self-center">$</span>
        <input
          v-model="rawCommand"
          @keydown.enter="runRaw"
          @keydown.up="historyUp"
          @keydown.down="historyDown"
          placeholder="Raw ADB shell command (developer+ only)"
          class="flex-1 bg-transparent border-none outline-none text-sm text-slate-200 font-mono placeholder-slate-700"
          :disabled="rawLoading"
          ref="rawInputEl"
        />
        <button
          @click="runRaw"
          :disabled="!rawCommand.trim() || rawLoading"
          class="text-xs text-slate-500 hover:text-slate-300 px-2 py-1 rounded hover:bg-[#2a2d3e] transition-colors"
        >
          Run
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  deviceSerial: string
}>()

const auth = useAuthStore()

const tabs = [
  { id: 'nl', label: 'Natural Language' },
  { id: 'raw', label: 'Raw Shell' },
]
const activeTab = ref('nl')

// --- Natural language tab ---
const nlQuery = ref('')
const nlLoading = ref(false)
const nlResult = ref<{
  commands: Array<{ cmd: string; tier: string; explanation: string; requires_confirmation: boolean; destructive: boolean }>
  needs_confirmation: boolean
  blocked_commands: string[]
} | null>(null)
const execConfirmed = ref(false)
const execLoading = ref(false)
const execResult = ref<{
  results: Array<{ command: string; output: string | null; error: string | null }>
  interpretation: string
} | null>(null)

async function translateCommand() {
  if (!nlQuery.value.trim() || nlLoading.value) return
  nlLoading.value = true
  nlResult.value = null
  execResult.value = null
  execConfirmed.value = false
  try {
    nlResult.value = await $fetch('/api/commands/natural', {
      method: 'POST',
      body: { device_serial: props.deviceSerial, query: nlQuery.value },
      headers: auth.authHeaders(),
    })
    if (!nlResult.value?.needs_confirmation && nlResult.value?.commands.length) {
      // auto-execute read-only commands
      const allReadOnly = nlResult.value.commands.every(c => c.tier === 'read_only')
      if (allReadOnly) {
        await executeCommands()
      }
    }
  } catch (e: any) {
    nlResult.value = { commands: [], needs_confirmation: false, blocked_commands: [`Error: ${e.message}`] }
  } finally {
    nlLoading.value = false
  }
}

async function executeCommands() {
  if (!nlResult.value?.commands.length) return
  execLoading.value = true
  try {
    execResult.value = await $fetch('/api/commands/execute', {
      method: 'POST',
      body: {
        device_serial: props.deviceSerial,
        commands: nlResult.value.commands,
        confirmed: execConfirmed.value,
      },
      headers: auth.authHeaders(),
    })
  } catch (e: any) {
    execResult.value = { results: [{ command: '(execute)', output: null, error: e.message }], interpretation: '' }
  } finally {
    execLoading.value = false
  }
}

// --- Raw shell tab ---
const terminalEl = ref<HTMLElement | null>(null)
const rawInputEl = ref<HTMLInputElement | null>(null)
const rawCommand = ref('')
const rawLoading = ref(false)
const rawHistory: string[] = []
let histIdx = -1

let Terminal: any = null
let term: any = null

async function initTerminal() {
  if (!terminalEl.value || term) return
  try {
    const xterm = await import('xterm')
    Terminal = xterm.Terminal
    const { FitAddon } = await import('@xterm/addon-fit')
    term = new Terminal({
      theme: { background: '#0d0f14', foreground: '#cdd6f4', cursor: '#cdd6f4', selectionBackground: '#313244' },
      fontFamily: 'JetBrains Mono, Fira Mono, monospace',
      fontSize: 12,
      lineHeight: 1.4,
      cursorBlink: false,
      disableStdin: true,
      scrollback: 2000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(terminalEl.value)
    fit.fit()
    term.writeln('\x1b[32mAndrobugger Raw Shell\x1b[0m — \x1b[33mDeveloper access required\x1b[0m')
    term.writeln('Commands run via ADB shell on the connected device.\r\n')
    const ro = new ResizeObserver(() => fit.fit())
    ro.observe(terminalEl.value!)
  } catch {
    // xterm not available; degrade gracefully
  }
}

watch(activeTab, (tab) => {
  if (tab === 'raw') {
    nextTick(initTerminal)
  }
})

async function runRaw() {
  const cmd = rawCommand.value.trim()
  if (!cmd || rawLoading.value) return
  rawHistory.unshift(cmd)
  if (rawHistory.length > 50) rawHistory.pop()
  histIdx = -1
  rawCommand.value = ''
  rawLoading.value = true
  if (term) {
    term.writeln(`\x1b[32m$ \x1b[0m${cmd}`)
  }
  try {
    const data = await $fetch('/api/commands/raw', {
      method: 'POST',
      body: { device_serial: props.deviceSerial, command: cmd },
      headers: auth.authHeaders(),
    })
    if (term) {
      const lines = (data.output || '(no output)').split('\n')
      for (const line of lines) {
        term.writeln(line)
      }
    }
  } catch (e: any) {
    if (term) term.writeln(`\x1b[31mError: ${e.data?.detail || e.message}\x1b[0m`)
  } finally {
    rawLoading.value = false
  }
}

function historyUp() {
  if (rawHistory.length === 0) return
  histIdx = Math.min(histIdx + 1, rawHistory.length - 1)
  rawCommand.value = rawHistory[histIdx]
}

function historyDown() {
  if (histIdx <= 0) { histIdx = -1; rawCommand.value = ''; return }
  histIdx--
  rawCommand.value = rawHistory[histIdx]
}

onUnmounted(() => {
  term?.dispose()
})
</script>
