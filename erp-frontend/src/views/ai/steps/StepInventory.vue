<template>
  <div class="step-inventory">
    <!-- Left: Heatmap -->
    <div v-loading="loading" class="chart-area">
      <v-chart v-if="!loading && hasData" :option="chartOption" autoresize style="height: 100%;" />
      <el-empty v-else-if="!loading" description="暂无库存数据" :image-size="80" />
    </div>

    <!-- Right: Product table + actions -->
    <div class="table-area">
      <div class="table-toolbar">
        <el-input v-model="search" placeholder="搜索产品" size="small" clearable prefix-icon="Search" style="width: 180px;" />
        <el-button size="small" @click="store.selectAll()">全选</el-button>
        <el-button size="small" @click="store.deselectAll()">取消</el-button>
      </div>

      <el-table
        :data="filteredProducts" max-height="320" size="small" stripe
        @selection-change="onSelectionChange"
        ref="tableRef"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="product_name" label="产品" min-width="120" />
        <el-table-column prop="current_qty" label="库存" width="70" align="right" />
        <el-table-column prop="min_stock" label="安全线" width="70" align="right" />
        <el-table-column label="补货量" width="90">
          <template #default="{ row }">
            <el-input-number
              v-model="store.quantities[row.product_id]"
              :min="0" :max="99999" size="small"
              style="width: 80px;"
              controls-position="right"
              @click.stop
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag
              :type="row.current_qty === 0 ? 'danger' : row.current_qty < row.min_stock * 0.5 ? 'warning' : 'info'"
              size="small" effect="plain"
            >
              {{ row.current_qty === 0 ? '缺货' : row.current_qty < row.min_stock * 0.5 ? '偏低' : '偏低' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="step-actions">
        <el-button type="info" @click="onRecommend" :loading="loading">
          🤖 智能推荐
        </el-button>
        <el-button type="primary" @click="store.nextStep()" :disabled="store.selectedIds.size === 0">
          下一步 ▶
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
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent, LegendComponent } from 'echarts/components'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { inventoryApi } from '@/api'

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, LegendComponent])

const store = usePurchaseDecisionStore()
const search = ref('')
const loading = ref(false)
const heatmapData = ref<any[]>([])
const tableRef = ref()

const filteredProducts = computed(() => {
  const all = store.allProducts
  if (!search.value) return all
  const kw = search.value.toLowerCase()
  return all.filter(p => p.product_name.toLowerCase().includes(kw) || p.product_code.toLowerCase().includes(kw))
})

const hasData = computed(() => heatmapData.value.length > 0)

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
    title: { text: '库存状态热力图', left: 'center', textStyle: { fontSize: 14, fontWeight: 'bold' } },
    tooltip: {
      position: 'top',
      formatter: (p: any) => {
        const item = heatmapData.value.find(d =>
          d.warehouse_name === whNames[p.data[0]] && d.product_name === prodNames[p.data[1]]
        )
        if (!item) return ''
        const status = item.alert_level >= 0.6 ? '告警' : item.alert_level >= 0.3 ? '偏高/偏低' : '正常'
        return `<b>${item.product_name}</b><br/>仓库: ${item.warehouse_name}<br/>库存: ${item.quantity} / 阈值: ${item.min_stock}-${item.max_stock}<br/>状态: ${status}`
      },
    },
    grid: { left: 160, right: 40, top: 50, bottom: 50 },
    xAxis: { type: 'category', data: whNames, splitArea: { show: true }, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'category', data: prodNames, splitArea: { show: true } },
    visualMap: {
      min: 0, max: 1, calculable: true,
      orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcc80', '#ef5350'] },
    },
    series: [{
      name: '库存状态', type: 'heatmap', data,
      label: { show: data.length < 50 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  }
})

function onSelectionChange(rows: any[]) {
  // Sync with store.selectedIds
  const ids = new Set(rows.map(r => r.product_id))
  store.selectedIds.value = ids
  // Set default quantities for selected
  for (const row of rows) {
    if (!store.quantities.value[row.product_id]) {
      const p = store.allProducts.find(x => x.product_id === row.product_id)
      if (p) store.quantities.value[row.product_id] = p.suggested_qty
    }
  }
}

async function onRecommend() {
  loading.value = true
  try {
    const res: any = await inventoryApi.alerts({ alert_type: 'low_stock', page_size: 100 })
    if (res && res.items) {
      // Auto-select all critical/high priority
      for (const item of res.items) {
        if (item.level === 'critical' || item.level === 'high') {
          store.selectedIds.value.add(item.product_id)
          store.quantities.value[item.product_id] = Math.max(0, (item.threshold_value || 0) - (item.current_quantity || 0))
        }
      }
    }
  } finally {
    loading.value = false
  }
}

async function loadData() {
  loading.value = true
  try {
    heatmapData.value = (await inventoryApi.heatmap()) || []
  } finally { loading.value = false }
}

onMounted(async () => {
  await Promise.all([store.fetchLowStockProducts(), loadData()])
})
</script>

<style scoped>
.step-inventory {
  display: flex;
  gap: 16px;
  height: 100%;
}
.chart-area {
  flex: 1;
  height: 380px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}
.table-area {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.table-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}
.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
