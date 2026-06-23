<template>
  <div class="step-inventory" v-loading="store.isLoading" element-loading-text="加载库存数据...">
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
    <div class="list-section">
      <div class="list-header">
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

      <!-- Card List -->
      <div v-if="filteredProducts.length === 0 && !store.isLoading" class="empty-state">
        暂无低库存产品
      </div>

      <div v-else class="card-list">
        <div
          v-for="product in filteredProducts"
          :key="product.product_id"
          class="product-card"
          :class="cardRiskClass(product)"
        >
          <!-- Card top row: checkbox + status tag + name + code + warehouse + ROP value + actions -->
          <div class="card-header">
            <el-checkbox
              :model-value="isSelected(product.product_id)"
              @change="(val: boolean) => onCheckChange(product.product_id, val)"
            />
            <el-tag :type="statusTagType(product)" size="small" effect="dark">
              {{ statusLabel(product) }}
            </el-tag>
            <span class="card-name">{{ product.product_name }}</span>
            <span class="card-code">{{ product.product_code }}</span>
            <el-tag size="small" type="info">{{ product.warehouse_name }}</el-tag>
            <span v-if="ropMap[product.product_id] != null" class="card-rop">
              ROP: {{ ropMap[product.product_id] }}
            </span>
            <div class="card-actions">
              <el-button link @click.stop="toggleExpand(product)">
                {{ expandedProductId === product.product_id ? '收起' : '详情' }}
              </el-button>
              <el-button link @click.stop="openEditDialog(product)">编辑</el-button>
              <el-button link type="danger" @click.stop="store.removeProduct(product.product_id)">删除</el-button>
            </div>
          </div>

          <!-- Card detail line: current qty / safety / max -->
          <div class="card-stats">
            <span>
              当前: <strong :class="{ 'text-danger': product.current_qty < product.min_stock }">{{ product.current_qty }}</strong>
            </span>
            <span>安全: <strong>{{ product.min_stock }}</strong></span>
            <span>最高: <strong>{{ product.max_stock }}</strong></span>
          </div>

          <!-- Expandable detail panel (only for the expanded product) -->
          <div v-if="expandedProductId === product.product_id" class="expand-panel">
            <!-- Stock info row -->
            <div class="expand-stock-row">
              <div class="stock-info-item">
                <span class="stock-info-label">当前库存</span>
                <span class="stock-info-value" :class="{ 'text-danger': product.current_qty < product.min_stock }">
                  {{ product.current_qty }} {{ product.unit }}
                </span>
              </div>
              <div class="stock-info-item">
                <span class="stock-info-label">安全库存</span>
                <span class="stock-info-value">{{ product.min_stock }} {{ product.unit }}</span>
              </div>
              <div class="stock-info-item">
                <span class="stock-info-label">最高库存</span>
                <span class="stock-info-value">{{ product.max_stock }} {{ product.unit }}</span>
              </div>
              <div class="stock-info-item">
                <span class="stock-info-label">缺口</span>
                <span class="stock-info-value" :class="{ 'text-danger': product.current_qty < product.min_stock }">
                  {{ Math.max(0, product.min_stock - product.current_qty) }} {{ product.unit }}
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
              <span class="qty-unit">{{ product.unit || '个' }}</span>
              <span v-if="ropResult?.suggested_qty" class="qty-hint">
                (ROP建议: {{ ropResult.suggested_qty }})
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- List Footer -->
      <div class="list-footer">
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
import { useChatStore } from '@/stores/chat'
import { aiApi, inventoryApi, productApi } from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const store = usePurchaseDecisionStore()
const chatStore = useChatStore()

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
    // Build warehouse_ids mapping: product_id → warehouse_id for per-warehouse ROP
    const warehouseIds: Record<number, number> = {}
    for (const p of store.allProducts) {
      if (p.warehouse_id) {
        warehouseIds[p.product_id] = p.warehouse_id
      }
    }
    const res: any = await aiApi.batchRop({ product_ids: ids, warehouse_ids: warehouseIds })
    if (res) {
      const map: Record<number, number> = {}
      const ropList: any[] = res.results || res.items || res.data || (Array.isArray(res) ? res : [])
      for (const r of ropList) {
        if (r && r.product_id != null) {
          map[Number(r.product_id)] = r.rop ?? 0
        }
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
// Section 3: AI Analysis → push to chat panel (text only)
// =========================================================================

let aiAnalysisPushed = false

async function pushAiAnalysisToChat() {
  if (store.allProducts.length === 0) return
  aiAnalysisPushed = true

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
    if (res && res.content) {
      chatStore.pushStepSummary('AI 库存分析', res.content)
    }
  } catch {
    chatStore.pushStepSummary('AI 库存分析', 'AI 分析服务暂不可用')
  }
}

// Watch for products to load -> auto-expand first product, load ROP, and push AI analysis to chat
watch(() => store.allProducts.length, (len) => {
  if (len > 0) {
    // Auto-expand the first (most risky) product
    if (!expandedProductId.value) {
      expandedProductId.value = store.allProducts[0].product_id
    }
    // Load batch ROP for all products (for accurate risk ranking)
    loadBatchRop()
    // Push AI analysis to chat panel if not already done
    if (!aiAnalysisPushed) {
      pushAiAnalysisToChat()
    }
  }
})

function riskRank(item: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): number {
  if (item.current_qty < item.min_stock) return 0 // 缺货
  // 用 ROP 判断：高于安全库存但低于 ROP -> 偏低(1)
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

function cardRiskClass(item: { product_id: number; current_qty: number; min_stock: number; max_stock: number }): string {
  const r = riskRank(item)
  return ['card-danger', 'card-warning', '', 'card-info'][r] || ''
}

// =========================================================================
// Selection
// =========================================================================

function isSelected(productId: number): boolean {
  return store.selectedIds.has(productId)
}

function onCheckChange(productId: number, val: boolean) {
  if (val) {
    store.selectedIds = new Set([...store.selectedIds, productId])
  } else {
    const newSet = new Set(store.selectedIds)
    newSet.delete(productId)
    store.selectedIds = newSet
  }
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

/** 客户端预测回退：WMA + 历史波动 */
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
  if (expandedProductId.value != null) {
    await loadDetailData(expandedProductId.value)
  }
}

// =========================================================================
// Detail: ROP Calculation
// =========================================================================

const ropLoading = ref(false)
const ropResult = ref<any>(null)
// P1-13 fix: deduplication cache to prevent watch + onMounted + auto-expand triple-triggering
const _detailFetchKey = ref<string>('')

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
    const warehouseId = expandedProduct.value?.warehouse_id
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
      const fallback = expandedProduct.value?.suggested_qty ?? 0
      const qtyToSet = (suggested != null && suggested > 0) ? suggested : (fallback > 0 ? fallback : 0)
      if (qtyToSet > 0 && (!(productId in store.quantities) || store.quantities[productId] === 0)) {
        store.quantities[productId] = qtyToSet
      }
    }
  } catch {
    // Silently handle errors
  } finally {
    detailChartLoading.value = false
    ropLoading.value = false
    _detailFetchKey.value = ''  // P1-13 fix: clear cache key after completion
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
/* Product List Section                                                        */
/* ========================================================================== */
.list-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.list-footer {
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

.empty-state {
  text-align: center;
  color: var(--text-secondary, #909399);
  padding: 40px 0;
  font-size: 14px;
}

/* ========================================================================== */
/* Card List                                                                   */
/* ========================================================================== */
.card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 520px;
  overflow-y: auto;
}

.product-card {
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 10px;
  padding: 12px 16px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
  cursor: default;
}
.product-card:hover {
  border-color: #c0c6d0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.product-card.card-danger {
  border-left: 3px solid var(--el-color-danger, #f56c6c);
  background: var(--el-color-danger-light-9, #fef0f0);
}
.product-card.card-warning {
  border-left: 3px solid var(--el-color-warning, #e6a23c);
  background: var(--el-color-warning-light-9, #fdf6ec);
}
.product-card.card-info {
  border-left: 3px solid #909399;
  background: #f4f4f5;
}

/* Card Header Row */
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.card-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.card-code {
  font-size: 12px;
  color: var(--text-secondary, #909399);
  flex-shrink: 0;
}
.card-rop {
  font-size: 13px;
  font-weight: 700;
  color: #005BF5;
  margin-left: auto;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

/* Card Stats Row */
.card-stats {
  display: flex;
  gap: 20px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary, #909399);
}
.card-stats strong {
  color: var(--text-primary, #303133);
  font-weight: 600;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

/* ========================================================================== */
/* Expandable Detail Panel (inside card)                                      */
/* ========================================================================== */
.expand-panel {
  border: 1px solid #d9ecff;
  border-radius: 10px;
  padding: 20px;
  margin-top: 12px;
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

.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
