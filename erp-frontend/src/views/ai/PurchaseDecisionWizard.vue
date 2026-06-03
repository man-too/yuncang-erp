<template>
  <el-card shadow="never" class="wizard-card">
    <div class="wizard-header">
      <div class="wizard-title">
        <span style="font-size: 18px; font-weight: 600;">采购决策生成</span>
        <span class="wizard-subtitle">逐步完成采购计划</span>
      </div>
      <el-button text @click="$emit('close')">✕ 关闭</el-button>
    </div>

    <!-- 进度条 -->
    <el-steps :active="store.currentStep" finish-status="success" align-center style="margin: 16px 0 24px;">
      <el-step v-for="(label, i) in store.stepLabels" :key="i" :title="label" />
    </el-steps>

    <!-- 单组件内容区 -->
    <div class="wizard-body">
      <component :is="currentStepComp" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import StepInventory from './steps/StepInventory.vue'
import StepRisk from './steps/StepRisk.vue'
import StepSupplier from './steps/StepSupplier.vue'
import StepForecast from './steps/StepForecast.vue'
import StepSummary from './steps/StepSummary.vue'

defineEmits<{ close: [] }>()
const store = usePurchaseDecisionStore()

const currentStepComp = computed(() => {
  switch (store.currentStep) {
    case 0: return StepInventory
    case 1: return StepRisk
    case 2: return StepSupplier
    case 3: return StepForecast
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
  border-bottom: 1px solid var(--border-light);
}
.wizard-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.wizard-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}
.wizard-body {
  min-height: 420px;
  width: 100%;
}
</style>
