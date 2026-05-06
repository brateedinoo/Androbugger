<template>
  <div class="rounded-xl border border-[#2a2d3e] bg-[#1a1d2e] p-5 flex flex-col gap-3 hover:border-blue-600 transition">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-white font-semibold">{{ device.model || 'Unknown Model' }}</p>
        <p class="text-slate-400 text-xs font-mono">{{ device.serial }}</p>
      </div>
      <span
        :class="[
          'text-xs px-2 py-0.5 rounded-full font-medium',
          device.connection_type === 'usb' ? 'bg-blue-900 text-blue-300' : 'bg-green-900 text-green-300'
        ]"
      >
        {{ device.connection_type.toUpperCase() }}
      </span>
    </div>

    <div class="text-xs text-slate-500 space-y-0.5">
      <p>Android {{ device.android_version || '?' }} · FW {{ device.firmware_version || '?' }}</p>
      <p v-if="device.ip_address">IP: {{ device.ip_address }}</p>
    </div>

    <div class="flex gap-2 mt-1">
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
defineProps<{ device: DeviceInfo }>()
defineEmits<{ diagnose: [serial: string]; disconnect: [serial: string] }>()
</script>
