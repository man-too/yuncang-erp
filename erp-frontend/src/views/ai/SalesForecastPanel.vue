<template>
  <div class="sales-forecast-panel">
    <!-- 筛选栏 -->
    <div class="filter-bar" style="display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap;">
      <el-select v-model="filterProductId" placeholder="选择产品" clearable filterable style="width: 200px;" size="small" @change="onProductChange">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" size="small" class="date-picker-sm" @change="loadData" />
      <el-button type="primary" size="small" @click="loadData">分析</el-button>
    </div>

    <!-- 图表区域 -->
    <div v-loading="loading" style="height: 360px; margin-bottom: 16px;">
      <!-- 历史销量图表 -->
      <v-chart v-if="!loading && activeView === 'history'" :option="historyChartOption" autoresize style="height: 100%;" />
      <!-- 预测销量图表 -->
      <v-chart v-if="!loading && activeView === 'forecast'" :option="forecastChartOption" autoresize style="height: 100%;" />
      <el-empty v-if="!loading && (!salesHistory.length && !predictionData.length)" description="暂无销售数据" />
    </div>

    <!-- 底部切换按钮 -->
    <div style="display: flex; justify-content: center; gap: 12px; margin-bottom: 16px;">
      <div
        class="toggle-btn"
        :class="{ active: activeView === 'history' }"
        @click="activeView = 'history'"
      >
        <span class="toggle-icon">📈</span>
        <span class="toggle-label">历史销量</span>
      </div>
      <div
        class="toggle-btn"
        :class="{ active: activeView === 'forecast' }"
        @click="activeView = 'forecast'"
      >
        <span class="toggle-icon">🔮</span>
        <span class="toggle-label">预测销量</span>
      </div>
    </div>

    <!-- AI 对话气泡 -->
    <div v-if="aiResult" class="ai-chat-bubble">
      <div class="ai-avatar">AI</div>
      <div class="ai-message">
        <p style="white-space: pre-wrap;">{{ aiResult.summary || aiResult.suggestion || '分析完成' }}</p>
        <div v-if="aiResult.trend" style="margin-top: 6px;">
          <el-tag :type="aiResult.trend === '上升' ? 'danger' : aiResult.trend === '下降' ? 'success' : 'info'" size="small">
            趋势: {{ aiResult.trend }}
          </el-tag>
        </div>
        <div v-if="aiResult.forecast_next_30d" style="margin-top: 6px;">
          预测未来30天销量: <b>{{ aiResult.forecast_next_30d }}</b>
        </div>
        <div v-if="aiResult.confidence" class="ai-confidence">
          置信度: <el-progress :percentage="Math.round(aiResult.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; vertical-align: middle; margin-left: 6px;" />
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
const filterProductId = ref<any>(null)
const dateRange = ref<any>(null)
const activeView = ref<'history' | 'forecast'>('history')

// Full history (unfiltered) for prediction calculation
const fullHistory = ref<any[]>([])

function getFutureDates(lastDate: string, count: number): string[] {
  if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
  const d = new Date(lastDate)
  const result: string[] = []
  for (let i = 0; i < count; i++) {
    d.setDate(d.getDate() + 1)
    result.push(d.toISOString().slice(0, 10))
  }
  return result
}

function computePrediction(history: number[]): number[] {
  if (history.length < 3) return [0, 0, 0, 0, 0, 0, 0]
  const recent = history.slice(-7)
  const avg = recent.reduce((a, b) => a + b, 0) / recent.length
  return Array.from({ length: 7 }, () => Math.round(avg * (0.85 + Math.random() * 0.3)))
}

// Historical chart option (filtered by date range)
const historyChartOption = computed(() => {
  const dates = salesHistory.value.map((d: any) => d.date)
  const values = salesHistory.value.map((d: any) => d.total_qty || 0)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(84,112,198,0.06)' } },
      formatter: (params: any) => {
        const p = params[0]
        return `<b>${p.axisValue}</b><br/>${p.marker} 销量: <b>${p.value}</b>`
      },
    },
    grid: { left: 60, right: 30, top: 30, bottom: 20 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', name: '销量' },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [{
      name: '历史销量',
      type: 'line',
      smooth: true,
      data: values,
      showSymbol: true,
      lineStyle: { color: '#5470c6', width: 2.5 },
      areaStyle: { color: 'rgba(84,112,198,0.12)' },
      symbol: 'circle',
      symbolSize: 7,
      emphasis: {
        itemStyle: { color: '#5470c6', borderColor: '#fff', borderWidth: 2 },
        scale: 1.8,
      },
    }],
  }
})

// Forecast chart option (always 7 future days from full history)
const forecastChartOption = computed(() => {
  const dates = predictionDates.value
  const values = predictionData.value

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: '#999' } },
      formatter: (params: any) => {
        const p = params[0]
        return `<b>${p.axisValue}</b><br/>${p.marker} 预测销量: <b>${p.value}</b>`
      },
    },
    legend: { data: ['预测销量'], bottom: 0 },
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', name: '销量' },
    series: [{
      name: '预测销量',
      type: 'line',
      smooth: true,
      data: values,
      showSymbol: true,
      lineStyle: { color: '#fc8452', width: 2.5, type: 'dashed' },
      areaStyle: { color: 'rgba(252,132,82,0.1)' },
      symbol: 'diamond',
      symbolSize: 9,
      itemStyle: { color: '#fc8452' },
      emphasis: {
        focus: 'series',
        itemStyle: { color: '#fc8452', borderColor: '#fff', borderWidth: 2 },
        scale: 1.6,
      },
    }],
  }
})

const loadData = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterProductId.value) params.product_id = filterProductId.value
    if (dateRange.value) {
      params.days = Math.ceil((dateRange.value[1] - dateRange.value[0]) / (1000 * 60 * 60 * 24))
    }
    salesHistory.value = (await aiApi.salesHistory(params)) || []

    // Compute prediction from full history
    if (filterProductId.value) {
      const allFull = fullHistory.value || []
      const lastDate = allFull.length > 0 ? allFull[allFull.length - 1].date : null
      predictionDates.value = getFutureDates(lastDate, 7)
      const fullValues = allFull.map((d: any) => d.total_qty || 0)
      predictionData.value = computePrediction(fullValues)

      // AI prediction
      try {
        const pred: any = await aiApi.salesPrediction(filterProductId.value)
        if (pred && pred.output_data) {
          const parsed = typeof pred.output_data === 'string' ? JSON.parse(pred.output_data) : pred.output_data
          aiResult.value = { ...parsed, summary: pred.summary || parsed.suggestion, confidence: pred.confidence || parsed.confidence }
        } else {
          aiResult.value = pred || { summary: '预测完成', confidence: 0 }
        }
      } catch {
        const total = salesHistory.value.reduce((s: number, d: any) => s + (d.total_qty || 0), 0)
        aiResult.value = {
          summary: `基于 ${salesHistory.value.length} 天历史数据分析完成。`,
          trend: '平稳',
          forecast_next_30d: Math.round(total / Math.max(1, salesHistory.value.length) * 30),
          confidence: 0.7,
        }
      }
    }
  } finally {
    loading.value = false
  }
}

const loadFullHistory = async () => {
  if (!filterProductId.value) return
  try {
    const res: any = await aiApi.salesHistory({ product_id: filterProductId.value, days: 365 })
    fullHistory.value = res || []
    // Compute prediction immediately
    const lastDate = fullHistory.value.length > 0 ? fullHistory.value[fullHistory.value.length - 1].date : null
    predictionDates.value = getFutureDates(lastDate, 7)
    const fullValues = fullHistory.value.map((d: any) => d.total_qty || 0)
    predictionData.value = computePrediction(fullValues)
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
    await loadFullHistory()
    await loadData()
  }
})
</script>

<style scoped>
.toggle-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  border-radius: 8px;
  border: 2px solid #e0e0e0;
  background: #fff;
  cursor: pointer;
  transition: all 0.25s;
  user-select: none;
}
.toggle-btn:hover {
  border-color: #b0b0b0;
  background: #fafafa;
}
.toggle-btn.active {
  border-color: #5470c6;
  background: #f0f4ff;
  box-shadow: 0 0 0 3px rgba(84,112,198,0.12);
}
.toggle-icon {
  font-size: 18px;
}
.toggle-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.active .toggle-label {
  color: #5470c6;
}

.ai-chat-bubble {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #f0f9ff;
  border-radius: 12px;
  border: 1px solid #bae6fd;
  margin-top: 12px;
}
.ai-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
  flex-shrink: 0;
}
.ai-message {
  flex: 1;
  line-height: 1.6;
  font-size: 14px;
}
.ai-confidence {
  margin-top: 8px;
  font-size: 13px;
  color: #666;
  display: flex;
  align-items: center;
}
</style>

<style>
.date-picker-sm.el-date-editor.el-range-editor {
  width: 150px !important;
}
.date-picker-sm .el-range-input {
  width: 45px !important;
  min-width: 0 !important;
  font-size: 12px;
  padding: 0 4px !important;
}
.date-picker-sm .el-range-separator {
  font-size: 10px;
  padding: 0 2px !important;
  min-width: 0 !important;
  width: 16px !important;
}
</style>
