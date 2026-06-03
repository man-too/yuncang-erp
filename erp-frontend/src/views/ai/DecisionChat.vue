<!-- 统一对话助手 -->
<template>
  <div class="decision-chat">
    <!-- 消息列表 -->
    <div class="chat-msgs" ref="msgContainer">
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
      <!-- 加载动画 -->
      <div v-if="store.isLoading" class="typing-bubble">
        <div class="typing-avatar">AI</div>
        <div class="typing-dots"><span /><span /><span /></div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input">
      <el-input
        v-model="inputText"
        type="textarea" :rows="2"
        placeholder="输入问题，如「分析库存风险」「对比供应商」..."
        resize="none"
        @keydown.enter.exact.prevent="handleSend"
      />
      <div class="input-footer">
        <el-button text size="small" @click="store.clearSession()" :disabled="store.messages.length === 0">
          清空对话
        </el-button>
        <el-button type="primary" @click="handleSend" :loading="store.isLoading" :disabled="!inputText.trim()">
          发送
        </el-button>
      </div>
    </div>

    <!-- 快捷操作 -->
    <QuickActions @quick-action="handleQuickAction" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import ChatMessage from './ChatMessage.vue'
import QuickActions from './QuickActions.vue'

const emit = defineEmits<{ panelFocus: [type: string] }>()
const store = useChatStore()
const inputText = ref('')
const msgContainer = ref<HTMLElement>()

function scrollToBottom() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
}

watch(() => store.messages.length, scrollToBottom)

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

function handleConfirm(messageId: string, bi: number, ai: number) {
  const msg = store.messages.find(m => m.id === messageId)
  const block = msg?.blocks[bi]
  const action = block?.actions?.[ai]
  if (!action) return
  // 直接执行，不弹窗（按用户要求内联确认）
  store.executeAction(action.action, action.params, messageId, bi, ai)
}

function handleCancel(_mid: string, _bi: number, _ai: number) {
  // 可以标记为已取消，当前不做处理
}

async function handleRetry(messageId: string, bi: number, ai: number) {
  const msg = store.messages.find(m => m.id === messageId)
  const block = msg?.blocks[bi]
  const action = block?.actions?.[ai]
  if (!action) return
  await store.executeAction(action.action, action.params, messageId, bi, ai)
}

onMounted(() => {
  store.initConversation()
})
</script>

<style scoped>
.decision-chat {
  display: flex; flex-direction: column;
  height: calc(100vh - 180px); min-height: 600px;
  border: 1px solid var(--border-color); border-radius: 12px;
  overflow: hidden; background: var(--bg-card);
}
.chat-msgs {
  flex: 1; overflow-y: auto; padding: var(--spacing-lg);
  display: flex; flex-direction: column; gap: 14px;
}
.chat-input {
  padding: 12px var(--spacing-lg);
  border-top: 1px solid var(--border-light);
  background: var(--bg-page);
}
.input-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

.typing-bubble { display: flex; gap: 10px; align-self: flex-start; }
.typing-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #1E3A5F, #2A4F7F);
}
.typing-dots {
  display: flex; gap: 4px; align-items: center;
  padding: 12px 16px; border-radius: 12px;
  background: var(--bg-page);
  border: 1px solid var(--border-color);
}
.typing-dots span {
  width: 7px; height: 7px; border-radius: 50%; background: var(--text-secondary);
  animation: dot-bounce 1.4s infinite ease-in-out both;
}
.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); }
  40% { transform: scale(1); }
}
</style>
