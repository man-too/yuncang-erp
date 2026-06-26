<template>
  <!-- Per-warehouse breakdown -->
  <div v-if="product.warehouse_breakdown && product.warehouse_breakdown.length > 0" class="expand-warehouse-section">
    <div class="warehouse-title">各仓库详情</div>
    <div class="warehouse-list">
      <div
        v-for="wh in product.warehouse_breakdown"
        :key="wh.warehouse_id"
        class="warehouse-row"
      >
        <div class="warehouse-row-header">
          <el-tag size="small" effect="plain">{{ wh.warehouse_name }}</el-tag>
          <span class="warehouse-stat">
            库存: <strong :class="{ 'text-danger': wh.current_qty < wh.min_stock }">{{ wh.current_qty }}</strong>
          </span>
          <span class="warehouse-stat">安全: <strong>{{ wh.min_stock }}</strong></span>
          <span class="warehouse-stat">最高: <strong>{{ wh.max_stock }}</strong></span>
          <span class="warehouse-stat">
            缺口: <strong class="text-danger">{{ Math.max(0, wh.min_stock - wh.current_qty) }}</strong>
          </span>
          <span v-if="wh.rop != null" class="warehouse-stat warehouse-rop">
            ROP: <strong>{{ wh.rop }}</strong>
          </span>
          <span v-if="wh.in_transit_qty > 0" class="warehouse-stat warehouse-transit">
            在途: {{ wh.in_transit_qty }}
          </span>
          <span v-if="wh.backlog_qty > 0" class="warehouse-stat warehouse-backlog">
            积压: {{ wh.backlog_qty }}
          </span>
        </div>
        <div class="warehouse-qty-row">
          <span class="qty-label-sm">采购量：</span>
          <el-input-number
            :model-value="getWhQty(product.product_id, wh.warehouse_id, wh.suggested_qty)"
            @update:model-value="(val: number) => setWhQty(product.product_id, wh.warehouse_id, val)"
            :min="0"
            :precision="0"
            size="small"
            style="width: 140px;"
          />
          <span class="qty-unit-sm">{{ product.unit || '个' }}</span>
          <span v-if="wh.suggested_qty > 0" class="qty-hint-sm">
            (建议: {{ wh.suggested_qty }})
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- Sales Forecast Chart -->
  <div class="expand-chart-section">
    <div class="chart-toolbar">
      <div class="time-tabs">
        <div class="time-tab" :class="{ active: detailTimeRange === '7d' }" @click="$emit('setTimeRange', '7d')">近7天</div>
        <div class="time-tab" :class="{ active: detailTimeRange === '30d' }" @click="$emit('setTimeRange', '30d')">近30天</div>
        <div class="time-tab" :class="{ active: detailTimeRange === '3m' }" @click="$emit('setTimeRange', '3m')">近3个月</div>
      </div>
    </div>
    <div v-loading="detailChartLoading" class="chart-area" style="height: 300px;">
      <v-chart
        v-if="!detailChartLoading && (detailHistoryData.length > 0 || detailPredictionData.length > 0)"
        :key="`detail-chart-${product.product_id}-${detailTimeRange}`"
        :option="detailChartOption"
        autoresize
        style="height: 100%;"
      />
      <el-empty v-else-if="!detailChartLoading" description="暂无销量数据" :image-size="60" />
    </div>
  </div>

  <!-- ROP Calculation Result -->
  <div class="expand-rop-section">
    <div class="rop-title">ROP 再订货点计算</div>
    <div v-if="ropLoading" class="rop-loading" v-loading="true" element-loading-text="计算中..."></div>
    <div v-else-if="ropResult" class="rop-grid">
      <div class="rop-item">
        <span class="rop-label">日均销量</span>
        <span class="rop-value">{{ ropResult.avg_daily_sales ?? '—' }}</span>
      </div>
      <div class="rop-item">
        <span class="rop-label">提前期(天)</span>
        <span class="rop-value">{{ ropResult.lead_time ?? '—' }}</span>
      </div>
      <div class="rop-item">
        <span class="rop-label">安全库存</span>
        <span class="rop-value">{{ ropResult.safety_stock ?? '—' }}</span>
      </div>
      <div class="rop-item">
        <span class="rop-label">再订货点(ROP)</span>
        <span class="rop-value rop-value--highlight">
          <el-tag
            :type="ropResult.precision_mode === 'final' ? 'success' : 'warning'"
            size="small"
            style="margin-right: 4px; vertical-align: middle;"
          >{{ ropResult.precision_mode === 'final' ? '终值' : '预估' }}</el-tag>
          {{ ropResult.rop ?? '—' }}
        </span>
        <span v-if="ropResult.note" class="rop-note">{{ ropResult.note }}</span>
      </div>
      <div class="rop-item">
        <span class="rop-label">建议采购量</span>
        <span class="rop-value rop-value--highlight">{{ ropResult.suggested_qty ?? '—' }}</span>
      </div>
    </div>
    <div v-else class="rop-placeholder">点击产品自动计算 ROP</div>
  </div>

  <!-- Total Purchase Quantity (aggregated from per-warehouse) -->
  <div class="expand-qty-row">
    <span class="qty-label">总采购数量：</span>
    <el-input-number
      :model-value="expandedQuantity"
      @update:model-value="$emit('update:expandedQuantity', $event)"
      :min="0"
      :precision="0"
      size="default"
      style="width: 180px;"
    />
    <span class="qty-unit">{{ product.unit || '个' }}</span>
    <span v-if="ropResult?.suggested_qty" class="qty-hint">
      (ROP建议: {{ ropResult.suggested_qty }})
    </span>
  </div>
</template>

<script setup lang="ts">
import VChart from 'vue-echarts'
import type { RestockItem } from '@/stores/purchaseDecision'

defineProps<{
  product: RestockItem
  expandedQuantity: number
  // Chart data
  detailChartLoading: boolean
  detailHistoryData: any[]
  detailPredictionData: number[]
  detailTimeRange: '7d' | '30d' | '3m'
  detailChartOption: any
  // ROP data
  ropLoading: boolean
  ropResult: any
  // Warehouse qty helpers
  getWhQty: (productId: number, warehouseId: number, fallback: number) => number
  setWhQty: (productId: number, warehouseId: number, val: number) => void
}>()

defineEmits<{
  'update:expandedQuantity': [val: number]
  setTimeRange: [range: '7d' | '30d' | '3m']
}>()
</script>

<style scoped>
/* Chart Area */
.expand-chart-section {
  margin: 0;
}
.chart-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.time-tabs {
  display: flex;
  gap: 4px;
}
.time-tab {
  padding: 4px 14px;
  border-radius: 6px;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  border: 1px solid #ddd;
  transition: all 0.2s;
  user-select: none;
  background: #fff;
}
.time-tab:hover {
  border-color: #409eff;
  color: #409eff;
}
.time-tab.active {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}
.chart-area {
  min-height: 300px;
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ROP Section */
.expand-rop-section {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 18px;
  background: #fff;
}
.rop-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
  color: var(--text-primary, #303133);
}
.rop-loading {
  min-height: 40px;
}
.rop-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.rop-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rop-label {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}
.rop-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.rop-value--highlight {
  color: #005BF5;
}
.rop-note {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary, #909399);
  margin-top: 2px;
}
.rop-placeholder {
  color: var(--text-secondary, #909399);
  font-size: 13px;
  font-style: italic;
}

/* Quantity Input Row */
.expand-qty-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
}
.qty-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.qty-unit {
  font-size: 13px;
  color: #606266;
}
.qty-hint {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}

/* Warehouse Breakdown Section */
.expand-warehouse-section {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 18px;
  background: #fff;
}
.warehouse-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--text-primary, #303133);
}
.warehouse-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.warehouse-row {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 14px;
  background: #fafafa;
}
.warehouse-row-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.warehouse-stat {
  font-size: 13px;
  color: var(--text-secondary, #909399);
}
.warehouse-stat strong {
  color: var(--text-primary, #303133);
  font-weight: 600;
}
.warehouse-rop strong {
  color: #005BF5;
  font-weight: 700;
}
.warehouse-transit {
  color: #409eff;
}
.warehouse-backlog {
  color: #e6a23c;
}
.warehouse-qty-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 4px;
}
.qty-label-sm {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.qty-unit-sm {
  font-size: 12px;
  color: #606266;
}
.qty-hint-sm {
  font-size: 11px;
  color: var(--text-secondary, #909399);
}
</style>
