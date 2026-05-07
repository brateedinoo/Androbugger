import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { $fetch } from 'ofetch'
import { useAuthStore } from './auth'

export interface DeviceInfo {
  serial: string
  model: string | null
  firmware_version: string | null
  connection_type: 'usb' | 'tcp'
  ip_address: string | null
  android_version: string | null
  connected_at: string
  last_seen: string
  health?: 'healthy' | 'warning' | 'critical'
}

export const useDevicesStore = defineStore('devices', () => {
  const devices = ref<DeviceInfo[]>([])
  let ws: WebSocket | null = null

  async function fetchDevices() {
    const auth = useAuthStore()
    const data = await $fetch('/api/devices', { headers: auth.authHeaders() })
    devices.value = data.devices
  }

  async function connectDevice(ip: string, port = 5555) {
    const auth = useAuthStore()
    const data = await $fetch('/api/devices/connect', {
      method: 'POST',
      body: { ip_address: ip, port },
      headers: auth.authHeaders(),
    })
    if (data.device) {
      const existing = devices.value.findIndex(d => d.serial === data.device.serial)
      if (existing >= 0) devices.value[existing] = data.device
      else devices.value.push(data.device)
    }
  }

  async function disconnectDevice(serial: string) {
    const auth = useAuthStore()
    await $fetch('/api/devices/disconnect', {
      method: 'POST',
      body: { serial },
      headers: auth.authHeaders(),
    })
    devices.value = devices.value.filter(d => d.serial !== serial)
  }

  function connectWebSocket() {
    if (ws) return
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/devices`)
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data)
      if (msg.type === 'init') {
        devices.value = msg.devices
      } else if (msg.type === 'connected') {
        const idx = devices.value.findIndex(d => d.serial === msg.device.serial)
        if (idx >= 0) devices.value[idx] = msg.device
        else devices.value.push(msg.device)
      } else if (msg.type === 'disconnected') {
        devices.value = devices.value.filter(d => d.serial !== msg.device.serial)
      }
    }
    ws.onclose = () => {
      ws = null
      setTimeout(connectWebSocket, 3000)
    }
  }

  function disconnectWebSocket() {
    ws?.close()
    ws = null
  }

  const deviceMap = computed(() =>
    Object.fromEntries(devices.value.map(d => [d.serial, d]))
  )

  return { devices, deviceMap, fetchDevices, connectDevice, disconnectDevice, connectWebSocket, disconnectWebSocket }
})
