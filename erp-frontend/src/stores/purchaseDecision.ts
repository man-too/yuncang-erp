/** 采购决策生成 — 跨步骤状态管理 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { inventoryApi, productApi, aiApi } from '@/api'
import { ElMessage } from 'element-plus'

export interface RestockItem {
  product_id: number
  product_name: string
  product_code: string
  specification?: string
  warehouse_id: number
  warehouse_name: string
  current_qty: number
  min_stock: number
  max_stock: number
  suggested_qty: number
  unit: string
  daily_sales_avg: number
  priority: string
  purchase_price?: number
}

export const usePurchaseDecisionStore = defineStore('purchaseDecision', () => {
  const currentStep = ref(0)
  const isExpanded = ref(false)
  const isLoading = ref(false)

  // Step 0: 库存分析（选产品+仓库，不设数量和价格）
  const allProducts = ref<RestockItem[]>([])
  const selectedIds = ref<Set<number>>(new Set())

  // AI recommendation result
  const aiRecommendation = ref<any>(null)

  // Step 1: 风险评估结果
  const riskResults = ref<Record<number, { level: string; score: number; reason: string; daily_sales: number; shortage_days: number }>>({})

  // Step 2: 供应商匹配（product_id → supplier_id[]）
  const supplierChoices = ref<Record<number, number[]>>({})
  // 供应商信息缓存（supplier_id → supplier info）
  const supplierInfo = ref<Record<number, any>>({})
  // 报价（product_id → unit_price，从所选供应商带入）
  const forecastPrices = ref<Record<number, number>>({})

  // Step 3: 销量预测（product_id → 最终采购数量）
  const forecastQuantities = ref<Record<number, number>>({})
  // 初始建议量（max_stock - current_qty），作为步骤3的默认值
  const quantities = ref<Record<number, number>>({})

  // Step 4: 汇总
  const purchasePlan = ref<any>(null)

  const selectedProducts = computed(() =>
    allProducts.value.filter(p => selectedIds.value.has(p.product_id))
  )

  const stepLabels = ['库存分析', '风险评估', '供应商匹配', '销量预测', '汇总确认']

  async function fetchLowStockProducts() {
    isLoading.value = true
    try {
      const res: any = await inventoryApi.lowStock({ page_size: 100 })
      if (res && res.items) {
        allProducts.value = res.items.map((item: any) => ({
          product_id: item.product_id,
          product_name: item.product_name || `产品#${item.product_id}`,
          product_code: item.product_code || '',
          specification: item.specification || '',
          warehouse_id: item.warehouse_id,
          warehouse_name: item.warehouse_name || `仓库#${item.warehouse_id}`,
          current_qty: item.current_qty ?? item.quantity ?? 0,
          min_stock: item.min_stock || 0,
          max_stock: item.max_stock || (item.min_stock || 0) * 2,
          suggested_qty: Math.max(0, (item.max_stock || 0) - (item.current_qty ?? item.quantity ?? 0)),
          unit: item.unit || '个',
          daily_sales_avg: 0,
          priority: (item.current_qty ?? item.quantity) === 0 ? 'critical' : (item.current_qty ?? item.quantity) < (item.min_stock || 0) ? 'high' : 'medium',
          purchase_price: item.purchase_price || 0,
        }))
      } else {
        allProducts.value = []
      }
    } catch {
      allProducts.value = []
    } finally {
      isLoading.value = false
    }
  }

  async function getRecommendation() {
    isLoading.value = true
    try {
      const res: any = await aiApi.chat({
        messages: [
          { role: 'user', content: '推荐需要补货的产品和补货量' },
        ],
        conversation_id: '',
      })
      if (res && res.blocks) {
        aiRecommendation.value = res
      }
    } catch {
      ElMessage.warning('推荐服务暂不可用，请手动选择')
    } finally {
      isLoading.value = false
    }
  }

  function toggleProduct(id: number) {
    const newSet = new Set(selectedIds.value)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    selectedIds.value = newSet
  }

  function selectAll() {
    selectedIds.value = new Set(allProducts.value.map(p => p.product_id))
  }

  function deselectAll() {
    selectedIds.value = new Set()
  }

  function addToProducts(product: any) {
    const exists = allProducts.value.find(p => p.product_id === product.id)
    if (exists) {
      ElMessage.warning('该产品已在清单中')
      return
    }
    const newItem: RestockItem = {
      product_id: product.id,
      product_code: product.code || '',
      product_name: product.name,
      specification: product.specification || '',
      warehouse_id: product.warehouse_id || 1,
      warehouse_name: product.warehouse_name || '默认仓库',
      current_qty: product.current_qty || product.quantity || 0,
      min_stock: product.min_stock || 0,
      max_stock: product.max_stock || 0,
      unit: product.unit || '个',
      suggested_qty: Math.max(0, (product.max_stock || 0) - (product.current_qty || product.quantity || 0)),
      daily_sales_avg: 0,
      priority: 'medium',
      purchase_price: product.purchase_price || 0,
    }
    allProducts.value.push(newItem)
  }

  function removeSelected() {
    const ids = new Set(selectedIds.value)
    allProducts.value = allProducts.value.filter(p => !ids.has(p.product_id))
    selectedIds.value = new Set()
  }

  function removeProduct(productId: number) {
    allProducts.value = allProducts.value.filter(p => p.product_id !== productId)
    selectedIds.value.delete(productId)
    delete quantities.value[productId]
  }

  function updateProduct(productId: number, updates: Partial<RestockItem>) {
    const idx = allProducts.value.findIndex(p => p.product_id === productId)
    if (idx !== -1) {
      allProducts.value[idx] = { ...allProducts.value[idx], ...updates }
    }
  }

  function setQuantity(id: number, qty: number) {
    quantities.value[id] = qty
  }

  function nextStep() {
    if (currentStep.value < 4) currentStep.value++
  }

  function prevStep() {
    if (currentStep.value > 0) currentStep.value--
  }

  function reset() {
    currentStep.value = 0
    selectedIds.value = new Set()
    quantities.value = {}
    aiRecommendation.value = null
    riskResults.value = {}
    supplierChoices.value = {}
    supplierInfo.value = {}
    forecastPrices.value = {}
    forecastQuantities.value = {}
    purchasePlan.value = null
  }

  function close() {
    isExpanded.value = false
    reset()
  }

  return {
    currentStep, isExpanded, isLoading,
    allProducts, selectedIds, quantities, aiRecommendation,
    riskResults, supplierChoices, supplierInfo, forecastPrices, forecastQuantities,
    purchasePlan, selectedProducts, stepLabels,
    fetchLowStockProducts, getRecommendation,
    toggleProduct, selectAll, deselectAll, addToProducts, removeSelected, removeProduct, updateProduct, setQuantity,
    nextStep, prevStep, reset, close,
  }
})
