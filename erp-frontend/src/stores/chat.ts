/** AI 对话会话状态管理（仅会话内有效，刷新丢失） */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { aiApi, inventoryApi } from '@/api'
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

  /** 快捷操作：直接调 API 生成图表 + 同时发给 LLM 做文本分析 */
  async function sendQuickAction(type: string, content: string) {
    if (!content.trim() || isLoading.value) return

    addMessage({ role: 'user', content, blocks: [] })
    isLoading.value = true

    try {
      // Step 1: Always fetch direct chart blocks (non-blocking for LLM)
      const directBlocks: MessageBlock[] = await fetchQuickActionBlocks(type)

      // Step 2: Try LLM for text analysis
      let llmContent = ''
      let llmBlocks: MessageBlock[] = []
      try {
        const apiMessages = messages.value
          .filter(m => m.role !== 'system')
          .map(m => ({ role: m.role, content: m.content }))

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

      // Step 3: Merge and display
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
      if (type === 'stock_alert') {
        const heatmapData: any = await inventoryApi.heatmap()
        if (!heatmapData || heatmapData.length === 0) return []
        const whNames: string[] = [...new Set(heatmapData.map((d: any) => d.warehouse_name))].filter(Boolean)
        const prodNames: string[] = [...new Set(heatmapData.map((d: any) => d.product_name))].filter(Boolean)
        const whIdx = Object.fromEntries(whNames.map((n, i) => [n, i]))
        const prodIdx = Object.fromEntries(prodNames.map((n, i) => [n, i]))
        const data = heatmapData.map((d: any) => [
          whIdx[d.warehouse_name] ?? 0,
          prodIdx[d.product_name] ?? 0,
          d.alert_level ?? 0,
        ])
        return [{
          type: 'chart', chartType: 'heatmap',
          data: {
            title: { text: '库存状态热力图', left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { position: 'top' },
            grid: { left: 160, right: 40, top: 50, bottom: 50 },
            xAxis: { type: 'category', data: whNames, splitArea: { show: true } },
            yAxis: { type: 'category', data: prodNames, splitArea: { show: true } },
            visualMap: { min: 0, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
              inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcc80', '#ef5350'] } },
            series: [{ name: '库存状态', type: 'heatmap', data,
              emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
          },
        }]
      }
      if (type === 'sales_forecast') {
        const history: any = await aiApi.salesHistory()
        const items = (history?.items || history || []).slice(0, 12)
        if (items.length === 0) return []
        const months = items.map((i: any) => i.date || i.month || '')
        const amounts = items.map((i: any) => i.amount || i.total_amount || 0)

        // WMA prediction: use last 3 months with weights [0.5, 0.3, 0.2] (most recent first)
        const last3 = amounts.slice(-3)
        const pred1 = last3.length >= 3
          ? last3[2] * 0.5 + last3[1] * 0.3 + last3[0] * 0.2
          : amounts[amounts.length - 1] || 0
        const pred2 = pred1 * 0.5 + last3[2] * 0.3 + last3[1] * 0.2

        // Generate forecast month labels — extract last numeric segment from month string
        const lastMonth = months[months.length - 1] || ''
        const monthNums = lastMonth.match(/\d+/g)
        const lastMonthNum = monthNums ? parseInt(monthNums[monthNums.length - 1], 10) : 0
        const predLabel1 = `${(lastMonthNum % 12) + 1}月(预)`
        const predLabel2 = `${((lastMonthNum + 1) % 12) + 1}月(预)`

        // Append forecast months and pad data for alignment
        const allMonths = [...months, predLabel1, predLabel2]
        const historicalData = [...amounts, null, null]
        const forecastData = [...months.map(() => null), pred1, pred2]

        return [{
          type: 'chart', chartType: 'line',
          data: {
            title: { text: '月度销售趋势', left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            legend: { data: ['销售额', '预测'], bottom: 0 },
            toolbox: { feature: { saveAsImage: {}, dataView: { readOnly: false }, restore: {} } },
            dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 30 }],
            grid: { left: 60, right: 30, top: 50, bottom: 80 },
            xAxis: { type: 'category', data: allMonths },
            yAxis: { type: 'value', name: '金额 (¥)' },
            series: [{
              name: '销售额', type: 'line', smooth: true, data: historicalData,
              lineStyle: { color: '#5470c6', width: 2.5 },
              areaStyle: { color: 'rgba(84,112,198,0.12)' },
              emphasis: { scale: 1.8 },
            }, {
              name: '预测', type: 'line', smooth: true, data: forecastData,
              lineStyle: { type: 'dashed', width: 2, color: '#ff6b6b' },
              itemStyle: { color: '#ff6b6b' },
              symbol: 'diamond',
              symbolSize: 8,
            }],
          },
        }]
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
