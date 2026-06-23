<template>
  <div class="quick-actions-list">
    <div
      v-for="action in actions"
      :key="action.type"
      class="quick-action-item"
      @click="handleAction(action)"
    >
      <el-icon :size="18" class="action-icon"><component :is="action.icon" /></el-icon>
      <div class="action-text">
        <span class="action-label">{{ action.label }}</span>
        <span class="action-desc">{{ action.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { TrendCharts, DataAnalysis, ShoppingBag, Warning, Sunny, Timer } from '@element-plus/icons-vue'

const emit = defineEmits<{
  quickAction: [payload: { type: string; prompt: string }]
}>()

const actions = [
  { type: 'stock_alert', label: '库存预警', description: '查看各仓库库存状况', prompt: '请分析当前库存状况，显示各仓库的库存预警信息', icon: TrendCharts },
  { type: 'sales_forecast', label: '销售预测', description: '预测未来销售趋势', prompt: '请对近期销售数据进行分析和预测', icon: DataAnalysis },
  { type: 'supplier_ranking', label: '供应商排名', description: '综合评估供应商表现', prompt: '请对所有供应商进行综合评分和排名分析', icon: ShoppingBag },
  { type: 'purchase_advice', label: '采购建议', description: '智能生成补货方案', prompt: '请根据当前库存和销售情况，给出采购补货建议', icon: Warning },
  { type: 'safety_stock', label: '安全库存', description: '分析安全库存水平', prompt: '请分析各产品的安全库存水平，给出建议', icon: Sunny },
  { type: 'transfer_advice', label: '调拨建议', description: '仓库间调拨建议', prompt: '请分析各仓库库存，给出调拨建议', icon: Timer },
]

function handleAction(action: (typeof actions)[0]) {
  emit('quickAction', { type: action.type, prompt: action.prompt })
}
</script>

<style scoped>
.quick-actions-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 220px;
}
.quick-action-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.quick-action-item:hover {
  background: var(--el-fill-color-light);
}
.action-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}
.action-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.action-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.action-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
