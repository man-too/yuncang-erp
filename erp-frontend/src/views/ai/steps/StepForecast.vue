<template>
  <div class="step-forecast">
    <!-- Upper: AI Sales Prediction Analysis -->
    <div class="ai-section">
      <div class="section-row">
        <span class="section-title">AI 销量预测分析</span>
      </div>
      <div v-if="aiLoading" class="ai-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>AI 正在分析销量数据，请稍候...</span>
      </div>
      <div v-else-if="aiResult" class="ai-bubble">
        <div class="ai-avatar">AI</div>
        <div class="ai-message">
          <p style="white-space: pre-wrap; margin: 0;">{{ aiResult.summary || aiResult.suggestion || '预测分析完成' }}</p>
          <div v-if="aiResult.trend" style="margin-top: 6px;">
            <el-tag :type="aiResult.trend === '上升' ? 'danger' : aiResult.trend === '下降' ? 'success' : 'info'" size="small">
              趋势: {{ aiResult.trend }}
            </el-tag>
          </div>
          <div v-if="aiResult.forecast_next_30d" style="margin-top: 6px;">
            预测未来30天销量: <b>{{ aiResult.forecast_next_30d }}</b>
          </div>
          <div v-if="aiResult.confidence" class="ai-confidence">
            置信度:
            <el-progress
              :percentage="Math.round(aiResult.confidence * 100)"
              :stroke-width="8"
              style="width: 120px; display: inline-block; margin-left: 6px;"
            />
          </div>
        </div>
      </div>
      <div v-else class="ai-placeholder">选择产品后自动进行 AI 销量预测分析</div>
    </div>

    <!-- Middle: Product Selector + History & Forecast Chart + Quantity -->
    <div class="chart-section">
      <div class="section-row" style="margin-bottom: 12px;">
        <span class="section-title">历史销量与预测</span>
        <el-select
          v-model="selectedProductId"
          placeholder="选择产品"
          filterable
          style="width: 260px;"
          @change="onProductChange"
        >
          <el-option
            v-for="p in store.allProducts"
            :key="p.product_id"
            :label="p.product_name"
            :value="p.product_id"
          />
        </el-select>
      </div>

      <div v-loading="chartLoading" class="chart-area">
        <v-chart
          v-if="!chartLoading && (historyData.length > 0 || predictionData.length > 0)"
          :option="chartOption"
          autoresize
          style="height: 340px;"
        />
        <el-empty
          v-else-if="!chartLoading"
          description="暂无销量数据，请选择产品"
          :image-size="80"
        />
      </div>

      <!-- Quantity adjustment for selected product -->
      <div v-if="selectedProduct" class="qty-row">
        <span class="qty-label">当前产品建议采购量：</span>
        <el-input-number
          v-model="selectedQuantity"
          :min="0"
          :precision="0"
          size="small"
          style="width: 160px;"
        />
        <span class="qty-unit">{{ selectedProduct.unit || '个' }}</span>
        <span class="qty-hint">
          （建议: {{ selectedProduct.suggested_qty }}，最大库存 {{ selectedProduct.max_stock }} - 当前 {{ selectedProduct.current_qty }}）
        </span>
      </div>
    </div>

    <!-- Lower: Overview Table + Navigation -->
    <div class="table-section">
      <div class="section-row" style="margin-bottom: 8px;">
        <span class="section-title">采购数量总览</span>
        <span class="section-count">共 {{ store.allProducts.length }} 项</span>
      </div>

      <el-table :data="store.allProducts" stripe size="small" max-height="360">
        <el-table-column prop="product_name" label="产品" min-width="130" show-overflow-tooltip />
        <el-table-column label="供应商" min-width="120">
          <template #default="{ row }">
            {{ getSupplierName(row.product_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="suggested_qty" label="建议量" width="80" align="right" />
        <el-table-column label="采购量" width="160" align="center">
          <template #default="{ row }">
            <el-input-number
              :model-value="store.quantities[row.product_id] ?? row.suggested_qty"
              @update:model-value="(v: number | undefined) => onQtyChange(row.product_id, v ?? 0)"
              :min="0"
              :precision="0"
              size="small"
              style="width: 130px;"
            />
          </template>
        </el-table-column>
        <el-table-column label="单价" width="100" align="right">
          <template #default="{ row }">
            &yen;{{ (store.forecastPrices[row.product_id] ?? row.purchase_price ?? 0).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">
            &yen;{{ computeAmount(row.product_id).toFixed(2) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="nav-row">
        <el-button @click="store.prevStep()">上一步</el-button>
        <el-button
          type="primary"
          :disabled="hasZeroQuantity || store.allProducts.length === 0"
          @click="onNextStep"
        >
          下一步：汇总确认 &rarr;
        </el-button>
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
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import { Loading } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { aiApi } from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const store = usePurchaseDecisionStore()

// -- Selected product --
const selectedProductId = ref<number | null>(null)
const selectedProduct = computed(() =>
  store.allProducts.find(p => p.product_id === selectedProductId.value) ?? null
)

// -- Selected product quantity (for the middle section input) --
const selectedQuantity = computed({
  get: () => {
    const pid = selectedProductId.value
    if (pid == null) return 0
    return store.quantities[pid] ?? selectedProduct.value?.suggested_qty ?? 0
  },
  set: (val: number) => {
    const pid = selectedProductId.value
    if (pid != null) {
      store.quantities[pid] = val
    }
  },
})

// -- AI prediction state --
const aiLoading = ref(false)
const aiResult = ref<any>(null)

// -- Chart state --
const chartLoading = ref(false)
const historyData = ref<any[]>([])
const predictionData = ref<number[]>([])
const predictionDates = ref<string[]>([])

// -- Helpers --
function getFutureDates(lastDate: string | null, count: number): string[] {
  if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
  const d = new Date(lastDate)
  return Array.from({ length: count }, (_, i) => {
    const nd = new Date(d)
    nd.setDate(nd.getDate() + i + 1)
    return nd.toISOString().slice(0, 10)
  })
}

// -- Chart option --
const chartOption = computed(() => {
  const histDates = historyData.value.map((d: any) => d.date)
  const histValues = historyData.value.map((d: any) => d.total_qty || 0)
  const predDates = predictionDates.value
  const predValues = predictionData.value

  const xData = [...histDates, ...predDates]

  const histSeries = [...histValues, ...Array(predDates.length).fill(null)] as (number | null)[]
  const predSeries = [...Array(histValues.length).fill(null), ...predValues] as (number | null)[]

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: '#999' } },
    },
    legend: {
      data: ['历史销量', '预测销量'],
      bottom: 0,
    },
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: '销量',
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: '历史销量',
        type: 'line',
        smooth: true,
        data: histSeries,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#5470c6', width: 2 },
      },
      {
        name: '预测销量',
        type: 'line',
        smooth: true,
        data: predSeries,
        showSymbol: true,
        symbol: 'diamond',
        symbolSize: 8,
        lineStyle: { color: '#fc8452', width: 2, type: 'dashed' },
        areaStyle: { color: 'rgba(252,132,82,0.1)' },
        itemStyle: { color: '#fc8452' },
      },
    ],
  }
})

// -- Data loading --
async function onProductChange() {
  const pid = selectedProductId.value
  if (pid == null) return

  aiLoading.value = true
  chartLoading.value = true
  aiResult.value = null
  historyData.value = []
  predictionData.value = []
  predictionDates.value = []

  try {
    // Load sales history
    const history = await aiApi.salesHistory({ product_id: pid, days: 90 })
    historyData.value = Array.isArray(history) ? history : []

    // Load AI prediction
    const pred: any = await aiApi.salesPrediction(pid)
    if (pred) {
      let parsed = pred.output_data
      if (typeof parsed === 'string') {
        try { parsed = JSON.parse(parsed) } catch { /* keep as string */ }
      }
      aiResult.value = {
        ...(typeof parsed === 'object' ? parsed : {}),
        summary: pred.summary || (typeof parsed === 'object' ? parsed?.suggestion : '') || '',
        confidence: pred.confidence ?? (typeof parsed === 'object' ? parsed?.confidence : undefined) ?? 0,
      }

      if (parsed?.predictions && Array.isArray(parsed.predictions)) {
        predictionData.value = parsed.predictions
        const lastDate =
          historyData.value.length > 0
            ? historyData.value[historyData.value.length - 1].date
            : null
        predictionDates.value = getFutureDates(lastDate, parsed.predictions.length)
      }
    }
  } catch {
    aiResult.value = { summary: 'AI 预测服务暂不可用，请稍后重试', trend: '未知', confidence: 0 }
  } finally {
    aiLoading.value = false
    chartLoading.value = false
  }
}

// -- Table helpers --
function getSupplierName(productId: number): string {
  const supplierId = store.supplierChoices[productId]
  if (supplierId == null) return '未分配'
  const info = store.supplierInfo[supplierId]
  return info?.name || info?.supplier_name || `供应商#${supplierId}`
}

function computeAmount(productId: number): number {
  const qty = store.quantities[productId] ?? store.allProducts.find(p => p.product_id === productId)?.suggested_qty ?? 0
  const price = store.forecastPrices[productId] ?? store.allProducts.find(p => p.product_id === productId)?.purchase_price ?? 0
  return qty * price
}

function onQtyChange(productId: number, value: number) {
  store.quantities[productId] = value
}

// -- Has any product with zero quantity --
const hasZeroQuantity = computed(() => {
  return store.allProducts.some(p => {
    const qty = store.quantities[p.product_id] ?? p.suggested_qty
    return qty <= 0
  })
})

// -- Navigation --
function onNextStep() {
  // Persist final quantities to forecastQuantities
  for (const p of store.allProducts) {
    store.forecastQuantities[p.product_id] =
      store.quantities[p.product_id] ?? p.suggested_qty
  }
  store.nextStep()
}

// -- Lifecycle --
onMounted(() => {
  // Initialize quantities from suggested_qty if not already set
  for (const p of store.allProducts) {
    if (!(p.product_id in store.quantities)) {
      store.quantities[p.product_id] = p.suggested_qty
    }
  }

  // Default select first product
  if (store.allProducts.length > 0 && selectedProductId.value == null) {
    selectedProductId.value = store.allProducts[0].product_id
    onProductChange()
  }
})
</script>

<style scoped>
.step-forecast {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

/* Shared */
.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.section-count {
  font-size: 12px;
  color: #909399;
}

/* Upper: AI Section */
.ai-section {
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 16px 20px;
  background: #f0f9ff;
}
.ai-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #909399;
  font-size: 13px;
  margin-top: 12px;
}
.ai-loading .is-loading {
  animation: rotating 2s linear infinite;
}
@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.ai-placeholder {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
  font-style: italic;
}
.ai-bubble {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e0f2fe;
  margin-top: 12px;
}
.ai-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 13px;
  flex-shrink: 0;
}
.ai-message {
  flex: 1;
  font-size: 14px;
  line-height: 1.6;
}
.ai-confidence {
  margin-top: 8px;
  font-size: 13px;
  color: #666;
  display: flex;
  align-items: center;
}

/* Middle: Chart Section */
.chart-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chart-area {
  min-height: 340px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qty-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 8px;
  flex-wrap: wrap;
}
.qty-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}
.qty-unit {
  font-size: 13px;
  color: #606266;
}
.qty-hint {
  font-size: 12px;
  color: #909399;
}

/* Lower: Table Section */
.table-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.nav-row {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 4px;
}
</style>
