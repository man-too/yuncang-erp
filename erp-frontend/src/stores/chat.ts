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

export interface ConversationMeta {
  id: string
  title: string
  last_message: string
  message_count: number
  updated_at: string | null
}

export const useChatStore = defineStore('chat', () => {
  const conversationId = ref('')
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const conversations = ref<ConversationMeta[]>([])
  const isNewConversation = ref(false)  // P0-2 修复：跨调用追踪当前请求，便于 clearSession / unmount 中止
  let currentController: AbortController | null = null

  function abortCurrentRequest() {
    if (currentController) {
      try { currentController.abort() } catch { /* ignore */ }
      currentController = null
    }
  }

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
    isNewConversation.value = false
    addMessage({ role: 'user', content, blocks: [] })

    const assistantMsg: ChatMessage = {
      id: uuid(), role: 'assistant', content: '', blocks: [], timestamp: Date.now()
    }
    messages.value.push(assistantMsg)
    isLoading.value = true

    // P0-2 修复：AbortController 用于 unmount / clearSession 时取消请求
    abortCurrentRequest()
    const controller = new AbortController()
    currentController = controller
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    let aborted = false

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
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      // P1-5 修复：timeoutId 提到外层作用域，catch/finally 都能 clear
      timeoutId = setTimeout(() => {
        aborted = true
        try { reader.cancel() } catch { /* ignore */ }
        try { controller.abort() } catch { /* ignore */ }
        if (!assistantMsg.content) assistantMsg.content = '响应超时，请重试。'
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
          let eventType = ''
          // P1-4 修复：累加多行 data: 而非只保留最后一条
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7)
            if (line.startsWith('data: ')) dataLines.push(line.slice(6))
          }
          const eventData = dataLines.join('\n')
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
            if (timeoutId !== null) {
              clearTimeout(timeoutId)
              timeoutId = null
            }
            try {
              const doneData = JSON.parse(eventData)
              if (doneData.conversation_id) conversationId.value = doneData.conversation_id
            } catch { /* ignore */ }
          }
        }
      }
    } catch (e: any) {
      // 静默处理 AbortError（用户主动取消或超时）
      if (e?.name !== 'AbortError' && !aborted && !assistantMsg.content) {
        assistantMsg.content = '抱歉，请求失败，请稍后重试。'
      }
    } finally {
      if (timeoutId !== null) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
      if (currentController === controller) currentController = null
      isLoading.value = false
      await autoSaveConversation()
    }
  }

  /** Generate a signature string for a chart block to detect duplicates */
  function chartBlockSignature(block: MessageBlock): string {
    const d = block.data || {}
    const chartType = block.chartType || d.series?.[0]?.type || 'unknown'
    const seriesLen = d.series?.length ?? 0
    const firstSeriesDataLen = d.series?.[0]?.data?.length ?? 0
    const xAxisLen = d.xAxis?.data?.length ?? 0
    const title = d.title?.text ?? ''
    return `${chartType}-${seriesLen}-${firstSeriesDataLen}-${xAxisLen}-${title}`
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
    isNewConversation.value = false

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
      // Merge blocks: only include LLM chart blocks if they don't duplicate direct blocks
      const directChartSigs = new Set(
        directBlocks
          .filter(b => b.type === 'chart' && b.data)
          .map(b => chartBlockSignature(b))
      )
      const filteredLlmBlocks = llmBlocks.filter(b => {
        if (b.type === 'chart' && b.data) {
          return !directChartSigs.has(chartBlockSignature(b))
        }
        return true
      })
      const msg = messages.value.find(m => m.id === assistantId)
      if (msg) {
        msg.content = finalContent
        msg.blocks = [...directBlocks, ...filteredLlmBlocks]
      }
    } catch {
      const msg = messages.value.find(m => m.id === assistantId)
      if (msg) {
        msg.content = '抱歉，请求失败，请稍后重试。'
        msg.blocks = []
      }
    } finally {
      isLoading.value = false
      await autoSaveConversation()
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

      // P1-4 修复：以 \n\n 切分事件块，块内多行 data: 累加
      const dispatchEvent = (eventType: string, dataPayload: string) => {
        const msg = messages.value.find(m => m.id === assistantId)
        if (!msg) return
        if (eventType === 'blocks') {
          try {
            const blocks = JSON.parse(dataPayload)
            if (Array.isArray(blocks)) {
              msg.blocks = blocks.map((b: any) => normalizeBlock(b))
              gotBlocks = true
            }
          } catch { /* ignore parse error */ }
        } else if (eventType === 'content_delta') {
          let text = dataPayload
          try {
            const parsed = JSON.parse(dataPayload)
            if (typeof parsed === 'string') text = parsed
            else if (typeof parsed === 'object' && parsed !== null) text = JSON.stringify(parsed)
          } catch { /* not valid JSON */ }
          msg.content += text
        }
      }

      const consumeBuffer = (final: boolean) => {
        const events = buffer.split('\n\n')
        if (!final) {
          buffer = events.pop() || ''
        } else {
          buffer = ''
        }
        for (const eventStr of events) {
          if (!eventStr.trim()) continue
          const lines = eventStr.split('\n')
          let evt = ''
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith('event: ')) evt = line.slice(7).trim()
            else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
          }
          if (evt) dispatchEvent(evt, dataLines.join('\n'))
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        consumeBuffer(false)
      }
      // 处理流末尾残留
      if (buffer.trim()) consumeBuffer(true)

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
    abortCurrentRequest()
    messages.value = []
    conversationId.value = ''
    isLoading.value = false
  }

  /** 对话持久化：获取对话列表 */
  async function fetchConversations() {
    try {
      const res: any = await aiApi.conversations.list()
      conversations.value = res || []
    } catch {
      conversations.value = []
    }
  }

  /** 对话持久化：加载指定对话 */
  async function loadConversation(id: string) {
    try {
      const res: any = await aiApi.conversations.get(id)
      conversationId.value = res.id
      messages.value = (res.messages || []).map((m: any) => ({
        id: uuid(),
        role: m.role || 'assistant',
        content: m.content || '',
        blocks: (m.blocks || []).map((b: any) => normalizeBlock(b)),
        timestamp: m.timestamp || Date.now(),
      }))
    } catch {
      ElMessage.error('加载对话失败')
    }
  }

  /** 对话持久化：删除对话 */
  async function deleteConversation(id: string) {
    try {
      await aiApi.conversations.delete(id)
      conversations.value = conversations.value.filter(c => c.id !== id)
      if (conversationId.value === id) {
        clearSession()
      }
    } catch {
      ElMessage.error('删除对话失败')
    }
  }

  /** 对话持久化：新建对话（先保存当前对话再清空，展示欢迎界面） */
  async function newConversation() {
    await autoSaveConversation()
    clearSession()
    isNewConversation.value = true
  }

  /** 对话持久化：自动保存（仅保留最近5轮/10条消息） */
  async function autoSaveConversation() {
    if (!conversationId.value || messages.value.length === 0) return
    const lastUserMsg = messages.value.filter(m => m.role === 'user').slice(-1)[0]
    const title = lastUserMsg?.content?.slice(0, 50) || '新对话'
    const msgsToSave = messages.value.slice(-10).map(m => ({
      role: m.role,
      content: m.content,
      blocks: m.blocks,
      timestamp: m.timestamp,
    }))
    try {
      await aiApi.conversations.save({
        id: conversationId.value,
        title,
        messages: msgsToSave,
      })
    } catch (e) { console.error('autoSaveConversation failed:', e) }
  }

  /** 向聊天面板推送步骤摘要（纯文本，无表格无图表） */
  function pushStepSummary(stepLabel: string, summaryText: string) {
    if (!summaryText) return
    addMessage({
      role: 'assistant',
      content: `**[${stepLabel}]**\n\n${summaryText}`,
      blocks: [],
    })
  }

  return {
    conversationId,
    messages,
    isLoading,
    conversations,
    isNewConversation,
    addMessage,
    sendMessage,
    sendQuickAction,
    executeAction,
    initConversation,
    clearSession,
    abortCurrentRequest,
    fetchConversations,
    loadConversation,
    deleteConversation,
    newConversation,
    autoSaveConversation,
    pushStepSummary,
  }
})
