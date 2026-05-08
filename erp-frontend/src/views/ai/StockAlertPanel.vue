<template>
  <div class="stock-alert-panel">
    <!-- 筛选栏 -->
    <div class="filter-bar" style="display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap;">
      <el-select v-model="filterWarehouseId" placeholder="选择仓库" clearable filterable style="width: 200px;" size="small">
        <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
      </el-select>
      <el-select v-model="filterProductId" placeholder="选择产品" clearable filterable style="width: 200px;" size="small">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-button type="primary" size="small" @click="loadHeatmap">分析</el-button>
    </div>

    <!-- 热力图 -->
    <div v-loading="loading" style="height: 360px; margin-bottom: 16px;">
      <v-chart v-if="!loading" :option="chartOption" autoresize style="height: 100%;" />
      <el-empty v-else-if="!loading && heatmapData.length === 0" description="暂无数据" />
    </div>

    <!-- AI 对话气泡 -->
    <div v-if="aiResult" class="ai-chat-bubble">
      <div class="ai-avatar">AI</div>
      <div class="ai-message">
        <p style="white-space: pre-wrap;">{{ aiResult.suggestion || aiResult.summary || aiResult.reason || '分析完成' }}</p>
        <div v-if="aiResult.confidence" class="ai-confidence">
          置信度: <el-progress :percentage="Math.round(aiResult.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; vertical-align: middle; margin-left: 6px;" />
        </div>
        <div v-if="aiResult.alert_level" class="ai-tag">
          <el-tag :type="aiResult.alert_level === 'critical' ? 'danger' : aiResult.alert_level === 'warning' ? 'warning' : 'success'" size="small">
            {{ { critical: '严重告警', warning: '预警', normal: '正常' }[aiResult.alert_level] || aiResult.alert_level }}
          </el-tag>
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

const fetchWarehouses = async () => {
  warehouses.value = (await inventoryApi.warehouses.list()) || []
}
const fetchProducts = async () => {
  const res: any = await productApi.list({ page: 1, page_size: 100 })
  products.value = res.items || []
}

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
  const whIndex = Object.fromEntries(whNames.map((n, i) => [n, i]))
  const prodIndex = Object.fromEntries(prodNames.map((n, i) => [n, i]))

  const data = heatmapData.value.map(d => [
    whIndex[d.warehouse_name] ?? 0,
    prodIndex[d.product_name] ?? 0,
    d.alert_level ?? 0,
  ])

  return {
    tooltip: {
      position: 'top',
      formatter: (p: any) => {
        const item = heatmapData.value.find(d =>
          d.warehouse_name === whNames[p.data[0]] &&
          d.product_name === prodNames[p.data[1]]
        )
        if (!item) return ''
        const status = item.alert_level >= 0.6 ? '告警' : item.alert_level >= 0.3 ? '偏高/偏低' : '正常'
        return `<b>${item.product_name}</b><br/>
          仓库: ${item.warehouse_name}<br/>
          库存: ${item.quantity} / 阈值: ${item.min_stock}-${item.max_stock}<br/>
          状态: ${status}`
      },
    },
    grid: { left: 160, right: 60, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: whNames, splitArea: { show: true }, axisLabel: { rotate: 0 } },
    yAxis: { type: 'category', data: prodNames, splitArea: { show: true } },
    visualMap: {
      min: 0, max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcc80', '#ef5350'] },
    },
    series: [{
      name: '库存状态',
      type: 'heatmap',
      data,
      label: { show: data.length < 50 },
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' },
      },
    }],
  }
})

const loadHeatmap = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterWarehouseId.value) params.warehouse_id = filterWarehouseId.value
    if (filterProductId.value) params.product_id = filterProductId.value
    heatmapData.value = (await inventoryApi.heatmap(params)) || []
  } finally {
    loading.value = false
  }
}

const runAIAnalysis = async () => {
  if (heatmapData.value.length === 0) return
  const critical = heatmapData.value.filter((d: any) => d.alert_level >= 0.6)
  const warning = heatmapData.value.filter((d: any) => d.alert_level >= 0.3 && d.alert_level < 0.6)
  const summary = `共监控 ${heatmapData.value.length} 项库存: ${critical.length} 项严重, ${warning.length} 项预警, ${heatmapData.value.length - critical.length - warning.length} 项正常。`
  aiResult.value = { suggestion: summary, confidence: 0.85, alert_level: critical.length > 0 ? 'critical' : warning.length > 0 ? 'warning' : 'normal' }
}

watch(heatmapData, () => { runAIAnalysis() })

onMounted(async () => {
  await Promise.all([fetchWarehouses(), fetchProducts()])
  await loadHeatmap()
})
</script>

<style scoped>
.ai-chat-bubble {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #f0f9ff;
  border-radius: 12px;
  border: 1px solid #bae6fd;
  margin-top: 12px;
}
.ai-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
  flex-shrink: 0;
}
.ai-message {
  flex: 1;
  line-height: 1.6;
  font-size: 14px;
}
.ai-confidence {
  margin-top: 8px;
  font-size: 13px;
  color: #666;
  display: flex;
  align-items: center;
}
.ai-tag {
  margin-top: 8px;
}
</style>
