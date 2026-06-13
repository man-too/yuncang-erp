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

    const assistantMsg: ChatMessage = {
      id: uuid(), role: 'assistant', content: '', blocks: [], timestamp: Date.now()
    }
    messages.value.push(assistantMsg)
    isLoading.value = true

    try {
      const apiMessages = messages.value
        .filter(m => m.role !== 'system' && m.id !== assistantMsg.id)
        .map(m => ({ role: m.role, content: m.content }))
      const token = localStorage.getItem('token')
      const res = await fetch('/api/ai/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ messages: apiMessages, conversation_id: conversationId.value }),
      })
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const timeoutId = setTimeout(() => {
        reader.cancel()
        if (!assistantMsg.content) assistantMsg.content = '响应超时，请重试。'
        isLoading.value = false
      }, 30000)
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const eventStr of events) {
          if (!eventStr.trim()) continue
          const lines = eventStr.split('\n')
          let eventType = '', eventData = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7)
            if (line.startsWith('data: ')) eventData = line.slice(6)
          }
          if (eventType === 'blocks') {
            try {
              const parsed = JSON.parse(eventData)
              assistantMsg.blocks = (Array.isArray(parsed) ? parsed : []).map((b: any) => normalizeBlock(b))
            } catch { /* ignore parse errors */ }
          } else if (eventType === 'content_delta') {
            // Backend JSON-encodes data; extract text
            let text = eventData
            try {
              const parsed = JSON.parse(eventData)
              if (typeof parsed === 'string') text = parsed
              else if (typeof parsed === 'object' && parsed !== null) text = JSON.stringify(parsed)
            } catch { /* not valid JSON, use raw text */ }
            assistantMsg.content += text
          } else if (eventType === 'done') {
            clearTimeout(timeoutId)
            try {
              const doneData = JSON.parse(eventData)
              if (doneData.conversation_id) conversationId.value = doneData.conversation_id
            } catch { /* ignore */ }
          }
        }
      }
      clearTimeout(timeoutId)
    } catch {
      if (!assistantMsg.content) assistantMsg.content = '抱歉，请求失败，请稍后重试。'
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

  /** 快捷操作：SSE 流式获取图表 + 模板分析 + LLM 深度分析 */
  async function sendQuickAction(type: string, content: string) {
    if (!content.trim() || isLoading.value) return

    addMessage({ role: 'user', content, blocks: [] })
    isLoading.value = true

    // Create assistant message placeholder for streaming updates
    const assistantId = uuid()
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      blocks: [],
      timestamp: Date.now(),
    }
    messages.value.push(assistantMsg)

    try {
      // Try SSE streaming first
      const streamOk = await _streamQuickAction(type, content, assistantId)
      if (streamOk) return

      // Fallback to non-streaming if SSE failed
      const quickResult = await fetchQuickActionBlocks(type)
      const directBlocks: MessageBlock[] = quickResult.blocks
      const fallbackContent: string = quickResult.content || ''

      // Ask LLM for text analysis
      let llmContent = ''
      let llmBlocks: MessageBlock[] = []
      try {
        const apiMessages = messages.value
          .filter(m => m.role !== 'system')
          .map(m => ({ role: m.role, content: m.content }))

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
        if (directBlocks.length === 0) {
          llmContent = '抱歉，请求失败，请稍后重试。'
        }
      }

      const finalContent = llmContent || fallbackContent || '数据已加载，请查看下方图表/表格。'
      // Update the assistant message
      const msg = messages.value.find(m => m.id === assistantId)
      if (msg) {
        msg.content = finalContent
        msg.blocks = [...directBlocks, ...llmBlocks]
      }
    } catch {
      const msg = messages.value.find(m => m.id === assistantId)
      if (msg) {
        msg.content = '抱歉，请求失败，请稍后重试。'
        msg.blocks = []
      }
    } finally {
      isLoading.value = false
    }
  }

  /** SSE 流式读取快捷操作，返回 true 表示成功 */
  async function _streamQuickAction(type: string, recentQ: string, assistantId: string): Promise<boolean> {
    try {
      const response = await aiApi.quickChartStream(type, recentQ)
      if (!response.ok) return false
      if (!response.body) return false

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let gotBlocks = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        // Keep the last incomplete line in buffer
        buffer = lines.pop() || ''

        let currentEvent = ''
        let currentData = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6)
          } else if (line === '' && currentEvent) {
            // Empty line = end of event
            const msg = messages.value.find(m => m.id === assistantId)
            if (!msg) continue

            if (currentEvent === 'blocks') {
              try {
                const blocks = JSON.parse(currentData)
                if (Array.isArray(blocks)) {
                  msg.blocks = blocks.map((b: any) => normalizeBlock(b))
                  gotBlocks = true
                }
              } catch { /* ignore parse error */ }
            } else if (currentEvent === 'content_delta') {
              // Backend always JSON-encodes the data field
              let text = currentData
              try {
                const parsed = JSON.parse(currentData)
                if (typeof parsed === 'string') text = parsed
                else if (typeof parsed === 'object' && parsed !== null) text = JSON.stringify(parsed)
              } catch { /* not valid JSON, use raw text */ }
              msg.content += text
            } else if (currentEvent === 'done') {
              // Stream complete
            }

            currentEvent = ''
            currentData = ''
          }
        }

        // Process any remaining complete event in buffer
        if (buffer.includes('\n\n')) {
          // Re-process next iteration
        }
      }

      // Process any remaining data in buffer
      if (buffer.trim()) {
        const remainingLines = buffer.split('\n')
        let evt = ''
        let dat = ''
        for (const line of remainingLines) {
          if (line.startsWith('event: ')) evt = line.slice(7).trim()
          else if (line.startsWith('data: ')) dat = line.slice(6)
        }
        if (evt && dat) {
          const msg = messages.value.find(m => m.id === assistantId)
          if (msg) {
            if (evt === 'blocks') {
              try {
                const blocks = JSON.parse(dat)
                if (Array.isArray(blocks)) {
                  msg.blocks = blocks.map((b: any) => normalizeBlock(b))
                  gotBlocks = true
                }
              } catch { /* ignore */ }
            } else if (evt === 'content_delta') {
              let text = dat
              try {
                const parsed = JSON.parse(dat)
                if (typeof parsed === 'string') text = parsed
                else if (typeof parsed === 'object' && parsed !== null) text = JSON.stringify(parsed)
              } catch { /* not valid JSON */ }
              msg.content += text
            }
          }
        }
      }

      // If we got at least blocks, consider it a success
      return gotBlocks || messages.value.find(m => m.id === assistantId)?.content !== ''
    } catch (e) {
      console.warn('SSE streaming failed, falling back to non-streaming:', e)
      return false
    }
  }

  async function fetchQuickActionBlocks(type: string): Promise<{ content: string; blocks: MessageBlock[] }> {
    try {
      // Use backend quick-chart API for all types — reliable, no LLM dependency
      const res: any = await aiApi.quickChart(type)
      const content = res?.content || ''
      const blocks = (res?.blocks && Array.isArray(res.blocks) && res.blocks.length > 0)
        ? res.blocks.map((b: any) => normalizeBlock(b))
        : []
      return { content, blocks }
    } catch {
      return { content: '', blocks: [] }
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
