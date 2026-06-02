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

    <!-- Section 2: Product Supplier Selection -->
    <div class="selection-section">
      <div class="section-row">
        <span class="section-title">供应商匹配</span>
        <span class="section-hint">为每个产品选择最优供应商</span>
      </div>

      <!-- Product Picker -->
      <div class="picker-row">
        <span class="picker-label">选择产品：</span>
        <el-select
          v-model="activeProductId"
          placeholder="请选择产品"
          filterable
          style="width: 360px;"
          @change="onProductChange"
        >
          <el-option
            v-for="p in store.allProducts"
            :key="p.product_id"
            :label="`${p.product_name} (${p.product_code || '无编码'})`"
            :value="p.product_id"
          >
            <span>{{ p.product_name }}</span>
            <span style="float: right; color: #909399; font-size: 12px;">{{ p.warehouse_name }}</span>
          </el-option>
        </el-select>
        <el-tag v-if="activeProductId && store.supplierChoices[activeProductId]" type="success" size="small" style="margin-left: 12px;">
          已选：{{ getSupplierName(store.supplierChoices[activeProductId]) }}
        </el-tag>
        <el-tag v-else-if="activeProductId" type="info" size="small" style="margin-left: 12px;">未选择供应商</el-tag>
      </div>

      <!-- Chart + Table (shown when a product is selected) -->
      <div v-if="activeProductId" class="match-area">
        <!-- Bar Chart -->
        <div v-loading="chartLoading" class="chart-area">
          <v-chart v-if="supplierChartOption" :option="supplierChartOption" autoresize style="height: 280px;" />
          <el-empty v-else description="暂无供应商数据" :image-size="60" />
        </div>

        <!-- Supplier Table with Radio -->
        <div class="table-area">
          <el-table
            :data="rankedSuppliers"
            stripe
            size="small"
            border
            max-height="260"
            highlight-current-row
            @current-change="onSupplierSelect"
          >
            <el-table-column width="50" align="center">
              <template #default="{ row }">
                <el-radio
                  :model-value="store.supplierChoices[activeProductId!]"
                  :value="row.id"
                  @change="onSupplierSelect(row)"
                />
              </template>
            </el-table-column>
            <el-table-column type="index" label="排名" width="55" align="center" />
            <el-table-column prop="name" label="供应商名称" min-width="130" />
            <el-table-column prop="rating" label="综合评分" width="90" align="right" sortable>
              <template #default="{ row }">
                <el-tag :type="row.rating >= 4 ? 'success' : row.rating >= 3 ? 'warning' : 'danger'" size="small">
                  {{ row.rating }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="lead_time" label="交期(天)" width="85" align="right" />
            <el-table-column prop="delivery_rate" label="交付率" width="80" align="right">
              <template #default="{ row }">
                {{ row.delivery_rate != null ? row.delivery_rate + '%' : '暂无' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <el-empty v-else description="请选择产品以匹配供应商" :image-size="60" />
    </div>

    <!-- Section 3: Selected Suppliers Summary & Navigation -->
    <div class="summary-section">
      <div class="section-row">
        <span class="section-title">已选供应商汇总</span>
        <span class="section-count">{{ chosenCount }} / {{ store.allProducts.length }} 已匹配</span>
      </div>

      <div class="tag-area">
        <template v-if="store.allProducts.length === 0">
          <span class="empty-hint">暂无产品，请先在上一步选择补货产品</span>
        </template>
        <template v-else>
          <el-tag
            v-for="p in store.allProducts"
            :key="p.product_id"
            :type="store.supplierChoices[p.product_id] ? 'success' : 'info'"
            size="default"
            closable
            class="choice-tag"
            @close="clearChoice(p.product_id)"
            @click="activeProductId = p.product_id"
          >
            {{ p.product_name }} →
            {{ getSupplierName(store.supplierChoices[p.product_id]) || '未选' }}
          </el-tag>
        </template>
      </div>

      <div class="nav-row">
        <el-button @click="store.prevStep()">上一步</el-button>
        <el-button
          type="primary"
          :disabled="!allProductsMatched"
          @click="handleNextStep"
        >
          下一步：销量预测 →
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

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const store = usePurchaseDecisionStore()

// ---- State ----
const rankingLoading = ref(false)
const chartLoading = ref(false)
const rankedSuppliers = ref<any[]>([])
const aiAnalysis = ref<any>(null)
const activeProductId = ref<number | null>(null)
const supplierList = ref<any[]>([])

// ---- Computed ----
const chosenCount = computed(() =>
  Object.keys(store.supplierChoices).filter(
    id => store.allProducts.some(p => p.product_id === Number(id))
  ).length
)

const allProductsMatched = computed(() => {
  if (store.allProducts.length === 0) return false
  return store.allProducts.every(p => store.supplierChoices[p.product_id] != null)
})

const supplierChartOption = computed(() => {
  if (!rankedSuppliers.value.length) return null
  const names = rankedSuppliers.value.map((s: any) => s.name)
  const ratings = rankedSuppliers.value.map((s: any) => s.rating || 0)
  return {
    tooltip: { trigger: 'axis' },
    title: {
      text: '供应商评分对比',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    grid: { left: 60, right: 30, top: 50, bottom: 40 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { fontSize: 11, rotate: names.length > 6 ? 30 : 0 },
    },
    yAxis: { type: 'value', name: '评分', min: 0, max: 5 },
    series: [{
      type: 'bar',
      barMaxWidth: 40,
      data: ratings.map((v: number) => ({
        value: v,
        itemStyle: {
          color: v >= 4 ? '#67c23a' : v >= 3 ? '#e6a23c' : '#f56c6c',
        },
      })),
      label: { show: true, position: 'top', formatter: '{c}' },
    }],
  }
})

// ---- Methods ----
function getSupplierName(id: number | undefined): string {
  if (!id) return ''
  const s = supplierList.value.find((s: any) => s.id === id)
  return s ? s.name : `供应商#${id}`
}

async function fetchRanking() {
  rankingLoading.value = true
  try {
    const res: any = await aiApi.supplierRanking()
    rankedSuppliers.value = res?.suppliers || []
    aiAnalysis.value = res?.ai_analysis || null
  } catch {
    ElMessage.warning('供应商排名获取失败')
  } finally {
    rankingLoading.value = false
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

function onProductChange(_productId: number) {
  // Chart and table use the global rankedSuppliers which is already loaded
}

function onSupplierSelect(row: any) {
  if (!activeProductId.value || !row) return
  store.supplierChoices[activeProductId.value] = row.id
  // Derive forecast price from supplier info if available
  const supplier = supplierList.value.find((s: any) => s.id === row.id)
  if (supplier && supplier.unit_price != null) {
    store.forecastPrices[activeProductId.value] = supplier.unit_price
  }
  // Cache supplier info
  store.supplierInfo[row.id] = row
}

function clearChoice(productId: number) {
  delete store.supplierChoices[productId]
  delete store.forecastPrices[productId]
}

function handleNextStep() {
  if (!allProductsMatched.value) {
    ElMessage.warning('请为所有产品选择供应商')
    return
  }
  store.nextStep()
}

// ---- Lifecycle ----
onMounted(async () => {
  await Promise.all([fetchRanking(), fetchSuppliers()])
  // Auto-select first product if any exist
  if (store.allProducts.length > 0) {
    activeProductId.value = store.allProducts[0].product_id
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
  color: #303133;
}
.section-hint {
  font-size: 12px;
  color: #909399;
}
.section-count {
  font-size: 12px;
  color: #909399;
}

/* Section 1: AI */
.ai-section {
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  padding: 16px 20px;
  background: #f6fdf3;
}
.ai-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #909399;
  font-size: 13px;
  padding: 12px 0;
}
.ai-bubble {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: #f0f9ff;
  border-radius: 12px;
  border: 1px solid #bae6fd;
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

/* Section 2: Selection */
.selection-section {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
}
.picker-row {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}
.picker-label {
  font-size: 14px;
  color: #606266;
  margin-right: 10px;
  white-space: nowrap;
}
.match-area {
  display: flex;
  gap: 20px;
}
.chart-area {
  flex: 1;
  min-height: 280px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}
.table-area {
  flex: 1;
  min-width: 400px;
}

/* Section 3: Summary */
.summary-section {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px 20px;
  background: #fff;
}
.tag-area {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  min-height: 36px;
  margin-bottom: 16px;
  align-items: center;
}
.choice-tag {
  cursor: pointer;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
  font-style: italic;
}
.nav-row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
