<template>
  <RouterView />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useDevicesStore } from '@/stores/devices'

const auth = useAuthStore()
const devicesStore = useDevicesStore()

onMounted(() => {
  if (auth.isAuthenticated) {
    devicesStore.connectWebSocket()
  }
})
</script>
