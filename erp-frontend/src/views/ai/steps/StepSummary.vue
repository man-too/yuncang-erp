<template>
  <div class="step-summary">
    <!-- 顶部：确认标题 -->
    <div class="summary-hero">
      <div class="hero-icon"><el-icon color="var(--color-success)"><CircleCheck /></el-icon></div>
      <div class="hero-text">
        <h3>采购计划确认</h3>
        <p>请核对以下采购计划，确认后生成采购订单</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ selectedProducts.length }}</div>
          <div class="stat-label">产品数</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ totalQuantity }}</div>
          <div class="stat-label">采购总量(件)</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value price">¥{{ avgPrice }}</div>
          <div class="stat-label">均价</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card highlight">
          <div class="stat-value price">¥{{ totalAmount }}</div>
          <div class="stat-label">预估总金额</div>
        </div>
      </el-col>
    </el-row>

    <!-- 订单预览表格 -->
    <div class="table-section">
      <h4>采购订单预览</h4>
      <el-table :data="orderItems" stripe size="default" max-height="400" class="order-table">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="product_name" label="产品名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="supplier_name" label="供应商" min-width="140" show-overflow-tooltip />
        <el-table-column prop="quantity" label="采购数量" width="110" align="center" />
        <el-table-column label="单价" width="110" align="right">
          <template #default="{ row }">¥{{ row.unit_price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">
            <span class="amount-cell">¥{{ row.total.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 底部合计与操作 -->
    <div class="summary-footer">
      <div class="footer-totals">
        <div class="total-row">
          <span class="total-label">合计产品</span>
          <span class="total-num">{{ selectedProducts.length }} 项</span>
        </div>
        <div class="total-row">
          <span class="total-label">合计数量</span>
          <span class="total-num">{{ totalQuantity }} 件</span>
        </div>
        <div class="total-row emphasis">
          <span class="total-label">采购总金额</span>
          <span class="total-num">¥{{ totalAmount }}</span>
        </div>
      </div>
      <div class="footer-actions">
        <el-button size="large" @click="store.prevStep()">◀ 返回修改</el-button>
        <el-button size="large" type="primary" @click="onConfirm" :loading="submitting" :disabled="orderItems.length === 0">
          确认生成采购订单
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { purchaseApi } from '@/api'

const store = usePurchaseDecisionStore()
const submitting = ref(false)

const selectedProducts = computed(() => store.allProducts)

const totalQuantity = computed(() => {
  return Object.values(store.forecastQuantities).reduce((a, b) => a + (b || 0), 0)
})

const totalAmount = computed(() => {
  return orderItems.value.reduce((s, item) => s + item.total, 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
})

const avgPrice = computed(() => {
  if (orderItems.value.length === 0) return '0.00'
  const avg = orderItems.value.reduce((s, i) => s + i.unit_price, 0) / orderItems.value.length
  return avg.toFixed(2)
})

const orderItems = computed(() => {
    const items: any[] = []
    for (const p of store.allProducts) {
      const qty = store.quantities[p.product_id] || store.suggestedQtys[p.product_id]?.suggested_qty || p.suggested_qty || 0
      if (qty <= 0) continue
      const price = store.forecastPrices[p.product_id] || p.purchase_price || 0

      // Check if we have per-supplier quantity allocation
      const allocations = store.supplierQuantities[p.product_id]
      if (allocations && Object.keys(allocations).length > 0) {
        for (const [sid, allocQty] of Object.entries(allocations)) {
          if ((allocQty as number) <= 0) continue
          const supplier = store.supplierInfo[Number(sid)]
          items.push({
            product_id: p.product_id,
            product_name: p.product_name,
            supplier_id: Number(sid),
            supplier_name: supplier?.name || supplier?.supplier_name || `供应商#${sid}`,
            quantity: allocQty as number,
            unit_price: price,
            total: (allocQty as number) * price,
          })
        }
      } else {
        // Fallback: use supplierChoices
        const supplierIds = store.supplierChoices[p.product_id] || []
        if (supplierIds.length === 0) {
          items.push({
            product_id: p.product_id,
            product_name: p.product_name,
            supplier_id: 1,
            supplier_name: '未指定',
            quantity: qty,
            unit_price: price,
            total: qty * price,
          })
        } else {
          for (const sid of supplierIds) {
            const supplier = store.supplierInfo[sid]
            items.push({
              product_id: p.product_id,
              product_name: p.product_name,
              supplier_id: sid,
              supplier_name: supplier?.name || supplier?.supplier_name || `供应商#${sid}`,
              quantity: qty,
              unit_price: price,
              total: qty * price,
            })
          }
        }
      }
    }
    return items
  })

async function onConfirm() {
  if (orderItems.value.length === 0) {
    ElMessage.warning('请至少选择一个产品')
    return
  }
  submitting.value = true
  try {
    // Group items by supplier_id to create separate orders per supplier
    const bySupplier: Record<number, any[]> = {}
    for (const item of orderItems.value) {
      if (!bySupplier[item.supplier_id]) bySupplier[item.supplier_id] = []
      bySupplier[item.supplier_id].push(item)
    }

    for (const [supplierId, items] of Object.entries(bySupplier)) {
      const orderData = {
        supplier_id: Number(supplierId),
        items: items.map(item => ({
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: item.unit_price,
        })),
        remark: '由AI采购决策生成',
      }
      await purchaseApi.create(orderData)
    }
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
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

/* 顶部 Hero */
.summary-hero {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, var(--color-info-bg), #E8F0F6);
  border-radius: 12px;
  border: 1px solid #d0e8f7;
}
.hero-icon {
  font-size: 48px;
  line-height: 1;
}
.hero-text h3 {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.hero-text p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

/* 统计卡片 */
.stats-row {
  margin: 0 !important;
}
.stat-card {
  text-align: center;
  padding: 16px 8px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: box-shadow 0.2s;
}
.stat-card:hover {
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
.stat-card.highlight {
  background: var(--color-danger-bg);
  border-color: var(--color-danger-light);
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}
.stat-value.price {
  color: var(--color-danger);
}
.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* 表格 */
.table-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.table-section h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.order-table :deep(.amount-cell) {
  font-weight: 600;
  color: var(--color-danger);
}

/* 底部 */
.summary-footer {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding: 20px 24px;
  background: var(--bg-page);
  border-radius: 12px;
  border: 1px solid var(--border-light);
}
.footer-totals {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.total-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.total-label {
  font-size: 14px;
  color: #606266;
  min-width: 80px;
  text-align: right;
}
.total-num {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.total-row.emphasis .total-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.total-row.emphasis .total-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-danger);
}
.footer-actions {
  display: flex;
  gap: 10px;
}
</style>
