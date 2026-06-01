/** 采购决策生成 — 跨步骤状态管理 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { inventoryApi, productApi, aiApi } from '@/api'
import { ElMessage } from 'element-plus'

export interface RestockItem {
  product_id: number
  product_name: string
  product_code: string
  warehouse: string
  current_qty: number
  min_stock: number
  max_stock: number
  suggested_qty: number
  unit: string
  daily_sales_avg: number
  priority: string
}

export const usePurchaseDecisionStore = defineStore('purchaseDecision', () => {
  const currentStep = ref(0)
  const isExpanded = ref(false)
  const isLoading = ref(false)

  // Step 1: 库存分析
  const allProducts = ref<RestockItem[]>([])
  const selectedIds = ref<Set<number>>(new Set())
  const quantities = ref<Record<number, number>>({})

  // AI recommendation result
  const aiRecommendation = ref<any>(null)

  // Step 2-4 placeholders (simplified for Phase 2)
  const confirmedIds = ref<Set<number>>(new Set())
  const supplierMapping = ref<Record<number, number>>({})
  const finalQuantities = ref<Record<number, number>>({})

  // Step 5: 汇总
  const purchasePlan = ref<any>(null)

  const selectedProducts = computed(() =>
    allProducts.value.filter(p => selectedIds.value.has(p.product_id))
  )

  const stepLabels = ['库存分析', '风险评估', '供应商匹配', '销量预测', '汇总确认']

  async function fetchLowStockProducts() {
    isLoading.value = true
    try {
      const res: any = await inventoryApi.alerts({ alert_type: 'low_stock', page_size: 100 })
      if (res && res.items) {
        allProducts.value = res.items.map((item: any) => ({
          product_id: item.product_id,
          product_name: item.product_name || `产品#${item.product_id}`,
          product_code: item.product_code || '',
          warehouse: item.warehouse_name || '',
          current_qty: item.current_quantity || 0,
          min_stock: item.threshold_value || 0,
          max_stock: item.max_stock || (item.threshold_value || 0) * 2,
          suggested_qty: Math.max(0, (item.threshold_value || 0) - (item.current_quantity || 0)),
          unit: item.unit || '个',
          daily_sales_avg: 0,
          priority: item.level || 'medium',
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
        // Auto-select recommended products
        // LLM may return table block with recommended items
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
    confirmedIds.value = new Set()
    supplierMapping.value = {}
    finalQuantities.value = {}
    purchasePlan.value = null
  }

  function close() {
    isExpanded.value = false
    reset()
  }

  return {
    currentStep, isExpanded, isLoading,
    allProducts, selectedIds, quantities, aiRecommendation,
    confirmedIds, supplierMapping, finalQuantities,
    purchasePlan, selectedProducts, stepLabels,
    fetchLowStockProducts, getRecommendation,
    toggleProduct, selectAll, deselectAll, setQuantity,
    nextStep, prevStep, reset, close,
  }
})
