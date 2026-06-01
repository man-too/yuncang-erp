<template>
  <div class="step-summary">
    <!-- Left: Summary overview -->
    <div class="summary-left">
      <div style="text-align: center; padding: 40px 0;">
        <div style="font-size: 48px;">✅</div>
        <h3>采购计划确认</h3>
        <p style="color: #909399; font-size: 14px;">请核对以下采购计划，确认后生成采购订单</p>
      </div>

      <el-row :gutter="12" style="margin-top: 12px;">
        <el-col :span="8">
          <el-card shadow="hover" style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold;">{{ selectedProducts.length }}</div>
            <div style="font-size: 12px; color: #909399;">产品数</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold;">{{ totalQuantity }}</div>
            <div style="font-size: 12px; color: #909399;">采购总量</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #f56c6c;">¥{{ totalAmount }}</div>
            <div style="font-size: 12px; color: #909399;">预估金额</div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Right: Order preview table -->
    <div class="summary-right">
      <h4 style="margin: 0 0 12px;">采购订单预览</h4>
      <el-table :data="orderItems" stripe size="small" max-height="360" highlight-current-row>
        <el-table-column prop="product_name" label="产品" min-width="120" />
        <el-table-column prop="quantity" label="数量" width="70" align="right" />
        <el-table-column prop="unit_price" label="单价" width="90" align="right" />
        <el-table-column prop="total" label="金额" width="100" align="right">
          <template #default="{ row }">¥{{ row.total.toFixed(2) }}</template>
        </el-table-column>
      </el-table>

      <div class="summary-actions">
        <el-button @click="store.prevStep()">◀ 返回修改</el-button>
        <el-button type="primary" @click="onConfirm" :loading="submitting" :disabled="orderItems.length === 0">
          ✅ 确认生成采购订单
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { purchaseApi } from '@/api'

const store = usePurchaseDecisionStore()
const submitting = ref(false)

const selectedProducts = computed(() => store.selectedProducts.value)

const totalQuantity = computed(() => {
  return Object.values(store.quantities.value).reduce((a, b) => a + (b || 0), 0)
})

const totalAmount = computed(() => {
  return orderItems.value.reduce((s, item) => s + item.total, 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
})

const orderItems = computed(() => {
  return selectedProducts.value.map(p => ({
    product_id: p.product_id,
    product_name: p.product_name,
    quantity: store.quantities.value[p.product_id] || p.suggested_qty || 0,
    unit_price: p.max_stock > 0 ? Math.round(p.max_stock / p.min_stock * 100) / 100 : 0,
    total: (store.quantities.value[p.product_id] || 0) * (p.max_stock > 0 ? Math.round(p.max_stock / p.min_stock * 100) / 100 : 0),
  })).filter(item => item.quantity > 0)
})

async function onConfirm() {
  if (orderItems.value.length === 0) {
    ElMessage.warning('请至少选择一个产品')
    return
  }
  submitting.value = true
  try {
    // Create purchase order using the first product's qty as sample (simplified)
    const orderData = {
      supplier_id: 1,
      items: orderItems.value.map(item => ({
        product_id: item.product_id,
        quantity: item.quantity,
        unit_price: item.unit_price,
      })),
      remark: '由AI采购决策生成',
    }
    await purchaseApi.create(orderData)
    ElMessage.success('采购订单已创建成功！')
    store.close()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建订单失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.step-summary {
  display: flex;
  gap: 20px;
  height: 100%;
}
.summary-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}
.summary-right {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.summary-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
