<template>
  <div class="ai-decision-layout">
    <!-- 左侧：聊天面板 -->
    <div class="chat-panel">
      <DecisionChat @panel-focus="handlePanelFocus" />
      <!-- 右上角浮动按钮组 -->
      <div class="top-right-btns">
        <div v-if="purchaseStore.isExpanded && purchaseStore.isCollapsed" class="float-btn" @click="purchaseStore.expand()" title="展开采购决策">
          <el-icon :size="16"><Right /></el-icon>
        </div>
        <div class="float-btn" @click="showConvDrawer = true" title="对话历史">
          <el-icon :size="18"><ChatDotRound /></el-icon>
        </div>
      </div>
    </div>

    <!-- 右侧：采购决策向导 -->
    <transition name="slide-right">
      <div v-if="purchaseStore.isExpanded && !purchaseStore.isCollapsed" class="wizard-panel">
        <PurchaseDecisionWizard @close="purchaseStore.close()" />
      </div>
    </transition>

    <!-- 对话历史抽屉 -->
    <ConversationDrawer v-model="showConvDrawer" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ChatDotRound, Right } from '@element-plus/icons-vue'
import PurchaseDecisionWizard from '@/views/ai/PurchaseDecisionWizard.vue'
import DecisionChat from '@/views/ai/DecisionChat.vue'
import ConversationDrawer from '@/views/ai/ConversationDrawer.vue'
import { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

defineOptions({ name: 'AIDecision' })

const purchaseStore = usePurchaseDecisionStore()
const showConvDrawer = ref(false)

const handlePanelFocus = (type: string) => {
  if (type === 'purchase_advice') {
    purchaseStore.isExpanded = true
    purchaseStore.isCollapsed = false
  }
}
</script>

<style scoped>
.ai-decision-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 120px);
  min-height: 500px;
  position: relative;
}
.chat-panel {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow-y: auto;
}
.wizard-panel {
  width: 50%;
  flex-shrink: 0;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
}

/* 滑入动画 */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  width: 0;
  opacity: 0;
  margin-right: -16px;
  overflow: hidden;
}

/* 右上角浮动按钮组 */
.top-right-btns {
  position: absolute;
  right: 12px;
  top: 12px;
  display: flex;
  gap: 8px;
  z-index: 5;
}
.float-btn {
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
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.float-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
</style>
