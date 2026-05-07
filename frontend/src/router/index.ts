import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('@/views/DashboardView.vue') },
    { path: '/diagnose/:sessionId', component: () => import('@/views/DiagnosticView.vue') },
    { path: '/history', component: () => import('@/views/HistoryView.vue') },
    { path: '/plugins', component: () => import('@/views/PluginsView.vue') },
    { path: '/compare', component: () => import('@/views/FirmwareCompare.vue') },
    { path: '/admin', component: () => import('@/views/AdminView.vue') },
    { path: '/analytics', component: () => import('@/views/AnalyticsView.vue') },
    { path: '/knowledge', component: () => import('@/views/KnowledgeView.vue') },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return '/login'
  }
})

export default router
