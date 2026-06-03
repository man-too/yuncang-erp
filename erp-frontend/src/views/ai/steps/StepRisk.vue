<template>
  <div class="step-risk" v-loading="loading">
    <!-- 上部: AI 风险分析汇总 -->
    <div class="summary-section">
      <el-alert
        v-if="summaryText"
        :title="'AI 风险评估汇总'"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="summary-text">{{ summaryText }}</div>
        </template>
      </el-alert>
      <el-alert
        v-else-if="!loading && store.allProducts.length > 0"
        title="暂无风险评估数据，请稍后重试"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <!-- 中部: 产品风险卡片列表 -->
    <div v-if="groups.length > 0" class="risk-groups">
      <div v-for="group in groups" :key="group.level" class="risk-group">
        <div class="group-header">
          <el-tag :type="group.tagType" size="default">
            {{ group.label }}
          </el-tag>
          <span class="group-count">{{ group.items.length }} 项</span>
        </div>
        <div class="group-cards">
          <el-card
            v-for="product in group.items"
            :key="product.product_id"
            class="risk-card"
            shadow="hover"
          >
            <div class="card-content">
              <div class="card-left">
                <div class="product-name">{{ product.product_name }}</div>
                <div class="product-code">{{ product.product_code }}</div>
              </div>
              <div class="card-center">
                <div class="info-row">
                  <span class="info-label">当前库存</span>
                  <span class="info-value">{{ product.current_qty }} {{ product.unit }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">日均销量</span>
                  <span class="info-value">
                    {{ dailySales(product) }} {{ product.unit }}/天
                  </span>
                </div>
                <div class="info-row">
                  <span class="info-label">缺货天数</span>
                  <span class="info-value" :class="shortageDaysClass(product)">
                    {{ shortageDays(product) ?? '—' }}
                    <template v-if="shortageDays(product) !== null"> 天</template>
                  </span>
                </div>
              </div>
              <div class="card-right">
                <el-tag :type="group.tagType" size="small">
                  {{ group.label }}
                </el-tag>
                <div class="score" v-if="riskScore(product.product_id)">
                  风险评分: {{ riskScore(product.product_id) }}
                </div>
                <el-button
                  type="danger"
                  link
                  size="small"
                  @click="onRemove(product.product_id)"
                >
                  移除
                </el-button>
              </div>
            </div>
            <div
              v-if="riskReason(product.product_id)"
              class="card-reason"
            >
              {{ riskReason(product.product_id) }}
            </div>
          </el-card>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-if="!loading && store.allProducts.length === 0"
      description="暂未选择产品，请返回上一步添加"
      :image-size="80"
    />

    <!-- 下部: 上一步/下一步按钮 -->
    <div class="nav-buttons">
      <el-button @click="store.prevStep()">上一步：库存分析</el-button>
      <el-button
        type="primary"
        :disabled="store.allProducts.length === 0"
        @click="store.nextStep()"
      >
        下一步：供应商匹配 →
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { aiApi } from '@/api'

const store = usePurchaseDecisionStore()
const loading = ref(false)

// ----- 风险等级定义 -----

const riskLevelOrder: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
}

const riskLevelLabels: Record<string, string> = {
  critical: '严重风险',
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}

const riskLevelTagTypes: Record<string, string> = {
  critical: 'danger',
  high: 'warning',
  medium: '',
  low: 'success',
}

// ----- 加载风险评估 -----

async function fetchRiskAssessment() {
  if (store.allProducts.length === 0) return

  const productIds = store.allProducts.map(p => p.product_id)
  const existingIds = Object.keys(store.riskResults).map(Number)
  const missingIds = productIds.filter(id => !existingIds.includes(id))

  if (missingIds.length === 0) return

  loading.value = true
  try {
    const res: any = await aiApi.stockAlertBatch({ product_ids: productIds })
    if (res && res.results) {
      for (const item of res.results) {
        store.riskResults[item.product_id] = {
          level: item.risk_level || 'low',
          score: item.risk_score ?? 0,
          reason: item.reason || '',
          daily_sales: item.daily_sales ?? 0,
          shortage_days: item.shortage_days ?? 0,
        }
      }
      ElMessage.success(`已完成 ${res.results.length} 项风险评估`)
    }
  } catch {
    ElMessage.warning('风险评估服务暂不可用，请稍后重试')
  } finally {
    loading.value = false
  }
}

// ----- 数据读取 -----

function riskInfo(productId: number) {
  return store.riskResults[productId]
}

function dailySales(product: { product_id: number; daily_sales_avg: number }) {
  const info = riskInfo(product.product_id)
  return info?.daily_sales ?? product.daily_sales_avg ?? 0
}

function shortageDays(product: { product_id: number }): number | null {
  const info = riskInfo(product.product_id)
  if (!info || info.shortage_days === undefined || info.shortage_days === null) return null
  return info.shortage_days
}

function riskScore(productId: number): number | null {
  const info = riskInfo(productId)
  if (!info || info.score === undefined || info.score === null) return null
  return info.score
}

function riskReason(productId: number): string | null {
  const info = riskInfo(productId)
  if (!info || !info.reason) return null
  return info.reason
}

function shortageDaysClass(product: { product_id: number }) {
  const days = shortageDays(product)
  if (days === null) return ''
  if (days <= 3) return 'text-danger'
  if (days <= 7) return 'text-warning'
  return 'text-success'
}

// ----- 按风险等级分组 -----

const groups = computed(() => {
  const map: Record<string, any[]> = {
    critical: [],
    high: [],
    medium: [],
    low: [],
  }

  for (const product of store.allProducts) {
    const info = riskInfo(product.product_id)
    const level = info?.level || 'low'
    if (map[level]) {
      map[level].push(product)
    } else {
      map.low.push(product)
    }
  }

  return Object.entries(map)
    .filter(([, items]) => items.length > 0)
    .sort(([a], [b]) => riskLevelOrder[a] - riskLevelOrder[b])
    .map(([level, items]) => ({
      level,
      label: riskLevelLabels[level] || level,
      tagType: riskLevelTagTypes[level] || '',
      items,
    }))
})

// ----- AI 汇总文本 -----

const summaryText = computed(() => {
  const results = store.riskResults
  if (!results || Object.keys(results).length === 0) return ''

  let criticalCount = 0
  let highCount = 0
  let mediumCount = 0
  let lowCount = 0

  for (const product of store.allProducts) {
    const info = riskInfo(product.product_id)
    const level = info?.level
    if (level === 'critical') criticalCount++
    else if (level === 'high') highCount++
    else if (level === 'medium') mediumCount++
    else lowCount++
  }

  const parts: string[] = []
  if (criticalCount > 0) parts.push(`${criticalCount} 项严重风险`)
  if (highCount > 0) parts.push(`${highCount} 项高风险`)
  if (mediumCount > 0) parts.push(`${mediumCount} 项中风险`)
  if (lowCount > 0) parts.push(`${lowCount} 项低风险`)

  return `已对 ${store.allProducts.length} 个产品完成风险评估：${parts.join('，')}。请优先处理严重风险项，考虑调整安全库存或寻找替代供应商。`
})

// ----- 移除产品 -----

function onRemove(productId: number) {
  store.removeProduct(productId)
  delete store.riskResults[productId]
}

// ----- 生命周期 -----

onMounted(() => {
  fetchRiskAssessment()
})
</script>

<style scoped>
.step-risk {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

/* ----- 上部: 汇总 ----- */
.summary-section {
  min-height: 40px;
}

.summary-text {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 13px;
}

/* ----- 中部: 风险卡片 ----- */
.risk-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.group-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.group-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.risk-card {
  border: 1px solid var(--border-light);
  border-radius: 8px;
}

.risk-card :deep(.el-card__body) {
  padding: 14px 16px;
}

.card-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.card-left {
  min-width: 140px;
  flex-shrink: 0;
}

.product-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.product-code {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.card-center {
  flex: 1;
  display: flex;
  gap: 20px;
}

.info-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.text-danger {
  color: var(--color-danger);
  font-weight: 600;
}

.text-warning {
  color: var(--color-warning);
  font-weight: 600;
}

.text-success {
  color: var(--color-success);
}

.card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.score {
  font-size: 11px;
  color: var(--text-secondary);
}

.card-reason {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-light);
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

/* ----- 下部: 导航按钮 ----- */
.nav-buttons {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}
</style>
