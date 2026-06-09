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

  const stepLabels = ['库存分析', '供应商匹配', '风险审核', '汇总确认']

  // Phase 3: ROP 建议采购量（product_id → ROP 计算结果）
  const suggestedQtys = ref<Record<number, any>>({})
  // Phase 3: 供应商数量分配（product_id → supplier_id → quantity）
  const supplierQuantities = ref<Record<number, Record<number, number>>>({})
  // Phase 3: 库存 KPI 数据
  const inventoryKpi = ref<any>(null)
  // Phase 3: 风险审核结果
  const auditResult = ref<any>(null)

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
    const newSet = new Set(selectedIds.value)
    newSet.delete(productId)
    selectedIds.value = newSet
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
    if (currentStep.value < 3) currentStep.value++
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
    // Phase 3: 重置新增状态
    suggestedQtys.value = {}
    supplierQuantities.value = {}
    inventoryKpi.value = null
    auditResult.value = null
  }

  function close() {
    isExpanded.value = false
    reset()
  }

  // Phase 3: 获取 ROP 建议采购量
  async function fetchSuggestedQty(productId: number, supplierId?: number) {
    try {
      const res: any = await aiApi.suggestedQty({ product_id: productId, supplier_id: supplierId })
      if (res) {
        suggestedQtys.value[productId] = res
      }
      return res
    } catch (e) {
      console.error('fetchSuggestedQty error:', e)
      return null
    }
  }

  // Phase 3: 获取库存 KPI
  async function fetchInventoryKpi() {
    try {
      const res: any = await aiApi.inventoryKpi()
      if (res) {
        inventoryKpi.value = res
      }
      return res
    } catch (e) {
      console.error('fetchInventoryKpi error:', e)
      return null
    }
  }

  // Phase 3: 获取供应商综合评分
  async function fetchSupplierScore(supplierIds?: number[]) {
    try {
      const res: any = await aiApi.supplierScore({ supplier_ids: supplierIds })
      return res
    } catch (e) {
      console.error('fetchSupplierScore error:', e)
      return null
    }
  }

  // Phase 3: 采购计划风险审核
  async function fetchAuditPlan() {
    // 遍历所有产品 × 所有已配供应商，用 supplierQuantities（Step1 数据）
    const items: Array<{ product_id: number; product_name: string; quantity: number; supplier_id: number; supplier_name: string }> = []

    for (const p of allProducts.value) {
      const allocations = supplierQuantities.value[p.product_id]
      const choices = supplierChoices.value[p.product_id] || []

      if (allocations && Object.keys(allocations).length > 0) {
        // 有供应商分配量：为每个 product-supplier 组合生成审核项
        for (const [sid, allocQty] of Object.entries(allocations)) {
          const supplierName = supplierInfo.value[Number(sid)]?.name || `供应商#${sid}`
          items.push({
            product_id: p.product_id,
            product_name: p.product_name,
            quantity: allocQty as number,
            supplier_id: Number(sid),
            supplier_name: supplierName,
          })
        }
      } else if (choices.length > 0) {
        // 有供应商选择但无分配量：用量取 quantities 或 suggested_qty
        for (const sid of choices) {
          const qty = quantities.value[p.product_id] || p.suggested_qty || 0
          const supplierName = supplierInfo.value[sid]?.name || `供应商#${sid}`
          items.push({
            product_id: p.product_id,
            product_name: p.product_name,
            quantity: qty,
            supplier_id: sid,
            supplier_name: supplierName,
          })
        }
      } else {
        // 无供应商：用 supplier_id = 0，不过滤掉
        const qty = quantities.value[p.product_id] || p.suggested_qty || 0
        if (qty > 0) {
          items.push({
            product_id: p.product_id,
            product_name: p.product_name,
            quantity: qty,
            supplier_id: 0,
            supplier_name: '未指定',
          })
        }
      }
    }

    if (items.length === 0) {
      ElMessage.warning('请先添加需要采购的产品')
      return null
    }

    try {
      const res: any = await aiApi.auditPlan({ items })
      if (res) {
        auditResult.value = res
      }
      return res
    } catch (e) {
      console.error('fetchAuditPlan error:', e)
      return null
    }
  }

  return {
    currentStep, isExpanded, isLoading,
    allProducts, selectedIds, quantities, aiRecommendation,
    riskResults, supplierChoices, supplierInfo, forecastPrices, forecastQuantities,
    purchasePlan, selectedProducts, stepLabels,
    // Phase 3: 新增状态
    suggestedQtys, supplierQuantities, inventoryKpi, auditResult,
    fetchLowStockProducts, getRecommendation,
    toggleProduct, selectAll, deselectAll, addToProducts, removeSelected, removeProduct, updateProduct, setQuantity,
    nextStep, prevStep, reset, close,
    // Phase 3: 新增 actions
    fetchSuggestedQty, fetchInventoryKpi, fetchSupplierScore, fetchAuditPlan,
  }
})
