<template>
  <div class="step-inventory">
    <!-- Section 1: KPI Cards -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value">{{ kpiTurnoverDays }}</div>
        <div class="kpi-label">周转天数</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{{ kpiDeadStockCount }}</div>
        <div class="kpi-label">呆滞品数</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{{ kpiDeadStockPct }}</div>
        <div class="kpi-label">呆滞品占比</div>
      </div>
      <div class="kpi-card kpi-card--highlight">
        <div class="kpi-value">{{ kpiCapitalOccupied }}</div>
        <div class="kpi-label">占用资金</div>
      </div>
    </div>

    <!-- Section 2: Product List sorted by risk -->
    <div class="table-section">
      <div class="table-header">
        <span class="section-title">库存产品清单</span>
        <div class="header-right">
          <el-select
            v-model="productFilter"
            placeholder="筛选产品"
            clearable
            filterable
            size="small"
            style="width: 220px;"
          >
            <el-option
              v-for="p in store.allProducts"
              :key="p.product_id"
              :label="`${p.product_name}（${p.product_code}）`"
              :value="p.product_id"
            />
          </el-select>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索产品…"
            clearable
            size="small"
            :prefix-icon="Search"
            style="width: 200px;"
          />
          <span class="section-count">共 {{ filteredProducts.length }} 项</span>
          <el-button type="primary" size="default" @click="openAddDialog">+ 添加产品</el-button>
        </div>
      </div>

      <el-table
        :data="filteredProducts"
        max-height="480"
        size="small"
        stripe
        row-key="product_id"
        @selection-change="onSelectionChange"
        ref="tableRef"
        :row-class-name="rowClassName"
        @row-click="onRowClick"
        highlight-current-row
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="状态" width="72" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row)" size="small" effect="dark">
              {{ statusLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="product_name" label="产品名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="product_code" label="编码" min-width="100" />
        <el-table-column prop="warehouse_name" label="仓库" min-width="110" />
        <el-table-column label="当前库存" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.current_qty < row.min_stock }">{{ row.current_qty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="min_stock" label="安全库存" min-width="90" align="right" />
        <el-table-column label="ROP" min-width="80" align="right">
          <template #default="{ row }">
            <span v-if="ropMap[row.product_id] != null" class="rop-cell">{{ ropMap[row.product_id] }}</span>
            <span v-else class="rop-none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="max_stock" label="最高库存" min-width="90" align="right" />
        <el-table-column label="操作" width="130" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="toggleExpand(row)">
              {{ expandedProductId === row.product_id ? '收起' : '详情' }}
            </el-button>
            <el-button link type="primary" size="small" @click.stop="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click.stop="store.removeProduct(row.product_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Expandable Detail Panel -->
      <div v-if="expandedProduct" class="expand-panel">
        <div class="expand-header">
          <span class="expand-title">{{ expandedProduct.product_name }} — 库存详情与销量预测</span>
          <el-button link type="info" size="small" @click="expandedProductId = null">收起</el-button>
        </div>

        <!-- Stock Info -->
        <div class="expand-stock-row">
          <div class="stock-info-item">
            <span class="stock-info-label">当前库存</span>
            <span class="stock-info-value" :class="{ 'text-danger': expandedProduct.current_qty < expandedProduct.min_stock }">
              {{ expandedProduct.current_qty }} {{ expandedProduct.unit }}
            </span>
          </div>
          <div class="stock-info-item">
            <span class="stock-info-label">安全库存</span>
            <span class="stock-info-value">{{ expandedProduct.min_stock }} {{ expandedProduct.unit }}</span>
          </div>
          <div class="stock-info-item">
            <span class="stock-info-label">最高库存</span>
            <span class="stock-info-value">{{ expandedProduct.max_stock }} {{ expandedProduct.unit }}</span>
          </div>
          <div class="stock-info-item">
            <span class="stock-info-label">缺口</span>
            <span class="stock-info-value" :class="{ 'text-danger': expandedProduct.current_qty < expandedProduct.min_stock }">
              {{ Math.max(0, expandedProduct.min_stock - expandedProduct.current_qty) }} {{ expandedProduct.unit }}
            </span>
          </div>
        </div>

        <!-- Sales Forecast Chart -->
        <div class="expand-chart-section">
          <div class="chart-toolbar">
            <div class="time-tabs">
              <div class="time-tab" :class="{ active: detailTimeRange === '7d' }" @click="setDetailTimeRange('7d')">近7天</div>
              <div class="time-tab" :class="{ active: detailTimeRange === '30d' }" @click="setDetailTimeRange('30d')">近30天</div>
              <div class="time-tab" :class="{ active: detailTimeRange === '3m' }" @click="setDetailTimeRange('3m')">近3个月</div>
            </div>
          </div>
          <div v-loading="detailChartLoading" class="chart-area" style="height: 300px;">
            <v-chart
              v-if="!detailChartLoading && (detailHistoryData.length > 0 || detailPredictionData.length > 0)"
              :key="`detail-chart-${expandedProductId}-${detailTimeRange}`"
              :option="detailChartOption"
              autoresize
              style="height: 100%;"
            />
            <el-empty v-else-if="!detailChartLoading" description="暂无销量数据" :image-size="60" />
          </div>
        </div>

        <!-- ROP Calculation Result -->
        <div class="expand-rop-section">
          <div class="rop-title">ROP 再订货点计算</div>
          <div v-if="ropLoading" class="rop-loading" v-loading="true" element-loading-text="计算中..."></div>
          <div v-else-if="ropResult" class="rop-grid">
            <div class="rop-item">
              <span class="rop-label">日均销量</span>
              <span class="rop-value">{{ ropResult.avg_daily_sales ?? '—' }}</span>
            </div>
            <div class="rop-item">
              <span class="rop-label">提前期(天)</span>
              <span class="rop-value">{{ ropResult.lead_time ?? '—' }}</span>
            </div>
            <div class="rop-item">
              <span class="rop-label">安全库存</span>
              <span class="rop-value">{{ ropResult.safety_stock ?? '—' }}</span>
            </div>
            <div class="rop-item">
              <span class="rop-label">再订货点(ROP)</span>
              <span class="rop-value rop-value--highlight">{{ ropResult.rop ?? '—' }}</span>
            </div>
            <div class="rop-item">
              <span class="rop-label">建议采购量</span>
              <span class="rop-value rop-value--highlight">{{ ropResult.suggested_qty ?? '—' }}</span>
            </div>
          </div>
          <div v-else class="rop-placeholder">点击产品自动计算 ROP</div>
        </div>

        <!-- Purchase Quantity Input -->
        <div class="expand-qty-row">
          <span class="qty-label">采购数量：</span>
          <el-input-number
            v-model="expandedQuantity"
            :min="0"
            :precision="0"
            size="default"
            style="width: 180px;"
          />
          <span class="qty-unit">{{ expandedProduct.unit || '个' }}</span>
          <span v-if="ropResult?.suggested_qty" class="qty-hint">
            (ROP建议: {{ ropResult.suggested_qty }})
          </span>
        </div>
      </div>

      <!-- Table Footer -->
      <div class="table-footer">
        <div class="footer-left">
          <el-button size="small" @click="store.selectAll()">全选</el-button>
          <el-button size="small" @click="store.deselectAll()">取消</el-button>
          <el-button size="small" type="danger" plain
            :disabled="store.selectedIds.size === 0"
            @click="store.removeSelected()">删除选中</el-button>
        </div>
        <el-button type="primary" :disabled="store.allProducts.length === 0" @click="handleNextStep">
          下一步：供应商匹配
        </el-button>
      </div>
    </div>

    <!-- Section 3: AI Intelligent Recommendation -->
    <div v-if="aiRecommendationLoading || aiContent" class="ai-section">
      <div class="section-row">
        <span class="section-title">🤖 AI 智能分析</span>
        <el-button v-if="!aiRecommendationLoading" size="small" @click="loadAiRecommendation">
          重新分析
        </el-button>
      </div>

      <!-- Loading -->
      <div v-if="aiRecommendationLoading" class="ai-loading" v-loading="true" element-loading-text="AI 分析中…"></div>

      <!-- Content -->
      <div v-else-if="aiContent" class="ai-content-card">
        <div class="ai-text" v-html="renderedContent"></div>

        <!-- Render charts from AI blocks -->
        <div v-for="(block, bi) in aiBlocks" :key="bi" class="ai-block">
          <div v-if="block.type === 'chart'" class="ai-chart-wrapper">
            <v-chart
              v-if="block.data"
              :key="`ai-chart-${bi}-${block.chartType || 'line'}-${(block.data.series || []).length}`"
              :option="block.data"
              autoresize
              style="height: 320px;"
            />
          </div>
          <div v-else-if="block.type === 'table'" class="ai-table-wrapper">
            <el-table :data="block.rows || []" stripe size="small" border max-height="300">
              <el-table-column
                v-for="col in (block.columns || [])" :key="col.key"
                :prop="col.key" :label="col.title" min-width="100" show-overflow-tooltip
              />
            </el-table>
          </div>
        </div>
      </div>
    </div>

    <!-- Add / Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑补货产品' : '添加补货产品'"
      width="500px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="dialogForm" :rules="formRules" label-width="80px">
        <el-form-item label="产品" prop="product_id">
          <el-select
            v-model="dialogForm.product_id"
            filterable remote
            :remote-method="remoteSearchProducts"
            :loading="productSearching"
            placeholder="输入产品名称或编码搜索"
            style="width: 100%"
            :disabled="isEditing"
            @change="onDialogProductChange"
          >
            <el-option v-for="p in productOptions" :key="p.id"
              :label="`${p.name} (${p.code})`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库" prop="warehouse_id">
          <el-select v-model="dialogForm.warehouse_id" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="规格">
          <el-input :model-value="dialogForm.specification || '—'" disabled />
        </el-form-item>
        <el-form-item label="单位">
          <el-input :model-value="dialogForm.unit || '—'" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitDialog">
          {{ isEditing ? '保存修改' : '添加到清单' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { aiApi, inventoryApi, productApi } from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const store = usePurchaseDecisionStore()

// =========================================================================
// Section 1: KPI Cards
// =========================================================================

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

// =========================================================================
// Section 2: Product List (sorted by risk, filtered by keyword)
// =========================================================================

const searchKeyword = ref('')
const productFilter = ref<number | null>(null)

// =========================================================================
// Section 2b: Batch ROP data (loaded on mount for risk ranking)
// =========================================================================

const ropMap = ref<Record<number, number>>({})
const batchRopLoading = ref(false)

async function loadBatchRop() {
  const ids = store.allProducts.map(p => p.product_id).filter(Boolean)
  if (ids.length === 0) return
  batchRopLoading.value = true
  try {
    const res: any = await aiApi.batchRop({ product_ids: ids })
    if (res) {
      const map: Record<number, number> = {}
      for (const [pid, data] of Object.entries(res)) {
        const d = data as any
        map[Number(pid)] = d.rop ?? 0
      }
      ropMap.value = map
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

// =========================================================================
// Section 3: AI Intelligent Recommendation
// =========================================================================

const aiRecommendationLoading = ref(false)
const aiContent = ref('')
const aiBlocks = ref<any[]>([])

const renderedContent = computed(() => {
  if (!aiContent.value) return ''
  // Simple markdown-like rendering to HTML
  let html = aiContent.value
    .replace(/### (.+)/g, '<h4>$1</h4>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/- (.+)/g, '<li>$1</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
  return `<p>${html}</p>`
})

async function loadAiRecommendation() {
  if (store.allProducts.length === 0) return
  aiRecommendationLoading.value = true
  aiContent.value = ''
  aiBlocks.value = []
  try {
    const productList = store.allProducts.slice(0, 10).map(p => {
      const rop = ropMap.value[p.product_id]
      const ropStr = rop != null ? ` / ROP: ${rop}` : ''
      return `${p.product_name}（库存: ${p.current_qty} / 安全: ${p.min_stock}${ropStr} / 最高: ${p.max_stock}）`
    }).join('\n')
    const kpiInfo = store.inventoryKpi
      ? `周转天数: ${store.inventoryKpi.turnover_days}，呆滞品: ${store.inventoryKpi.dead_stock_count}，资金: ${store.inventoryKpi.capital_occupied}`
      : ''

    const res: any = await aiApi.chat({
      messages: [
        { role: 'user', content: `请分析当前库存状况并给出补货建议。\n\n库存KPI:\n${kpiInfo}\n\n待补货产品列表:\n${productList}\n\n请给出：1. 总体库存健康度评估 2. 按优先级列出需补货产品及建议量 3. 特殊风险提示` },
      ],
      conversation_id: '',
    })
    if (res) {
      aiContent.value = res.content || ''
      aiBlocks.value = Array.isArray(res.blocks) ? res.blocks : []
    }
  } catch {
    aiContent.value = 'AI 分析服务暂不可用'
  } finally {
    aiRecommendationLoading.value = false
  }
}

// Watch for products to load → auto-expand first product, load ROP, and run AI analysis
watch(() => store.allProducts.length, (len) => {
  if (len > 0) {
    // Auto-expand the first (most risky) product
    if (!expandedProductId.value) {
      expandedProductId.value = store.allProducts[0].product_id
    }
    // Load batch ROP for all products (for accurate risk ranking)
    loadBatchRop()
    // Run AI analysis if not already done
    if (!aiContent.value && !aiRecommendationLoading.value) {
      loadAiRecommendation()
    }
  }
})

function riskRank(item: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): number {
  if (item.current_qty < item.min_stock) return 0 // 缺货
  // 用 ROP 判断：高于安全库存但低于 ROP → 偏低(1)
  const rop = ropMap.value[item.product_id]
  if (rop != null && rop > item.min_stock && item.current_qty < rop) return 1 // 低于ROP
  if (rop != null && item.current_qty >= rop) return 2 // 正常（>= ROP）
  // ROP 不可用时，用比例估算兜底
  const range = item.max_stock - item.min_stock
  if (range <= 0) return 2
  const ratio = (item.current_qty - item.min_stock) / range
  if (ratio < 0.3) return 1 // 偏低 (close to ROP zone)
  if (ratio > 0.9) return 3 // 偏高
  return 2 // 正常
}

const sortedProducts = computed(() => {
  return [...store.allProducts].sort((a, b) => {
    return riskRank(a) - riskRank(b)
  })
})

const filteredProducts = computed(() => {
  let result = sortedProducts.value
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

// When filter selects a single product, auto-expand it
watch(productFilter, (pid) => {
  if (pid != null) {
    expandedProductId.value = pid
  }
})

function statusLabel(row: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
  const r = riskRank(row)
  return ['缺货', '低于ROP', '正常', '偏高'][r] || '正常'
}

function statusTagType(row: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
  const r = riskRank(row)
  return ['danger', 'warning', 'success', 'info'][r] || 'info'
}

function rowClassName({ row }: { row: any }): string {
  const r = riskRank(row)
  return ['row-danger', 'row-warning', '', 'row-info'][r] || ''
}

// =========================================================================
// Expandable Detail
// =========================================================================

const expandedProductId = ref<number | null>(null)
const expandedProduct = computed(() =>
  expandedProductId.value != null
    ? store.allProducts.find(p => p.product_id === expandedProductId.value) ?? null
    : null
)

// Purchase quantity for expanded product
const expandedQuantity = computed({
  get: () => {
    const pid = expandedProductId.value
    if (pid == null) return 0
    return store.quantities[pid] ?? expandedProduct.value?.suggested_qty ?? 0
  },
  set: (val: number) => {
    const pid = expandedProductId.value
    if (pid != null) {
      store.quantities[pid] = val
    }
  },
})

function toggleExpand(row: any) {
  if (expandedProductId.value === row.product_id) {
    expandedProductId.value = null
  } else {
    expandedProductId.value = row.product_id
  }
}

function onRowClick(row: any) {
  toggleExpand(row)
}

// Watch expandedProductId to load detail data
watch(expandedProductId, (pid) => {
  if (pid != null) {
    loadDetailData(pid)
  }
})

// =========================================================================
// Detail: Sales Forecast Chart
// =========================================================================

const detailChartLoading = ref(false)
const detailHistoryData = ref<any[]>([])
const detailPredictionData = ref<number[]>([])
const detailPredictionDates = ref<string[]>([])
const detailTimeRange = ref<'7d' | '30d' | '3m'>('30d')

function getFutureDates(lastDate: string | null, count: number): string[] {
  if (!lastDate) return Array.from({ length: count }, (_, i) => `D+${i + 1}`)
  const d = new Date(lastDate)
  return Array.from({ length: count }, (_, i) => {
    const nd = new Date(d)
    nd.setDate(nd.getDate() + i + 1)
    return nd.toISOString().slice(0, 10)
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
  if (expandedProductId.value != null) {
    await loadDetailData(expandedProductId.value)
  }
}

// =========================================================================
// Detail: ROP Calculation
// =========================================================================

const ropLoading = ref(false)
const ropResult = ref<any>(null)
// P1-13 修复：去重缓存，防止 watch + onMounted + auto-expand 三重触发
const _detailFetchKey = ref<string>('')

async function loadDetailData(productId: number) {
  const key = `${productId}-${detailTimeRange.value}`
  if (_detailFetchKey.value === key) return  // 相同请求正在进行中
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
    const [history, pred, rop] = await Promise.allSettled([
      aiApi.salesHistory({ product_id: productId, days }),
      aiApi.salesPrediction(productId),
      store.fetchSuggestedQty(productId),
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
        const dailyAvg = Math.round(parsed.forecast_next_30d / 30)
        detailPredictionData.value = Array.from({ length: 7 }, () => dailyAvg)
        detailPredictionDates.value = getFutureDates(lastDate, 7)
      }
    }

    // Process ROP
    if (rop.status === 'fulfilled' && rop.value) {
      ropResult.value = rop.value
      // Set default purchase quantity from ROP suggestion
      const suggested = rop.value.suggested_qty
      if (suggested != null && suggested > 0) {
        if (!(productId in store.quantities) || store.quantities[productId] === 0) {
          store.quantities[productId] = suggested
        }
      }
    }
  } catch {
    // Silently handle errors
  } finally {
    detailChartLoading.value = false
    ropLoading.value = false
    _detailFetchKey.value = ''  // P1-13 修复：完成调用后清空缓存键
  }
}

// =========================================================================
// Navigation
// =========================================================================

function handleNextStep() {
  if (store.allProducts.length === 0) {
    ElMessage.warning('请先添加补货产品')
    return
  }
  // Initialize quantities for products that haven't been set
  for (const p of store.allProducts) {
    if (!(p.product_id in store.quantities) || store.quantities[p.product_id] === 0) {
      store.quantities[p.product_id] = p.suggested_qty
    }
  }
  store.nextStep()
}

// =========================================================================
// Table selection
// =========================================================================

const tableRef = ref()

function onSelectionChange(rows: any[]) {
  store.selectedIds = new Set(rows.map(r => r.product_id))
}

// =========================================================================
// Add / Edit Dialog
// =========================================================================

const dialogVisible = ref(false)
const isEditing = ref(false)
const editingProductId = ref(0)
const productSearching = ref(false)
const productOptions = ref<any[]>([])
const formRef = ref<FormInstance>()
const warehouses = ref<any[]>([])

const dialogForm = ref({
  product_id: null as number | null,
  product_name: '', product_code: '',
  warehouse_id: null as number | null,
  specification: '', unit: '个',
})

const formRules: FormRules = {
  product_id: [{ required: true, message: '请选择产品', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
}

function openAddDialog() {
  isEditing.value = false
  editingProductId.value = 0
  dialogForm.value = {
    product_id: null, product_name: '', product_code: '',
    warehouse_id: warehouses.value[0]?.id || null,
    specification: '', unit: '个',
  }
  productOptions.value = []
  formRef.value?.resetFields()
  dialogVisible.value = true
}

function openEditDialog(row: any) {
  isEditing.value = true
  editingProductId.value = row.product_id
  dialogForm.value = {
    product_id: row.product_id,
    product_name: row.product_name,
    product_code: row.product_code,
    warehouse_id: row.warehouse_id,
    specification: row.specification || '',
    unit: row.unit || '个',
  }
  productOptions.value = [{ id: row.product_id, name: row.product_name, code: row.product_code }]
  formRef.value?.resetFields()
  dialogVisible.value = true
}

async function remoteSearchProducts(query: string) {
  if (!query || query.trim().length < 1) { productOptions.value = []; return }
  productSearching.value = true
  try {
    const res: any = await productApi.list({ keyword: query.trim(), page_size: 20 })
    productOptions.value = (res?.items || []).map((p: any) => ({
      id: p.id, name: p.name, code: p.code,
      specification: p.specification || '', unit: p.unit || '个',
      purchase_price: p.purchase_price || 0,
      min_stock: p.min_stock || 0, max_stock: p.max_stock || 0,
    }))
  } catch { productOptions.value = [] }
  finally { productSearching.value = false }
}

async function onDialogProductChange(productId: number) {
  const prod = productOptions.value.find(p => p.id === productId)
  if (!prod) return
  dialogForm.value.product_name = prod.name
  dialogForm.value.product_code = prod.code
  dialogForm.value.specification = prod.specification || ''
  dialogForm.value.unit = prod.unit || '个'
}

async function submitDialog() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  if (isEditing.value) {
    store.updateProduct(editingProductId.value, {
      warehouse_id: dialogForm.value.warehouse_id!,
      warehouse_name: warehouses.value.find((w: any) => w.id === dialogForm.value.warehouse_id)?.name || '',
      unit: dialogForm.value.unit,
      specification: dialogForm.value.specification,
    })
    ElMessage.success('修改已保存')
  } else {
    const matchedProd = productOptions.value.find(p => p.id === dialogForm.value.product_id)
    store.addToProducts({
      id: dialogForm.value.product_id!,
      name: dialogForm.value.product_name,
      code: dialogForm.value.product_code,
      warehouse_id: dialogForm.value.warehouse_id!,
      warehouse_name: warehouses.value.find((w: any) => w.id === dialogForm.value.warehouse_id)?.name || '默认仓库',
      current_qty: matchedProd?.current_qty || matchedProd?.quantity || 0,
      min_stock: matchedProd?.min_stock || 0,
      max_stock: matchedProd?.max_stock || 0,
      unit: dialogForm.value.unit,
      specification: dialogForm.value.specification,
      purchase_price: matchedProd?.purchase_price || 0,
    })
    ElMessage.success('产品已添加')
  }
  dialogVisible.value = false
}

// =========================================================================
// Lifecycle
// =========================================================================

onMounted(async () => {
  await Promise.all([
    store.fetchLowStockProducts(),
    store.fetchInventoryKpi(),
    (async () => {
      try { warehouses.value = (await inventoryApi.warehouses.list() as any) || [] }
      catch { warehouses.value = [] }
    })(),
  ])
})
</script>

<style scoped>
.step-inventory {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 8px 0;
}

/* ========================================================================== */
/* KPI Cards                                                                  */
/* ========================================================================== */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.kpi-card {
  background: #fff;
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 10px;
  padding: 18px 20px;
  text-align: center;
}
.kpi-card--highlight {
  border-color: #e0f2fe;
  background: linear-gradient(135deg, #f0f9ff 0%, #fff 100%);
}
.kpi-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary, #303133);
  line-height: 1.2;
}
.kpi-card--highlight .kpi-value {
  color: #005BF5;
}
.kpi-label {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary, #909399);
}

/* ========================================================================== */
/* Product List Table                                                         */
/* ========================================================================== */
.table-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}
.footer-left {
  display: flex;
  gap: 8px;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary, #303133);
}
.section-count {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}

/* Row highlighting */
:deep(.row-danger) {
  background-color: #fef0f0 !important;
}
:deep(.row-warning) {
  background-color: #fdf6ec !important;
}
:deep(.row-info) {
  background-color: #f0f9ff !important;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}
.rop-cell {
  font-weight: 600;
  color: #005BF5;
}
.rop-none {
  color: #c0c4cc;
}

/* ========================================================================== */
/* Expandable Detail Panel                                                    */
/* ========================================================================== */
.expand-panel {
  border: 1px solid #d9ecff;
  border-radius: 10px;
  padding: 20px;
  background: #fafcff;
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: slideDown 0.2s ease-out;
}
@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 800px; }
}
.expand-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.expand-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary, #303133);
}

/* Stock Info Row */
.expand-stock-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.stock-info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stock-info-label {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}
.stock-info-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

/* Chart Area */
.expand-chart-section {
  margin: 0;
}
.chart-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.time-tabs {
  display: flex;
  gap: 4px;
}
.time-tab {
  padding: 4px 14px;
  border-radius: 6px;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  border: 1px solid #ddd;
  transition: all 0.2s;
  user-select: none;
  background: #fff;
}
.time-tab:hover {
  border-color: #409eff;
  color: #409eff;
}
.time-tab.active {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}
.chart-area {
  min-height: 300px;
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ROP Section */
.expand-rop-section {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 18px;
  background: #fff;
}
.rop-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
  color: var(--text-primary, #303133);
}
.rop-loading {
  min-height: 40px;
}
.rop-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.rop-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rop-label {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}
.rop-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.rop-value--highlight {
  color: #005BF5;
}
.rop-placeholder {
  color: var(--text-secondary, #909399);
  font-size: 13px;
  font-style: italic;
}

/* Quantity Input Row */
.expand-qty-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
}
.qty-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.qty-unit {
  font-size: 13px;
  color: #606266;
}
.qty-hint {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}

/* ========================================================================== */
/* AI Recommendation Section                                                   */
/* ========================================================================== */
.ai-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ai-loading {
  min-height: 80px;
}
.ai-content-card {
  background: linear-gradient(135deg, #f5f7fa, #eef2f7);
  border: 1px solid #d9e2ef;
  border-radius: 10px;
  padding: 18px 22px;
}
.ai-text {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
}
.ai-text p {
  margin: 4px 0;
}
.ai-text li {
  margin-left: 16px;
  list-style: disc;
}
.ai-text h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 6px;
  color: #005BF5;
}
.ai-text h4:first-child {
  margin-top: 0;
}
.ai-block {
  margin-top: 16px;
}
.ai-chart-wrapper {
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}
.ai-table-wrapper {
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 8px;
  overflow: hidden;
}
</style>
