import { computed } from 'vue'
import type { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

type PurchaseDecisionStore = ReturnType<typeof usePurchaseDecisionStore>

export function useInventoryKpi(store: PurchaseDecisionStore) {
  const kpiTurnoverDays = computed(() => {
    const v = store.inventoryKpi?.turnover_days
    return v != null ? v : '—'
  })

  const kpiDeadStockCount = computed(() => {
    const v = store.inventoryKpi?.dead_stock_count
    return v != null ? v : '—'
  })

  const kpiDeadStockPct = computed(() => {
    const v = store.inventoryKpi?.dead_stock_pct
    return v != null ? (typeof v === 'number' ? `${v.toFixed(1)}%` : v) : '—'
  })

  const kpiCapitalOccupied = computed(() => {
    const v = store.inventoryKpi?.capital_occupied
    if (v == null) return '—'
    if (typeof v === 'number') {
      if (v >= 10000) return `¥${(v / 10000).toFixed(1)}万`
      return `¥${v.toFixed(0)}`
    }
    return v
  })

  return {
    kpiTurnoverDays,
    kpiDeadStockCount,
    kpiDeadStockPct,
    kpiCapitalOccupied,
  }
}
