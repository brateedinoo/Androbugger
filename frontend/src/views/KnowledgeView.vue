<template>
  <div class="min-h-screen bg-[#0f1117] text-white">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-xl font-bold">Knowledge Base</h1>
      <button
        v-if="canContribute"
        @click="showAdd = true"
        class="ml-auto bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg"
      >+ Add Entry</button>
    </header>

    <main class="p-6 max-w-5xl mx-auto space-y-6">
      <!-- Filters -->
      <div class="flex flex-wrap gap-3 items-center">
        <input
          v-model="q" @input="debouncedLoad"
          placeholder="Search entries…"
          class="bg-[#1a1d2e] border border-[#2a2d3e] rounded-lg px-3 py-1.5 text-sm flex-1 min-w-48"
        />
        <div class="flex gap-1">
          <button
            v-for="ns in namespaces" :key="ns.value"
            @click="filterNs = ns.value; loadEntries()"
            :class="filterNs === ns.value
              ? 'bg-blue-600 text-white'
              : 'bg-[#1a1d2e] text-slate-400 hover:text-white'"
            class="text-xs px-3 py-1.5 rounded-lg transition"
          >{{ ns.label }}</button>
        </div>
      </div>

      <!-- Entry list -->
      <div v-if="loading" class="text-slate-500">Loading…</div>
      <div v-else-if="entries.length === 0" class="text-slate-500 text-sm">No entries found.</div>
      <div v-else class="space-y-3">
        <div
          v-for="entry in entries" :key="entry.id"
          class="bg-[#1a1d2e] border border-[#2a2d3e] rounded-xl p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <h3 class="font-semibold truncate">{{ entry.title }}</h3>
                <span :class="nsBadgeClass(entry.namespace)"
                  class="text-[10px] px-2 py-0.5 rounded-full">
                  {{ entry.namespace.replace('_', ' ') }}
                </span>
                <span v-if="entry.is_manual"
                  class="text-[10px] px-2 py-0.5 rounded-full bg-purple-900/40 text-purple-300">
                  manual
                </span>
              </div>
              <p class="text-slate-400 text-xs mt-1">Added {{ fmtDate(entry.indexed_at) }}</p>
            </div>

            <!-- Vote buttons -->
            <div class="flex items-center gap-1 shrink-0">
              <button @click="vote(entry.id, true)"
                class="flex items-center gap-1 text-xs text-slate-400 hover:text-green-400 transition px-2 py-1 rounded hover:bg-green-900/20">
                👍 {{ entry.helpful_votes }}
              </button>
              <button @click="vote(entry.id, false)"
                class="flex items-center gap-1 text-xs text-slate-400 hover:text-red-400 transition px-2 py-1 rounded hover:bg-red-900/20">
                👎 {{ entry.unhelpful_votes }}
              </button>

              <!-- Edit / Delete -->
              <button
                v-if="canEdit(entry)"
                @click="startEdit(entry)"
                class="text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-[#2a2d3e]"
              >Edit</button>
              <button
                v-if="auth.user?.role === 'admin'"
                @click="deleteEntry(entry.id)"
                class="text-xs text-red-500 hover:text-red-400 px-2 py-1 rounded hover:bg-red-900/20"
              >Delete</button>
            </div>
          </div>

          <!-- Helpful bar -->
          <div v-if="entry.helpful_votes + entry.unhelpful_votes > 0"
            class="mt-2 h-1.5 bg-[#2a2d3e] rounded-full overflow-hidden">
            <div class="h-full bg-green-500 rounded-full"
              :style="`width: ${helpfulPct(entry)}%`">
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div class="flex items-center gap-3 text-sm text-slate-400">
        <button :disabled="page <= 1" @click="page--; loadEntries()"
          class="disabled:opacity-30 hover:text-white transition">← Prev</button>
        <span>Page {{ page }} / {{ Math.ceil(total / pageSize) || 1 }}</span>
        <button :disabled="page * pageSize >= total" @click="page++; loadEntries()"
          class="disabled:opacity-30 hover:text-white transition">Next →</button>
      </div>
    </main>

    <!-- Add / Edit modal -->
    <div v-if="showAdd || editingEntry"
      class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div class="bg-[#1a1d2e] rounded-xl p-6 w-full max-w-xl space-y-4">
        <h2 class="text-lg font-semibold">{{ editingEntry ? 'Edit Entry' : 'Add Knowledge Entry' }}</h2>

        <div>
          <label class="block text-sm text-slate-400 mb-1">Title</label>
          <input v-model="form.title"
            class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded-lg px-3 py-2 text-sm" />
        </div>
        <div v-if="!editingEntry">
          <label class="block text-sm text-slate-400 mb-1">Namespace</label>
          <select v-model="form.namespace"
            class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded-lg px-3 py-2 text-sm">
            <option value="manual">Manual</option>
            <option value="vendor_docs">Vendor Docs</option>
            <option value="aosp_reference">AOSP Reference</option>
          </select>
        </div>
        <div>
          <label class="block text-sm text-slate-400 mb-1">Content</label>
          <textarea v-model="form.content" rows="8"
            class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded-lg px-3 py-2 text-sm font-mono resize-y">
          </textarea>
        </div>

        <p v-if="modalError" class="text-red-400 text-sm">{{ modalError }}</p>

        <div class="flex gap-3 justify-end">
          <button @click="closeModal"
            class="text-sm text-slate-400 hover:text-white px-4 py-2">Cancel</button>
          <button @click="submitEntry" :disabled="saving"
            class="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const entries = ref<any[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const q = ref('')
const filterNs = ref('')

const showAdd = ref(false)
const editingEntry = ref<any>(null)
const form = ref({ title: '', content: '', namespace: 'manual' })
const saving = ref(false)
const modalError = ref('')

let debounceTimer: ReturnType<typeof setTimeout>

const namespaces = [
  { value: '', label: 'All' },
  { value: 'vendor_docs', label: 'Vendor Docs' },
  { value: 'past_diagnoses', label: 'Past Diagnoses' },
  { value: 'aosp_reference', label: 'AOSP' },
  { value: 'manual', label: 'Manual' },
]

const canContribute = computed(() =>
  ['developer', 'admin'].includes(auth.user?.role ?? '')
)

function canEdit(entry: any): boolean {
  if (auth.user?.role === 'admin') return true
  return auth.user?.role === 'developer' && entry.author_id === auth.user?.id
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.token}`,
      ...(options.headers as Record<string, string> ?? {}),
    },
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function loadEntries() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (q.value) params.set('q', q.value)
    if (filterNs.value) params.set('namespace', filterNs.value)
    const data = await apiFetch(`/api/knowledge/entries?${params}`)
    entries.value = data.entries ?? []
    total.value = data.total ?? 0
  } catch { entries.value = [] }
  finally { loading.value = false }
}

function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { page.value = 1; loadEntries() }, 300)
}

async function vote(id: string, helpful: boolean) {
  try {
    await apiFetch(`/api/knowledge/entries/${id}/feedback?helpful=${helpful}`, { method: 'POST' })
    await loadEntries()
  } catch { /* ignore */ }
}

function startEdit(entry: any) {
  editingEntry.value = entry
  form.value = { title: entry.title, content: entry.metadata ?? '', namespace: entry.namespace }
}

function closeModal() {
  showAdd.value = false
  editingEntry.value = null
  form.value = { title: '', content: '', namespace: 'manual' }
  modalError.value = ''
}

async function submitEntry() {
  if (!form.value.title.trim() || !form.value.content.trim()) {
    modalError.value = 'Title and content are required.'
    return
  }
  saving.value = true
  modalError.value = ''
  try {
    if (editingEntry.value) {
      await apiFetch(`/api/knowledge/entries/${editingEntry.value.id}`, {
        method: 'PUT',
        body: JSON.stringify({ title: form.value.title, content: form.value.content }),
      })
    } else {
      await apiFetch('/api/knowledge/entries', {
        method: 'POST',
        body: JSON.stringify(form.value),
      })
    }
    closeModal()
    await loadEntries()
  } catch (e: any) {
    modalError.value = e.message || 'Save failed.'
  } finally {
    saving.value = false
  }
}

async function deleteEntry(id: string) {
  if (!confirm('Delete this knowledge entry?')) return
  try {
    await apiFetch(`/api/knowledge/entries/${id}`, { method: 'DELETE' })
    await loadEntries()
  } catch { /* ignore */ }
}

function helpfulPct(entry: any): number {
  const total = entry.helpful_votes + entry.unhelpful_votes
  return total ? Math.round((entry.helpful_votes / total) * 100) : 0
}

function nsBadgeClass(ns: string): string {
  const map: Record<string, string> = {
    vendor_docs: 'bg-blue-900/40 text-blue-300',
    past_diagnoses: 'bg-green-900/40 text-green-300',
    aosp_reference: 'bg-orange-900/40 text-orange-300',
    manual: 'bg-purple-900/40 text-purple-300',
  }
  return map[ns] ?? 'bg-slate-700 text-slate-300'
}

function fmtDate(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString()
}

onMounted(loadEntries)
</script>
