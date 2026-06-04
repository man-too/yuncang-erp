<template>
  <div class="step-inventory">
    <!-- Section 1: 库存充裕率条形图 -->
    <el-collapse v-model="activeSections" class="inventory-collapse" @change="onCollapseChange">
      <el-collapse-item title="库存充裕率概览" name="chart">
        <div v-loading="chartLoading" class="chart-area">
          <v-chart
            ref="barChartRef"
            v-if="!chartLoading && hasData"
            :option="chartOption"
            autoresize
            style="height: 400px;"
          />
          <el-empty v-else-if="!chartLoading" description="暂无库存数据" :image-size="80" />
        </div>
        <!-- AI 分析结果 -->
        <div class="ai-analysis-section">
          <div v-if="aiLoading" class="ai-loading" v-loading="true" element-loading-text="AI 正在分析库存...">
            <span style="margin-left: 8px;">AI 正在分析库存数据...</span>
          </div>
          <el-alert v-else-if="store.aiRecommendation" type="success" :closable="false" show-icon>
            <template #default>
              <div class="ai-result-text">{{ aiResultText }}</div>
            </template>
          </el-alert>
          <div v-else class="ai-placeholder">AI 分析暂时不可用</div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Section 3: 补货清单 -->
    <div class="table-section">
      <div class="table-header">
        <span class="section-title">补货清单</span>
        <div class="header-right">
          <span class="section-count">共 {{ store.allProducts.length }} 项</span>
          <el-button type="primary" size="default" @click="openAddDialog">+ 添加产品</el-button>
        </div>
      </div>

      <el-table
        :data="store.allProducts"
        max-height="420"
        size="small"
        stripe
        @selection-change="onSelectionChange"
        ref="tableRef"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="product_name" label="产品名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="product_code" label="编码" min-width="100" />
        <el-table-column prop="specification" label="规格" min-width="100" show-overflow-tooltip />
        <el-table-column prop="unit" label="单位" width="60" align="center" />
        <el-table-column prop="warehouse_name" label="仓库" min-width="110" />
        <el-table-column prop="current_qty" label="当前库存" min-width="90" align="right" />
        <el-table-column prop="min_stock" label="最低库存" min-width="90" align="right" />
        <el-table-column label="操作" width="110" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="store.removeProduct(row.product_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-footer">
        <div class="footer-left">
          <el-button size="small" @click="store.selectAll()">全选</el-button>
          <el-button size="small" @click="store.deselectAll()">取消</el-button>
          <el-button size="small" type="danger" plain
            :disabled="store.selectedIds.size === 0"
            @click="store.removeSelected()">删除选中</el-button>
        </div>
        <el-button type="primary" :disabled="store.allProducts.length === 0" @click="handleNextStep">
          下一步：风险评估 →
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
import { ref, computed, onMounted, nextTick } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { inventoryApi, productApi } from '@/api'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const store = usePurchaseDecisionStore()

// -- Section 1: 库存充裕率条形图 --
const chartLoading = ref(false)
const inventoryItems = ref<any[]>([])
const activeSections = ref<string[]>(['chart'])
const barChartRef = ref<any>(null)

const hasData = computed(() => inventoryItems.value.length > 0)

interface SufficiencyItem {
  product_name: string
  current_qty: number
  min_stock: number
  max_stock: number
  sufficiency: number
}

const sufficiencyData = computed<SufficiencyItem[]>(() => {
  return inventoryItems.value
    .map((item: any) => {
      const currentQty = item.quantity ?? 0
      const maxStock = item.max_stock ?? 0
      const minStock = item.min_stock ?? 0
      let sufficiency = 0
      if (maxStock > 0) {
        sufficiency = (currentQty / maxStock) * 100
      } else if (minStock > 0) {
        sufficiency = (currentQty / minStock) * 50
      }
      sufficiency = Math.min(Math.max(sufficiency, 0), 100)
      return {
        product_name: item.product_name || '未知产品',
        current_qty: currentQty,
        min_stock: minStock,
        max_stock: maxStock,
        sufficiency: Math.round(sufficiency * 10) / 10,
      }
    })
    .sort((a, b) => a.sufficiency - b.sufficiency) // 升序排列，最缺货的在最上面
})

function getBarColor(value: number): string {
  if (value < 30) return '#ef5350'
  if (value < 60) return '#ff9800'
  return '#4caf50'
}

const chartOption = computed(() => {
  const data = sufficiencyData.value
  const categories = data.map(d => d.product_name)
  const values = data.map(d => d.sufficiency)
  const bgValues = data.map(d => 100 - d.sufficiency)

  return {
    title: { text: '库存充裕率概览', left: 'center', textStyle: { fontSize: 14, fontWeight: 'bold' } },
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex
        if (idx == null) return ''
        const item = data[idx]
        return `<b>${item.product_name}</b><br/>当前库存: ${item.current_qty}<br/>安全库存: ${item.min_stock}~${item.max_stock}<br/>充裕率: ${item.sufficiency}%`
      },
    },
    grid: { left: 160, right: 40, top: 50, bottom: 30 },
    xAxis: {
      type: 'value' as const,
      max: 100,
      axisLabel: { formatter: '{value}%' },
    },
    yAxis: {
      type: 'category' as const,
      data: categories,
      axisLabel: { width: 140, overflow: 'truncate', fontSize: 11 },
    },
    series: [
      {
        name: '充裕率',
        type: 'bar' as const,
        stack: 'total',
        data: values.map(v => ({
          value: v,
          itemStyle: { color: getBarColor(v) },
        })),
        barWidth: '60%',
      },
      {
        name: '背景',
        type: 'bar' as const,
        stack: 'total',
        data: bgValues,
        itemStyle: { color: '#e0e0e0' },
        barWidth: '60%',
        z: -1,
        tooltip: { show: false },
      },
    ],
  }
})

async function loadInventoryData() {
  chartLoading.value = true
  try {
    const res: any = await inventoryApi.stock({ page_size: 100 })
    inventoryItems.value = res?.items || []
  } catch {
    inventoryItems.value = []
  } finally {
    chartLoading.value = false
  }
}

// -- Collapse change → resize chart to avoid ghost rendering --
function onCollapseChange(val: string[]) {
  if (val.includes('chart')) {
    nextTick(() => {
      setTimeout(() => {
        const chart = barChartRef.value
        if (chart) chart.resize()
      }, 300)
    })
  }
}

// -- Section 2: AI --
const aiLoading = ref(false)

const aiResultText = computed(() => {
  const rec = store.aiRecommendation
  if (!rec) return ''
  if (rec.summary) return rec.summary
  if (rec.content) return rec.content
  const blocks = rec.blocks || []
  const parts: string[] = []
  for (const block of blocks) {
    if (block.type === 'text' && block.content) parts.push(block.content)
    else if (block.type === 'table' && block.rows) {
      parts.push(block.rows.map((r: any) => `${r.product_name || r.name} ${r.quantity || r.suggested_qty || ''}件`).filter(Boolean).join('；'))
    }
  }
  return parts.join('\n') || 'AI 已完成分析，请查看补货清单'
})

async function loadAIRecommendation() {
  aiLoading.value = true
  try {
    await store.getRecommendation()
    if (store.aiRecommendation) {
      const blocks = store.aiRecommendation.blocks || []
      for (const block of blocks) {
        if (block.type === 'table' && block.rows) {
          for (const row of block.rows) {
            const productName = row.product_name || row.name || ''
            const product = store.allProducts.find(
              p => p.product_name === productName || p.product_id === row.product_id
            )
            if (product) {
              store.selectedIds.value.add(product.product_id)
              store.quantities.value[product.product_id] =
                row.quantity || row.suggested_qty || Math.max(0, product.min_stock - product.current_qty)
            }
          }
        }
      }
    }
  } catch {
    // AI 分析暂时不可用，静默处理
  } finally {
    aiLoading.value = false
  }
}

// -- Section 3: 补货清单 --
const tableRef = ref()
const warehouses = ref<any[]>([])

function handleNextStep() {
  if (store.allProducts.length === 0) {
    ElMessage.warning('请先添加补货产品')
    return
  }
  store.nextStep()
}

// -- Add/Edit Dialog --
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingProductId = ref(0)
const productSearching = ref(false)
const productOptions = ref<any[]>([])
const formRef = ref<FormInstance>()

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

// -- Table selection --
function onSelectionChange(rows: any[]) {
  store.selectedIds.value = new Set(rows.map(r => r.product_id))
}

// -- Lifecycle --
onMounted(async () => {
  await Promise.all([
    store.fetchLowStockProducts(),
    loadInventoryData(),
    loadAIRecommendation(),
    (async () => {
      try { warehouses.value = (await inventoryApi.warehouses.list()) || [] }
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

/* Section 1: 充裕率条形图 */
.inventory-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 15px;
  padding: 10px 0;
}
.chart-area {
  min-height: 340px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* AI 分析区域（条形图下方） */
.ai-analysis-section {
  margin-top: 16px;
  min-height: 40px;
}
.ai-analysis-section .ai-loading {
  display: flex;
  align-items: center;
  color: var(--text-secondary);
  font-size: 13px;
  min-height: 40px;
}
.ai-placeholder {
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
}
.ai-result-text {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 13px;
}

/* Section 3: Table */
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

/* Shared */
.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}
.section-count {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
