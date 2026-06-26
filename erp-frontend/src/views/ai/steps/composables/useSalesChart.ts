import { ref, computed, watch } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { aiApi } from '@/api'
import type { RestockItem, usePurchaseDecisionStore } from '@/stores/purchaseDecision'

type PurchaseDecisionStore = ReturnType<typeof usePurchaseDecisionStore>

interface ExpandedProductHolder {
  expandedProductId: Ref<number | null>
  expandedProduct: ComputedRef<RestockItem | null>
}

export function useSalesChart(
  expanded: ExpandedProductHolder,
  store: PurchaseDecisionStore,
) {
  const detailChartLoading = ref(false)
  const detailHistoryData = ref<any[]>([])
  const detailPredictionData = ref<number[]>([])
  const detailPredictionDates = ref<string[]>([])
  const detailTimeRange = ref<'7d' | '30d' | '3m'>('30d')

  // P1-13 fix: deduplication cache to prevent watch + onMounted + auto-expand triple-triggering
  const _detailFetchKey = ref<string>('')

  function getFutureDates(lastDate: string | null, count: number): string[] {
    if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
    const d = new Date(lastDate)
    return Array.from({ length: count }, (_, i) => {
      const nd = new Date(d)
      nd.setDate(nd.getDate() + i + 1)
      return nd.toISOString().slice(0, 10)
    })
  }

  /** Client-side fallback prediction: WMA + historical volatility */
  function computeFallbackPrediction(history: any[]): number[] {
    const quantities = history.map((h: any) => h.total_qty || h.qty || 0).filter((v: number) => v != null)
    if (quantities.length < 3) return Array.from({ length: 7 }, () => 0)
    const last7 = quantities.slice(-7)
    const weights = [0.05, 0.08, 0.12, 0.15, 0.18, 0.22, 0.20]
    const w = weights.slice(-last7.length)
    const wma = Math.round(last7.reduce((s, v, i) => s + v * w[i], 0) / w.reduce((a, b) => a + b, 0))
    const avg = last7.reduce((s, v) => s + v, 0) / last7.length
    const stdDev = Math.sqrt(last7.reduce((s, v) => s + (v - avg) ** 2, 0) / last7.length)
    const volatility = stdDev * 0.3
    return Array.from({ length: 7 }, (_, i) => {
      const noise = Math.sin(i * 2.7 + 1.3) * volatility
      return Math.max(0, Math.round(wma + noise))
    })
  }

  function aggregateWeekly(dailyData: any[]): any[] {
    if (dailyData.length === 0) return []
    const weeks: any[] = []
    let currentWeek: any[] = []
    let weekStart = ''
    for (const d of dailyData) {
      const date = new Date(d.date)
      const dayOfWeek = date.getDay()
      if (dayOfWeek === 1 && currentWeek.length > 0) {
        const totalQty = currentWeek.reduce((s: number, x: any) => s + (x.total_qty || 0), 0)
        weeks.push({
          date: weekStart,
          dateLabel: `${weekStart.slice(5)}~${currentWeek[currentWeek.length - 1].date.slice(5)}`,
          total_qty: totalQty,
        })
        currentWeek = []
      }
      if (currentWeek.length === 0) weekStart = d.date
      currentWeek.push(d)
    }
    if (currentWeek.length > 0) {
      const totalQty = currentWeek.reduce((s: number, x: any) => s + (x.total_qty || 0), 0)
      weeks.push({
        date: weekStart,
        dateLabel: `${weekStart.slice(5)}~${currentWeek[currentWeek.length - 1].date.slice(5)}`,
        total_qty: totalQty,
      })
    }
    return weeks
  }

  const detailChartOption = computed(() => {
    const range = detailTimeRange.value
    const predDates = detailPredictionDates.value
    const predValues = detailPredictionData.value

    // 3m: weekly aggregation, no prediction overlay
    if (range === '3m') {
      const weeklyData = aggregateWeekly(detailHistoryData.value)
      const dates = weeklyData.map((d: any) => d.dateLabel)
      const values = weeklyData.map((d: any) => d.total_qty || 0)
      return {
        tooltip: {
          trigger: 'axis' as const,
          axisPointer: { type: 'shadow' as const },
          formatter: (params: any) => {
            const p = params[0]
            return `${p.axisValue}<br/>${p.marker} 周销量: ${p.value}`
          },
        },
        grid: { left: 50, right: 20, top: 20, bottom: 50 },
        xAxis: { type: 'category' as const, data: dates, axisLabel: { fontSize: 11, rotate: 30 } },
        yAxis: { type: 'value' as const, name: '周销量' },
        dataZoom: [
          { type: 'inside' as const, start: 0, end: 100 },
          { type: 'slider' as const, start: 0, end: 100, height: 18, bottom: 5 },
        ],
        series: [{
          name: '周销量', type: 'line' as const, smooth: true, data: values,
          showSymbol: true, symbol: 'circle', symbolSize: 7,
          lineStyle: { color: '#005BF5', width: 2.5 },
          areaStyle: { color: 'rgba(0,91,245,0.12)' },
          emphasis: { scale: 1.8 },
        }],
      }
    }

    // 7d / 30d: daily data with prediction overlay
    const histDates = detailHistoryData.value.map((d: any) => d.date)
    const histValues = detailHistoryData.value.map((d: any) => d.total_qty || 0)
    const xData = [...histDates, ...predDates]
    const histSeries = [...histValues, ...Array(predDates.length).fill(null)] as (number | null)[]
    const predSeries = [...Array(histValues.length).fill(null), ...predValues] as (number | null)[]

    if (range === '7d') {
      return {
        tooltip: { trigger: 'axis' as const, axisPointer: { type: 'cross' as const } },
        legend: { data: ['历史销量', '预测销量'], bottom: 0 },
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category' as const, data: xData, axisLabel: { fontSize: 11 } },
        yAxis: { type: 'value' as const, name: '销量' },
        series: [
          {
            name: '历史销量', type: 'line' as const, smooth: true, data: histSeries,
            showSymbol: true, symbol: 'circle', symbolSize: 8,
            lineStyle: { color: '#005BF5', width: 2.5 },
            areaStyle: { color: 'rgba(0,91,245,0.12)' },
            label: { show: true, position: 'top' as const, fontSize: 11, fontWeight: 600 },
          },
          {
            name: '预测销量', type: 'line' as const, smooth: true, data: predSeries,
            showSymbol: true, symbol: 'diamond', symbolSize: 7,
            lineStyle: { color: '#fc8452', width: 2, type: 'dashed' as const },
            areaStyle: { color: 'rgba(252,132,82,0.1)' },
            itemStyle: { color: '#fc8452' },
          },
        ],
      }
    }

    // 30d default: daily + dataZoom slider
    return {
      tooltip: { trigger: 'axis' as const, axisPointer: { type: 'cross' as const, crossStyle: { color: '#999' } } },
      legend: { data: ['历史销量', '预测销量'], bottom: 0 },
      grid: { left: 50, right: 20, top: 20, bottom: 50 },
      xAxis: { type: 'category' as const, data: xData, axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' as const, name: '销量' },
      dataZoom: [
        { type: 'inside' as const, start: 0, end: 100 },
        { type: 'slider' as const, start: 0, end: 100, height: 18, bottom: 5 },
      ],
      series: [
        {
          name: '历史销量', type: 'line' as const, smooth: true, data: histSeries,
          showSymbol: true, symbol: 'circle', symbolSize: 5,
          lineStyle: { color: '#005BF5', width: 2 },
        },
        {
          name: '预测销量', type: 'line' as const, smooth: true, data: predSeries,
          showSymbol: true, symbol: 'diamond', symbolSize: 7,
          lineStyle: { color: '#fc8452', width: 2, type: 'dashed' as const },
          areaStyle: { color: 'rgba(252,132,82,0.1)' },
          itemStyle: { color: '#fc8452' },
        },
      ],
    }
  })

  async function setDetailTimeRange(range: '7d' | '30d' | '3m') {
    detailTimeRange.value = range
    if (expanded.expandedProductId.value != null) {
      await loadDetailData(expanded.expandedProductId.value)
    }
  }

  // ROP detail loading (kept here because it shares the detail fetch lifecycle)
  const ropLoading = ref(false)
  const ropResult = ref<any>(null)

  async function loadDetailData(productId: number) {
    const key = `${productId}-${detailTimeRange.value}`
    if (_detailFetchKey.value === key) return  // same request already in progress
    _detailFetchKey.value = key

    detailChartLoading.value = true
    ropLoading.value = true
    detailHistoryData.value = []
    detailPredictionData.value = []
    detailPredictionDates.value = []
    ropResult.value = null

    try {
      // Load sales history + prediction in parallel with ROP
      const daysMap = { '7d': 7, '30d': 30, '3m': 90 }
      const days = daysMap[detailTimeRange.value] || 30
      const warehouseId = expanded.expandedProduct.value?.warehouse_id
      const [history, pred, rop] = await Promise.allSettled([
        aiApi.salesHistory({ product_id: productId, days }),
        aiApi.salesPrediction(productId),
        store.fetchSuggestedQty(productId, undefined, warehouseId),
      ])

      // Process history
      if (history.status === 'fulfilled') {
        detailHistoryData.value = Array.isArray(history.value) ? history.value : []
      }

      // Process prediction
      if (pred.status === 'fulfilled' && pred.value) {
        const predValue = pred.value as any
        let parsed = predValue.output_data ?? predValue.data ?? predValue
        if (typeof parsed === 'string') {
          try { parsed = JSON.parse(parsed) } catch { /* keep as string */ }
        }
        const lastDate =
          detailHistoryData.value.length > 0
            ? detailHistoryData.value[detailHistoryData.value.length - 1].date
            : null
        if (parsed?.predictions && Array.isArray(parsed.predictions)) {
          detailPredictionData.value = parsed.predictions.slice(0, 7)
          detailPredictionDates.value = getFutureDates(lastDate, 7)
        } else if (parsed?.forecast_next_30d) {
          // Has total but no daily predictions: generate volatile prediction from history
          detailPredictionData.value = computeFallbackPrediction(detailHistoryData.value)
          detailPredictionDates.value = getFutureDates(lastDate, 7)
        }
      }

      // Process ROP
      if (rop.status === 'fulfilled' && rop.value) {
        ropResult.value = rop.value
        // Set default purchase quantity: prefer ROP suggestion, fallback to product's suggested_qty
        const suggested = rop.value.suggested_qty
        const fallback = expanded.expandedProduct.value?.suggested_qty ?? 0
        const qtyToSet = (suggested != null && suggested > 0) ? suggested : (fallback > 0 ? fallback : 0)
        if (qtyToSet > 0 && (!(productId in store.quantities) || store.quantities[productId] === 0)) {
          store.quantities[productId] = qtyToSet
        }
      }
    } catch (e) {
      console.error('loadDetailData error:', e)
    } finally {
      detailChartLoading.value = false
      ropLoading.value = false
      _detailFetchKey.value = ''  // P1-13 fix: clear cache key after completion
    }
  }

  return {
    detailChartLoading,
    detailHistoryData,
    detailPredictionData,
    detailPredictionDates,
    detailTimeRange,
    detailChartOption,
    setDetailTimeRange,
    ropLoading,
    ropResult,
    loadDetailData,
  }
}
