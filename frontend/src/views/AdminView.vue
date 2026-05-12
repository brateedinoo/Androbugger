<template>
  <div class="min-h-screen bg-[#0f1117] text-white flex flex-col">
    <header class="border-b border-[#2a2d3e] px-6 py-3 flex items-center gap-4">
      <RouterLink to="/" class="text-slate-400 hover:text-white text-sm">← Dashboard</RouterLink>
      <h1 class="text-lg font-semibold">Admin</h1>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar tabs -->
      <nav class="w-48 border-r border-[#2a2d3e] p-3 space-y-1 flex-shrink-0">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="['w-full text-left px-3 py-2 rounded-lg text-sm transition',
            activeTab === tab.id
              ? 'bg-blue-600 text-white font-medium'
              : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e2130]']"
        >
          {{ tab.label }}
        </button>
      </nav>

      <!-- Content area -->
      <div class="flex-1 overflow-y-auto p-6">

        <!-- Stats tab -->
        <div v-if="activeTab === 'stats'" class="space-y-6 max-w-3xl">
          <h2 class="text-base font-semibold">System Overview</h2>
          <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div v-for="s in statCards" :key="s.label" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 text-center">
              <p class="text-2xl font-bold text-blue-400">{{ s.value }}</p>
              <p class="text-slate-500 text-xs mt-0.5">{{ s.label }}</p>
            </div>
          </div>

          <!-- Activity chart (sparkline via bars) -->
          <div v-if="stats?.activity_7d?.length" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5">
            <h3 class="text-sm font-medium text-slate-300 mb-4">Activity (Last 7 Days)</h3>
            <div class="flex items-end gap-1.5 h-20">
              <div
                v-for="day in stats.activity_7d"
                :key="day.day"
                class="flex-1 bg-blue-500 rounded-t"
                :style="{ height: `${Math.max(8, (day.count / maxActivity) * 100)}%` }"
                :title="`${day.day}: ${day.count} events`"
              />
            </div>
            <div class="flex justify-between text-xs text-slate-600 mt-1">
              <span>{{ stats.activity_7d[0]?.day?.slice(5) }}</span>
              <span>{{ stats.activity_7d[stats.activity_7d.length - 1]?.day?.slice(5) }}</span>
            </div>
          </div>
        </div>

        <!-- Users tab -->
        <div v-if="activeTab === 'users'" class="space-y-5 max-w-3xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold">Users</h2>
            <button @click="showCreateUser = !showCreateUser"
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition">
              + New User
            </button>
          </div>

          <!-- Create user form -->
          <div v-if="showCreateUser" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-3">
            <h3 class="text-sm font-medium text-slate-300">Create User</h3>
            <div class="grid grid-cols-3 gap-3">
              <input v-model="newUser.username" placeholder="Username"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              <input v-model="newUser.password" type="password" placeholder="Password"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              <select v-model="newUser.role"
                class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500">
                <option v-for="r in roles" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
            <div class="flex gap-2">
              <button @click="createUser" :disabled="!newUser.username || !newUser.password || userLoading"
                class="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm transition">
                {{ userLoading ? 'Creating…' : 'Create' }}
              </button>
              <button @click="showCreateUser = false" class="px-4 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 text-sm hover:text-slate-200 transition">Cancel</button>
            </div>
            <p v-if="userError" class="text-red-400 text-sm">{{ userError }}</p>
          </div>

          <!-- User table -->
          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl overflow-hidden">
            <table class="w-full text-sm">
              <thead class="border-b border-[#2a2d3e] text-slate-400 text-xs">
                <tr>
                  <th class="px-4 py-3 text-left">Username</th>
                  <th class="px-4 py-3 text-left">Role</th>
                  <th class="px-4 py-3 text-left">Last Login</th>
                  <th class="px-4 py-3 text-left">Created</th>
                  <th class="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in users" :key="u.id" class="border-b border-[#2a2d3e] last:border-0">
                  <td class="px-4 py-3 font-medium">{{ u.username }}</td>
                  <td class="px-4 py-3">
                    <select :value="u.role" @change="changeRole(u.id, ($event.target as HTMLSelectElement).value)"
                      class="bg-transparent border border-[#2a2d3e] rounded px-2 py-0.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500">
                      <option v-for="r in roles" :key="r" :value="r">{{ r }}</option>
                    </select>
                  </td>
                  <td class="px-4 py-3 text-slate-400 text-xs">{{ u.last_login?.slice(0, 16).replace('T', ' ') || '—' }}</td>
                  <td class="px-4 py-3 text-slate-400 text-xs">{{ u.created_at?.slice(0, 10) }}</td>
                  <td class="px-4 py-3 text-right">
                    <button v-if="u.id !== currentUserId" @click="deleteUser(u.id)"
                      class="text-xs text-red-500 hover:text-red-300 transition">Delete</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Audit log tab -->
        <div v-if="activeTab === 'audit'" class="space-y-4 max-w-5xl">
          <div class="flex items-center gap-3 flex-wrap">
            <h2 class="text-base font-semibold">Audit Log</h2>
            <div class="flex gap-2 ml-auto flex-wrap">
              <input v-model="auditFilters.action" @keyup.enter="loadAudit" placeholder="Filter action…"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none focus:border-blue-500 w-36" />
              <select v-model="auditFilters.severity" @change="loadAudit"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none">
                <option value="">All severity</option>
                <option>info</option><option>warning</option><option>error</option>
              </select>
              <select v-model="auditFilters.days" @change="loadAudit"
                class="px-3 py-1.5 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-300 text-xs focus:outline-none">
                <option :value="7">Last 7 days</option>
                <option :value="30">Last 30 days</option>
                <option :value="90">Last 90 days</option>
              </select>
              <button @click="exportAudit"
                class="px-3 py-1.5 rounded-lg border border-[#2a2d3e] text-slate-400 hover:text-slate-200 text-xs transition">
                ↓ CSV
              </button>
              <button @click="pruneAudit"
                class="px-3 py-1.5 rounded-lg border border-red-800 text-red-400 hover:text-red-300 text-xs transition">
                Prune old
              </button>
            </div>
          </div>

          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl overflow-hidden">
            <table class="w-full text-xs font-mono">
              <thead class="border-b border-[#2a2d3e] text-slate-500">
                <tr>
                  <th class="px-3 py-2.5 text-left">Time</th>
                  <th class="px-3 py-2.5 text-left">Action</th>
                  <th class="px-3 py-2.5 text-left">Severity</th>
                  <th class="px-3 py-2.5 text-left">Device</th>
                  <th class="px-3 py-2.5 text-left">Detail</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in auditEntries" :key="e.id" class="border-b border-[#2a2d3e] last:border-0 hover:bg-[#1e2130]">
                  <td class="px-3 py-2 text-slate-500 whitespace-nowrap">{{ e.timestamp?.slice(0, 19).replace('T', ' ') }}</td>
                  <td class="px-3 py-2 text-slate-300">{{ e.action }}</td>
                  <td class="px-3 py-2">
                    <span :class="severityBadge(e.severity)" class="px-1.5 py-0.5 rounded text-[10px]">{{ e.severity }}</span>
                  </td>
                  <td class="px-3 py-2 text-slate-500 max-w-[120px] truncate">{{ e.device_serial || '—' }}</td>
                  <td class="px-3 py-2 text-slate-500 max-w-[240px] truncate">{{ formatDetail(e.detail) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-if="!auditEntries.length && !auditLoading" class="text-slate-500 text-sm text-center py-8">No entries found</p>
          </div>

          <!-- Pagination -->
          <div class="flex items-center justify-between text-xs text-slate-500">
            <span>{{ auditTotal }} total entries</span>
            <div class="flex gap-2">
              <button @click="auditPage = Math.max(1, auditPage - 1); loadAudit()" :disabled="auditPage <= 1"
                class="px-3 py-1 rounded border border-[#2a2d3e] disabled:opacity-40 hover:border-blue-500 transition">← Prev</button>
              <span class="px-3 py-1">Page {{ auditPage }}</span>
              <button @click="auditPage++; loadAudit()" :disabled="auditEntries.length < auditPerPage"
                class="px-3 py-1 rounded border border-[#2a2d3e] disabled:opacity-40 hover:border-blue-500 transition">Next →</button>
            </div>
          </div>
        </div>

        <!-- LLM providers tab -->
        <div v-if="activeTab === 'llm'" class="space-y-5 max-w-2xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold">LLM Providers</h2>
            <button @click="showAddProvider = !showAddProvider"
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition">
              + Add Provider
            </button>
          </div>

          <!-- Add provider form -->
          <div v-if="showAddProvider" class="bg-[#161925] border border-blue-700 rounded-xl p-5 space-y-4">
            <h3 class="text-sm font-medium text-slate-300">New Provider</h3>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="text-xs text-slate-500 mb-1 block">Type</label>
                <select v-model="newProvider.provider_type"
                  @change="newProvider.is_local = ['ollama','vllm'].includes(newProvider.provider_type); newProviderModels = []; newProvider.model_name = ''"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="ollama">Ollama</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="openai">OpenAI</option>
                  <option value="vllm">vLLM</option>
                </select>
              </div>
              <div v-if="newProvider.is_local">
                <label class="text-xs text-slate-500 mb-1 block">Endpoint URL</label>
                <input v-model="newProvider.endpoint_url" placeholder="http://192.168.1.50:11434"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
            </div>
            <div>
              <label class="text-xs text-slate-500 mb-1 block">Model</label>
              <div class="flex gap-2">
                <select v-if="newProviderModels.length" v-model="newProvider.model_name"
                  class="flex-1 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500">
                  <option v-for="m in newProviderModels" :key="m" :value="m">{{ m }}</option>
                </select>
                <input v-else v-model="newProvider.model_name"
                  :placeholder="newProviderModelsLoading ? 'Loading…' : 'e.g. qwen3:14b'"
                  :disabled="newProviderModelsLoading"
                  class="flex-1 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50" />
                <button @click="fetchNewProviderModels" :disabled="newProviderModelsLoading"
                  class="px-3 py-2 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-400 text-xs hover:border-blue-500 disabled:opacity-50 transition whitespace-nowrap">
                  {{ newProviderModelsLoading ? '…' : 'Fetch models' }}
                </button>
              </div>
              <p v-if="newProviderModelsError" class="text-amber-400 text-xs mt-1">{{ newProviderModelsError }}</p>
            </div>
            <div>
              <label class="text-xs text-slate-500 mb-1 block">Max tokens</label>
              <input v-model.number="newProvider.max_tokens" type="number" min="256" max="200000"
                class="w-32 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div class="flex gap-2">
              <button @click="addProvider" :disabled="!newProvider.model_name || providerSaving"
                class="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm transition">
                {{ providerSaving ? 'Adding…' : 'Add Provider' }}
              </button>
              <button @click="showAddProvider = false"
                class="px-4 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 text-sm hover:text-slate-200 transition">
                Cancel
              </button>
            </div>
          </div>

          <!-- Provider cards -->
          <div class="space-y-3">
            <div v-for="p in providers" :key="p.id"
              class="bg-[#161925] border border-[#2a2d3e] rounded-xl overflow-hidden">
              <!-- Card header -->
              <div class="p-4 flex items-center gap-3 cursor-pointer select-none" @click="toggleExpand(p.id)">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-medium text-sm capitalize">{{ p.provider_type }}</span>
                    <span v-if="p.is_default" class="px-1.5 py-0.5 rounded text-[10px] bg-yellow-900 text-yellow-300">Default</span>
                    <span class="text-slate-500 text-xs truncate">{{ p.model_name }}</span>
                  </div>
                  <p v-if="p.endpoint_url && p.is_local" class="text-slate-600 text-xs mt-0.5 truncate">{{ p.endpoint_url }}</p>
                </div>
                <div class="flex items-center gap-3 flex-shrink-0">
                  <div @click.stop="toggleProviderEnabled(p)"
                    :class="['w-10 h-5 rounded-full transition-colors relative cursor-pointer',
                      p.is_enabled ? 'bg-blue-600' : 'bg-[#2a2d3e]']">
                    <div :class="['w-4 h-4 bg-white rounded-full absolute top-0.5 transition-transform',
                      p.is_enabled ? 'translate-x-5' : 'translate-x-0.5']" />
                  </div>
                  <span class="text-slate-600 text-xs w-2">{{ expandedProvider === p.id ? '▲' : '▼' }}</span>
                </div>
              </div>

              <!-- Expanded edit form -->
              <div v-if="expandedProvider === p.id" class="border-t border-[#2a2d3e] p-4 space-y-4">
                <div v-if="p.is_local">
                  <label class="text-xs text-slate-500 mb-1 block">Endpoint URL</label>
                  <input v-model="providerEdits[p.id].endpoint_url"
                    placeholder="http://ollama:11434"
                    @blur="onEndpointBlur(p)"
                    class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label class="text-xs text-slate-500 mb-1 block">Model</label>
                  <div class="flex gap-2">
                    <select v-if="providerModels[p.id]?.length" v-model="providerEdits[p.id].model_name"
                      class="flex-1 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500">
                      <option v-for="m in providerModels[p.id]" :key="m" :value="m">{{ m }}</option>
                    </select>
                    <input v-else v-model="providerEdits[p.id].model_name"
                      :placeholder="providerModelsLoading[p.id] ? 'Loading models…' : 'Model name'"
                      :disabled="!!providerModelsLoading[p.id]"
                      class="flex-1 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50" />
                    <button @click="loadProviderModels(p)" :disabled="!!providerModelsLoading[p.id]"
                      class="px-3 py-2 rounded-lg bg-[#1e2130] border border-[#2a2d3e] text-slate-400 text-xs hover:border-blue-500 disabled:opacity-50 transition whitespace-nowrap">
                      {{ providerModelsLoading[p.id] ? '…' : '↻ Refresh' }}
                    </button>
                  </div>
                  <p v-if="providerModelsError[p.id]" class="text-amber-400 text-xs mt-1">{{ providerModelsError[p.id] }}</p>
                </div>
                <div>
                  <label class="text-xs text-slate-500 mb-1 block">Max tokens</label>
                  <input v-model.number="providerEdits[p.id].max_tokens" type="number" min="256" max="200000"
                    class="w-32 px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div class="flex gap-2 flex-wrap items-center">
                  <button @click="saveProvider(p)" :disabled="providerSaving"
                    class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm transition">
                    {{ providerSaving ? 'Saving…' : 'Save' }}
                  </button>
                  <button v-if="!p.is_default" @click="setDefault(p)" :disabled="providerSaving"
                    class="px-4 py-2 rounded-lg border border-yellow-700 text-yellow-400 hover:bg-yellow-900/30 disabled:opacity-50 text-sm transition">
                    Set as default
                  </button>
                  <button v-if="!p.is_default" @click="deleteProvider(p)"
                    class="px-4 py-2 rounded-lg border border-red-800 text-red-400 hover:bg-red-900/30 text-sm transition ml-auto">
                    Delete
                  </button>
                </div>
                <p v-if="providerSaveError" class="text-red-400 text-xs">{{ providerSaveError }}</p>
              </div>
            </div>
            <p v-if="!providers.length" class="text-slate-500 text-sm">No providers configured</p>
          </div>
        </div>

        <!-- Fine-tuning tab -->
        <div v-if="activeTab === 'finetune'" class="space-y-6 max-w-2xl">
          <h2 class="text-base font-semibold">Fine-Tuning Data</h2>

          <!-- Stats cards -->
          <div v-if="finetuneStats" class="grid grid-cols-2 gap-4">
            <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 text-center">
              <p class="text-3xl font-bold text-blue-400">{{ finetuneStats.exportable_sessions }}</p>
              <p class="text-slate-500 text-sm mt-1">Exportable Sessions</p>
              <p class="text-slate-600 text-xs mt-0.5">resolved with root cause, fix, and LLM report</p>
            </div>
            <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 text-center">
              <p v-if="finetuneStats.last_export" class="text-sm font-medium text-green-400">
                {{ finetuneStats.last_export.record_count }} records
              </p>
              <p v-else class="text-2xl font-bold text-slate-500">—</p>
              <p class="text-slate-500 text-sm mt-1">Last Export</p>
              <p v-if="finetuneStats.last_export" class="text-slate-600 text-xs mt-0.5 truncate">
                {{ finetuneStats.last_export.exported_at?.slice(0, 19).replace('T', ' ') }}
              </p>
              <p v-else class="text-slate-600 text-xs mt-0.5">never exported</p>
            </div>
          </div>

          <!-- Export form -->
          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-4">
            <h3 class="text-sm font-medium text-slate-300">Export Training Data</h3>
            <div class="space-y-3">
              <div>
                <label class="block text-xs text-slate-500 mb-1">Output Path</label>
                <input v-model="exportPath" placeholder="/tmp/androbugger-training.jsonl"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500 font-mono" />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Min Quality Filter</label>
                <select v-model="exportMinQuality"
                  class="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none">
                  <option :value="0.0">All (no filter)</option>
                  <option :value="0.5">≥ 0.5</option>
                  <option :value="0.8">≥ 0.8</option>
                </select>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <button @click="exportFinetuneData" :disabled="exportLoading || !finetuneStats?.exportable_sessions"
                class="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition">
                {{ exportLoading ? 'Exporting…' : 'Export Training Data' }}
              </button>
              <p v-if="exportResult" class="text-green-400 text-sm">
                ✓ {{ exportResult.record_count }} records exported ({{ exportResult.skipped_count }} skipped)
              </p>
              <p v-if="exportError" class="text-red-400 text-sm">{{ exportError }}</p>
            </div>
          </div>

          <!-- Docs link -->
          <div class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 text-sm text-slate-400">
            See <code class="text-slate-300">docs/fine-tuning-guide.md</code> for the Unsloth/LoRA fine-tuning workflow, GGUF conversion, and Ollama Modelfile template.
          </div>
        </div>

        <!-- Scheduled diagnostics tab -->
        <div v-if="activeTab === 'scheduled'" class="space-y-5 max-w-3xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold">Scheduled Diagnostics</h2>
            <button @click="showCreateSchedule = !showCreateSchedule"
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition">
              + New Schedule
            </button>
          </div>

          <!-- Create schedule form -->
          <div v-if="showCreateSchedule" class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-5 space-y-4">
            <h3 class="text-sm font-medium text-slate-300">New Scheduled Diagnostic</h3>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-slate-500 mb-1">Name</label>
                <input v-model="newSchedule.name" placeholder="e.g. Nightly device check"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Cron Expression</label>
                <input v-model="newSchedule.cron_expr" placeholder="0 2 * * *"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm font-mono focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Device Serial (optional)</label>
                <input v-model="newSchedule.device_serial" placeholder="Leave blank for group"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-white text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Template</label>
                <select v-model="newSchedule.template_id"
                  class="w-full px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2a2d3e] text-slate-300 text-sm focus:outline-none">
                  <option value="">Default</option>
                  <option value="performance">Performance Focus</option>
                  <option value="crash">Crash Investigation</option>
                  <option value="network">Network Diagnostic</option>
                </select>
              </div>
            </div>
            <div class="flex gap-2">
              <button @click="createSchedule" :disabled="!newSchedule.name || !newSchedule.cron_expr || scheduleLoading"
                class="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm transition">
                {{ scheduleLoading ? 'Creating…' : 'Create' }}
              </button>
              <button @click="showCreateSchedule = false"
                class="px-4 py-2 rounded-lg border border-[#2a2d3e] text-slate-400 text-sm hover:text-slate-200 transition">Cancel</button>
            </div>
            <p v-if="scheduleError" class="text-red-400 text-sm">{{ scheduleError }}</p>
          </div>

          <!-- Schedule list -->
          <div class="space-y-2">
            <div v-for="s in schedules" :key="s.id"
              class="bg-[#161925] border border-[#2a2d3e] rounded-xl p-4 flex items-center justify-between gap-4">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-sm truncate">{{ s.name }}</span>
                  <span :class="s.enabled ? 'bg-green-900 text-green-300' : 'bg-slate-800 text-slate-400'"
                    class="px-1.5 py-0.5 rounded text-[10px]">{{ s.enabled ? 'enabled' : 'disabled' }}</span>
                </div>
                <div class="flex gap-4 text-xs text-slate-500 mt-1">
                  <span class="font-mono">{{ s.cron_expr }}</span>
                  <span v-if="s.device_serial">device: {{ s.device_serial }}</span>
                  <span v-if="s.template_id">template: {{ s.template_id }}</span>
                  <span v-if="s.next_run_at">next: {{ s.next_run_at?.slice(0, 16).replace('T', ' ') }}</span>
                  <span v-if="s.last_run_at">last: {{ s.last_run_at?.slice(0, 16).replace('T', ' ') }}</span>
                </div>
              </div>
              <button @click="deleteSchedule(s.id)" class="text-xs text-red-500 hover:text-red-300 flex-shrink-0 transition">Delete</button>
            </div>
            <p v-if="!schedules.length" class="text-slate-500 text-sm text-center py-8">No scheduled diagnostics configured</p>
          </div>
        </div>

        <!-- ── Integrations tab ───────────────────────────────── -->
        <div v-if="activeTab === 'integrations'" class="space-y-6 max-w-4xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold">Webhook Endpoints</h2>
            <button @click="showAddWebhook = true"
              class="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg">
              + Add Webhook
            </button>
          </div>

          <div v-if="webhooks.length === 0" class="text-slate-500 text-sm text-center py-8">
            No webhook endpoints configured.
          </div>

          <div class="space-y-3">
            <div v-for="wh in webhooks" :key="wh.id"
              class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4 space-y-2">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="font-semibold text-sm">{{ wh.name }}</p>
                  <p class="text-slate-400 text-xs font-mono truncate max-w-xs">{{ wh.url }}</p>
                  <div class="flex flex-wrap gap-1 mt-1">
                    <span v-for="ev in parseEvents(wh.events)" :key="ev"
                      class="text-[10px] bg-blue-900/40 text-blue-300 px-2 py-0.5 rounded-full">{{ ev }}</span>
                    <span v-if="!parseEvents(wh.events).length" class="text-slate-600 text-xs">no events</span>
                  </div>
                </div>
                <div class="flex gap-2 shrink-0">
                  <button @click="testWebhook(wh.id)"
                    class="text-xs border border-[#2a2d3e] hover:border-blue-500 text-slate-400 hover:text-slate-200 px-2 py-1 rounded transition">
                    Test
                  </button>
                  <button @click="toggleWebhookEnabled(wh)"
                    :class="wh.enabled ? 'text-green-400 hover:text-slate-300' : 'text-slate-500 hover:text-green-400'"
                    class="text-xs px-2 py-1 rounded transition">
                    {{ wh.enabled ? '● On' : '○ Off' }}
                  </button>
                  <button @click="deleteWebhook(wh.id)"
                    class="text-xs text-red-500 hover:text-red-400 px-2 py-1 rounded transition">Delete</button>
                </div>
              </div>
              <p v-if="webhookTestResult[wh.id]" class="text-xs"
                :class="webhookTestResult[wh.id].ok ? 'text-green-400' : 'text-red-400'">
                {{ webhookTestResult[wh.id].ok
                  ? `✓ HTTP ${webhookTestResult[wh.id].status}`
                  : `✗ ${webhookTestResult[wh.id].error}` }}
              </p>
            </div>
          </div>

          <!-- Add webhook modal -->
          <div v-if="showAddWebhook"
            class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
            <div class="bg-[#1a1d2e] rounded-xl p-6 w-full max-w-md space-y-4">
              <h3 class="font-semibold">Add Webhook</h3>
              <input v-model="newWebhook.name" placeholder="Name"
                class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded px-3 py-2 text-sm" />
              <input v-model="newWebhook.url" placeholder="https://example.com/webhook"
                class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded px-3 py-2 text-sm" />
              <input v-model="newWebhook.secret" placeholder="HMAC secret (optional)"
                class="w-full bg-[#0f1117] border border-[#2a2d3e] rounded px-3 py-2 text-sm" />
              <div>
                <p class="text-slate-400 text-xs mb-2">Events:</p>
                <div class="flex flex-wrap gap-2">
                  <label v-for="ev in availableEvents" :key="ev" class="flex items-center gap-1 text-xs text-slate-300">
                    <input type="checkbox" :value="ev" v-model="newWebhook.events" class="rounded" />
                    {{ ev }}
                  </label>
                </div>
              </div>
              <div class="flex gap-3 justify-end">
                <button @click="showAddWebhook = false" class="text-sm text-slate-400 hover:text-white px-3 py-1.5">Cancel</button>
                <button @click="createWebhook"
                  class="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-1.5 rounded-lg">Add</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ── System tab ─────────────────────────────────────── -->
        <div v-if="activeTab === 'system'" class="space-y-6 max-w-3xl">
          <h2 class="text-base font-semibold">System Health</h2>

          <div v-if="sysHealth" class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4">
              <p class="text-slate-400 text-xs">DB Size</p>
              <p class="text-xl font-bold mt-1">{{ fmtBytes(sysHealth.db_size_bytes) }}</p>
            </div>
            <div class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4">
              <p class="text-slate-400 text-xs">Sessions</p>
              <p class="text-xl font-bold mt-1">{{ sysHealth.session_count }}</p>
            </div>
            <div class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4">
              <p class="text-slate-400 text-xs">Knowledge Entries</p>
              <p class="text-xl font-bold mt-1">{{ sysHealth.knowledge_entry_count }}</p>
            </div>
            <div class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4">
              <p class="text-slate-400 text-xs">Active Schedules</p>
              <p class="text-xl font-bold mt-1">{{ sysHealth.active_scheduled_count }}</p>
            </div>
            <div class="bg-[#0f1117] border border-[#2a2d3e] rounded-xl p-4 col-span-2">
              <p class="text-slate-400 text-xs">Next Scheduled Run</p>
              <p class="text-sm font-semibold mt-1">{{ sysHealth.next_scheduled_run?.slice(0, 16).replace('T', ' ') ?? '—' }}</p>
            </div>
          </div>

          <div class="flex items-center justify-between mt-4">
            <h2 class="text-base font-semibold">Data Retention</h2>
            <button @click="runRetention"
              class="text-xs border border-[#2a2d3e] hover:border-red-500 text-slate-400 hover:text-red-400 px-3 py-1.5 rounded transition">
              Run Now
            </button>
          </div>
          <p v-if="retentionResult" class="text-green-400 text-sm">{{ retentionResult }}</p>

          <div class="space-y-2">
            <div v-for="policy in retentionPolicies" :key="policy.entity"
              class="flex items-center gap-3 bg-[#0f1117] border border-[#2a2d3e] rounded-xl px-4 py-3">
              <span class="text-sm font-mono flex-1">{{ policy.entity }}</span>
              <input v-model.number="policy.max_age_days" type="number" min="1"
                class="w-20 bg-[#1a1d2e] border border-[#2a2d3e] rounded px-2 py-1 text-sm text-right" />
              <span class="text-slate-400 text-sm">days</span>
              <label class="flex items-center gap-1 text-xs text-slate-400">
                <input type="checkbox" v-model="policy.enabled" class="rounded" />
                Enabled
              </label>
              <button @click="saveRetentionPolicy(policy)"
                class="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded">Save</button>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const tabs = [
  { id: 'stats', label: 'Overview' },
  { id: 'users', label: 'Users' },
  { id: 'audit', label: 'Audit Log' },
  { id: 'llm', label: 'LLM Providers' },
  { id: 'finetune', label: 'Fine-Tuning' },
  { id: 'scheduled', label: 'Scheduled' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'system', label: 'System' },
]
const activeTab = ref('stats')
const currentUserId = computed(() => auth.user?.id)

// ── Stats ──────────────────────────────────────────────────────────────
const stats = ref<any>(null)
const maxActivity = computed(() =>
  Math.max(1, ...((stats.value?.activity_7d || []).map((d: any) => d.count)))
)
const statCards = computed(() => stats.value ? [
  { label: 'Total Users', value: stats.value.user_count },
  { label: 'Diagnostic Sessions', value: stats.value.session_count },
  { label: 'Resolved Sessions', value: stats.value.resolved_count },
  { label: 'Audit Entries', value: stats.value.audit_entry_count },
] : [])

async function loadStats() {
  try {
    stats.value = await $fetch('/api/admin/stats', { headers: auth.authHeaders() })
  } catch { /* ignore */ }
}

// ── Users ──────────────────────────────────────────────────────────────
const users = ref<any[]>([])
const showCreateUser = ref(false)
const userLoading = ref(false)
const userError = ref('')
const newUser = ref({ username: '', password: '', role: 'technician' })
const roles = ['technician', 'qa_engineer', 'developer', 'admin']

async function loadUsers() {
  try {
    const data = await $fetch('/api/admin/users', { headers: auth.authHeaders() })
    users.value = data.users
  } catch { /* ignore */ }
}

async function createUser() {
  userLoading.value = true
  userError.value = ''
  try {
    await $fetch('/api/admin/users', {
      method: 'POST',
      body: newUser.value,
      headers: auth.authHeaders(),
    })
    newUser.value = { username: '', password: '', role: 'technician' }
    showCreateUser.value = false
    await loadUsers()
  } catch (e: any) {
    userError.value = e?.data?.detail || e.message
  } finally {
    userLoading.value = false
  }
}

async function changeRole(userId: string, role: string) {
  try {
    await $fetch(`/api/admin/users/${userId}/role`, {
      method: 'PATCH',
      body: { role },
      headers: auth.authHeaders(),
    })
    await loadUsers()
  } catch { /* ignore */ }
}

async function deleteUser(userId: string) {
  if (!confirm('Delete this user?')) return
  try {
    await $fetch(`/api/admin/users/${userId}`, { method: 'DELETE', headers: auth.authHeaders() })
    await loadUsers()
  } catch { /* ignore */ }
}

// ── Audit ──────────────────────────────────────────────────────────────
const auditEntries = ref<any[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPerPage = 50
const auditLoading = ref(false)
const auditFilters = ref({ action: '', severity: '', days: 30 })

async function loadAudit() {
  auditLoading.value = true
  try {
    const params = new URLSearchParams({
      page: String(auditPage.value),
      per_page: String(auditPerPage),
      days: String(auditFilters.value.days),
    })
    if (auditFilters.value.action) params.set('action', auditFilters.value.action)
    if (auditFilters.value.severity) params.set('severity', auditFilters.value.severity)
    const data = await $fetch(`/api/admin/audit?${params}`, { headers: auth.authHeaders() })
    auditEntries.value = data.entries
    auditTotal.value = data.total
  } catch { /* ignore */ } finally {
    auditLoading.value = false
  }
}

async function exportAudit() {
  const url = `/api/admin/audit/export?days=${auditFilters.value.days}`
  const resp = await fetch(url, { headers: auth.authHeaders() as HeadersInit })
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `audit-${auditFilters.value.days}d.csv`
  a.click()
}

async function pruneAudit() {
  if (!confirm('Delete all audit entries beyond the retention period?')) return
  try {
    const data = await $fetch('/api/admin/audit/prune', { method: 'DELETE', headers: auth.authHeaders() })
    alert(`Deleted ${data.deleted} old entries.`)
    await loadAudit()
  } catch { /* ignore */ }
}

function formatDetail(detail: string | null): string {
  if (!detail) return ''
  try { return JSON.stringify(JSON.parse(detail)) } catch { return detail }
}

function severityBadge(s: string) {
  return { info: 'bg-blue-900 text-blue-300', warning: 'bg-yellow-900 text-yellow-300', error: 'bg-red-900 text-red-300' }[s] || 'bg-slate-800 text-slate-400'
}

// ── LLM Providers ──────────────────────────────────────────────────────
const providers = ref<any[]>([])
const expandedProvider = ref<string | null>(null)
const providerEdits = ref<Record<string, any>>({})
const providerModels = ref<Record<string, string[]>>({})
const providerModelsLoading = ref<Record<string, boolean>>({})
const providerModelsError = ref<Record<string, string>>({})
const providerSaving = ref(false)
const providerSaveError = ref('')
const showAddProvider = ref(false)
const newProvider = ref({ provider_type: 'ollama', model_name: '', endpoint_url: 'http://ollama:11434', is_local: true, max_tokens: 4096 })
const newProviderModels = ref<string[]>([])
const newProviderModelsLoading = ref(false)
const newProviderModelsError = ref('')

async function loadProviders() {
  try {
    const data = await $fetch('/api/admin/llm-providers', { headers: auth.authHeaders() })
    providers.value = data.providers
  } catch { /* ignore */ }
}

function toggleExpand(id: string) {
  if (expandedProvider.value === id) { expandedProvider.value = null; return }
  expandedProvider.value = id
  const p = providers.value.find(x => x.id === id)
  if (p) {
    providerEdits.value[id] = {
      endpoint_url: p.endpoint_url || '',
      model_name: p.model_name || '',
      max_tokens: p.max_tokens || 4096,
    }
    loadProviderModels(p)
  }
}

async function loadProviderModels(p: any, endpointOverride?: string) {
  providerModelsLoading.value[p.id] = true
  providerModelsError.value[p.id] = ''
  try {
    const params = new URLSearchParams()
    const override = endpointOverride ?? providerEdits.value[p.id]?.endpoint_url
    if (override) params.set('endpoint_url_override', override)
    const data = await $fetch(`/api/admin/llm-providers/${p.id}/models?${params}`, { headers: auth.authHeaders() })
    providerModels.value[p.id] = data.models || []
    if (data.error) providerModelsError.value[p.id] = data.error
  } catch {
    providerModelsError.value[p.id] = 'Could not fetch models'
  } finally {
    providerModelsLoading.value[p.id] = false
  }
}

let _endpointDebounce: ReturnType<typeof setTimeout> | null = null
function onEndpointBlur(p: any) {
  if (_endpointDebounce) clearTimeout(_endpointDebounce)
  _endpointDebounce = setTimeout(() => loadProviderModels(p, providerEdits.value[p.id]?.endpoint_url), 300)
}

async function toggleProviderEnabled(p: any) {
  try {
    await $fetch(`/api/admin/llm-providers/${p.id}`, {
      method: 'PATCH', body: { enabled: !p.is_enabled }, headers: auth.authHeaders(),
    })
    p.is_enabled = !p.is_enabled
  } catch { /* ignore */ }
}

async function saveProvider(p: any) {
  providerSaving.value = true
  providerSaveError.value = ''
  try {
    const edit = providerEdits.value[p.id]
    await $fetch(`/api/admin/llm-providers/${p.id}`, {
      method: 'PATCH',
      body: { endpoint_url: edit.endpoint_url || null, model_name: edit.model_name, max_tokens: edit.max_tokens },
      headers: auth.authHeaders(),
    })
    Object.assign(p, { endpoint_url: edit.endpoint_url, model_name: edit.model_name, max_tokens: edit.max_tokens })
    expandedProvider.value = null
  } catch (e: any) {
    providerSaveError.value = e?.data?.detail || 'Save failed'
  } finally { providerSaving.value = false }
}

async function setDefault(p: any) {
  providerSaving.value = true
  try {
    await $fetch(`/api/admin/llm-providers/${p.id}`, {
      method: 'PATCH', body: { is_default: true }, headers: auth.authHeaders(),
    })
    await loadProviders()
    expandedProvider.value = null
  } catch { /* ignore */ } finally { providerSaving.value = false }
}

async function deleteProvider(p: any) {
  if (!confirm(`Delete provider "${p.provider_type} / ${p.model_name}"?`)) return
  try {
    await $fetch(`/api/admin/llm-providers/${p.id}`, { method: 'DELETE', headers: auth.authHeaders() })
    providers.value = providers.value.filter(x => x.id !== p.id)
    if (expandedProvider.value === p.id) expandedProvider.value = null
  } catch (e: any) { alert(e?.data?.detail || 'Delete failed') }
}

async function fetchNewProviderModels() {
  newProviderModelsLoading.value = true
  newProviderModelsError.value = ''
  newProviderModels.value = []
  try {
    const params = new URLSearchParams({
      provider_type: newProvider.value.provider_type,
      endpoint_url: newProvider.value.endpoint_url || '',
    })
    const data = await $fetch(`/api/admin/llm-provider-models?${params}`, { headers: auth.authHeaders() })
    newProviderModels.value = data.models || []
    if (data.error) newProviderModelsError.value = data.error
    if (data.models?.length && !newProvider.value.model_name) newProvider.value.model_name = data.models[0]
  } catch { newProviderModelsError.value = 'Could not fetch models' } finally {
    newProviderModelsLoading.value = false
  }
}

async function addProvider() {
  providerSaving.value = true
  try {
    await $fetch('/api/admin/llm-providers', {
      method: 'POST',
      body: {
        provider_type: newProvider.value.provider_type,
        model_name: newProvider.value.model_name,
        endpoint_url: newProvider.value.endpoint_url || null,
        is_local: newProvider.value.is_local,
        max_tokens: newProvider.value.max_tokens,
      },
      headers: auth.authHeaders(),
    })
    await loadProviders()
    showAddProvider.value = false
    newProvider.value = { provider_type: 'ollama', model_name: '', endpoint_url: 'http://ollama:11434', is_local: true, max_tokens: 4096 }
    newProviderModels.value = []
  } catch (e: any) { alert(e?.data?.detail || 'Add failed') } finally {
    providerSaving.value = false
  }
}

// ── Fine-Tuning ────────────────────────────────────────────────────────
const finetuneStats = ref<any>(null)
const exportPath = ref('/tmp/androbugger-training.jsonl')
const exportMinQuality = ref(0.0)
const exportLoading = ref(false)
const exportResult = ref<any>(null)
const exportError = ref('')

async function loadFinetuneStats() {
  try {
    finetuneStats.value = await $fetch('/api/admin/finetune/stats', { headers: auth.authHeaders() })
  } catch { /* ignore */ }
}

async function exportFinetuneData() {
  exportLoading.value = true
  exportResult.value = null
  exportError.value = ''
  try {
    exportResult.value = await $fetch('/api/admin/finetune/export', {
      method: 'POST',
      body: { output_path: exportPath.value, min_quality: exportMinQuality.value },
      headers: auth.authHeaders(),
    })
    await loadFinetuneStats()
  } catch (e: any) {
    exportError.value = e?.data?.detail || e.message || 'Export failed'
  } finally {
    exportLoading.value = false
  }
}

// ── Scheduled Diagnostics ──────────────────────────────────────────────
const schedules = ref<any[]>([])
const showCreateSchedule = ref(false)
const scheduleLoading = ref(false)
const scheduleError = ref('')
const newSchedule = ref({ name: '', cron_expr: '', device_serial: '', template_id: '' })

async function loadSchedules() {
  try {
    const data = await $fetch('/api/scheduled-diagnostics', { headers: auth.authHeaders() })
    schedules.value = data.schedules || []
  } catch { /* ignore */ }
}

async function createSchedule() {
  scheduleLoading.value = true
  scheduleError.value = ''
  try {
    await $fetch('/api/scheduled-diagnostics', {
      method: 'POST',
      body: {
        name: newSchedule.value.name,
        cron_expr: newSchedule.value.cron_expr,
        device_serial: newSchedule.value.device_serial || null,
        template_id: newSchedule.value.template_id || null,
      },
      headers: auth.authHeaders(),
    })
    newSchedule.value = { name: '', cron_expr: '', device_serial: '', template_id: '' }
    showCreateSchedule.value = false
    await loadSchedules()
  } catch (e: any) {
    scheduleError.value = e?.data?.detail || e.message
  } finally {
    scheduleLoading.value = false
  }
}

async function deleteSchedule(id: string) {
  if (!confirm('Delete this schedule?')) return
  try {
    await $fetch(`/api/scheduled-diagnostics/${id}`, { method: 'DELETE', headers: auth.authHeaders() })
    await loadSchedules()
  } catch { /* ignore */ }
}

// ── Integrations (webhooks) ────────────────────────────────────────────
const webhooks = ref<any[]>([])
const showAddWebhook = ref(false)
const webhookTestResult = ref<Record<string, any>>({})
const newWebhook = ref({ name: '', url: '', secret: '', events: [] as string[] })
const availableEvents = [
  'session.completed', 'session.failed', 'hardware.alert',
  'regression.detected', 'plugin.error',
]

function parseEvents(raw: string | string[]): string[] {
  if (Array.isArray(raw)) return raw
  try { return JSON.parse(raw) } catch { return [] }
}

async function loadWebhooks() {
  try {
    const data = await $fetch('/api/webhooks', { headers: auth.authHeaders() })
    webhooks.value = data.webhooks ?? []
  } catch { /* ignore */ }
}

async function createWebhook() {
  try {
    await $fetch('/api/webhooks', {
      method: 'POST', headers: auth.authHeaders(), body: newWebhook.value
    })
    showAddWebhook.value = false
    newWebhook.value = { name: '', url: '', secret: '', events: [] }
    await loadWebhooks()
  } catch { /* ignore */ }
}

async function deleteWebhook(id: string) {
  if (!confirm('Delete webhook endpoint?')) return
  await $fetch(`/api/webhooks/${id}`, { method: 'DELETE', headers: auth.authHeaders() })
  await loadWebhooks()
}

async function toggleWebhookEnabled(wh: any) {
  await $fetch(`/api/webhooks/${wh.id}`, {
    method: 'PUT', headers: auth.authHeaders(),
    body: { enabled: !wh.enabled },
  })
  await loadWebhooks()
}

async function testWebhook(id: string) {
  try {
    const result = await $fetch(`/api/webhooks/${id}/test`, {
      method: 'POST', headers: auth.authHeaders()
    })
    webhookTestResult.value[id] = result
    setTimeout(() => { delete webhookTestResult.value[id] }, 5000)
  } catch { /* ignore */ }
}

// ── System health & retention ──────────────────────────────────────────
const sysHealth = ref<any>(null)
const retentionPolicies = ref<any[]>([])
const retentionResult = ref('')

async function loadSystem() {
  try {
    const [health, retention] = await Promise.all([
      $fetch('/api/system/health', { headers: auth.authHeaders() }),
      $fetch('/api/system/retention', { headers: auth.authHeaders() }),
    ])
    sysHealth.value = health
    retentionPolicies.value = retention.policies ?? []
  } catch { /* ignore */ }
}

async function saveRetentionPolicy(policy: any) {
  await $fetch(`/api/system/retention/${policy.entity}`, {
    method: 'PUT', headers: auth.authHeaders(),
    body: { max_age_days: policy.max_age_days, enabled: policy.enabled },
  })
}

async function runRetention() {
  if (!confirm('Run retention purge now? This deletes old records permanently.')) return
  const result = await $fetch('/api/system/retention/run', {
    method: 'POST', headers: auth.authHeaders()
  })
  const summary = Object.entries(result.deleted)
    .map(([k, v]) => `${k}: ${v} deleted`)
    .join(', ')
  retentionResult.value = `Purge complete — ${summary}`
  setTimeout(() => { retentionResult.value = '' }, 8000)
}

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

// ── Lifecycle ──────────────────────────────────────────────────────────
watch(activeTab, (tab) => {
  if (tab === 'stats') loadStats()
  else if (tab === 'users') loadUsers()
  else if (tab === 'audit') loadAudit()
  else if (tab === 'llm') loadProviders()
  else if (tab === 'finetune') loadFinetuneStats()
  else if (tab === 'scheduled') loadSchedules()
  else if (tab === 'integrations') loadWebhooks()
  else if (tab === 'system') loadSystem()
})

onMounted(loadStats)
</script>
