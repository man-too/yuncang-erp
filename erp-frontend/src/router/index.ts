import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页', icon: 'Odometer' },
      },
      {
        path: 'supplier',
        name: 'Supplier',
        component: () => import('@/views/Supplier.vue'),
        meta: { title: '供应商管理', icon: 'Van' },
      },
      {
        path: 'product',
        name: 'Product',
        component: () => import('@/views/Product.vue'),
        meta: { title: '产品管理', icon: 'Box' },
      },
      {
        path: 'purchase',
        name: 'Purchase',
        component: () => import('@/views/Purchase.vue'),
        meta: { title: '采购管理', icon: 'ShoppingCart' },
      },
      {
        path: 'inventory',
        name: 'Inventory',
        component: () => import('@/views/Inventory.vue'),
        meta: { title: '库存管理', icon: 'Coin' },
      },
      {
        path: 'sales',
        name: 'Sales',
        component: () => import('@/views/Sales.vue'),
        meta: { title: '销售管理', icon: 'Shop' },
      },
      {
        path: 'ai-decision',
        name: 'AIDecision',
        component: () => import('@/views/AIDecision.vue'),
        meta: { title: 'AI 智能决策', icon: 'MagicStick' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
function isTokenValid(token: string): boolean {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return false
    const payload = JSON.parse(atob(parts[1]))
    return payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.name !== 'Login' && (!token || !isTokenValid(token))) {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router
