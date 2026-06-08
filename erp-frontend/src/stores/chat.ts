/** AI 对话会话状态管理（仅会话内有效，刷新丢失） */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { aiApi } from '@/api'
import { ElMessage } from 'element-plus'

export interface ActionItem {
  label: string
  action: string
  params: Record<string, any>
  confirmTitle: string
  confirmDetail: string
  status?: 'pending' | 'loading' | 'success' | 'error'
  resultMessage?: string
  resultLink?: string
}

export interface MessageBlock {
  type: 'chart' | 'table' | 'actions'
  chartType?: string
  data?: any
  columns?: Array<{ key: string; title: string }>
  rows?: Array<Record<string, any>>
  actions?: ActionItem[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  blocks: MessageBlock[]
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const conversationId = ref('')
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)

  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
    })
  }

  function addMessage(msg: Omit<ChatMessage, 'id' | 'timestamp'>) {
    messages.value.push({
      ...msg,
      id: uuid(),
      timestamp: Date.now(),
    })
  }

  async function sendMessage(content: string) {
    if (!content.trim() || isLoading.value) return

    addMessage({ role: 'user', content, blocks: [] })

    const apiMessages = messages.value
      .filter(m => m.role !== 'system')
      .map(m => ({ role: m.role, content: m.content }))

    isLoading.value = true
    try {
      const res: any = await aiApi.chat({
        messages: apiMessages,
        conversation_id: conversationId.value,
      })
      conversationId.value = res.conversation_id || conversationId.value
      addMessage({
        role: 'assistant',
        content: res.content || 'AI 处理完成，请查看上方图表数据。',
        blocks: (res.blocks || []).map((b: any) => normalizeBlock(b)),
      })
    } catch (e: any) {
      addMessage({ role: 'assistant', content: '抱歉，请求失败，请稍后重试。', blocks: [] })
      ElMessage.error(e?.response?.data?.detail || '对话请求失败')
    } finally {
      isLoading.value = false
    }
  }

  function normalizeBlock(b: any): MessageBlock {
    // Ensure action items have initial status
    if (b.type === 'actions' && b.actions) {
      return {
        ...b,
        actions: b.actions.map((a: ActionItem) => ({
          ...a,
          status: a.status || 'pending',
          confirmTitle: a.confirmTitle || a.label,
          confirmDetail: a.confirmDetail || '',
        })),
      }
    }
    return b
  }

  async function executeAction(action: string, params: Record<string, any>, messageId: string, blockIndex: number, actionIndex: number) {
    const msg = messages.value.find(m => m.id === messageId)
    if (!msg) return
    const block = msg.blocks[blockIndex]
    if (!block || block.type !== 'actions' || !block.actions) return

    const item = block.actions[actionIndex]
    if (!item) return

    item.status = 'loading'
    try {
      const res: any = await aiApi.execute({
        conversation_id: conversationId.value,
        action,
        params,
      })
      if (res.success) {
        item.status = 'success'
        item.resultMessage = res.message
        item.resultLink = res.link
      } else {
        item.status = 'error'
        item.resultMessage = res.message || '执行失败'
      }
    } catch (e: any) {
      item.status = 'error'
      item.resultMessage = e?.response?.data?.detail || '执行失败'
    }
  }

  async function initConversation() {
    if (messages.value.length > 0) return
    isLoading.value = true
    try {
      const res: any = await aiApi.chat({ messages: [], conversation_id: '' })
      conversationId.value = res.conversation_id || ''
      addMessage({
        role: 'assistant',
        content: res.content || '您好！我是供应链AI助手。请尝试发送消息开始对话。',
        blocks: (res.blocks || []).map((b: any) => normalizeBlock(b)),
      })
    } catch {
      addMessage({
        role: 'assistant',
        content: '您好！我是供应链AI助手。请尝试发送消息开始对话。',
        blocks: [],
      })
    } finally {
      isLoading.value = false
    }
  }

  /** 快捷操作：先拿确定性图表，再发给 LLM 做文字分析 */
  async function sendQuickAction(type: string, content: string) {
    if (!content.trim() || isLoading.value) return

    addMessage({ role: 'user', content, blocks: [] })
    isLoading.value = true

    try {
      // Step 1: Always fetch direct chart blocks from backend (100% deterministic)
      const directBlocks: MessageBlock[] = await fetchQuickActionBlocks(type)

      // Step 2: Ask LLM for text analysis only (charts already displayed)
      let llmContent = ''
      let llmBlocks: MessageBlock[] = []
      try {
        const apiMessages = messages.value
          .filter(m => m.role !== 'system')
          .map(m => ({ role: m.role, content: m.content }))

        // Append a system hint so LLM doesn't generate duplicate charts
        apiMessages.push({
          role: 'system',
          content: directBlocks.length > 0
            ? '注意：可视化图表已经由系统自动生成并展示给用户了。你只需要提供文字分析和建议，不需要再调用任何 render_* 或图表生成工具。'
            : '请调用合适的工具获取数据，按用户需求在 blocks 中返回图表或表格。',
        } as any)

        const res: any = await aiApi.chat({
          messages: apiMessages,
          conversation_id: conversationId.value,
        })
        conversationId.value = res.conversation_id || conversationId.value
        llmContent = res.content || ''
        llmBlocks = (res.blocks || []).map((b: any) => normalizeBlock(b))
      } catch {
        if (directBlocks.length > 0) {
          llmContent = 'AI 文字分析暂时不可用，图表数据正常显示。'
        } else {
          llmContent = '抱歉，请求失败，请稍后重试。'
        }
      }

      // Step 3: Merge — directBlocks first (charts), llmBlocks has action buttons etc.
      addMessage({
        role: 'assistant',
        content: llmContent,
        blocks: [...directBlocks, ...llmBlocks],
      })
    } catch {
      addMessage({ role: 'assistant', content: '抱歉，请求失败，请稍后重试。', blocks: [] })
    } finally {
      isLoading.value = false
    }
  }

  async function fetchQuickActionBlocks(type: string): Promise<MessageBlock[]> {
    try {
      // Use backend quick-chart API for all types — reliable, no LLM dependency
      const res: any = await aiApi.quickChart(type)
      if (res?.blocks && Array.isArray(res.blocks) && res.blocks.length > 0) {
        return res.blocks.map((b: any) => normalizeBlock(b))
      }
      return []
    } catch {
      return []
    }
  }

  function clearSession() {
    messages.value = []
    conversationId.value = ''
  }

  return {
    conversationId,
    messages,
    isLoading,
    addMessage,
    sendMessage,
    sendQuickAction,
    executeAction,
    initConversation,
    clearSession,
  }
})
