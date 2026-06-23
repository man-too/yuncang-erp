<template>
  <div class="chat-welcome">
    <div class="welcome-avatar">
      <el-icon :size="36"><MagicStick /></el-icon>
    </div>
    <h2 class="welcome-title">您好，我是供应链 AI 助手</h2>
    <p class="welcome-subtitle">我可以帮您分析库存、预测销售、评估供应商、生成采购方案</p>
    <div class="welcome-grid">
      <div
        v-for="item in items"
        :key="item.label"
        class="welcome-item"
        @click="handleClick(item)"
      >
        <div class="item-icon">
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
        </div>
        <span class="item-label">{{ item.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MagicStick, TrendCharts, DataAnalysis, ShoppingCart, Warning, Timer, Box } from '@element-plus/icons-vue'

const emit = defineEmits<{
  quickAction: [payload: { type: string; prompt: string }]
}>()

const items = [
  { label: '库存预警', icon: TrendCharts, type: 'stock_alert', prompt: '请分析当前库存状况，显示各仓库的库存预警信息' },
  { label: '销售预测', icon: DataAnalysis, type: 'sales_forecast', prompt: '请对近期销售数据进行分析和预测' },
  { label: '供应商排名', icon: ShoppingCart, type: 'supplier_ranking', prompt: '请对所有供应商进行综合评分和排名分析' },
  { label: '采购建议', icon: Warning, type: 'purchase_advice', prompt: '请根据当前库存和销售情况，给出采购补货建议' },
  { label: '安全库存', icon: Box, type: 'safety_stock', prompt: '请分析各产品的安全库存水平，给出建议' },
  { label: '调拨建议', icon: Timer, type: 'transfer_advice', prompt: '请分析各仓库库存，给出调拨建议' },
]

function handleClick(item: typeof items[0]) {
  emit('quickAction', { type: item.type, prompt: item.prompt })
}
</script>

<style scoped>
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px 24px;
  text-align: center;
}
.welcome-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #333;
  color: #fff;
  margin-bottom: 20px;
}
.welcome-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 8px;
  color: #222;
}
.welcome-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0 0 28px;
  max-width: 320px;
  line-height: 1.5;
}
.welcome-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  max-width: 420px;
  width: 100%;
}
.welcome-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 20px;
  border: 1px solid #d9d9d9;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.welcome-item:hover {
  border-color: #333;
  background: #f5f5f5;
}
.item-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f0f0;
  color: #333;
  flex-shrink: 0;
}
.item-label {
  font-size: 13px;
  color: #333;
}
</style>
