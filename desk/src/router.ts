import { createRouter, createWebHistory } from 'vue-router'

import { session } from '@/session'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: () => import('@/components/AppShell.vue'),
      children: [
        { path: '', redirect: { name: 'flows' } },
        { path: 'flows', name: 'flows', component: () => import('@/views/FlowsView.vue') },
        {
          path: 'flows/:id',
          name: 'flow',
          component: () => import('@/views/FlowEditorView.vue'),
          props: true,
        },
        { path: 'prompts', name: 'prompts', component: () => import('@/views/PromptsView.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.name !== 'login' && !session.user) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && session.user) return { name: 'flows' }
  return true
})
