<template>
  <div class="stock-alert-panel">
    <div class="filter-bar" style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">
      <el-select v-model="filterWarehouseId" placeholder="选择仓库" clearable filterable style="width: 180px;" size="small">
        <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
      </el-select>
      <el-select v-model="filterProductId" placeholder="选择产品" clearable filterable style="width: 180px;" size="small">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-button type="primary" size="small" @click="loadHeatmap">分析</el-button>
    </div>

    <div v-loading="loading" style="max-height: 400px; overflow-y: auto; margin-bottom: 12px;">
      <el-table v-if="!loading && heatmapData.length > 0" :data="sortedData" stripe size="small" show-summary :summary-method="getSummary">
        <el-table-column prop="product_name" label="产品名" min-width="120" />
        <el-table-column prop="warehouse_name" label="仓库名" min-width="100" />
        <el-table-column prop="quantity" label="库存量" align="right" width="90" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.alert_level >= 0.6 ? 'danger' : row.alert_level >= 0.3 ? 'warning' : 'success'" size="small">
              {{ row.alert_level >= 0.6 ? '严重' : row.alert_level >= 0.3 ? '预警' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="建议" min-width="160">
          <template #default="{ row }">
            {{ row.suggestion || '—' }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!loading" description="暂无数据" />
    </div>

    <div v-if="aiResult" class="ai-bubble">
      <div class="ai-avatar">AI</div>
      <div class="ai-message">
        <p style="white-space: pre-wrap; margin: 0;">{{ aiResult.suggestion || aiResult.summary || '分析完成' }}</p>
        <div v-if="aiResult.confidence" class="ai-confidence">
          置信度: <el-progress :percentage="Math.round(aiResult.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; margin-left: 6px;" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { inventoryApi, productApi, aiApi } from '@/api'
import { ElMessage } from 'element-plus'

const warehouses = ref<any[]>([])
const products = ref<any[]>([])
const heatmapData = ref<any[]>([])
const loading = ref(false)
const aiResult = ref<any>(null)
const filterWarehouseId = ref(null)
const filterProductId = ref(null)

const sortedData = computed(() => {
  return [...heatmapData.value].sort((a, b) => (b.alert_level ?? 0) - (a.alert_level ?? 0))
})

const getSummary = ({ columns }: { columns: any[] }) => {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) {
      sums.push(`共 ${heatmapData.value.length} 项`)
    } else {
      sums.push('')
    }
  })
  return sums
}

const loadHeatmap = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterWarehouseId.value) params.warehouse_id = filterWarehouseId.value
    if (filterProductId.value) params.product_id = filterProductId.value
    heatmapData.value = (await inventoryApi.heatmap(params) as any) || []
  } finally { loading.value = false }
}

const runAIAnalysis = async () => {
  if (heatmapData.value.length === 0) return
  try {
    const productIds = [...new Set(heatmapData.value.map((d: any) => d.product_id))]
    const res: any = await aiApi.stockAlertBatch({ product_ids: productIds })
    if (res && res.results) {
      const critical = res.results.filter((r: any) => r.risk_level === 'critical')
      const warning = res.results.filter((r: any) => r.risk_level === 'warning')
      const normal = res.results.filter((r: any) => r.risk_level === 'normal' || r.risk_level === 'unknown')
      const suggestions = res.results
        .filter((r: any) => r.suggestion)
        .map((r: any) => `• **${r.product_name}**: ${r.suggestion}`)
        .slice(0, 10)
        .join('\n')
      aiResult.value = {
        suggestion: `共分析 ${res.results.length} 项产品库存:\n- ${critical.length} 项严重告警\n- ${warning.length} 项预警\n- ${normal.length} 项正常\n\n${suggestions}`,
        confidence: 0.8,
      }
    }
  } catch {
    // Fallback to local analysis
    const critical = heatmapData.value.filter((d: any) => d.alert_level >= 0.6)
    const warning = heatmapData.value.filter((d: any) => d.alert_level >= 0.3 && d.alert_level < 0.6)
    aiResult.value = { suggestion: `共监控 ${heatmapData.value.length} 项库存: ${critical.length} 项严重, ${warning.length} 项预警, ${heatmapData.value.length - critical.length - warning.length} 项正常。`, confidence: 0.85 }
  }
}

watch(heatmapData, () => runAIAnalysis())

onMounted(async () => {
  // P0-3 修复：捕获初始化失败，避免整面板白屏
  try {
    const [whRes, prodRes]: any = await Promise.all([inventoryApi.warehouses.list(), productApi.list({ page: 1, page_size: 100 })])
    warehouses.value = whRes || []
    products.value = prodRes.items || []
    await loadHeatmap()
  } catch (e: any) {
    console.warn('[StockAlertPanel] init failed', e)
    ElMessage.error('库存预警面板加载失败，请重试')
  }
})
</script>

<style scoped>
.filter-bar { background: var(--bg-filter); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); }
.ai-bubble { display: flex; gap: 12px; padding: 14px; background: var(--color-info-bg); border-radius: 12px; border: 1px solid var(--color-info-light); }
.ai-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #005BF5, #2e7bff); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px; flex-shrink: 0; }
.ai-message { flex: 1; font-size: 14px; line-height: 1.6; }
.ai-confidence { margin-top: 8px; font-size: 13px; color: #666; display: flex; align-items: center; }
</style>
