<template>
  <div class="wizard-expand-btn" @click="purchaseStore.expand()">
    <el-icon :size="16"><Right /></el-icon>
  </div>
</template>

<script setup lang="ts">
import { Right } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

const purchaseStore = usePurchaseDecisionStore()
</script>

<style scoped>
.wizard-expand-btn {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  cursor: pointer;
  transition: all 0.2s;
  z-index: 5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.wizard-expand-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
</style>
