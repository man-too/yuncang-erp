<template>
  <div class="step-supplier">
    <!-- Section 1: AI Supplier Recommendation -->
    <div class="ai-section">
      <div class="section-row">
        <span class="section-title">AI 供应商推荐</span>
        <el-button type="warning" size="small" @click="fetchRanking" :loading="rankingLoading">
          刷新排名
        </el-button>
      </div>
      <div v-if="rankingLoading" class="ai-loading">
        <span>AI 正在分析供应商排名...</span>
      </div>
      <div v-else-if="aiAnalysis" class="ai-bubble">
        <div class="ai-avatar">AI</div>
        <div class="ai-message">
          <p style="white-space: pre-wrap; margin: 0;">{{ aiAnalysis.summary || aiAnalysis.content || '供应商排名分析完成' }}</p>
          <div v-if="aiAnalysis.confidence != null" class="ai-confidence">
            置信度:
            <el-progress :percentage="Math.round(aiAnalysis.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; margin-left: 6px;" />
          </div>
        </div>
      </div>
      <el-empty v-else description="点击「刷新排名」获取 AI 供应商排名" :image-size="60" />
    </div>

    <!-- Section 2: Supplier Bar Chart Comparison -->
    <div v-if="scoreData.length > 0" class="chart-section">
      <div class="section-row">
        <span class="section-title">供应商评分对比</span>
      </div>
      <div v-loading="chartLoading" class="chart-area">
        <v-chart v-if="supplierChartOption" :option="supplierChartOption" autoresize style="height: 280px;" />
        <el-empty v-else description="暂无供应商数据" :image-size="60" />
      </div>
    </div>

    <!-- Section 3: Product-Supplier Allocation -->
    <div class="allocation-section">
      <div class="section-row">
        <span class="section-title">供应商匹配与数量分配</span>
        <span class="section-hint">为每个产品选择供应商并分配采购数量</span>
      </div>

      <div v-if="store.allProducts.length === 0" class="empty-hint">
        暂无产品，请先在库存分析步骤添加补货产品
      </div>

      <div v-else class="product-allocation-list">
        <el-card
          v-for="product in store.allProducts"
          :key="product.product_id"
          class="product-card"
          shadow="hover"
        >
          <!-- Product Header -->
          <div class="product-header">
            <div class="product-info">
              <span class="product-name">{{ product.product_name }}</span>
              <span class="product-code">{{ product.product_code }}</span>
              <el-tag size="small" type="info">{{ product.warehouse_name }}</el-tag>
            </div>
            <div class="product-qty-info">
              <span class="qty-label">需采购量:</span>
              <span class="qty-value">{{ getNeededQty(product) }} {{ product.unit }}</span>
              <el-tag
                :type="allocationStatus(product.product_id).type"
                size="small"
                style="margin-left: 8px;"
              >
                已分配: {{ allocatedQty(product.product_id) }}/{{ getNeededQty(product) }} {{ product.unit }}
              </el-tag>
            </div>
          </div>

          <!-- Allocation Warning -->
          <el-alert
            v-if="allocationStatus(product.product_id).over"
            type="error"
            :closable="false"
            show-icon
            style="margin-bottom: 10px;"
          >
            <template #default>
              分配总量 ({{ allocatedQty(product.product_id) }}) 超过需采购量 ({{ getNeededQtyById(product.product_id) }})
            </template>
          </el-alert>

          <!-- Supplier Allocation Table -->
          <el-table
            :data="getProductSuppliers(product.product_id)"
            size="small"
            stripe
            border
            max-height="240"
            style="width: 100%;"
          >
            <el-table-column width="50" align="center">
              <template #default="{ row }">
                <el-checkbox
                  :model-value="isSupplierChecked(product.product_id, row.supplier_id)"
                  @change="onSupplierToggle(product.product_id, row.supplier_id, $event)"
                />
              </template>
            </el-table-column>
            <el-table-column prop="supplier_name" label="供应商名称" min-width="130" show-overflow-tooltip />
            <el-table-column label="综合评分" width="90" align="center" sortable :sort-method="sortByScore">
              <template #default="{ row }">
                <el-tag
                  :type="row.total_score >= 80 ? 'success' : row.total_score >= 60 ? 'warning' : 'danger'"
                  size="small"
                >
                  {{ row.total_score }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="风险" width="100" align="center">
              <template #default="{ row }">
                <el-tooltip
                  v-if="row.is_single_source"
                  content="单源依赖：该供应商独家供应部分产品，建议开发备选供应商"
                  placement="top"
                >
                  <el-tag type="danger" size="small">单源风险</el-tag>
                </el-tooltip>
                <el-tooltip
                  v-if="row.risk_penalty > 0"
                  :content="`风险扣分: ${row.risk_penalty} (单源: ${row.single_source_penalty}, 交付波动: ${row.delay_std_penalty})`"
                  placement="top"
                >
                  <el-tag type="warning" size="small">-{{ row.risk_penalty }}</el-tag>
                </el-tooltip>
                <span v-if="!row.is_single_source && row.risk_penalty === 0" style="color: #67c23a; font-size: 12px;">低风险</span>
              </template>
            </el-table-column>
            <el-table-column label="交付评分" width="85" align="center">
              <template #default="{ row }">
                {{ row.delivery ?? '—' }}
              </template>
            </el-table-column>
            <el-table-column label="建议分配" width="100" align="center">
              <template #default="{ row }">
                <span class="suggested-qty">{{ getSuggestedAllocation(product.product_id, row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="实际分配" width="160" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-if="isSupplierChecked(product.product_id, row.supplier_id)"
                  :model-value="getAllocatedQty(product.product_id, row.supplier_id)"
                  :min="0"
                  :max="getNeededQty(product)"
                  :step="1"
                  size="small"
                  controls-position="right"
                  style="width: 130px;"
                  @change="onAllocationChange(product.product_id, row.supplier_id, $event)"
                />
                <span v-else style="color: #c0c4cc; font-size: 12px;">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </div>

    <!-- Section 4: Allocation Summary & Navigation -->
    <div class="summary-section">
      <div class="section-row">
        <span class="section-title">分配汇总</span>
        <span class="section-count">{{ fullyAllocatedCount }} / {{ store.allProducts.length }} 已全部分配</span>
      </div>

      <div class="summary-tags">
        <template v-if="store.allProducts.length === 0">
          <span class="empty-hint">暂无产品</span>
        </template>
        <template v-else>
          <el-tag
            v-for="p in store.allProducts"
            :key="p.product_id"
            :type="allocationStatus(p.product_id).type"
            size="default"
            class="summary-tag"
          >
            {{ p.product_name }}:
            {{ allocatedQty(p.product_id) }}/{{ getNeededQty(p) }} {{ p.unit }}
            <template v-if="allocationStatus(p.product_id).over"> (超出!)</template>
          </el-tag>
        </template>
      </div>

      <div class="nav-row">
        <el-button @click="store.prevStep()">上一步：库存分析</el-button>
        <el-button
          type="primary"
          :disabled="!canProceed"
          @click="handleNextStep"
        >
          下一步：风险审核 →
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
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { ElMessage } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { aiApi, supplierApi } from '@/api'
import type { RestockItem } from '@/stores/purchaseDecision'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const store = usePurchaseDecisionStore()

// ---- State ----
const rankingLoading = ref(false)
const chartLoading = ref(false)
const aiAnalysis = ref<any>(null)
const supplierList = ref<any[]>([])
// Score data from /ai/supplier-score — array of { supplier_id, supplier_name, total_score, delivery, risk_penalty, is_single_source, ... }
const scoreData = ref<any[]>([])

// ---- Computed: Chart ----
const supplierChartOption = computed(() => {
  if (!scoreData.value.length) return null
  const names = scoreData.value.map((s: any) => s.supplier_name || `供应商#${s.supplier_id}`)
  const scores = scoreData.value.map((s: any) => s.total_score || 0)
  const penalties = scoreData.value.map((s: any) => s.risk_penalty || 0)
  return {
    tooltip: { trigger: 'axis' },
    title: {
      text: '供应商评分对比',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    legend: { top: 30, data: ['综合评分', '风险扣分'] },
    grid: { left: 60, right: 30, top: 60, bottom: 40 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { fontSize: 11, rotate: names.length > 6 ? 30 : 0 },
    },
    yAxis: { type: 'value', name: '评分', min: 0 },
    series: [
      {
        name: '综合评分',
        type: 'bar',
        barMaxWidth: 40,
        data: scores.map((v: number) => ({
          value: v,
          itemStyle: {
            color: v >= 80 ? '#2D8C4A' : v >= 60 ? '#F27A00' : '#C53030',
          },
        })),
        label: { show: true, position: 'top', formatter: '{c}' },
      },
      {
        name: '风险扣分',
        type: 'bar',
        barMaxWidth: 40,
        data: penalties,
        itemStyle: { color: '#E6A23C' },
        label: { show: true, position: 'top', formatter: (p: any) => p.value > 0 ? `-${p.value}` : '' },
      },
    ],
  }
})

// ---- Computed: Allocation Status ----
const fullyAllocatedCount = computed(() =>
  store.allProducts.filter(p => {
    const needed = getNeededQty(p)
    const allocated = allocatedQty(p.product_id)
    return allocated === needed && needed > 0
  }).length
)

const canProceed = computed(() => {
  if (store.allProducts.length === 0) return false
  return store.allProducts.every(p => {
    const needed = getNeededQty(p)
    const allocated = allocatedQty(p.product_id)
    // Must have at least one supplier checked and allocation must not exceed needed
    const hasSupplier = (store.supplierChoices[p.product_id] || []).length > 0
    return hasSupplier && allocated > 0 && allocated <= needed
  })
})

// ---- Methods: Data Fetching ----
async function fetchRanking() {
  rankingLoading.value = true
  try {
    const res: any = await aiApi.supplierRanking()
    aiAnalysis.value = res?.ai_analysis || null
  } catch {
    ElMessage.warning('供应商排名获取失败')
  } finally {
    rankingLoading.value = false
  }
}

async function fetchSupplierScores() {
  chartLoading.value = true
  try {
    // Fetch all supplier scores (no filter) to populate the allocation tables
    const res: any = await aiApi.supplierScore({})
    scoreData.value = res?.suppliers || []
    // Cache supplier info into store
    for (const s of scoreData.value) {
      store.supplierInfo[s.supplier_id] = {
        id: s.supplier_id,
        name: s.supplier_name,
        total_score: s.total_score,
        delivery: s.delivery,
        risk_penalty: s.risk_penalty,
        is_single_source: s.is_single_source,
        suggested_share: s.suggested_share,
      }
    }
  } catch {
    scoreData.value = []
  } finally {
    chartLoading.value = false
  }
}

async function fetchSuppliers() {
  try {
    const res: any = await supplierApi.list({ page_size: 100 })
    supplierList.value = res?.items || []
  } catch {
    supplierList.value = []
  }
}

// ---- Methods: Product Needed Qty ----
function getNeededQty(product: RestockItem): number {
  // Priority: suggestedQtys from ROP > suggested_qty from store > quantities
  const pid = product.product_id
  const ropData = store.suggestedQtys[pid]
  if (ropData && ropData.suggested_qty) return ropData.suggested_qty
  if (store.quantities[pid] && store.quantities[pid] > 0) return store.quantities[pid]
  return product.suggested_qty || 0
}

// ---- Methods: Supplier List per Product ----
function getProductSuppliers(_productId: number): any[] {
  // All suppliers with score data are available for every product
  // In a more advanced version, we could filter by product-supplier relationship
  return scoreData.value
}

// ---- Methods: Allocation ----
function isSupplierChecked(productId: number, supplierId: number): boolean {
  return (store.supplierChoices[productId] || []).includes(supplierId)
}

function getAllocatedQty(productId: number, supplierId: number): number {
  return store.supplierQuantities[productId]?.[supplierId] || 0
}

function allocatedQty(productId: number): number {
  const alloc = store.supplierQuantities[productId]
  if (!alloc) return 0
  return Object.values(alloc).reduce((sum, v) => sum + v, 0)
}

function allocationStatus(productId: number): { type: string; over: boolean } {
  const needed = getNeededQtyById(productId)
  const allocated = allocatedQty(productId)
  if (allocated > needed) return { type: 'danger', over: true }
  if (allocated === needed && needed > 0) return { type: 'success', over: false }
  if (allocated > 0) return { type: 'warning', over: false }
  return { type: 'info', over: false }
}

function getNeededQtyById(productId: number): number {
  const product = store.allProducts.find(p => p.product_id === productId)
  if (!product) return 0
  return getNeededQty(product)
}

// ---- Methods: Suggested Allocation ----
function getSuggestedAllocation(productId: number, supplier: any): number {
  const needed = getNeededQtyById(productId)
  if (needed <= 0) return 0

  // Calculate allocation by delivery score proportion among all checked suppliers
  const checkedSuppliers = (store.supplierChoices[productId] || [])
  if (checkedSuppliers.length === 0) {
    // If no suppliers checked yet, suggest based on this supplier's delivery score vs total
    const totalDelivery = scoreData.value.reduce((sum, s) => sum + (s.delivery || 0), 0)
    if (totalDelivery <= 0) return 0
    return Math.round(needed * ((supplier.delivery || 0) / totalDelivery))
  }

  // Only among checked suppliers
  const checkedScoreData = scoreData.value.filter(s => checkedSuppliers.includes(s.supplier_id))
  const totalDelivery = checkedScoreData.reduce((sum, s) => sum + (s.delivery || 0), 0)
  if (totalDelivery <= 0) return 0

  const proportion = (supplier.delivery || 0) / totalDelivery
  return Math.round(needed * proportion)
}

// ---- Methods: User Actions ----
function onSupplierToggle(productId: number, supplierId: number, checked: boolean) {
  if (!store.supplierChoices[productId]) {
    store.supplierChoices[productId] = []
  }
  const list = store.supplierChoices[productId]
  if (checked) {
    if (!list.includes(supplierId)) list.push(supplierId)
    // Auto-fill suggested allocation
    const supplier = scoreData.value.find(s => s.supplier_id === supplierId)
    if (supplier) {
      const suggested = getSuggestedAllocation(productId, supplier)
      if (suggested > 0) {
        if (!store.supplierQuantities[productId]) {
          store.supplierQuantities[productId] = {}
        }
        store.supplierQuantities[productId][supplierId] = suggested
      }
    }
  } else {
    const idx = list.indexOf(supplierId)
    if (idx !== -1) list.splice(idx, 1)
    // Clear allocation for this supplier
    if (store.supplierQuantities[productId]) {
      delete store.supplierQuantities[productId][supplierId]
    }
  }
}

function onAllocationChange(productId: number, supplierId: number, value: number | null) {
  const qty = value || 0
  if (!store.supplierQuantities[productId]) {
    store.supplierQuantities[productId] = {}
  }
  store.supplierQuantities[productId][supplierId] = qty
}

function sortByScore(a: any, b: any): number {
  return (a.total_score || 0) - (b.total_score || 0)
}

function handleNextStep() {
  if (!canProceed.value) {
    ElMessage.warning('请为所有产品选择供应商并完成数量分配')
    return
  }
  store.nextStep()
}

// ---- Lifecycle ----
onMounted(async () => {
  await Promise.all([fetchRanking(), fetchSuppliers(), fetchSupplierScores()])
  // Auto-suggest allocations for products that have no allocations yet
  for (const product of store.allProducts) {
    if (!store.supplierChoices[product.product_id] || store.supplierChoices[product.product_id].length === 0) {
      // Auto-select top 2 suppliers by total_score
      const topSuppliers = scoreData.value
        .filter(s => !s.is_single_source || scoreData.value.length <= 2)
        .slice(0, 2)
      if (topSuppliers.length > 0) {
        store.supplierChoices[product.product_id] = topSuppliers.map(s => s.supplier_id)
        // Auto-allocate by delivery score proportion
        const needed = getNeededQty(product)
        if (needed > 0) {
          const totalDelivery = topSuppliers.reduce((sum, s) => sum + (s.delivery || 0), 0)
          if (totalDelivery > 0) {
            store.supplierQuantities[product.product_id] = {}
            for (const s of topSuppliers) {
              const proportion = (s.delivery || 0) / totalDelivery
              store.supplierQuantities[product.product_id][s.supplier_id] = Math.round(needed * proportion)
            }
            // Fix rounding: ensure total matches needed
            const allocated = allocatedQty(product.product_id)
            if (allocated !== needed && topSuppliers.length > 0) {
              const diff = needed - allocated
              // Add/subtract diff from the top supplier
              const topId = topSuppliers[0].supplier_id
              store.supplierQuantities[product.product_id][topId] = (store.supplierQuantities[product.product_id][topId] || 0) + diff
            }
          }
        }
      }
    }
  }
})
</script>

<style scoped>
.step-supplier {
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
  margin-bottom: 10px;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}
.section-hint {
  font-size: 12px;
  color: var(--text-secondary);
}
.section-count {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Section 1: AI */
.ai-section {
  border: 1px solid var(--color-success-light);
  border-radius: 8px;
  padding: 16px 20px;
  background: var(--color-success-bg);
}
.ai-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  padding: 12px 0;
}
.ai-bubble {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: var(--color-info-bg);
  border-radius: 12px;
  border: 1px solid var(--color-info-light);
}
.ai-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #005BF5, #2e7bff);
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

/* Section 2: Chart */
.chart-section {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
}
.chart-area {
  min-height: 280px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Section 3: Allocation */
.allocation-section {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
}
.product-allocation-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.product-card {
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
.product-card :deep(.el-card__body) {
  padding: 14px 16px;
}
.product-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.product-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.product-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.product-code {
  font-size: 12px;
  color: var(--text-secondary);
}
.product-qty-info {
  display: flex;
  align-items: center;
  gap: 4px;
}
.qty-label {
  font-size: 13px;
  color: var(--text-secondary);
}
.qty-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.suggested-qty {
  font-size: 12px;
  color: #909399;
}

/* Section 4: Summary */
.summary-section {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
}
.summary-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  min-height: 36px;
  margin-bottom: 16px;
  align-items: center;
}
.summary-tag {
  cursor: default;
}
.empty-hint {
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
}
.nav-row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
