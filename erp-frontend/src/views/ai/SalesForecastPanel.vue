<template>
  <div class="sales-forecast-panel">
    <div class="filter-bar" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">
      <el-select v-model="filterProductId" placeholder="选择产品查看详情" clearable filterable style="width: 220px;" size="small" @change="onProductSelect">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-button v-if="viewMode === 'product'" type="default" size="small" @click="backToAggregate">
        <el-icon style="margin-right: 4px;"><ArrowLeft /></el-icon>返回总览
      </el-button>
      <el-date-picker v-if="viewMode === 'product'" v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" size="small" style="width: 220px;" />
      <el-button v-if="viewMode === 'product'" type="primary" size="small" @click="loadProductData">分析</el-button>
    </div>

    <div v-loading="loading" style="height: 360px; margin-bottom: 12px;">
      <v-chart v-if="!loading && hasData" :option="chartOption" autoresize style="height: 100%;" />
      <el-empty v-else-if="!loading" description="暂无销售数据" />
    </div>

    <!-- TOP 5 产品排名（聚合模式） -->
    <div v-if="viewMode === 'aggregate' && topProducts.length > 0" class="top-products-section">
      <div class="section-title">TOP 5 畅销产品</div>
      <div class="top-products-list">
        <div v-for="(item, idx) in topProducts" :key="item.product_id" class="top-product-item" @click="selectTopProduct(item)">
          <span class="top-rank" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</span>
          <span class="top-name">{{ item.name }}</span>
          <span class="top-qty">{{ item.total_qty }} 件</span>
          <span class="top-amount">¥{{ formatAmount(item.total_amount) }}</span>
        </div>
      </div>
    </div>

    <!-- 产品模式：切换按钮 -->
    <div v-if="viewMode === 'product'" style="display: flex; justify-content: center; gap: 12px; margin-bottom: 12px;">
      <div class="toggle-btn" :class="{ active: activeView === 'history' }" @click="activeView = 'history'">
        <el-icon class="toggle-icon"><TrendCharts /></el-icon>
        <span class="toggle-label">历史销量</span>
      </div>
      <div class="toggle-btn" :class="{ active: activeView === 'forecast' }" @click="activeView = 'forecast'">
        <el-icon class="toggle-icon"><DataAnalysis /></el-icon>
        <span class="toggle-label">预测销量（LLM）</span>
      </div>
    </div>

    <div v-if="viewMode === 'product' && aiResult" class="ai-bubble">
      <div class="ai-avatar">AI</div>
      <div class="ai-message">
        <p style="white-space: pre-wrap; margin: 0;">{{ aiResult.summary || aiResult.suggestion || '分析完成' }}</p>
        <div v-if="aiResult.trend" style="margin-top: 6px;">
          <el-tag :type="aiResult.trend === '上升' ? 'danger' : aiResult.trend === '下降' ? 'success' : 'info'" size="small">趋势: {{ aiResult.trend }}</el-tag>
        </div>
        <div v-if="aiResult.forecast_next_30d" style="margin-top: 6px;">预测未来30天销量: <b>{{ aiResult.forecast_next_30d }}</b></div>
        <div v-if="aiResult.confidence" class="ai-confidence">
          置信度: <el-progress :percentage="Math.round(aiResult.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; margin-left: 6px;" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent } from 'echarts/components'
import { TrendCharts, DataAnalysis, ArrowLeft } from '@element-plus/icons-vue'
import { productApi, aiApi } from '@/api'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent])

const products = ref<any[]>([])
const loading = ref(false)
const aiResult = ref<any>(null)
const dateRange = ref<any>(null)
const activeView = ref<'history' | 'forecast'>('history')

// View mode: aggregate or product
const viewMode = ref<'aggregate' | 'product'>('aggregate')
const filterProductId = ref<number | null>(null)

// Aggregate mode data
const aggregateData = ref<any[]>([])
const topProducts = ref<any[]>([])

// Product mode data
const productDailyData = ref<any[]>([])
const predictions = ref<number[]>([])
const predictionDates = ref<string[]>([])

const hasData = computed(() => {
  if (viewMode.value === 'aggregate') return aggregateData.value.length > 0
  return productDailyData.value.length > 0
})

function formatAmount(val: number): string {
  if (val >= 10000) return (val / 10000).toFixed(1) + '万'
  return val.toLocaleString()
}

function getFutureDates(lastDate: string, count: number): string[] {
  if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
  const d = new Date(lastDate)
  return Array.from({ length: count }, (_, i) => {
    const nd = new Date(d)
    nd.setDate(nd.getDate() + i + 1)
    return nd.toISOString().slice(0, 10)
  })
}

function calculateWMA(data: number[], days = 7): number {
  const weights = [0.05, 0.08, 0.12, 0.15, 0.18, 0.22, 0.20]
  const slice = data.slice(-days)
  if (slice.length === 0) return 0
  const w = weights.slice(-slice.length)
  const sum = w.reduce((s, wi, i) => s + wi * slice[i], 0)
  return Math.round(sum / w.reduce((a, b) => a + b, 0))
}

function computePrediction(history: number[]): number[] {
  if (history.length < 3) return Array.from({ length: 30 }, () => 0)
  const wma = calculateWMA(history)
  return Array.from({ length: 30 }, () => wma)
}

const chartOption = computed(() => {
  if (viewMode.value === 'aggregate') {
    // Aggregate mode: monthly bar + line chart
    const months = aggregateData.value.map((d: any) => d.month)
    const qtys = aggregateData.value.map((d: any) => d.total_qty || 0)
    const amounts = aggregateData.value.map((d: any) => d.total_amount || 0)

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', crossStyle: { color: '#999' } },
        formatter: (params: any) => {
          let tip = params[0].axisValue + '<br/>'
          params.forEach((p: any) => {
            const val = p.seriesName === '销售金额' ? '¥' + (p.value || 0).toLocaleString() : (p.value || 0)
            tip += `${p.marker} ${p.seriesName}: ${val}<br/>`
          })
          return tip
        },
      },
      legend: { data: ['销售数量', '销售金额'], bottom: 0 },
      grid: { left: 60, right: 60, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: months, axisLabel: { fontSize: 11 } },
      yAxis: [
        { type: 'value', name: '数量', position: 'left' },
        { type: 'value', name: '金额(元)', position: 'right', axisLabel: { formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + '万' : v } },
      ],
      series: [
        {
          name: '销售数量', type: 'bar', data: qtys, yAxisIndex: 0,
          itemStyle: { color: '#005BF5', borderRadius: [4, 4, 0, 0] },
          barWidth: '40%',
        },
        {
          name: '销售金额', type: 'line', data: amounts, yAxisIndex: 1, smooth: true,
          lineStyle: { color: '#fc8452', width: 2.5 },
          itemStyle: { color: '#fc8452' },
          symbol: 'circle', symbolSize: 8,
        },
      ],
    }
  }

  // Product mode
  const isForecast = activeView.value === 'forecast'

  if (isForecast) {
    const dates = predictionDates.value
    const values = predictions.value
    const historyDates = productDailyData.value.map((d: any) => d.date)
    const historyValues = productDailyData.value.map((d: any) => d.total_qty || 0)

    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#999' } } },
      legend: { data: ['历史销量', '预测销量'], bottom: 0 },
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: [...historyDates, ...dates], axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', name: '销量' },
      dataZoom: [{ type: 'inside', start: 0, end: 100 }],
      series: [
        { name: '历史销量', type: 'line', smooth: true, data: [...historyValues, ...Array(dates.length).fill(null)],
          showSymbol: true, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#005BF5', width: 2 } },
        { name: '预测销量', type: 'line', smooth: true, data: [...Array(historyValues.length).fill(null), ...values],
          showSymbol: true, symbol: 'diamond', symbolSize: 8, lineStyle: { color: '#fc8452', width: 2, type: 'dashed' },
          areaStyle: { color: 'rgba(252,132,82,0.1)' }, itemStyle: { color: '#fc8452' } },
      ],
    }
  }

  // History view (product mode)
  const dates = productDailyData.value.map((d: any) => d.date)
  const values = productDailyData.value.map((d: any) => d.total_qty || 0)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(84,112,198,0.06)' } } },
    grid: { left: 60, right: 30, top: 30, bottom: 20 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', name: '销量' },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [{
      name: '历史销量', type: 'line', smooth: true, data: values, showSymbol: true, symbol: 'circle', symbolSize: 7,
      lineStyle: { color: '#005BF5', width: 2.5 }, areaStyle: { color: 'rgba(0,91,245,0.12)' },
      emphasis: { scale: 1.8 },
    }],
  }
})

// Load aggregate data (no product_id)
const loadAggregateData = async () => {
  loading.value = true
  try {
    const res: any = await aiApi.salesHistory({})
    if (res && res.monthly_data) {
      aggregateData.value = res.monthly_data || []
      topProducts.value = res.top_products || []
    } else {
      aggregateData.value = []
      topProducts.value = []
    }
  } catch {
    aggregateData.value = []
    topProducts.value = []
  } finally {
    loading.value = false
  }
}

// Load product-specific data
const loadProductData = async () => {
  if (!filterProductId.value) return
  loading.value = true
  viewMode.value = 'product'
  activeView.value = 'history'
  try {
    const params: any = { product_id: filterProductId.value }
    if (dateRange.value) {
      const diff = Math.ceil((dateRange.value[1] - dateRange.value[0]) / (1000 * 60 * 60 * 24))
      params.days = diff
    }
    productDailyData.value = (await aiApi.salesHistory(params)) || []

    // LLM prediction
    try {
      const pred: any = await aiApi.salesPrediction(filterProductId.value)
      if (pred) {
        let parsed = pred.output_data
        if (typeof parsed === 'string') try { parsed = JSON.parse(parsed) } catch (e) { console.warn('Failed to parse output_data:', e); parsed = null }
        if (parsed) {
          aiResult.value = { ...parsed, summary: pred.summary || parsed?.suggestion || '', confidence: pred.confidence || parsed?.confidence || 0 }
        } else {
          aiResult.value = { summary: pred.summary || '', confidence: pred.confidence || 0 }
        }
        // Use LLM prediction data for chart
        if (parsed && parsed.predictions && parsed.predictions.length > 0) {
          predictions.value = parsed.predictions
          const lastDate = productDailyData.value.length > 0 ? productDailyData.value[productDailyData.value.length - 1].date : null
          predictionDates.value = parsed.prediction_dates || getFutureDates(lastDate, parsed.predictions.length)
        } else {
          // WMA fallback
          const fullValues = productDailyData.value.map((d: any) => d.total_qty || 0)
          predictions.value = computePrediction(fullValues)
          const lastDate = productDailyData.value.length > 0 ? productDailyData.value[productDailyData.value.length - 1].date : null
          predictionDates.value = getFutureDates(lastDate, 30)
        }
      }
    } catch {
      // Fallback: WMA prediction
      const fullValues = productDailyData.value.map((d: any) => d.total_qty || 0)
      predictions.value = computePrediction(fullValues)
      const lastDate = productDailyData.value.length > 0 ? productDailyData.value[productDailyData.value.length - 1].date : null
      predictionDates.value = getFutureDates(lastDate, 30)
      aiResult.value = { summary: `基于 ${productDailyData.value.length} 天数据完成分析`, trend: '平稳', confidence: 0.6 }
    }
  } finally { loading.value = false }
}

const onProductSelect = (val: number | null) => {
  if (val) {
    filterProductId.value = val
    loadProductData()
  } else {
    backToAggregate()
  }
}

const backToAggregate = () => {
  filterProductId.value = null
  viewMode.value = 'aggregate'
  aiResult.value = null
  productDailyData.value = []
  predictions.value = []
  predictionDates.value = []
  loadAggregateData()
}

const selectTopProduct = (item: any) => {
  filterProductId.value = item.product_id
  loadProductData()
}

onMounted(async () => {
  // Load product list
  const res: any = await productApi.list({ page: 1, page_size: 100 })
  products.value = res.items || []

  // Load aggregate data (default view)
  await loadAggregateData()
})
</script>

<style scoped>
.filter-bar { background: var(--bg-filter); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); }
.toggle-btn { display: flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 8px; border: 2px solid #e0e0e0; background: #fff; cursor: pointer; transition: all 0.25s; user-select: none; }
.toggle-btn:hover { border-color: #b0b0b0; background: #fafafa; }
.toggle-btn.active { border-color: var(--color-primary); background: var(--color-info-bg); box-shadow: 0 0 0 3px rgba(30, 58, 95, 0.12); }
.toggle-icon { font-size: 16px; }
.toggle-label { font-size: 13px; font-weight: 600; color: #333; }
.active .toggle-label { color: var(--color-primary); }
.ai-bubble { display: flex; gap: 12px; padding: 14px; background: var(--color-info-bg); border-radius: 12px; border: 1px solid var(--color-info-light); }
.ai-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #005BF5, #2e7bff); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px; flex-shrink: 0; }
.ai-message { flex: 1; font-size: 14px; line-height: 1.6; }
.ai-confidence { margin-top: 8px; font-size: 13px; color: #666; display: flex; align-items: center; }

/* TOP 5 产品排名 */
.top-products-section { margin-top: 4px; padding: 14px; background: var(--color-info-bg); border-radius: 12px; border: 1px solid var(--color-info-light); }
.section-title { font-size: 14px; font-weight: 600; color: var(--color-primary); margin-bottom: 10px; }
.top-products-list { display: flex; flex-direction: column; gap: 8px; }
.top-product-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #fff; border-radius: 8px; border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s; }
.top-product-item:hover { border-color: var(--color-primary); box-shadow: 0 2px 8px rgba(0, 91, 245, 0.1); }
.top-rank { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fff; background: #999; flex-shrink: 0; }
.rank-1 { background: linear-gradient(135deg, #FFD700, #FFA500); }
.rank-2 { background: linear-gradient(135deg, #C0C0C0, #A0A0A0); }
.rank-3 { background: linear-gradient(135deg, #CD7F32, #B87333); }
.top-name { flex: 1; font-size: 13px; font-weight: 500; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-qty { font-size: 12px; color: #666; }
.top-amount { font-size: 12px; color: var(--color-primary); font-weight: 600; }
</style>
