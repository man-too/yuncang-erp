import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { aiApi } from '@/api'
import type { RestockItem, usePurchaseDecisionStore } from '@/stores/purchaseDecision'

type PurchaseDecisionStore = ReturnType<typeof usePurchaseDecisionStore>

interface RopMeta {
  precision_mode?: string
  lead_time_source?: string
  note?: string
}

export function useRopBatch(store: PurchaseDecisionStore) {
  const ropMap = ref<Record<number, number>>({})
  const ropMetaMap = ref<Record<number, RopMeta>>({})
  const batchRopLoading = ref(false)

  async function loadBatchRop() {
    const ids = store.allProducts.map(p => p.product_id).filter(Boolean)
    if (ids.length === 0) return
    batchRopLoading.value = true
    try {
      // Build warehouse_ids mapping: product_id -> warehouse_id for per-warehouse ROP
      const warehouseIds: Record<number, number> = {}
      for (const p of store.allProducts) {
        if (p.warehouse_id) {
          warehouseIds[p.product_id] = p.warehouse_id
        }
      }
      const res: any = await aiApi.batchRop({ product_ids: ids, warehouse_ids: warehouseIds })
      if (res) {
        const map: Record<number, number> = {}
        const metaMap: Record<number, RopMeta> = {}
        const ropList: any[] = res.results || res.items || res.data || (Array.isArray(res) ? res : [])
        for (const r of ropList) {
          if (r && r.product_id != null) {
            map[Number(r.product_id)] = r.rop ?? 0
            metaMap[Number(r.product_id)] = {
              precision_mode: r.precision_mode,
              lead_time_source: r.lead_time_source,
              note: r.note,
            }
          }
        }
        ropMap.value = map
        ropMetaMap.value = metaMap
      }
    } catch {
      // Batch ROP is optional fallback
    } finally {
      batchRopLoading.value = false
    }
  }

  function getRop(productId: number): number | null {
    return ropMap.value[productId] ?? null
  }

  function riskRank(item: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): number {
    if (item.current_qty < item.min_stock) return 0 // Out of stock
    // Use ROP: above safety stock but below ROP -> low(1)
    const rop = ropMap.value[item.product_id]
    if (rop != null && rop > item.min_stock && item.current_qty < rop) return 1 // Below ROP
    if (rop != null && item.current_qty >= rop) return 2 // Normal (>= ROP)
    // ROP unavailable: use ratio estimate fallback
    const range = item.max_stock - item.min_stock
    if (range <= 0) return 2
    const ratio = (item.current_qty - item.min_stock) / range
    if (ratio < 0.3) return 1 // Low (close to ROP zone)
    if (ratio > 0.9) return 3 // High
    return 2 // Normal
  }

  const sortedProducts = computed(() => {
    return [...store.allProducts].sort((a, b) => {
      return riskRank(a) - riskRank(b)
    })
  })

  function filteredProducts(
    sorted: ComputedRef<RestockItem[]>,
    productFilter: Ref<number | null>,
    searchKeyword: Ref<string>,
  ): ComputedRef<RestockItem[]> {
    return computed(() => {
      let result = sorted.value
      // Product dropdown filter
      if (productFilter.value != null) {
        result = result.filter(p => p.product_id === productFilter.value)
      }
      // Keyword search filter
      if (searchKeyword.value.trim()) {
        const kw = searchKeyword.value.trim().toLowerCase()
        result = result.filter(p =>
          p.product_name.toLowerCase().includes(kw) ||
          (p.product_code && p.product_code.toLowerCase().includes(kw))
        )
      }
      return result
    })
  }

  function statusLabel(row: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
    const r = riskRank(row)
    return ['缺货', '低于ROP', '正常', '偏高'][r] || '正常'
  }

  function statusTagType(row: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
    const r = riskRank(row)
    return ['danger', 'warning', 'success', 'info'][r] || 'info'
  }

  function cardRiskClass(item: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
    const r = riskRank(item)
    return ['card-danger', 'card-warning', '', 'card-info'][r] || ''
  }

  return {
    ropMap,
    ropMetaMap,
    batchRopLoading,
    loadBatchRop,
    getRop,
    riskRank,
    sortedProducts,
    filteredProducts,
    statusLabel,
    statusTagType,
    cardRiskClass,
  }
}
