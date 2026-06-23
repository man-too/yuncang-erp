<template>
  <div class="decision-chat">
    <!-- 消息区域 -->
    <div class="chat-msgs" ref="msgContainer">
      <ChatWelcome
        v-if="store.isNewConversation && store.messages.length === 0 && !store.isLoading"
        @quick-action="handleQuickAction"
      />
      <template v-else-if="store.messages.length > 0 || store.isLoading">
        <ChatMessage
          v-for="msg in store.messages" :key="msg.id"
          :role="msg.role"
          :content="msg.content"
          :blocks="msg.blocks"
          :message-id="msg.id"
          @confirm="handleConfirm"
          @cancel="handleCancel"
          @retry="handleRetry"
        />
        <div v-if="store.isLoading" class="typing-bubble">
          <div class="typing-avatar">AI</div>
          <div class="typing-dots"><span /><span /><span /></div>
        </div>
      </template>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input">
      <el-input
        v-model="inputText"
        type="textarea" :rows="2"
        placeholder="输入问题，如「分析库存风险」「对比供应商」..."
        resize="none"
        @compositionstart="isComposing = true"
        @compositionend="isComposing = false"
        @keydown.enter.exact.prevent="onEnterKey"
      />
      <div class="input-footer">
        <div class="input-left">
          <el-popover placement="top-start" :width="260" trigger="click">
            <template #reference>
              <el-button text size="small" :icon="Plus">快捷</el-button>
            </template>
            <QuickActions @quick-action="handleQuickAction" />
          </el-popover>
          <el-button text size="small" @click="handleOrderAssist" class="order-assist-btn">
            <el-icon><ShoppingCart /></el-icon> 帮我下单
          </el-button>
        </div>
        <div class="input-right">
          <el-button text size="small" @click="store.clearSession()" :disabled="store.messages.length === 0">
            清空
          </el-button>
          <el-button type="primary" size="small" @click="handleSend" :loading="store.isLoading" :disabled="!inputText.trim()">
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { Plus, ShoppingCart } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import ChatMessage from './ChatMessage.vue'
import ChatWelcome from './ChatWelcome.vue'
import QuickActions from './QuickActions.vue'

const emit = defineEmits<{ panelFocus: [type: string] }>()
const store = useChatStore()
const inputText = ref('')
const isComposing = ref(false)
const msgContainer = ref<HTMLElement>()

function scrollToBottom() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
}

watch(() => store.messages.length, () => {
  scrollToBottom()
  nextTick(() => {
    window.dispatchEvent(new Event('resize'))
  })
})

function onEnterKey() {
  if (isComposing.value) return
  handleSend()
}

async function handleSend() {
  if (!inputText.value.trim() || store.isLoading) return
  const text = inputText.value.trim()
  inputText.value = ''
  await store.sendMessage(text)
  scrollToBottom()
}

function handleQuickAction(payload: { type: string; prompt: string }) {
  emit('panelFocus', payload.type)
  store.sendQuickAction(payload.type, payload.prompt)
}

function handleOrderAssist() {
  emit('panelFocus', 'purchase_advice')
}

function handleConfirm(messageId: string, bi: number, ai: number) {
  const msg = store.messages.find(m => m.id === messageId)
  const block = msg?.blocks[bi]
  const action = block?.actions?.[ai]
  if (!action) return
  store.executeAction(action.action, action.params, messageId, bi, ai)
}

function handleCancel(_mid: string, _bi: number, _ai: number) {}

async function handleRetry(messageId: string, bi: number, ai: number) {
  const msg = store.messages.find(m => m.id === messageId)
  const block = msg?.blocks[bi]
  const action = block?.actions?.[ai]
  if (!action) return
  await store.executeAction(action.action, action.params, messageId, bi, ai)
}

onMounted(() => {
  if (store.messages.length === 0 && !store.isNewConversation) {
    store.initConversation()
  }
})
</script>

<style scoped>
.decision-chat {
  display: flex; flex-direction: column;
  height: 100%;
  border: 1px solid var(--el-border-color-lighter); border-radius: 12px;
  overflow: hidden; background: var(--el-bg-color);
}
.chat-msgs {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 14px;
  scrollbar-gutter: stable;
}
.chat-input {
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
.input-left {
  display: flex;
  gap: 8px;
}
.input-right {
  display: flex;
  gap: 8px;
}

.typing-bubble { display: flex; gap: 10px; align-self: flex-start; }
.typing-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #005BF5, #2e7bff);
}
.typing-dots {
  display: flex; gap: 4px; align-items: center;
  padding: 12px 16px; border-radius: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.typing-dots span {
  width: 7px; height: 7px; border-radius: 50%; background: var(--el-text-color-secondary);
  animation: dot-bounce 1.4s infinite ease-in-out both;
}
.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); }
  40% { transform: scale(1); }
}
.order-assist-btn {
  font-size: 14px;
}
.order-assist-btn .el-icon {
}
</style>
