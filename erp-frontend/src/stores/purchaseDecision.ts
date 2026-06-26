/** 采购决策生成 — 跨步骤状态管理 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { inventoryApi, productApi, aiApi } from '@/api'
import { ElMessage } from 'element-plus'

export interface WarehouseBreakdown {
  warehouse_id: number
  warehouse_name: string
  current_qty: number
  min_stock: number
  max_stock: number
  suggested_qty: number
  in_transit_qty: number
  backlog_qty: number
  // ROP-enriched fields (populated after batch-rop call)
  rop?: number
  trend?: string
  trend_change_pct?: number
  abc_class?: string
  demand_desc?: string
}

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
  // Phase 3: ROP-related fields surfaced from /ai/batch-rop
  rop?: number
  in_transit_qty?: number
  backlog_qty?: number
  trend?: string
  trend_change_pct?: number
  abc_class?: string
  demand_desc?: string
  // Phase 3: AI replenish-recommend metadata
  aiReason?: string
  aiFactors?: string[]
  // B5: ROP 语义标注
  precision_mode?: 'estimate' | 'final'
  lead_time_source?: string
  note?: string
  // Warehouse breakdown: per-warehouse details for products short in multiple warehouses
  warehouse_breakdown?: WarehouseBreakdown[]
  shortage_warehouse_count?: number
}

export const usePurchaseDecisionStore = defineStore('purchaseDecision', () => {
  const currentStep = ref(0)
  const isExpanded = ref(false)
  const isCollapsed = ref(false)
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
  // Per-warehouse purchase quantities (product_id → warehouse_id → quantity)
  const warehouseQuantities = ref<Record<number, Record<number, number>>>({})
  // Phase 3: 库存 KPI 数据
  const inventoryKpi = ref<any>(null)
  // Phase 3: 风险审核结果
  const auditResult = ref<any>(null)
  // Phase 3: AI 补货推荐摘要
  const aiSummary = ref<string>('')

  async function fetchLowStockProducts() {
    isLoading.value = true
    try {
      const res: any = await inventoryApi.lowStock({ page_size: 100 })
      if (res && (res.products || res.items)) {
        // Prefer grouped products (with warehouse_breakdown) if available
        const groupedProducts: any[] = res.products || []
        const flatItems: any[] = res.items || []

        let baseItems: RestockItem[]

        if (groupedProducts.length > 0) {
          // New grouped format: one item per product with warehouse_breakdown
          baseItems = groupedProducts.map((prod: any) => {
            const currentQty = prod.current_qty ?? 0
            const maxStock = prod.max_stock || (prod.min_stock || 0) * 2
            // Use first warehouse as the "primary" for backward compat fields
            const primaryWh = prod.warehouse_breakdown?.[0]
            return {
              product_id: prod.product_id,
              product_name: prod.product_name || `产品#${prod.product_id}`,
              product_code: prod.product_code || '',
              specification: prod.specification || '',
              warehouse_id: primaryWh?.warehouse_id || 0,
              warehouse_name: primaryWh?.warehouse_name || '',
              current_qty: currentQty,
              min_stock: prod.min_stock || 0,
              max_stock: maxStock,
              // Fallback formula; will be overwritten by batch-rop result if available
              suggested_qty: prod.suggested_qty || Math.max(0, maxStock - currentQty),
              unit: prod.unit || '个',
              daily_sales_avg: 0,
              priority: currentQty === 0 ? 'critical' : currentQty < (prod.min_stock || 0) ? 'high' : 'medium',
              purchase_price: prod.purchase_price || 0,
              warehouse_breakdown: (prod.warehouse_breakdown || []).map((wh: any) => ({
                warehouse_id: wh.warehouse_id,
                warehouse_name: wh.warehouse_name || `仓库#${wh.warehouse_id}`,
                current_qty: wh.current_qty ?? 0,
                min_stock: wh.min_stock ?? 0,
                max_stock: wh.max_stock ?? 0,
                suggested_qty: wh.suggested_qty ?? 0,
                in_transit_qty: wh.in_transit_qty ?? 0,
                backlog_qty: wh.backlog_qty ?? 0,
              })),
              shortage_warehouse_count: prod.shortage_warehouse_count || (prod.warehouse_breakdown || []).length,
            }
          })
        } else {
          // Fallback: old flat format (one row per product×warehouse)
          baseItems = flatItems.map((item: any) => {
            const currentQty = item.current_qty ?? item.quantity ?? 0
            const maxStock = item.max_stock || (item.min_stock || 0) * 2
            return {
              product_id: item.product_id,
              product_name: item.product_name || `产品#${item.product_id}`,
              product_code: item.product_code || '',
              specification: item.specification || '',
              warehouse_id: item.warehouse_id,
              warehouse_name: item.warehouse_name || `仓库#${item.warehouse_id}`,
              current_qty: currentQty,
              min_stock: item.min_stock || 0,
              max_stock: maxStock,
              suggested_qty: Math.max(0, (item.max_stock || 0) - currentQty),
              unit: item.unit || '个',
              daily_sales_avg: 0,
              priority: currentQty === 0 ? 'critical' : currentQty < (item.min_stock || 0) ? 'high' : 'medium',
              purchase_price: item.purchase_price || 0,
            }
          })
        }

        // Try batch ROP enrichment (per-warehouse)
        const productIds = baseItems.map(b => b.product_id)
        if (productIds.length > 0) {
          try {
            // Build warehouse_ids mapping for per-warehouse ROP
            const warehouseIds: Record<number, number> = {}
            for (const item of baseItems) {
              if (item.warehouse_id) {
                warehouseIds[item.product_id] = item.warehouse_id
              }
            }
            const ropRes: any = await aiApi.batchRop({ product_ids: productIds, warehouse_ids: warehouseIds })
            const ropList: any[] = (ropRes && (ropRes.results || ropRes.items || ropRes.data)) || (Array.isArray(ropRes) ? ropRes : [])
            const ropMap: Record<number, any> = {}
            for (const r of ropList) {
              if (r && r.product_id != null) ropMap[r.product_id] = r
            }
            for (const item of baseItems) {
              const r = ropMap[item.product_id]
              if (r) {
                if (typeof r.suggested_qty === 'number' && r.suggested_qty > 0) {
                  item.suggested_qty = r.suggested_qty
                }
                if (typeof r.rop === 'number') item.rop = r.rop
                if (typeof r.in_transit_qty === 'number') item.in_transit_qty = r.in_transit_qty
                if (typeof r.backlog_qty === 'number') item.backlog_qty = r.backlog_qty
                if (r.trend != null) item.trend = r.trend
                if (typeof r.trend_change_pct === 'number') item.trend_change_pct = r.trend_change_pct
                if (r.abc_class != null) item.abc_class = r.abc_class
                if (r.demand_desc != null) item.demand_desc = r.demand_desc
                // B5: ROP 语义标注
                if (r.precision_mode != null) item.precision_mode = r.precision_mode
                if (r.lead_time_source != null) item.lead_time_source = r.lead_time_source
                if (r.note != null) item.note = r.note
                // Cache full ROP record into store for downstream steps
                suggestedQtys.value[item.product_id] = r
              }
            }

            // Enrich warehouse_breakdown with per-warehouse ROP data
            // Build a list of all (product_id, warehouse_id) pairs from breakdowns
            const allPairs: Array<{ productId: number; warehouseId: number }> = []
            for (const item of baseItems) {
              if (item.warehouse_breakdown && item.warehouse_breakdown.length > 0) {
                for (const wh of item.warehouse_breakdown) {
                  allPairs.push({ productId: item.product_id, warehouseId: wh.warehouse_id })
                }
              }
            }
            if (allPairs.length > 0) {
              // Group by warehouse_id to batch efficiently
              const byWarehouse: Record<number, number[]> = {}
              for (const pair of allPairs) {
                if (!byWarehouse[pair.warehouseId]) byWarehouse[pair.warehouseId] = []
                if (!byWarehouse[pair.warehouseId].includes(pair.productId)) {
                  byWarehouse[pair.warehouseId].push(pair.productId)
                }
              }
              // Call batch-rop for each warehouse group
              const whRopPromises = Object.entries(byWarehouse).map(async ([whId, pids]) => {
                const whMap: Record<number, number> = {}
                for (const pid of pids) {
                  whMap[pid] = Number(whId)
                }
                try {
                  const r: any = await aiApi.batchRop({ product_ids: pids, warehouse_ids: whMap })
                  const list: any[] = r?.results || r?.items || r?.data || (Array.isArray(r) ? r : [])
                  return list.map((ropItem: any) => ({
                    ...ropItem,
                    _warehouse_id: Number(whId),
                  }))
                } catch {
                  return []
                }
              })
              const whRopResults = await Promise.allSettled(whRopPromises)
              // Build composite key map: "productId:warehouseId" -> ROP result
              const whRopMap: Record<string, any> = {}
              for (const settled of whRopResults) {
                if (settled.status === 'fulfilled') {
                  for (const r of settled.value) {
                    if (r && r.product_id != null && r._warehouse_id != null) {
                      whRopMap[`${r.product_id}:${r._warehouse_id}`] = r
                    }
                  }
                }
              }
              // Apply to warehouse_breakdown
              for (const item of baseItems) {
                if (item.warehouse_breakdown) {
                  for (const wh of item.warehouse_breakdown) {
                    const key = `${item.product_id}:${wh.warehouse_id}`
                    const r = whRopMap[key]
                    if (r) {
                      if (typeof r.suggested_qty === 'number' && r.suggested_qty > 0) {
                        wh.suggested_qty = r.suggested_qty
                      }
                      if (typeof r.rop === 'number') wh.rop = r.rop
                      if (r.trend != null) wh.trend = r.trend
                      if (typeof r.trend_change_pct === 'number') wh.trend_change_pct = r.trend_change_pct
                      if (r.abc_class != null) wh.abc_class = r.abc_class
                      if (r.demand_desc != null) wh.demand_desc = r.demand_desc
                    }
                  }
                }
              }
            }
          } catch (e) {
            // Fallback formula already applied; just log
            console.error('batchRop failed, using fallback formula:', e)
          }
        }

        allProducts.value = baseItems
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
      const productIds = allProducts.value.map(p => p.product_id)
      if (productIds.length === 0) {
        aiSummary.value = ''
        return
      }
      const res: any = await aiApi.replenishRecommend(productIds)
      const data: any = (res && (res.data || res)) || {}
      const recommendations: any[] = data.recommendations || []
      if (recommendations.length > 0) {
        const recMap: Record<number, any> = {}
        for (const r of recommendations) {
          if (r && r.product_id != null) recMap[r.product_id] = r
        }
        for (const p of allProducts.value) {
          const r = recMap[p.product_id]
          if (!r) continue
          if (typeof r.adjusted_qty === 'number') {
            p.suggested_qty = r.adjusted_qty
          } else if (typeof r.baseline_qty === 'number') {
            p.suggested_qty = r.baseline_qty
          }
          if (typeof r.adjustment_reason === 'string') {
            p.aiReason = r.adjustment_reason
          }
          if (Array.isArray(r.adjustment_factors)) {
            p.aiFactors = r.adjustment_factors
          }
        }
      }
      aiSummary.value = (data.summary && String(data.summary)) || ''
      aiRecommendation.value = data
    } catch (e) {
      console.error('getRecommendation error:', e)
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

  function setWarehouseQuantity(productId: number, warehouseId: number, qty: number) {
    if (!warehouseQuantities.value[productId]) {
      warehouseQuantities.value[productId] = {}
    }
    warehouseQuantities.value[productId][warehouseId] = qty
  }

  function getWarehouseQuantity(productId: number, warehouseId: number, fallback: number = 0): number {
    return warehouseQuantities.value[productId]?.[warehouseId] ?? fallback
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
    warehouseQuantities.value = {}
    inventoryKpi.value = null
    auditResult.value = null
    aiSummary.value = ''
  }

  function close() {
    isExpanded.value = false
    isCollapsed.value = false
    reset()
  }

  function collapse() {
    isCollapsed.value = true
  }

  function expand() {
    isCollapsed.value = false
  }

  // Phase 3: 获取 ROP 建议采购量（支持按仓库计算）
  async function fetchSuggestedQty(productId: number, supplierId?: number, warehouseId?: number) {
    try {
      const res: any = await aiApi.suggestedQty({ product_id: productId, supplier_id: supplierId, warehouse_id: warehouseId })
      if (res) {
        suggestedQtys.value[productId] = res
        // B5: Sync precision_mode/lead_time_source/note back to allProducts item
        const idx = allProducts.value.findIndex(p => p.product_id === productId)
        if (idx !== -1) {
          if (res.precision_mode != null) allProducts.value[idx].precision_mode = res.precision_mode
          if (res.lead_time_source != null) allProducts.value[idx].lead_time_source = res.lead_time_source
          if (res.note != null) allProducts.value[idx].note = res.note
          if (typeof res.rop === 'number') allProducts.value[idx].rop = res.rop
          if (typeof res.suggested_qty === 'number' && res.suggested_qty > 0) allProducts.value[idx].suggested_qty = res.suggested_qty
        }
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
    currentStep, isExpanded, isCollapsed, isLoading,
    allProducts, selectedIds, quantities, aiRecommendation,
    riskResults, supplierChoices, supplierInfo, forecastPrices, forecastQuantities,
    purchasePlan, selectedProducts, stepLabels,
    // Phase 3: 新增状态
    suggestedQtys, supplierQuantities, inventoryKpi, auditResult, aiSummary,
    fetchLowStockProducts, getRecommendation,
    toggleProduct, selectAll, deselectAll, addToProducts, removeSelected, removeProduct, updateProduct, setQuantity,
    setWarehouseQuantity, getWarehouseQuantity,
    nextStep, prevStep, reset, close, collapse, expand,
    // Phase 3: 新增 actions
    fetchSuggestedQty, fetchInventoryKpi, fetchSupplierScore, fetchAuditPlan,
    // Per-warehouse quantities
    warehouseQuantities,
  }
})
