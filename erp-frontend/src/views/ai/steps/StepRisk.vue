<template>
  <div class="step-risk" v-loading="loading">
    <!-- Weather Summary Card -->
    <div v-if="weatherText" class="weather-card">
      <div class="weather-icon">
        <el-icon :size="28"><Cloudy /></el-icon>
      </div>
      <div class="weather-info">
        <div class="weather-title">外部环境 — 天气概况</div>
        <div class="weather-text">{{ weatherText }}</div>
      </div>
    </div>

    <!-- KPI Metric Cards -->
    <div v-if="kpiData" class="kpi-row">
      <el-card class="kpi-card" shadow="hover">
        <div class="kpi-icon"><el-icon :size="22"><Clock /></el-icon></div>
        <div class="kpi-content">
          <div class="kpi-label">周转天数</div>
          <div class="kpi-value">{{ kpiData.turnover_days ?? '—' }}<span class="kpi-unit">天</span></div>
        </div>
      </el-card>
      <el-card class="kpi-card" shadow="hover">
        <div class="kpi-icon kpi-icon--warning"><el-icon :size="22"><Box /></el-icon></div>
        <div class="kpi-content">
          <div class="kpi-label">呆滞品数</div>
          <div class="kpi-value">{{ kpiData.dead_stock_count ?? '—' }}<span class="kpi-unit">项</span></div>
        </div>
      </el-card>
      <el-card class="kpi-card" shadow="hover">
        <div class="kpi-icon kpi-icon--danger"><el-icon :size="22"><Money /></el-icon></div>
        <div class="kpi-content">
          <div class="kpi-label">资金占用</div>
          <div class="kpi-value">{{ formatCurrency(kpiData.capital_occupied) }}<span class="kpi-unit">元</span></div>
        </div>
      </el-card>
    </div>

    <!-- Risk Matrix Table -->
    <div v-if="riskMatrix.length > 0" class="matrix-section">
      <div class="section-row">
        <span class="section-title">风险矩阵</span>
        <el-button size="small" @click="runAudit" :loading="loading">重新审核</el-button>
      </div>
      <div class="filter-row">
        <span class="filter-label">风险类型筛选：</span>
        <el-checkbox-group v-model="selectedCategories" size="small">
          <el-checkbox label="供应商风险" value="供应商风险" />
          <el-checkbox label="库存风险" value="库存风险" />
          <el-checkbox label="需求风险" value="需求风险" />
        </el-checkbox-group>
      </div>
      <el-table
        :data="filteredRiskMatrix"
        stripe
        size="small"
        border
        max-height="360"
        class="risk-table"
      >
        <el-table-column prop="category" label="类别" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="categoryTagType(row.category)" size="small" effect="plain">
              {{ row.category }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="item" label="风险项" min-width="180" show-overflow-tooltip />
        <el-table-column prop="probability" label="概率" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.probability)" size="small">{{ row.probability }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="impact" label="影响" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.impact)" size="small">{{ row.impact }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="mitigability" label="可缓解" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.mitigability, true)" size="small">{{ row.mitigability }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="分" width="70" align="center" sortable>
          <template #default="{ row }">
            <span :class="scoreClass(row.score)">{{ row.score }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="建议" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>

    <!-- Product Risk Details -->
    <div v-if="productRisks.length > 0" class="product-risk-section">
      <h4 class="section-title">产品风险详情</h4>
      <el-table
        :data="productRisks"
        stripe
        size="small"
        border
        max-height="320"
      >
        <el-table-column prop="product_name" label="产品名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="stock_risk" label="库存风险" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.stock_risk)" size="small">{{ row.stock_risk }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="supplier_risk" label="供应商风险" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.supplier_risk)" size="small">{{ row.supplier_risk }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_qty" label="当前库存" width="100" align="right" />
        <el-table-column prop="rop" label="再订货点" width="100" align="right" />
        <el-table-column prop="supplier_name" label="供应商" min-width="120" show-overflow-tooltip />
      </el-table>
    </div>

    <!-- Empty state when no audit result yet -->
    <el-empty
      v-if="riskMatrix.length === 0 && productRisks.length === 0 && !loading && !kpiData"
      description="暂无风险审核数据，点击下方按钮开始审核"
      :image-size="80"
    />

    <!-- Overall Risk Level -->
    <div v-if="overallRisk" class="overall-section">
      <div class="overall-label">整体风险等级</div>
      <div class="overall-badge" :class="overallRiskClass">
        {{ overallRisk }}
      </div>
    </div>

    <!-- AI Action Suggestion -->
    <el-alert
      v-if="actionSuggestion"
      :title="actionSuggestion"
      :type="actionAlertType"
      :closable="false"
      show-icon
    />

    <!-- Navigation -->
    <div class="nav-buttons">
      <el-button @click="store.prevStep()">上一步：供应商匹配</el-button>
      <el-button
        type="primary"
        :disabled="!auditResult"
        @click="store.nextStep()"
      >
        下一步：汇总确认 →
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Cloudy, Clock, Box, Money } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { aiApi } from '@/api'

const store = usePurchaseDecisionStore()
const loading = ref(false)

// ----- Risk type filter -----
const selectedCategories = ref<string[]>(['供应商风险', '库存风险', '需求风险'])

// ----- Computed from store.auditResult -----

const auditResult = computed(() => store.auditResult)

const riskMatrix = computed(() => {
  const res = auditResult.value
  if (!res || !Array.isArray(res.risk_matrix)) return []
  return res.risk_matrix
})

const filteredRiskMatrix = computed(() => {
  if (selectedCategories.value.length === 0) return riskMatrix.value
  return riskMatrix.value.filter((row: any) => selectedCategories.value.includes(row.category))
})

const overallRisk = computed(() => {
  const res = auditResult.value
  if (!res) return null
  return res.overall_risk || null
})

const actionSuggestion = computed(() => {
  const res = auditResult.value
  if (!res) return null
  return res.action || null
})

const weatherText = computed(() => {
  const res = auditResult.value
  if (res && res.weather_summary) return res.weather_summary
  return weatherData.value || null
})

const kpiData = computed(() => {
  const res = auditResult.value
  if (!res || !res.kpi) return null
  return res.kpi
})

const productRisks = computed(() => {
  const res = auditResult.value
  if (!res || !Array.isArray(res.product_risks)) return []
  return res.product_risks
})

// ----- Weather data (fallback if not in auditResult) -----

const weatherData = ref<string | null>(null)
const isFetchingWeather = ref(false)

async function fetchWeather() {
  if (isFetchingWeather.value) return
  isFetchingWeather.value = true
  try {
    const res: any = await aiApi.weather({ city: '上海' })
    if (res) {
      // Build a readable summary from the weather response
      if (typeof res === 'string') {
        weatherData.value = res
      } else if (res.summary) {
        weatherData.value = res.summary
      } else if (res.forecast && Array.isArray(res.forecast)) {
        const lines = res.forecast.slice(0, 3).map((d: any) =>
          `${d.date || ''} ${d.weather || d.condition || ''} ${d.temp_high ?? d.high ?? ''}/${d.temp_low ?? d.low ?? ''}°C`
        )
        weatherData.value = lines.join('；')
      } else if (res.weather || res.condition) {
        weatherData.value = `${res.city || '上海'}：${res.weather || res.condition}，${res.temperature ?? res.temp ?? ''}°C`
      }
    }
  } catch {
    // Weather is optional, silently ignore
  } finally {
    isFetchingWeather.value = false
  }
}

// ----- Risk audit -----

// P1-11 修复：并发锁防止重复触发
const isAuditing = ref(false)

async function runAudit() {
  if (isAuditing.value) return
  isAuditing.value = true
  loading.value = true
  try {
    const res = await store.fetchAuditPlan()
    if (res) {
      ElMessage.success('风险审核完成')
    } else if (!res) {
      // fetchAuditPlan already shows a warning if items are empty
    }
  } catch {
    ElMessage.warning('风险审核服务暂不可用')
  } finally {
    loading.value = false
    isAuditing.value = false
  }
}

// ----- Tag type helpers -----

const categoryColors: Record<string, string> = {
  '供应商风险': 'warning',
  '需求风险': 'danger',
  '库存风险': '',
  '外部风险': 'info',
  '供应链风险': 'warning',
}

function categoryTagType(category: string): string {
  return categoryColors[category] || ''
}

function levelTagType(level: string, invert = false): string {
  // For probability/impact: 高=danger, 中=warning, 低=success
  // For mitigability (invert=true): 高=success, 中=warning, 低=danger
  const map = invert
    ? { '高': 'success', '中': 'warning', '低': 'danger' } as const
    : { '高': 'danger', '中': 'warning', '低': 'success' } as const
  return map[level as keyof typeof map] || 'info'
}

function riskTagType(level: string): string {
  const map: Record<string, string> = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'success',
  }
  return map[level] || 'info'
}

function formatCurrency(value: number | undefined | null): string {
  if (value == null) return '—'
  return '¥' + value.toLocaleString()
}

function scoreClass(score: number): string {
  if (score >= 8) return 'score-critical'
  if (score >= 5) return 'score-high'
  if (score >= 3) return 'score-medium'
  return 'score-low'
}

const overallRiskClass = computed(() => {
  const r = overallRisk.value
  if (!r) return ''
  if (r === '高' || r === 'high') return 'risk-high'
  if (r === '中' || r === 'medium') return 'risk-medium'
  return 'risk-low'
})

const actionAlertType = computed(() => {
  const r = overallRisk.value
  if (r === '高' || r === 'high') return 'error'
  if (r === '中' || r === 'medium') return 'warning'
  return 'success'
})

// ----- Lifecycle -----

onMounted(async () => {
  // Fetch weather in parallel (non-blocking)
  fetchWeather()
  // Run audit if not already done
  if (!auditResult.value) {
    await runAudit()
  }
})
</script>

<style scoped>
.step-risk {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

/* ----- Weather Card ----- */
.weather-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #e8f4fd, #f0f7ff);
  border: 1px solid #b3d8fd;
  border-radius: 10px;
}
.weather-icon {
  flex-shrink: 0;
  color: #409eff;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #d9ecff;
}
.weather-info {
  flex: 1;
}
.weather-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.weather-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
}

/* ----- Matrix Section ----- */
.matrix-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ----- KPI Cards ----- */
.kpi-row {
  display: flex;
  gap: 16px;
}
.kpi-card {
  flex: 1;
  border-radius: 10px;
}
.kpi-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
}
.kpi-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #ecf5ff;
  color: #409eff;
}
.kpi-icon--warning {
  background: #fdf6ec;
  color: #e6a23c;
}
.kpi-icon--danger {
  background: #fef0f0;
  color: #f56c6c;
}
.kpi-content {
  flex: 1;
  min-width: 0;
}
.kpi-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}
.kpi-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.kpi-unit {
  font-size: 13px;
  font-weight: 400;
  color: #909399;
  margin-left: 4px;
}

/* ----- Product Risk Section ----- */
.product-risk-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.product-risk-section .section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  margin: 0;
}
.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}
.risk-table :deep(.score-critical) {
  color: #c45656;
  font-weight: 700;
}
.risk-table :deep(.score-high) {
  color: #e6a23c;
  font-weight: 600;
}
.risk-table :deep(.score-medium) {
  color: #e6a23c;
}
.risk-table :deep(.score-low) {
  color: #67c23a;
}

/* ----- Overall Risk ----- */
.overall-section {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--border-light);
}
.overall-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.overall-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 24px;
  border-radius: 20px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
}
.overall-badge.risk-high {
  background: #fef0f0;
  color: #c45656;
  border: 2px solid #fbc4c4;
}
.overall-badge.risk-medium {
  background: #fdf6ec;
  color: #e6a23c;
  border: 2px solid #f5dab1;
}
.overall-badge.risk-low {
  background: #f0f9eb;
  color: #67c23a;
  border: 2px solid #c2e7b0;
}

/* ----- Navigation ----- */
.nav-buttons {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}
</style>
