/** API 请求封装 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：自动带 Token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      router.push('/login')
      ElMessage.error('登录已过期，请重新登录')
    } else {
      ElMessage.error(error.response?.data?.detail || '请求失败')
    }
    return Promise.reject(error)
  },
)

export default http

// ========== API 方法 ==========

/** 认证 */
export const authApi = {
  login: (data: { username: string; password: string }) =>
    http.post('/auth/login', data),
  register: (data: { username: string; email: string; password: string; display_name?: string }) =>
    http.post('/auth/register', data),
  getMe: () => http.get('/auth/me'),
}

/** 供应商 */
export const supplierApi = {
  list: (params?: any) => http.get('/suppliers', { params }),
  get: (id: number) => http.get(`/suppliers/${id}`),
  create: (data: any) => http.post('/suppliers', data),
  update: (id: number, data: any) => http.put(`/suppliers/${id}`, data),
  delete: (id: number) => http.delete(`/suppliers/${id}`),
}

/** 产品 */
export const productApi = {
  list: (params?: any) => http.get('/products', { params }),
  get: (id: number) => http.get(`/products/${id}`),
  create: (data: any) => http.post('/products', data),
  update: (id: number, data: any) => http.put(`/products/${id}`, data),
  delete: (id: number) => http.delete(`/products/${id}`),
  categories: {
    list: () => http.get('/products/categories/list'),
    create: (data: any) => http.post('/products/categories', data),
  },
}

/** 采购 */
export const purchaseApi = {
  list: (params?: any) => http.get('/purchase/orders', { params }),
  get: (id: number) => http.get(`/purchase/orders/${id}`),
  create: (data: any) => http.post('/purchase/orders', data),
  approve: (id: number) => http.post(`/purchase/orders/${id}/approve`),
  delete: (id: number) => http.delete(`/purchase/orders/${id}`),
  inbound: (data: any) => http.post('/purchase/inbound', data),
}

/** 库存 */
export const inventoryApi = {
  warehouses: {
    list: () => http.get('/inventory/warehouses'),
    create: (data: any) => http.post('/inventory/warehouses', data),
    delete: (id: number) => http.delete(`/inventory/warehouses/${id}`),
  },
  stock: (params?: any) => http.get('/inventory/stock', { params }),
  delete: (id: number) => http.delete(`/inventory/stock/${id}`),
  adjust: (data: any) => http.post('/inventory/adjust', data),
  records: (params?: any) => http.get('/inventory/records', { params }),
  alerts: (params?: any) => http.get('/inventory/alerts', { params }),
  deleteAlert: (id: number) => http.delete(`/inventory/alerts/${id}`),
  resolveAlert: (id: number) => http.post(`/inventory/alerts/${id}/resolve`),
  heatmap: (params?: any) => http.get('/inventory/heatmap', { params }),
  lowStock: (params?: any) => http.get('/inventory/low-stock', { params }),
}

/** 销售 */
export const saleApi = {
  customers: {
    list: (params?: any) => http.get('/sales/customers', { params }),
    create: (data: any) => http.post('/sales/customers', data),
    update: (id: number, data: any) => http.put(`/sales/customers/${id}`, data),
    delete: (id: number) => http.delete(`/sales/customers/${id}`),
  },
  orders: {
    list: (params?: any) => http.get('/sales/orders', { params }),
    get: (id: number) => http.get(`/sales/orders/${id}`),
    create: (data: any) => http.post('/sales/orders', data),
    delete: (id: number) => http.delete(`/sales/orders/${id}`),
  },
  outbound: (data: any) => http.post('/sales/outbound', data),
}

/** AI 智能决策 */
export const aiApi = {
  stockAlert: (productId: number) => http.post('/ai/stock-alert', null, { params: { product_id: productId } }),
  salesForecast: (productId: number) => http.post('/ai/sales-prediction', null, { params: { product_id: productId } }),
  supplierRecommend: (productId: number) => http.post('/ai/supplier-recommend', null, { params: { product_id: productId } }),
  history: (params?: any) => http.get('/ai/history', { params }),
  dashboard: () => http.get('/ai/dashboard'),
  supplierAnalysis: (params?: any) => http.get('/ai/supplier-analysis', { params }),
  supplierRanking: () => http.get('/ai/supplier-ranking'),
  salesHistory: (params?: any) => http.get('/ai/sales-history', { params }),
  salesPrediction: (productId: number) => http.post('/ai/sales-prediction', null, { params: { product_id: productId } }),
  /** AI 批量风险评估 */
  stockAlertBatch: (data: { product_ids: number[] }) => http.post('/ai/stock-alert-batch', data),
  /** AI 对话助手 */
  chat: (data: { messages: any[]; conversation_id: string }) => http.post('/ai/chat', data),
  /** 快捷操作直接获取图表 blocks */
  quickChart: (type: string) => http.get('/ai/quick-chart', { params: { type } }),
  execute: (data: { conversation_id: string; action: string; params: Record<string, any> }) =>
    http.post('/ai/execute', data),
  /** 库存 KPI */
  inventoryKpi: () => http.post('/ai/inventory-kpi'),
  /** ROP 建议采购量 */
  suggestedQty: (data: { product_id: number; supplier_id?: number }) => http.post('/ai/suggested-qty', null, { params: data }),
  /** 批量 ROP 计算 */
  batchRop: (data: { product_ids: number[] }) => http.post('/ai/batch-rop', data),
  /** 供应商综合评分 */
  supplierScore: (data?: { supplier_ids?: number[] }) => http.post('/ai/supplier-score', data),
  /** 天气查询 */
  weather: (params?: { city?: string; days?: number }) => http.get('/ai/weather', { params }),
  /** 采购计划风险审核 */
  auditPlan: (data: { items: Array<{ product_id: number; product_name: string; quantity: number; supplier_id: number; supplier_name: string }> }) => http.post('/ai/audit-plan', data),
}
