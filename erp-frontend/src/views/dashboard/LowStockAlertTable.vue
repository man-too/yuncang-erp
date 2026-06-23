<template>
  <el-card shadow="never" class="alert-card">
    <template #header>
      <span class="card-title">低库存预警 (Top 10)</span>
    </template>
    <el-table
      :data="store.lowStockItems"
      stripe
      size="small"
      max-height="300"
    >
      <el-table-column prop="product_name" label="产品" min-width="140" show-overflow-tooltip />
      <el-table-column prop="warehouse_name" label="仓库" min-width="100" show-overflow-tooltip />
      <el-table-column label="当前库存" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-danger': row.current_qty < row.min_stock }">
            {{ row.current_qty }} {{ row.unit }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="min_stock" label="安全库存" width="100" align="right">
        <template #default="{ row }">
          {{ row.min_stock }} {{ row.unit }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.current_qty === 0 ? 'danger' : row.current_qty < row.min_stock ? 'warning' : 'success'"
            size="small"
            effect="dark"
          >
            {{ row.current_qty === 0 ? '缺货' : row.current_qty < row.min_stock ? '偏低' : '正常' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { useDashboardStore } from '@/stores/dashboard'

const store = useDashboardStore()
</script>

<style scoped>
.alert-card { border-radius: 8px; }
.card-title { font-weight: 600; font-size: 14px; }
.text-danger {
  color: var(--el-color-danger);
  font-weight: 600;
}
</style>
