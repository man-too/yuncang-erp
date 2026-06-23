<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h2>首页</h2>
      <el-button
        :icon="Refresh"
        circle
        @click="dashboardStore.fetchAll()"
        :loading="dashboardStore.isLoading"
      />
    </div>

    <DashboardKpiCards />

    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <SalesAmountTrend />
      </el-col>
      <el-col :span="12">
        <SalesVolumeTrend />
      </el-col>
    </el-row>

    <div style="margin-top: 16px;">
      <LowStockAlertTable />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onActivated } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useDashboardStore } from '@/stores/dashboard'
import DashboardKpiCards from './dashboard/DashboardKpiCards.vue'
import SalesAmountTrend from './dashboard/SalesAmountTrend.vue'
import SalesVolumeTrend from './dashboard/SalesVolumeTrend.vue'
import LowStockAlertTable from './dashboard/LowStockAlertTable.vue'

defineOptions({ name: 'Dashboard' })

const dashboardStore = useDashboardStore()

onMounted(() => {
  dashboardStore.fetchAll()
})

onActivated(() => {
  // Refresh data when re-activated from keep-alive
  dashboardStore.fetchAll()
})
</script>

<style scoped>
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.dashboard-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
</style>
