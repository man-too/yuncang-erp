<template>
  <el-row :gutter="12" class="kpi-row">
    <el-col :span="4" v-for="card in cards" :key="card.key">
      <div class="kpi-card" :class="{ 'kpi-card--accent': card.accent }">
        <div class="kpi-icon" :style="{ background: card.bgColor }">
          <el-icon :size="18" :color="card.iconColor"><component :is="card.icon" /></el-icon>
        </div>
        <div class="kpi-info">
          <div class="kpi-value">{{ card.value }}</div>
          <div class="kpi-label">{{ card.label }}</div>
        </div>
      </div>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ShoppingCart, Wallet, Document, Warning, Van, TrendCharts } from '@element-plus/icons-vue'
import { useDashboardStore } from '@/stores/dashboard'

const store = useDashboardStore()

const cards = computed(() => {
  const d = store.kpiData
  return [
    {
      key: 'today_orders', label: '今日订单', value: d?.today_orders ?? '—',
      icon: ShoppingCart, bgColor: '#f0f5ff', iconColor: '#2e7bff',
    },
    {
      key: 'monthly_amount', label: '本月金额', value: formatMoney(d?.monthly_amount),
      icon: Wallet, bgColor: '#e8f0fe', iconColor: '#4a8af4',
    },
    {
      key: 'pending_approval', label: '待审批订单', value: d?.pending_approval ?? '—',
      icon: Document, bgColor: '#dce8fc', iconColor: '#3a6fd8', accent: true,
    },
    {
      key: 'low_stock', label: '低库存产品', value: d?.low_stock_products ?? '—',
      icon: Warning, bgColor: '#cddaf6', iconColor: '#2a55b5', accent: true,
    },
    {
      key: 'pending_inbound', label: '待入库', value: d?.pending_inbound ?? '—',
      icon: Van, bgColor: '#bed0f2', iconColor: '#1e44a0',
    },
    {
      key: 'growth', label: '销售增长率', value: formatGrowth(d?.sales_growth_rate),
      icon: TrendCharts, bgColor: '#aec7ee', iconColor: '#13378a',
    },
  ]
})

function formatMoney(v: number | undefined): string {
  if (v == null) return '—'
  if (v >= 10000) return `¥${(v / 10000).toFixed(1)}万`
  return `¥${v.toFixed(0)}`
}

function formatGrowth(v: number | undefined): string {
  if (v == null) return '—'
  const prefix = v > 0 ? '+' : ''
  return `${prefix}${v.toFixed(1)}%`
}
</script>

<style scoped>
.kpi-row { margin-bottom: 4px; }
.kpi-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
.kpi-card--accent {
  border-color: var(--el-color-warning-light-5);
}
.kpi-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kpi-info { min-width: 0; }
.kpi-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}
.kpi-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
</style>
