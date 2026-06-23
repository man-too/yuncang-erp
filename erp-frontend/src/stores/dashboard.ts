/** 仪表盘状态管理 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { dashboardApi, inventoryApi } from '@/api'

export interface DashboardKPI {
  today_orders: number
  monthly_amount: number
  pending_approval: number
  low_stock_products: number
  pending_inbound: number
  sales_growth_rate: number
}

export interface TrendData {
  dates: string[]
  sales_amounts: number[]
  purchase_amounts: number[]
}

export interface SalesVolumeData {
  dates: string[]
  quantities: number[]
}

export interface PurchaseAmountData {
  dates: string[]
  purchase_amounts: number[]
}

export interface LowStockItem {
  product_id: number
  product_name: string
  product_code: string
  warehouse_name: string
  current_qty: number
  min_stock: number
  unit: string
}

export const useDashboardStore = defineStore('dashboard', () => {
  const kpiData = ref<DashboardKPI | null>(null)
  const trendData = ref<TrendData | null>(null)
  const salesVolumeData = ref<SalesVolumeData | null>(null)
  const purchaseAmountData = ref<PurchaseAmountData | null>(null)
  const lowStockItems = ref<LowStockItem[]>([])
  const isLoading = ref(false)

  async function fetchKPI() {
    try {
      const res: any = await dashboardApi.kpi()
      kpiData.value = res
    } catch (e) {
      console.error('fetchKPI error:', e)
    }
  }

  async function fetchTrend(params?: { product_id?: number; days?: number }) {
    try {
      const res: any = await dashboardApi.trend(params)
      trendData.value = res
    } catch (e) {
      console.error('fetchTrend error:', e)
    }
  }

  async function fetchSalesVolume(params?: { product_id?: number; days?: number }) {
    try {
      const res: any = await dashboardApi.salesVolume(params)
      salesVolumeData.value = res
    } catch (e) {
      console.error('fetchSalesVolume error:', e)
    }
  }

  async function fetchPurchaseAmount(params?: { product_id?: number; days?: number }) {
    try {
      const res: any = await dashboardApi.purchaseAmount(params)
      purchaseAmountData.value = res
    } catch (e) {
      console.error('fetchPurchaseAmount error:', e)
    }
  }

  async function fetchLowStock() {
    try {
      const res: any = await inventoryApi.lowStock({ page_size: 10 })
      lowStockItems.value = res?.items || []
    } catch (e) {
      console.error('fetchLowStock error:', e)
    }
  }

  async function fetchAll() {
    isLoading.value = true
    try {
      await Promise.allSettled([
        fetchKPI(),
        fetchTrend(),
        fetchSalesVolume(),
        fetchPurchaseAmount(),
        fetchLowStock(),
      ])
    } finally {
      isLoading.value = false
    }
  }

  return {
    kpiData, trendData, salesVolumeData, purchaseAmountData, lowStockItems, isLoading,
    fetchKPI, fetchTrend, fetchSalesVolume, fetchPurchaseAmount, fetchLowStock, fetchAll,
  }
})
