<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    direction="rtl"
    size="360px"
    title="对话历史"
  >
    <div class="conv-drawer">
      <el-button type="primary" size="small" style="width: 100%; margin-bottom: 16px;" @click="handleNew">
        新建对话
      </el-button>
      <div v-if="store.conversations.length === 0" class="conv-empty">
        暂无历史对话
      </div>
      <div v-else class="conv-list">
        <div
          v-for="conv in store.conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === store.conversationId }"
          @click="handleLoad(conv.id)"
        >
          <div class="conv-info">
            <div class="conv-title">{{ conv.title || '新对话' }}</div>
            <div class="conv-preview">{{ conv.last_message || '无消息' }}</div>
            <div class="conv-meta">{{ conv.message_count }} 条消息 · {{ formatTime(conv.updated_at) }}</div>
          </div>
          <el-button
            text size="small"
            :icon="Delete"
            @click.stop="handleDelete(conv.id)"
          />
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'

defineProps<{ modelValue: boolean }>()
defineEmits<{ 'update:modelValue': [val: boolean] }>()

const store = useChatStore()

onMounted(() => {
  store.fetchConversations()
})

function handleNew() {
  store.newConversation()
}

async function handleLoad(id: string) {
  await store.loadConversation(id)
}

async function handleDelete(id: string) {
  await store.deleteConversation(id)
}

function formatTime(t: string | null) {
  if (!t) return ''
  try {
    const d = new Date(t)
    const now = new Date()
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.conv-drawer { padding: 0 4px; }
.conv-empty {
  text-align: center; color: var(--el-text-color-secondary);
  padding: 40px 0; font-size: 14px;
}
.conv-list { display: flex; flex-direction: column; gap: 8px; }
.conv-item {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 10px 12px; border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  cursor: pointer; transition: all 0.2s;
}
.conv-item:hover { background: var(--el-fill-color-light); }
.conv-item.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.conv-info { flex: 1; min-width: 0; }
.conv-title {
  font-size: 14px; font-weight: 500; color: var(--el-text-color-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.conv-preview {
  font-size: 12px; color: var(--el-text-color-secondary);
  margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.conv-meta { font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 4px; }
</style>
