<template>
  <div
    class="product-card"
    :class="riskClass"
  >
    <!-- Card top row: checkbox + status tag + name + code + shortage count + total gap + ROP + actions -->
    <div class="card-header">
      <el-checkbox
        :model-value="selected"
        @change="(val: boolean) => $emit('check', productId, val)"
      />
      <el-tag :type="tagType" size="small" effect="dark">
        {{ tagLabel }}
      </el-tag>
      <span class="card-name">{{ productName }}</span>
      <span class="card-code">{{ productCode }}</span>
      <!-- Show warehouse count badge if multiple warehouses -->
      <el-tag
        v-if="warehouseCount > 1"
        size="small"
        type="warning"
        effect="plain"
      >
        {{ warehouseCount }} 个仓库缺货
      </el-tag>
      <el-tag v-else size="small" type="info">{{ warehouseName }}</el-tag>
      <span v-if="rop != null" class="card-rop">
        <el-tag
          :type="ropMeta?.precision_mode === 'final' ? 'success' : 'warning'"
          size="small"
          style="margin-right: 4px;"
        >{{ ropMeta?.precision_mode === 'final' ? '终值' : '预估' }}</el-tag>
        ROP: {{ rop }}
        <span v-if="ropMeta?.note" class="card-rop-note">{{ ropMeta.note }}</span>
      </span>
      <div class="card-actions">
        <el-button link @click.stop="$emit('toggle')">
          {{ expanded ? '收起' : '详情' }}
        </el-button>
        <el-button link @click.stop="$emit('edit')">编辑</el-button>
        <el-button link type="danger" @click.stop="$emit('delete')">删除</el-button>
      </div>
    </div>

    <!-- Card detail line: total current qty / safety / max / total gap -->
    <div class="card-stats">
      <span>
        总库存: <strong :class="{ 'text-danger': currentQty < minStock }">{{ currentQty }}</strong>
      </span>
      <span>安全: <strong>{{ minStock }}</strong></span>
      <span>最高: <strong>{{ maxStock }}</strong></span>
      <span>
        总缺口: <strong class="text-danger">{{ suggestedQty }}</strong>
      </span>
    </div>

    <!-- Expandable detail panel slot -->
    <div v-if="expanded" class="expand-panel">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
interface RopMeta {
  precision_mode?: string
  lead_time_source?: string
  note?: string
}

defineProps<{
  productId: number
  productName: string
  productCode: string
  warehouseName: string
  warehouseCount: number
  currentQty: number
  minStock: number
  maxStock: number
  suggestedQty: number
  expanded: boolean
  selected: boolean
  riskClass: string
  tagType: string
  tagLabel: string
  rop: number | null
  ropMeta: RopMeta | null
}>()

defineEmits<{
  check: [productId: number, val: boolean]
  toggle: []
  edit: []
  delete: []
}>()
</script>

<style scoped>
.product-card {
  border: 1px solid var(--border-light, #ebeef5);
  border-radius: 10px;
  padding: 12px 16px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
  cursor: default;
}
.product-card:hover {
  border-color: #c0c6d0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.product-card.card-danger {
  border-left: 3px solid var(--el-color-danger, #f56c6c);
  background: var(--el-color-danger-light-9, #fef0f0);
}
.product-card.card-warning {
  border-left: 3px solid var(--el-color-warning, #e6a23c);
  background: var(--el-color-warning-light-9, #fdf6ec);
}
.product-card.card-info {
  border-left: 3px solid #909399;
  background: #f4f4f5;
}

/* Card Header Row */
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.card-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.card-code {
  font-size: 12px;
  color: var(--text-secondary, #909399);
  flex-shrink: 0;
}
.card-rop {
  font-size: 13px;
  font-weight: 700;
  color: #005BF5;
  margin-left: auto;
}
.card-rop-note {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary, #909399);
  margin-left: 4px;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

/* Card Stats Row */
.card-stats {
  display: flex;
  gap: 20px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary, #909399);
}
.card-stats strong {
  color: var(--text-primary, #303133);
  font-weight: 600;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

/* Expandable Detail Panel (inside card) */
.expand-panel {
  border: 1px solid #d9ecff;
  border-radius: 10px;
  padding: 20px;
  margin-top: 12px;
  background: #fafcff;
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: slideDown 0.2s ease-out;
}
@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 800px; }
}
</style>
