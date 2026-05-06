<template>
  <div :class="['rounded-xl border bg-[#1a1d2e] p-5 flex flex-col gap-3 transition cursor-pointer select-none',
    selected ? 'border-blue-500 ring-1 ring-blue-500' :
    health?.is_outlier ? 'border-red-700 hover:border-red-500' :
    'border-[#2a2d3e] hover:border-blue-600']"
    @click="$emit('select', device.serial)"
  >
    <div class="flex items-start justify-between">
      <div class="flex-1 min-w-0">
        <p class="text-white font-semibold truncate">{{ device.model || 'Unknown Model' }}</p>
        <p class="text-slate-400 text-xs font-mono">{{ device.serial }}</p>
      </div>
      <div class="flex items-center gap-1.5 flex-shrink-0">
        <!-- Outlier warning -->
        <span v-if="health?.is_outlier" class="text-xs px-1.5 py-0.5 rounded bg-red-900 text-red-300 font-medium" title="High failure rate vs fleet">⚠ Outlier</span>
        <span :class="['text-xs px-2 py-0.5 rounded-full font-medium',
          device.connection_type === 'usb' ? 'bg-blue-900 text-blue-300' : 'bg-green-900 text-green-300']">
          {{ device.connection_type.toUpperCase() }}
        </span>
      </div>
    </div>

    <div class="text-xs text-slate-500 space-y-0.5">
      <p>Android {{ device.android_version || '?' }} · FW {{ device.firmware_version || '?' }}</p>
      <p v-if="device.ip_address">IP: {{ device.ip_address }}</p>
    </div>

    <!-- Health bar -->
    <div v-if="health" class="space-y-1.5">
      <!-- Last session status -->
      <div class="flex items-center gap-2 text-xs">
        <span class="text-slate-500">Last:</span>
        <span v-if="health.last_session"
          :class="statusBadge(health.last_session.status)"
          class="px-1.5 py-0.5 rounded-full text-[10px] font-medium">
          {{ health.last_session.status }}
        </span>
        <span v-if="health.last_session?.started_at" class="text-slate-600">
          {{ relativeTime(health.last_session.started_at) }}
        </span>
        <span v-else class="text-slate-600">Never diagnosed</span>
      </div>

      <!-- 7-day stats mini bar -->
      <div class="flex items-center gap-3 text-xs text-slate-500">
        <span>7d: {{ health.sessions_7d }} sessions</span>
        <span v-if="health.failures_7d" class="text-red-400">{{ health.failures_7d }} failed</span>
        <span v-if="health.resolved_7d" class="text-green-400">{{ health.resolved_7d }} resolved</span>
      </div>
    </div>
    <div v-else-if="healthLoading" class="h-4 bg-[#2a2d3e] rounded animate-pulse" />

    <div class="flex gap-2 mt-1" @click.stop>
      <button
        @click="$emit('diagnose', device.serial)"
        class="flex-1 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition"
      >
        Diagnose
      </button>
      <button
        @click="$emit('disconnect', device.serial)"
        class="px-3 py-1.5 rounded-lg border border-[#2a2d3e] hover:border-red-500 text-slate-400 hover:text-red-400 text-sm transition"
      >
        Disconnect
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DeviceInfo } from '@/stores/devices'

interface Health {
  last_session: { status: string; started_at: string } | null
  sessions_7d: number
  failures_7d: number
  resolved_7d: number
  fail_rate_7d: number
  is_outlier: boolean
}

defineProps<{
  device: DeviceInfo
  health?: Health | null
  healthLoading?: boolean
  selected?: boolean
}>()

defineEmits<{
  diagnose: [serial: string]
  disconnect: [serial: string]
  select: [serial: string]
}>()

function statusBadge(status: string) {
  return {
    running: 'bg-yellow-900 text-yellow-300',
    completed: 'bg-blue-900 text-blue-300',
    resolved: 'bg-green-900 text-green-300',
    failed: 'bg-red-900 text-red-300',
  }[status] || 'bg-slate-800 text-slate-400'
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}
</script>
