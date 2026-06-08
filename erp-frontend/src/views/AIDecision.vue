<template>
  <div>
    <!-- 概览统计 -->
    <el-row :gutter="16" style="margin-bottom: 12px;">
      <el-col :span="6" v-for="card in summaryCards" :key="card.title">
        <el-card shadow="hover" style="text-align: center; padding: 4px 0;">
          <div style="font-size: 22px; font-weight: bold; line-height: 1.2;">{{ card.value }}</div>
          <div style="font-size: 12px; color: #999;">{{ card.title }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 采购决策 -->
    <div style="margin-bottom: 12px;">
      <el-button type="primary" size="small" @click="purchaseStore.isExpanded = !purchaseStore.isExpanded">
        采购决策生成
      </el-button>
    </div>

    <PurchaseDecisionWizard v-if="purchaseStore.isExpanded" style="margin-bottom: 12px;" @close="purchaseStore.close()" />

    <!-- AI 对话助手 -->
    <DecisionChat @panel-focus="handlePanelFocus" />

    <!-- 决策历史 -->
    <el-collapse v-model="historyOpen" style="margin-top: 12px;">
      <el-collapse-item title="AI 决策历史" name="history">
        <el-table :data="historyList" stripe v-loading="historyLoading" max-height="300" size="small">
          <el-table-column prop="decision_type" label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="typeTag(row.decision_type)" size="small">{{ typeLabel(row.decision_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="160" />
          <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
          <el-table-column prop="confidence" label="置信度" width="90">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.confidence * 100)" :status="row.confidence > 0.7 ? 'success' : 'warning'" :stroke-width="8" />
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, shallowReactive } from 'vue'
import { aiApi } from '@/api'
import PurchaseDecisionWizard from '@/views/ai/PurchaseDecisionWizard.vue'
import DecisionChat from '@/views/ai/DecisionChat.vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
const purchaseStore = usePurchaseDecisionStore()
const historyOpen = ref(false)
const historyList = ref<any[]>([])
const historyLoading = ref(false)

const summaryCards = shallowReactive([
  { title: 'AI 决策总数', value: 0 },
  { title: '高置信度建议', value: 0 },
  { title: '库存预警', value: 0 },
  { title: '库存总项', value: 0 },
])

const typeTag = (t: string) => ({ stock_alert: 'danger', sales_forecast: 'warning', supplier_recommend: 'success' }[t] || 'info')
const typeLabel = (t: string) => ({ stock_alert: '库存预警', sales_forecast: '销售预测', supplier_recommend: '供应商推荐' }[t] || t)

const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const res: any = await aiApi.history({ limit: 20 })
    historyList.value = res || []
  } catch (_) {} finally { historyLoading.value = false }
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

const handlePanelFocus = (type: string) => {
  if (type === 'purchase_advice') purchaseStore.isExpanded = true
}

onMounted(() => { fetchHistory(); fetchDashboard() })
</script>
