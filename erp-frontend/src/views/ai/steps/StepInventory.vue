<template>
  <div class="step-inventory">
    <!-- Section 1: Heatmap -->
    <el-collapse v-model="activeSections" class="inventory-collapse" @change="onCollapseChange">
      <el-collapse-item title="库存热力图" name="heatmap">
        <div v-loading="heatmapLoading" class="chart-area">
          <v-chart
            ref="heatmapChartRef"
            v-if="!heatmapLoading && hasData"
            :option="chartOption"
            autoresize
            style="height: 340px;"
            @click="onHeatmapClick"
          />
          <el-empty v-else-if="!heatmapLoading" description="暂无库存数据" :image-size="80" />
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- Section 2: AI Recommendation -->
    <div class="ai-section">
      <div class="section-row">
        <span class="section-title">AI 智能推荐分析</span>
        <el-button type="warning" size="small" @click="onRecommend" :loading="aiLoading">
          智能推荐
        </el-button>
      </div>
      <div class="ai-content">
        <div v-if="aiLoading" class="ai-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>AI 正在分析库存数据，请稍候...</span>
        </div>
        <el-alert v-else-if="aiResultText" type="success" :closable="false" show-icon>
          <template #default>
            <div class="ai-result-text">{{ aiResultText }}</div>
          </template>
        </el-alert>
        <div v-else class="ai-placeholder">点击「智能推荐」获取 AI 补货建议</div>
      </div>
    </div>

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
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent, LegendComponent } from 'echarts/components'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { inventoryApi, productApi } from '@/api'

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, LegendComponent])

const store = usePurchaseDecisionStore()

// -- Section 1: Heatmap --
const heatmapLoading = ref(false)
const heatmapData = ref<any[]>([])
const activeSections = ref<string[]>(['heatmap'])
const heatmapChartRef = ref<any>(null)

const hasData = computed(() => heatmapData.value.length > 0)

const warehouseNames = computed(() => {
  const names = [...new Set(heatmapData.value.map((d: any) => d.warehouse_name))].filter(Boolean)
  return names.length ? names : ['默认仓库']
})
const productNames = computed(() => {
  const names = [...new Set(heatmapData.value.map((d: any) => d.product_name))].filter(Boolean)
  return names.length ? names : ['默认产品']
})

const chartOption = computed(() => {
  const whNames = warehouseNames.value
  const prodNames = productNames.value
  const whIdx: Record<string, number> = Object.fromEntries(whNames.map((n, i) => [n, i]))
  const prodIdx: Record<string, number> = Object.fromEntries(prodNames.map((n, i) => [n, i]))
  const data = heatmapData.value.map((d: any) => [
    whIdx[d.warehouse_name] ?? 0, prodIdx[d.product_name] ?? 0, d.alert_level ?? 0,
  ])
  return {
    title: { text: '库存状态热力图', left: 'center', textStyle: { fontSize: 14, fontWeight: 'bold' } },
    tooltip: {
      position: 'top',
      formatter: (p: any) => {
        const item = heatmapData.value.find(
          (d: any) => d.warehouse_name === whNames[p.data[0]] && d.product_name === prodNames[p.data[1]]
        )
        if (!item) return ''
        const status = item.alert_level >= 0.6 ? '告警' : item.alert_level >= 0.3 ? '偏高/偏低' : '正常'
        return `<b>${item.product_name}</b><br/>仓库: ${item.warehouse_name}<br/>库存: ${item.quantity} / 阈值: ${item.min_stock}-${item.max_stock}<br/>状态: ${status}`
      },
    },
    grid: { left: 160, right: 40, top: 50, bottom: 50 },
    xAxis: { type: 'category', data: whNames, splitArea: { show: true }, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'category', data: prodNames, splitArea: { show: true }, axisLabel: { width: 140, overflow: 'truncate', fontSize: 11 } },
    visualMap: { min: 0, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcc80', '#ef5350'] } },
    series: [{ name: '库存状态', type: 'heatmap', data, label: { show: data.length < 50 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
  }
})

async function loadHeatmap() {
  heatmapLoading.value = true
  try { heatmapData.value = (await inventoryApi.heatmap()) || [] }
  finally { heatmapLoading.value = false }
}

// -- Collapse change → resize chart to avoid ghost rendering --
function onCollapseChange(val: string[]) {
  if (val.includes('heatmap')) {
    nextTick(() => {
      setTimeout(() => {
        const chart = heatmapChartRef.value
        if (chart) chart.resize()
      }, 300)
    })
  }
}

// -- Heatmap click → add to restock list --
function onHeatmapClick(params: any) {
  if (!params.data) return
  const whName = warehouseNames.value[params.data[0]]
  const prodName = productNames.value[params.data[1]]
  const item = heatmapData.value.find(
    (d: any) => d.warehouse_name === whName && d.product_name === prodName
  )
  if (!item) return
  const exists = store.allProducts.find(p => p.product_id === item.product_id)
  if (exists) {
    ElMessage.warning(`${item.product_name} 已在补货清单中`)
    return
  }
  store.addToProducts({
    id: item.product_id,
    name: item.product_name,
    code: item.product_code || '',
    warehouse_id: item.warehouse_id || 1,
    warehouse_name: item.warehouse_name || '默认仓库',
    current_qty: item.quantity || 0,
    min_stock: item.min_stock || 0,
    max_stock: item.max_stock || 0,
    unit: item.unit || '个',
    purchase_price: item.purchase_price || 0,
  })
  ElMessage.success(`${item.product_name} 已添加到补货清单`)
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

async function onRecommend() {
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
      ElMessage.success('AI 推荐已加载')
    }
  } catch { ElMessage.warning('推荐服务暂不可用，请手动选择') }
  finally { aiLoading.value = false }
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
    loadHeatmap(),
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

/* Section 1: Heatmap */
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

/* Section 2: AI */
.ai-section {
  border: 1px solid var(--color-success-light);
  border-radius: 8px;
  padding: 16px 20px;
  background: var(--color-success-bg);
}
.ai-content {
  margin-top: 12px;
  min-height: 40px;
}
.ai-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
}
.ai-loading .is-loading {
  animation: rotating 2s linear infinite;
}
@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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
