<template>
  <div>
    <h2 style="margin-bottom: 16px;">AI 智能决策中心</h2>

    <!-- 概览统计 -->
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="6" v-for="card in summaryCards" :key="card.title">
        <el-card shadow="hover">
          <div style="text-align: center;">
            <div style="font-size: 28px; font-weight: bold;">{{ card.value }}</div>
            <div style="font-size: 12px; color: #999;">{{ card.title }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 三大折叠模块 -->
    <el-collapse v-model="activePanels" style="margin-bottom: 16px;">
      <!-- 库存预警 -->
      <el-collapse-item title="📊 库存预警模块" name="stock-alert">
        <StockAlertPanel />
      </el-collapse-item>

      <!-- 销售预测 -->
      <el-collapse-item title="📈 销售预测模块" name="sales-forecast">
        <SalesForecastPanel />
      </el-collapse-item>

      <!-- 供应商分析 -->
      <el-collapse-item title="🏆 供应商分析模块" name="supplier-analysis">
        <SupplierAnalysisPanel />
      </el-collapse-item>
    </el-collapse>

    <!-- AI 决策历史 -->
    <el-card shadow="never">
      <template #header>AI 决策历史</template>
      <el-table :data="historyList" stripe v-loading="historyLoading">
        <el-table-column prop="decision_type" label="类型" width="140">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.decision_type)" size="small">{{ typeLabel(row.decision_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="summary" label="摘要" min-width="250" />
        <el-table-column prop="confidence" label="置信度" width="100">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.confidence * 100)" :status="row.confidence > 0.7 ? 'success' : 'warning'" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, shallowReactive } from 'vue'
import { aiApi } from '@/api'
import StockAlertPanel from '@/views/ai/StockAlertPanel.vue'
import SalesForecastPanel from '@/views/ai/SalesForecastPanel.vue'
import SupplierAnalysisPanel from '@/views/ai/SupplierAnalysisPanel.vue'

const activePanels = ref(['stock-alert', 'sales-forecast', 'supplier-analysis'])
const historyList = ref<any[]>([])
const historyLoading = ref(false)

const summaryCards = shallowReactive([
  { title: 'AI 决策总数', value: 0 },
  { title: '高置信度建议', value: 0 },
  { title: '库存预警', value: 0 },
  { title: '库存异常', value: 0 },
])

const typeTag = (t: string) => ({
  stock_alert: 'danger', sales_forecast: 'warning', supplier_recommend: 'success',
}[t] || 'info')

const typeLabel = (t: string) => ({
  stock_alert: '库存预警', sales_forecast: '销售预测', supplier_recommend: '供应商推荐',
}[t] || t)

const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const res: any = await aiApi.history({ limit: 50 })
    historyList.value = res || []
  } catch (_) {} finally {
    historyLoading.value = false
  }
}

const fetchDashboard = async () => {
  try {
    const res: any = await aiApi.dashboard()
    if (res) {
      summaryCards[0].value = res.total_decisions || 0
      summaryCards[1].value = res.high_confidence_decisions || 0
      summaryCards[2].value = res.low_stock_count || 0
      summaryCards[3].value = res.total_inventory_items || 0
    }
  } catch (_) {}
}

onMounted(() => {
  fetchHistory()
  fetchDashboard()
})
</script>
