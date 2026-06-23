<template>
  <div class="wizard-card">
    <div class="wizard-header">
      <div class="wizard-title">
        <span style="font-size: 16px; font-weight: 600;">采购决策生成</span>
        <span class="wizard-subtitle">{{ store.stepLabels[store.currentStep] }}</span>
      </div>
      <div class="wizard-actions">
        <el-button text size="small" @click="store.collapse()" title="折叠（保留进度）">
          <el-icon><Right /></el-icon>
        </el-button>
        <el-button text size="small" @click="$emit('close')" title="退出（重置进度）">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 进度条 -->
    <el-steps :active="store.currentStep" finish-status="success" align-center style="margin: 12px 0 20px;" size="small">
      <el-step v-for="(label, i) in store.stepLabels" :key="i" :title="label" />
    </el-steps>

    <!-- 步骤内容 -->
    <div class="wizard-body">
      <component :is="currentStepComp" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { Right, Close } from '@element-plus/icons-vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'
import { useChatStore } from '@/stores/chat'
import StepInventory from './steps/StepInventory.vue'
import StepRisk from './steps/StepRisk.vue'
import StepSupplier from './steps/StepSupplier.vue'
import StepSummary from './steps/StepSummary.vue'

defineEmits<{ close: [] }>()

const store = usePurchaseDecisionStore()
const chatStore = useChatStore()

const currentStepComp = computed(() => {
  switch (store.currentStep) {
    case 0: return StepInventory
    case 1: return StepSupplier
    case 2: return StepRisk
    case 3: return StepSummary
    default: return StepInventory
  }
})

// 步骤切换时推送摘要到聊天面板
watch(() => store.currentStep, (newStep, oldStep) => {
  if (oldStep !== newStep) {
    const summary = buildStepSummary(oldStep)
    if (summary) {
      chatStore.pushStepSummary(store.stepLabels[oldStep], summary)
    }
  }
})

function buildStepSummary(step: number): string {
  switch (step) {
    case 0: {
      const total = store.allProducts.length
      const lowStock = store.allProducts.filter(p => p.current_qty < p.min_stock).length
      const outOfStock = store.allProducts.filter(p => p.current_qty === 0).length
      return `已识别 ${total} 个低库存产品，其中 ${lowStock} 项低于安全库存，${outOfStock} 项缺货。`
    }
    case 1: {
      const supplierCount = Object.keys(store.supplierInfo).length
      const allocatedCount = Object.keys(store.supplierQuantities).length
      return `已匹配 ${supplierCount} 家供应商，${allocatedCount} 个产品完成分配。`
    }
    case 2: {
      const riskLevel = store.auditResult?.overall_risk || '未评估'
      return `风险审核完成，整体风险等级：${riskLevel}。`
    }
    case 3: {
      const itemCount = store.allProducts.length
      return `采购方案已确认，共 ${itemCount} 项产品。`
    }
    default:
      return ''
  }
}
</script>

<style scoped>
.wizard-card {
  padding: 16px 20px;
  height: 100%;
  overflow-y: auto;
}
.wizard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.wizard-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.wizard-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.wizard-actions {
  display: flex;
  gap: 4px;
}
.wizard-body {
  min-height: 400px;
  width: 100%;
}
</style>
