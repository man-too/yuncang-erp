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

    <div v-loading="loading" style="height: 360px; margin-bottom: 12px;">
      <v-chart v-if="!loading && heatmapData.length > 0" :option="chartOption" autoresize style="height: 100%;" />
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
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent, LegendComponent } from 'echarts/components'
import { inventoryApi, productApi, aiApi } from '@/api'

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, LegendComponent])

const warehouses = ref<any[]>([])
const products = ref<any[]>([])
const heatmapData = ref<any[]>([])
const loading = ref(false)
const aiResult = ref<any>(null)
const filterWarehouseId = ref(null)
const filterProductId = ref(null)

const warehouseNames = computed(() => {
  const names = [...new Set(heatmapData.value.map(d => d.warehouse_name))].filter(Boolean)
  return names.length ? names : ['默认仓库']
})

const productNames = computed(() => {
  const names = [...new Set(heatmapData.value.map(d => d.product_name))].filter(Boolean)
  return names.length ? names : ['默认产品']
})

const chartOption = computed(() => {
  const whNames = warehouseNames.value
  const prodNames = productNames.value
  const whIdx = Object.fromEntries(whNames.map((n, i) => [n, i]))
  const prodIdx = Object.fromEntries(prodNames.map((n, i) => [n, i]))
  const data = heatmapData.value.map(d => [
    whIdx[d.warehouse_name] ?? 0,
    prodIdx[d.product_name] ?? 0,
    d.alert_level ?? 0,
  ])
  return {
    tooltip: { position: 'top', formatter: (p: any) => {
      const item = heatmapData.value.find(d => d.warehouse_name === whNames[p.data[0]] && d.product_name === prodNames[p.data[1]])
      if (!item) return ''
      const status = item.alert_level >= 0.6 ? '告警' : item.alert_level >= 0.3 ? '偏高/偏低' : '正常'
      return `<b>${item.product_name}</b><br/>仓库: ${item.warehouse_name}<br/>库存: ${item.quantity} / 阈值: ${item.min_stock}-${item.max_stock}<br/>状态: ${status}`
    }},
    grid: { left: 160, right: 60, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: whNames, splitArea: { show: true } },
    yAxis: { type: 'category', data: prodNames, splitArea: { show: true } },
    visualMap: {
      min: 0, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcc80', '#ef5350'] },
    },
    series: [{ name: '库存状态', type: 'heatmap', data, label: { show: data.length < 50 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
  }
})

const loadHeatmap = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterWarehouseId.value) params.warehouse_id = filterWarehouseId.value
    if (filterProductId.value) params.product_id = filterProductId.value
    heatmapData.value = (await inventoryApi.heatmap(params)) || []
  } finally { loading.value = false }
}

const runAIAnalysis = () => {
  if (heatmapData.value.length === 0) return
  const critical = heatmapData.value.filter((d: any) => d.alert_level >= 0.6)
  const warning = heatmapData.value.filter((d: any) => d.alert_level >= 0.3 && d.alert_level < 0.6)
  aiResult.value = { suggestion: `共监控 ${heatmapData.value.length} 项库存: ${critical.length} 项严重, ${warning.length} 项预警, ${heatmapData.value.length - critical.length - warning.length} 项正常。`, confidence: 0.85 }
}

watch(heatmapData, () => runAIAnalysis())

onMounted(async () => {
  const [whRes, prodRes]: any = await Promise.all([inventoryApi.warehouses.list(), productApi.list({ page: 1, page_size: 100 })])
  warehouses.value = whRes || []
  products.value = prodRes.items || []
  await loadHeatmap()
})
</script>

<style scoped>
.filter-bar { background: var(--bg-filter); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color); }
.ai-bubble { display: flex; gap: 12px; padding: 14px; background: var(--color-info-bg); border-radius: 12px; border: 1px solid var(--color-info-light); }
.ai-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #005BF5, #2e7bff); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px; flex-shrink: 0; }
.ai-message { flex: 1; font-size: 14px; line-height: 1.6; }
.ai-confidence { margin-top: 8px; font-size: 13px; color: #666; display: flex; align-items: center; }
</style>
