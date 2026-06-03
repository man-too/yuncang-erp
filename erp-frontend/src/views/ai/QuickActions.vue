<!-- 快捷操作底部面板 -->
<template>
  <div class="quick-panel" :class="{ collapsed: isCollapsed }">
    <div class="toggle-bar" @click="isCollapsed = !isCollapsed">
      <span class="toggle-label">
        <el-icon><Operation /></el-icon>
        快捷操作
        <el-icon><ArrowDown v-if="isCollapsed" /><ArrowUp v-else /></el-icon>
      </span>
    </div>
    <div v-show="!isCollapsed" class="actions-grid">
      <div
        v-for="action in quickActions" :key="action.label"
        class="action-cell" @click="$emit('quickAction', { type: action.type, prompt: action.prompt })"
      >
        <el-icon class="cell-icon"><component :is="action.icon" /></el-icon>
        <span class="cell-label">{{ action.label }}</span>
        <span class="cell-desc">{{ action.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { WarningFilled, TrendCharts, Trophy, Search, ShoppingCartFull, Refresh } from '@element-plus/icons-vue'

defineEmits<{ quickAction: [payload: { type: string; prompt: string }] }>()

const isCollapsed = ref(true)

const quickActions = [
  { icon: WarningFilled, label: '库存预警', type: 'stock_alert', description: '分析库存风险，定位紧缺产品',
    prompt: '请用热力图展示库存风险分布，用表格列出需要紧急补货的产品，按风险等级排序。' },
  { icon: TrendCharts, label: '销售预测', type: 'sales_forecast', description: '预测未来30天销量趋势',
    prompt: '请分析销售趋势数据，给出备货建议和销售洞察。' },
  { icon: Trophy, label: '供应商排名', type: 'supplier_ranking', description: '多维度评估供应商表现',
    prompt: '请用柱状图展示各供应商评分对比，用表格列出综合排名，从质量、交付、价格、服务四个维度分析。' },
  { icon: Search, label: '综合诊断', type: 'dashboard', description: '全链路供应链健康检查',
    prompt: '请对当前供应链状况进行综合诊断，包括库存健康度、销售趋势、供应商表现，并给出改进建议。' },
  { icon: ShoppingCartFull, label: '采购建议', type: 'purchase_advice', description: '智能生成采购补货方案',
    prompt: '根据当前低库存产品和销售趋势，推荐需要采购的产品清单及建议采购量，并推荐最佳供应商。' },
  { icon: Refresh, label: '调拨建议', type: 'transfer_advice', description: '优化仓库间库存配置',
    prompt: '分析各仓库的库存分布，识别库存分布不均衡的产品，给出调拨建议。' },
]
</script>

<style scoped>
.quick-panel { border-top: 2px solid var(--border-color); background: var(--bg-page); transition: all 0.3s; }
.toggle-bar {
  padding: 8px 16px; cursor: pointer; text-align: center;
  color: var(--text-regular); font-size: 13px; user-select: none;
}
.toggle-bar:hover { background: var(--bg-page); opacity: 0.8; }
.toggle-label { display: inline-flex; align-items: center; gap: 6px; }

.actions-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 10px; padding: 0 16px 14px;
}
.action-cell {
  display: flex; flex-direction: column; align-items: center;
  padding: 12px 6px; border-radius: 10px; border: 1px solid var(--border-color);
  background: var(--bg-card); cursor: pointer; transition: all 0.2s;
}
.action-cell:hover {
  border-color: var(--color-accent); box-shadow: 0 2px 12px rgba(200, 152, 60, 0.15);
  transform: translateY(-2px);
}
.cell-icon { font-size: 22px; }
.cell-label { font-weight: 600; font-size: 14px; color: var(--text-primary); margin-top: 4px; }
.cell-desc { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
</style>
