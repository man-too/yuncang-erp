<template>
  <el-card shadow="never" class="trend-card">
    <template #header>
      <div class="card-header">
        <div class="card-title-group">
          <span class="card-title">销售趋势</span>
          <div class="mode-tabs">
            <div
              v-for="tab in modeTabs" :key="tab.key"
              class="mode-tab"
              :class="{ active: mode === tab.key }"
              @click="mode = tab.key"
            >{{ tab.label }}</div>
          </div>
        </div>
        <div class="card-controls">
          <el-select
            v-model="selectedProduct"
            placeholder="全部产品"
            clearable
            filterable
            remote
            :remote-method="searchProducts"
            size="small"
            style="width: 160px;"
          >
            <el-option v-for="p in productOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <div class="time-tabs">
            <div
              v-for="tab in timeTabs" :key="tab.days"
              class="time-tab"
              :class="{ active: selectedDays === tab.days }"
              @click="selectedDays = tab.days"
            >{{ tab.label }}</div>
          </div>
        </div>
      </div>
    </template>
    <div v-if="!chartData" class="chart-empty">暂无数据</div>
    <v-chart
      v-else
      :option="chartOption"
      autoresize
      style="height: 280px;"
    />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { useDashboardStore } from '@/stores/dashboard'
import { productApi } from '@/api'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const store = useDashboardStore()

const mode = ref<'amount' | 'volume'>('amount')
const selectedProduct = ref<number | undefined>(undefined)
const selectedDays = ref(30)
const productOptions = ref<{ id: number; name: string }[]>([])

const modeTabs = [
  { key: 'amount' as const, label: '销售额' },
  { key: 'volume' as const, label: '销售量' },
]

const timeTabs = [
  { label: '7天', days: 7 },
  { label: '14天', days: 14 },
  { label: '30天', days: 30 },
]

async function searchProducts(query: string) {
  if (!query.trim()) { productOptions.value = []; return }
  try {
    const res: any = await productApi.list({ keyword: query.trim(), page_size: 20 })
    productOptions.value = (res?.items || []).map((p: any) => ({ id: p.id, name: p.name }))
  } catch { productOptions.value = [] }
}

const chartData = computed(() => {
  if (mode.value === 'amount') return store.trendData
  return store.salesVolumeData
})

watch([mode, selectedProduct, selectedDays], () => {
  const params = { product_id: selectedProduct.value, days: selectedDays.value }
  if (mode.value === 'amount') {
    store.fetchTrend(params)
  } else {
    store.fetchSalesVolume(params)
  }
}, { immediate: true })

const chartOption = computed(() => {
  const d = chartData.value
  if (!d) return {}

  if (mode.value === 'amount') {
    return {
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: any) => {
          const p = params[0]
          const val = typeof p.value === 'number' && p.value >= 10000
            ? `¥${(p.value / 10000).toFixed(1)}万`
            : `¥${p.value}`
          return `${p.axisValue}<br/>${p.marker} 销售金额: ${val}`
        },
      },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category' as const,
        data: d.dates.map((s: string) => s.slice(5)),
        axisLabel: { fontSize: 11 },
      },
      yAxis: {
        type: 'value' as const,
        axisLabel: {
          formatter: (v: number) => v >= 10000 ? `${(v / 10000).toFixed(0)}万` : `${v}`,
        },
      },
      series: [
        {
          name: '销售金额',
          type: 'line' as const,
          smooth: true,
          data: d.sales_amounts,
          lineStyle: { width: 2 },
          itemStyle: { color: '#409eff' },
          areaStyle: { color: 'rgba(64,158,255,0.08)' },
        },
      ],
    }
  }

  // volume mode
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: d.dates.map((s: string) => s.slice(5)),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value' as const, name: '销量' },
    series: [{
      type: 'bar' as const,
      data: d.quantities,
      barMaxWidth: 24,
      itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
    }],
  }
})
</script>

<style scoped>
.trend-card { border-radius: 8px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.card-title { font-weight: 600; font-size: 14px; }
.mode-tabs {
  display: flex;
  gap: 4px;
}
.mode-tab {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  transition: all 0.2s;
  user-select: none;
}
.mode-tab:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.mode-tab.active {
  background: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}
.card-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.time-tabs {
  display: flex;
  gap: 4px;
}
.time-tab {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  transition: all 0.2s;
  user-select: none;
}
.time-tab:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.time-tab.active {
  background: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}
.chart-empty {
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
}
</style>
