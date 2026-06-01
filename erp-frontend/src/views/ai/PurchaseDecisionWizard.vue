<template>
  <el-card shadow="never" class="wizard-card">
    <div class="wizard-header">
      <div class="wizard-title">
        <span style="font-size: 18px; font-weight: 600;">🚀 采购决策生成</span>
        <span class="wizard-subtitle">逐步完成采购计划</span>
      </div>
      <el-button text @click="$emit('close')">✕ 关闭</el-button>
    </div>

    <!-- 进度条 -->
    <el-steps :active="store.currentStep" finish-status="success" align-center style="margin: 16px 0 24px;">
      <el-step v-for="(label, i) in store.stepLabels" :key="i" :title="label" />
    </el-steps>

    <!-- 左右分栏内容 -->
    <div class="wizard-body">
      <!-- 左侧图表 -->
      <div class="left-panel">
        <component :is="currentChartComp" />
      </div>

      <!-- 右侧操作 -->
      <div class="right-panel">
        <component :is="currentTableComp" />
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

// Use components: step containers render both chart + table in their slot
import StepInventory from './steps/StepInventory.vue'
import StepSummary from './steps/StepSummary.vue'

const emit = defineEmits<{ close: [] }>()
const store = usePurchaseDecisionStore()

// Simplified for Phase 2: Step0 = Inventory, Step4 = Summary
// Steps 1-3 render the chart/table from the same component
const currentChartComp = computed(() => {
  switch (store.currentStep) {
    case 0: return StepInventory
    default: return StepInventory
  }
})

const currentTableComp = computed(() => {
  switch (store.currentStep) {
    case 4: return StepSummary
    default: return StepInventory
  }
})
</script>

<style scoped>
.wizard-card {
  border: 1px solid #409eff;
  border-radius: 12px;
  overflow: visible;
}
.wizard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 4px;
  border-bottom: 1px solid #ebeef5;
}
.wizard-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.wizard-subtitle {
  font-size: 13px;
  color: #909399;
}
.wizard-body {
  display: flex;
  gap: 20px;
  min-height: 420px;
}
.left-panel {
  flex: 1;
  min-width: 0;
}
.right-panel {
  width: 440px;
  flex-shrink: 0;
}
</style>
