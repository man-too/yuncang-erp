<template>
  <div class="supplier-analysis-panel">
    <!-- 筛选栏 -->
    <div class="filter-bar" style="display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap;">
      <el-select v-model="filterSupplierId" placeholder="选择供应商" clearable filterable style="width: 220px;" size="small">
        <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-button type="primary" size="small" @click="loadData">分析</el-button>
    </div>

    <!-- 指标切换按钮 -->
    <div style="margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap;">
      <el-button v-for="m in metrics" :key="m.key" :type="activeMetric === m.key ? 'primary' : 'default'" size="small" plain @click="activeMetric = m.key">
        {{ m.label }}
      </el-button>
    </div>

    <!-- 柱状图 -->
    <div v-loading="loading" style="height: 300px; margin-bottom: 16px;">
      <v-chart v-if="!loading && chartData.length" :option="chartOption" autoresize style="height: 100%;" />
      <el-empty v-else-if="!loading" description="暂无供应商数据" />
    </div>

    <!-- AI 供应商排名表 -->
    <div v-if="rankingData.length" style="margin-bottom: 16px;">
      <h4 style="margin-bottom: 8px;">AI 供应商智能排名</h4>
      <el-table :data="rankingData" stripe size="small" border max-height="300">
        <el-table-column type="index" label="排名" width="60" />
        <el-table-column prop="name" label="供应商名称" min-width="150" />
        <el-table-column prop="rating" label="评分" width="80" align="right" />
        <el-table-column prop="lead_time" label="交期(天)" width="80" align="right" />
        <el-table-column prop="avg_evaluation" label="综合评分" width="100" align="right">
          <template #default="{ row }">
            <el-tag :type="row.avg_evaluation >= 4 ? 'success' : row.avg_evaluation >= 3 ? 'warning' : 'danger'" size="small">
              {{ row.avg_evaluation }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="delivery_rate" label="交付率" width="90" align="right">
          <template #default="{ row }">
            {{ row.delivery_rate != null ? row.delivery_rate + '%' : '暂无' }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- AI 对话气泡 -->
    <div v-if="aiResult" class="ai-chat-bubble">
      <div class="ai-avatar">AI</div>
      <div class="ai-message">
        <p style="white-space: pre-wrap;">{{ aiResult.summary || '分析完成' }}</p>
        <div v-if="aiResult.rankings && aiResult.rankings.length" style="margin-top: 8px;">
          <div v-for="r in aiResult.rankings.slice(0, 3)" :key="r.supplier_id" style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #eee;">
            <span>{{ r.supplier_name }}</span>
            <span><b>{{ r.ai_score }}分</b></span>
          </div>
        </div>
        <div v-if="aiResult.confidence" class="ai-confidence">
          置信度: <el-progress :percentage="Math.round(aiResult.confidence * 100)" :stroke-width="8" style="width: 120px; display: inline-block; vertical-align: middle; margin-left: 6px;" />
        </div>
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
import { supplierApi, aiApi } from '@/api'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const suppliers = ref<any[]>([])
const analysisData = ref<any[]>([])
const rankingData = ref<any[]>([])
const filterSupplierId = ref(null)
const loading = ref(false)
const aiResult = ref<any>(null)
const activeMetric = ref('total_score')

const metrics = [
  { key: 'quality_score', label: '质量评分', color: '#5470c6' },
  { key: 'delivery_score', label: '交付评分', color: '#91cc75' },
  { key: 'price_score', label: '价格评分', color: '#fac858' },
  { key: 'service_score', label: '服务评分', color: '#ee6666' },
  { key: 'total_score', label: '综合评分', color: '#73c0de' },
  { key: 'delivery_rate', label: '交付率', color: '#3ba272' },
  { key: 'receive_rate', label: '收货率', color: '#fc8452' },
]

const chartData = computed(() => {
  let data = analysisData.value
  if (filterSupplierId.value) {
    data = data.filter(d => d.supplier_id === filterSupplierId.value)
  }
  return data.sort((a, b) => (b[activeMetric.value] || 0) - (a[activeMetric.value] || 0))
})

const chartOption = computed(() => {
  const metric = metrics.find(m => m.key === activeMetric.value)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 80, right: 30, top: 30, bottom: 50 },
    xAxis: {
      type: 'category',
      data: chartData.value.map(d => d.supplier_name),
      axisLabel: { rotate: 0, fontSize: 11 },
    },
    yAxis: { type: 'value', name: metric?.label || '' },
    series: [{
      type: 'bar',
      data: chartData.value.map(d => ({
        value: d[activeMetric.value] || 0,
        itemStyle: { color: metric?.color || '#5470c6' },
      })),
      barMaxWidth: 40,
      label: {
        show: true,
        position: 'top',
        formatter: (p: any) => activeMetric.value.includes('rate') ? p.value + '%' : p.value,
      },
    }],
  }
})

const loadData = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (filterSupplierId.value) params.supplier_id = filterSupplierId.value
    analysisData.value = (await aiApi.supplierAnalysis(params)) || []
    const rankRes: any = await aiApi.supplierRanking()
    rankingData.value = rankRes.suppliers || []
    aiResult.value = rankRes.ai_analysis || null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const res: any = await supplierApi.list({ page: 1, page_size: 100 })
  suppliers.value = res.items || []
  await loadData()
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
</style>
