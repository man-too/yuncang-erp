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
          <span class="section-count">共 {{ productFilteredList.length }} 项</span>
          <el-button type="primary" size="default" @click="openAddDialog">+ 添加产品</el-button>
        </div>
      </div>

      <!-- Card List -->
      <div v-if="productFilteredList.length === 0 && !store.isLoading" class="empty-state">
        暂无低库存产品
      </div>

      <div v-else class="card-list">
        <ProductCard
          v-for="product in productFilteredList"
          :key="product.product_id"
          :product-id="product.product_id"
          :product-name="product.product_name"
          :product-code="product.product_code"
          :warehouse-name="product.warehouse_name"
          :warehouse-count="product.warehouse_breakdown?.length || 1"
          :current-qty="product.current_qty"
          :min-stock="product.min_stock"
          :max-stock="product.max_stock"
          :suggested-qty="product.suggested_qty"
          :expanded="expandedProductId === product.product_id"
          :selected="isSelected(product.product_id)"
          :risk-class="cardRiskClass(product)"
          :tag-type="statusTagType(product)"
          :tag-label="statusLabel(product)"
          :rop="ropMap[product.product_id] ?? null"
          :rop-meta="ropMetaMap[product.product_id] ?? null"
          @check="(productId, val) => onCheckChange(productId, val)"
          @toggle="toggleExpand(product)"
          @edit="openEditDialog(product)"
          @delete="store.removeProduct(product.product_id)"
        >
          <!-- Expandable detail slot content -->
          <template #default>
            <ProductExpandPanel
              :product="product"
              :expanded-quantity="expandedQuantity"
              :detail-chart-loading="detailChartLoading"
              :detail-history-data="detailHistoryData"
              :detail-prediction-data="detailPredictionData"
              :detail-time-range="detailTimeRange"
              :detail-chart-option="detailChartOption"
              :rop-loading="ropLoading"
              :rop-result="ropResult"
              :get-wh-qty="getWhQty"
              :set-wh-qty="setWhQty"
              @update:expanded-quantity="expandedQuantity = $event"
              @set-time-range="onSetDetailTimeRange"
            />
          </template>
        </ProductCard>
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
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { useChatStore } from '@/stores/chat'
import { aiApi, inventoryApi } from '@/api'
import { useInventoryKpi } from './composables/useInventoryKpi'
import { useSalesChart } from './composables/useSalesChart'
import { useRopBatch } from './composables/useRopBatch'
import { useProductDialog } from './composables/useProductDialog'
import ProductCard from './ProductCard.vue'
import ProductExpandPanel from './ProductExpandPanel.vue'

const store = usePurchaseDecisionStore()
const chatStore = useChatStore()

// =========================================================================
// Composables
// =========================================================================

const { kpiTurnoverDays, kpiDeadStockCount, kpiDeadStockPct, kpiCapitalOccupied } = useInventoryKpi(store)

const {
  ropMap, ropMetaMap, batchRopLoading,
  loadBatchRop, getRop, riskRank,
  sortedProducts, filteredProducts: filteredProductsFactory,
  statusLabel, statusTagType, cardRiskClass,
} = useRopBatch(store)

// Expandable detail state
const expandedProductId = ref<number | null>(null)
const expandedProduct = computed(() =>
  expandedProductId.value != null
    ? store.allProducts.find(p => p.product_id === expandedProductId.value) ?? null
    : null
)

const {
  detailChartLoading, detailHistoryData, detailPredictionData,
  detailTimeRange, detailChartOption, setDetailTimeRange,
  ropLoading, ropResult, loadDetailData,
} = useSalesChart(
  { expandedProductId, expandedProduct },
  store,
)

// =========================================================================
// Product filtering
// =========================================================================

const searchKeyword = ref('')
const productFilter = ref<number | null>(null)

const productFilteredList = filteredProductsFactory(sortedProducts, productFilter, searchKeyword)

// When filter selects a single product, auto-expand it
watch(productFilter, (pid) => {
  if (pid != null) {
    expandedProductId.value = pid
  }
})

// =========================================================================
// AI Analysis → push to chat panel
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
watch(() => store.allProducts.length, async (len) => {
  if (len > 0) {
    // Auto-expand the first (most risky) product
    if (!expandedProductId.value) {
      expandedProductId.value = store.allProducts[0].product_id
    }
    // Load batch ROP for all products (for accurate risk ranking)
    await loadBatchRop()
    // Ensure inventoryKpi is loaded before pushing AI analysis
    if (!store.inventoryKpi) {
      await store.fetchInventoryKpi()
    }
    // Push AI analysis to chat panel if not already done
    if (!aiAnalysisPushed) {
      pushAiAnalysisToChat()
    }
  }
})

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

// Purchase quantity for expanded product (aggregated from per-warehouse)
const expandedQuantity = computed({
  get: () => {
    const pid = expandedProductId.value
    if (pid == null) return 0
    // Sum per-warehouse quantities if available
    const product = expandedProduct.value
    if (product?.warehouse_breakdown && product.warehouse_breakdown.length > 0) {
      let total = 0
      for (const wh of product.warehouse_breakdown) {
        total += store.warehouseQuantities[pid]?.[wh.warehouse_id] ?? wh.suggested_qty ?? 0
      }
      return total
    }
    return store.quantities[pid] ?? expandedProduct.value?.suggested_qty ?? 0
  },
  set: (val: number) => {
    const pid = expandedProductId.value
    if (pid != null) {
      store.quantities[pid] = val
    }
  },
})

// Per-warehouse quantity helpers
function getWhQty(productId: number, warehouseId: number, fallback: number = 0): number {
  return store.warehouseQuantities[productId]?.[warehouseId] ?? fallback
}

function setWhQty(productId: number, warehouseId: number, val: number) {
  store.setWarehouseQuantity(productId, warehouseId, val)
  // Sync the aggregated quantity
  const product = store.allProducts.find(p => p.product_id === productId)
  if (product?.warehouse_breakdown) {
    let total = 0
    for (const wh of product.warehouse_breakdown) {
      total += store.warehouseQuantities[productId]?.[wh.warehouse_id] ?? wh.suggested_qty ?? 0
    }
    store.quantities[productId] = total
  }
}

function toggleExpand(row: any) {
  if (expandedProductId.value === row.product_id) {
    expandedProductId.value = null
  } else {
    expandedProductId.value = row.product_id
  }
}

function onSetDetailTimeRange(range: '7d' | '30d' | '3m') {
  setDetailTimeRange(range)
}

// Watch expandedProductId to load detail data
watch(expandedProductId, (pid) => {
  if (pid != null) {
    loadDetailData(pid)
  }
})

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
    // Initialize per-warehouse quantities from breakdown
    if (p.warehouse_breakdown && p.warehouse_breakdown.length > 0) {
      for (const wh of p.warehouse_breakdown) {
        if (!store.warehouseQuantities[p.product_id]?.[wh.warehouse_id]) {
          store.setWarehouseQuantity(p.product_id, wh.warehouse_id, wh.suggested_qty)
        }
      }
      // Sync aggregated quantity
      let total = 0
      for (const wh of p.warehouse_breakdown) {
        total += store.warehouseQuantities[p.product_id]?.[wh.warehouse_id] ?? wh.suggested_qty ?? 0
      }
      if (!(p.product_id in store.quantities) || store.quantities[p.product_id] === 0) {
        store.quantities[p.product_id] = total
      }
    } else if (!(p.product_id in store.quantities) || store.quantities[p.product_id] === 0) {
      store.quantities[p.product_id] = p.suggested_qty
    }
  }
  store.nextStep()
}

// =========================================================================
// Add / Edit Dialog
// =========================================================================

const {
  dialogVisible, isEditing, productSearching, productOptions,
  formRef, warehouses, dialogForm, formRules,
  openAddDialog, openEditDialog, remoteSearchProducts,
  onDialogProductChange, submitDialog,
} = useProductDialog(store)

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

/* KPI Cards */
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

/* Product List Section */
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

/* Card List */
.card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 520px;
  overflow-y: auto;
}

</style>
