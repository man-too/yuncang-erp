<template>
  <div class="step-placeholder">
    <el-card shadow="hover">
      <el-result icon="info" :title="title" sub-title="此功能正在开发中，敬请期待">
        <template #extra>
          <el-tag type="info" size="large">Coming Soon</el-tag>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

const store = usePurchaseDecisionStore()
const title = computed(() => store.stepLabels[store.currentStep] || '')
</script>

<style scoped>
.step-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 320px;
}
</style>
