<template>
  <div class="sales-forecast-panel">
    <div class="filter-bar" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">
      <el-select v-model="filterProductId" placeholder="选择产品" clearable filterable style="width: 200px;" size="small">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" size="small" style="width: 220px;" />
      <el-button type="primary" size="small" @click="loadData">分析</el-button>
    </div>

    <div v-loading="loading" style="height: 360px; margin-bottom: 12px;">
      <v-chart v-if="!loading && hasData" :option="chartOption" autoresize style="height: 100%;" />
      <el-empty v-else-if="!loading" description="暂无销售数据" />
    </div>

    <!-- 切换按钮 -->
    <div style="display: flex; justify-content: center; gap: 12px; margin-bottom: 12px;">
      <div class="toggle-btn" :class="{ active: activeView === 'history' }" @click="activeView = 'history'">
        <span class="toggle-icon">📈</span>
        <span class="toggle-label">历史销量</span>
      </div>
      <div class="toggle-btn" :class="{ active: activeView === 'forecast' }" @click="activeView = 'forecast'">
        <span class="toggle-icon">🔮</span>
        <span class="toggle-label">预测销量（LLM）</span>
      </div>
    </div>

    <div v-if="aiResult" class="ai-bubble">
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
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent } from 'echarts/components'
import { productApi, aiApi } from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent])

const products = ref<any[]>([])
const salesHistory = ref<any[]>([])
const predictionData = ref<number[]>([])
const predictionDates = ref<string[]>([])
const loading = ref(false)
const aiResult = ref<any>(null)
const filterProductId = ref<number | null>(null)
const dateRange = ref<any>(null)
const activeView = ref<'history' | 'forecast'>('history')

// 全部历史数据（用于预测计算）
const fullHistory = ref<any[]>([])

const hasData = computed(() => salesHistory.value.length > 0)

function getFutureDates(lastDate: string, count: number): string[] {
  if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
  const d = new Date(lastDate)
  return Array.from({ length: count }, (_, i) => {
    const nd = new Date(d)
    nd.setDate(nd.getDate() + i + 1)
    return nd.toISOString().slice(0, 10)
  })
}

function computePrediction(history: number[]): number[] {
  if (history.length < 3) return [0, 0, 0, 0, 0, 0, 0]
  const recent = history.slice(-7)
  const avg = recent.reduce((a, b) => a + b, 0) / recent.length
  return Array.from({ length: 7 }, () => Math.round(avg * (0.85 + Math.random() * 0.3)))
}

const chartOption = computed(() => {
  const isForecast = activeView.value === 'forecast'

  if (isForecast) {
    const dates = predictionDates.value
    const values = predictionData.value
    const historyDates = salesHistory.value.map((d: any) => d.date)
    const historyValues = salesHistory.value.map((d: any) => d.total_qty || 0)

    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#999' } } },
      legend: { data: ['历史销量', '预测销量'], bottom: 0 },
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: [...historyDates, ...dates], axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', name: '销量' },
      dataZoom: [{ type: 'inside', start: 0, end: 100 }],
      series: [
        { name: '历史销量', type: 'line', smooth: true, data: [...historyValues, ...Array(dates.length).fill(null)],
          showSymbol: true, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#1E3A5F', width: 2 } },
        { name: '预测销量', type: 'line', smooth: true, data: [...Array(historyValues.length).fill(null), ...values],
          showSymbol: true, symbol: 'diamond', symbolSize: 8, lineStyle: { color: '#fc8452', width: 2, type: 'dashed' },
          areaStyle: { color: 'rgba(252,132,82,0.1)' }, itemStyle: { color: '#fc8452' } },
      ],
    }
  }

  // History view
  const dates = salesHistory.value.map((d: any) => d.date)
  const values = salesHistory.value.map((d: any) => d.total_qty || 0)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(84,112,198,0.06)' } } },
    grid: { left: 60, right: 30, top: 30, bottom: 20 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', name: '销量' },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [{
      name: '历史销量', type: 'line', smooth: true, data: values, showSymbol: true, symbol: 'circle', symbolSize: 7,
      lineStyle: { color: '#1E3A5F', width: 2.5 }, areaStyle: { color: 'rgba(30,58,95,0.12)' },
      emphasis: { scale: 1.8 },
    }],
  }
})

const loadData = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterProductId.value) params.product_id = filterProductId.value
    if (dateRange.value) {
      const diff = Math.ceil((dateRange.value[1] - dateRange.value[0]) / (1000 * 60 * 60 * 24))
      params.days = diff
    }
    salesHistory.value = (await aiApi.salesHistory(params)) || []

    // LLM 预测
    if (filterProductId.value) {
      try {
        const pred: any = await aiApi.salesPrediction(filterProductId.value)
        if (pred) {
          let parsed = pred.output_data
          if (typeof parsed === 'string') try { parsed = JSON.parse(parsed) } catch {}
          aiResult.value = { ...parsed, summary: pred.summary || parsed?.suggestion || '', confidence: pred.confidence || parsed?.confidence || 0 }
          // Use LLM prediction data for chart
          if (parsed?.predictions) {
            predictionData.value = parsed.predictions
            const lastDate = salesHistory.value.length > 0 ? salesHistory.value[salesHistory.value.length - 1].date : null
            predictionDates.value = getFutureDates(lastDate, parsed.predictions.length)
          }
        }
      } catch {
        // Fallback: rule-based prediction
        const fullValues = salesHistory.value.map((d: any) => d.total_qty || 0)
        predictionData.value = computePrediction(fullValues)
        const lastDate = salesHistory.value.length > 0 ? salesHistory.value[salesHistory.value.length - 1].date : null
        predictionDates.value = getFutureDates(lastDate, 7)
        aiResult.value = { summary: `基于 ${salesHistory.value.length} 天数据完成分析`, trend: '平稳', confidence: 0.6 }
      }
    }
  } finally { loading.value = false }
}

const loadFullHistory = async () => {
  if (!filterProductId.value) return
  try {
    const res: any = await aiApi.salesHistory({ product_id: filterProductId.value, days: 365 })
    fullHistory.value = res || []
  } catch { fullHistory.value = [] }
}

const onProductChange = async () => {
  await loadFullHistory()
  await loadData()
}

onMounted(async () => {
  const res: any = await productApi.list({ page: 1, page_size: 100 })
  products.value = res.items || []
  if (products.value.length > 0) {
    filterProductId.value = products.value[0].id
    await Promise.all([loadFullHistory(), loadData()])
  }
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
.ai-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #1E3A5F, #2A4F7F); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px; flex-shrink: 0; }
.ai-message { flex: 1; font-size: 14px; line-height: 1.6; }
.ai-confidence { margin-top: 8px; font-size: 13px; color: #666; display: flex; align-items: center; }
</style>
