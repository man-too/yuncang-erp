<!-- 聊天消息气泡：文字 + 图表 + 表格 + 操作按钮 -->
<template>
  <div :class="['chat-message', role]">
    <div class="msg-avatar">{{ role === 'user' ? '我' : 'AI' }}</div>
    <div class="msg-body">
      <div class="msg-bubble">
        <!-- 文字内容（简单 Markdown） -->
        <div class="msg-content" v-html="renderedContent" />

        <!-- 结构化 Blocks (原有 + 防御性提取) -->
        <div v-for="(block, bi) in allBlocks" :key="bi" class="msg-block">
          <!-- 图表 -->
          <div v-if="block.type === 'chart'" class="chart-container">
            <v-chart v-if="hasValidChartData(block)" :option="chartWithDefaultTitle(block)" autoresize class="chart-render" />
            <el-empty v-else description="图表数据加载失败" :image-size="80" />
          </div>

          <!-- 表格 -->
          <el-table
            v-else-if="block.type === 'table'"
            :data="block.rows || []"
            stripe border size="small" max-height="420"
            highlight-current-row row-class-name="enhanced-row"
            class="block-table"
          >
            <el-table-column
              v-for="col in (block.columns || [])"
              :key="col.key"
              :prop="col.key"
              :label="col.title"
              min-width="100"
            >
              <template #default="{ row }">
                <span :class="getCellClass(col.key, row[col.key])">
                  <template v-if="isStatusValue(row[col.key])">
                    <el-tag :type="getStatusType(row[col.key])" size="small" effect="plain">
                      {{ row[col.key] }}
                    </el-tag>
                  </template>
                  <template v-else>
                    {{ formatCellValue(col.key, row[col.key]) }}
                  </template>
                </span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 操作按钮 -->
          <div v-else-if="block.type === 'actions'" class="block-actions">
            <div v-for="(action, ai) in (block.actions || [])" :key="ai" class="action-row">
              <!-- pending: 确认/取消 -->
              <template v-if="!action.status || action.status === 'pending'">
                <div class="action-card">
                  <div class="action-text">
                    <strong>{{ action.label }}</strong>
                    <p v-if="action.confirmDetail" style="margin:4px 0 0;font-size:13px;color: var(--text-secondary);">
                      {{ action.confirmDetail }}
                    </p>
                  </div>
                  <div class="action-btns">
                    <el-button size="small" type="primary" @click="$emit('confirm', messageId, bi, ai)">
                      {{ action.confirmTitle || '确认执行' }}
                    </el-button>
                    <el-button size="small" @click="$emit('cancel', messageId, bi, ai)">放弃</el-button>
                  </div>
                </div>
              </template>

              <!-- loading -->
              <el-tag v-else-if="action.status === 'loading'" type="info" size="small" class="action-status">
                <el-icon class="is-loading"><Loading /></el-icon> 执行中...
              </el-tag>

              <!-- success -->
              <div v-else-if="action.status === 'success'" class="action-status success">
                <el-icon color="var(--color-success)"><CircleCheck /></el-icon>
                <span>{{ action.resultMessage }}</span>
                <el-button
                  v-if="action.resultLink" size="small" type="primary" link
                  @click="navigateTo(action.resultLink!)"
                >查看详情</el-button>
              </div>

              <!-- error -->
              <div v-else-if="action.status === 'error'" class="action-status error">
                <el-icon color="var(--color-danger)"><CircleClose /></el-icon>
                <span>{{ action.resultMessage }}</span>
                <el-button size="small" type="warning" @click="$emit('retry', messageId, bi, ai)">重试</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  HeatmapChart, LineChart, BarChart, PieChart, ScatterChart, RadarChart,
} from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, VisualMapComponent, DataZoomComponent,
  ToolboxComponent, PolarComponent,
} from 'echarts/components'
import type { MessageBlock } from '@/stores/chat'

use([
  CanvasRenderer,
  HeatmapChart, LineChart, BarChart, PieChart, ScatterChart, RadarChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  VisualMapComponent, DataZoomComponent, ToolboxComponent, PolarComponent,
])

const props = defineProps<{
  role: 'user' | 'assistant' | 'system'
  content: string
  blocks: MessageBlock[]
  messageId: string
}>()

defineEmits<{
  confirm: [messageId: string, blockIndex: number, actionIndex: number]
  cancel: [messageId: string, blockIndex: number, actionIndex: number]
  retry: [messageId: string, blockIndex: number, actionIndex: number]
}>()

const router = useRouter()

// 防御性处理：检测并提取 content 中残留的 chart JSON
function sanitizeContent(content: string, blocks: MessageBlock[]): { cleanContent: string, extraBlocks: MessageBlock[] } {
  const extraBlocks: MessageBlock[] = []
  let cleanContent = content

  // 检测 content 中是否包含 {"type":"chart" 或 {"type": "chart" 模式
  const chartPattern = /\{\s*"type"\s*:\s*"chart"/g
  let match
  while ((match = chartPattern.exec(cleanContent)) !== null) {
    const start = match.index
    // 用花括号匹配提取完整 JSON
    let depth = 0
    let inString = false
    let escape = false
    let end = start
    for (let i = start; i < cleanContent.length; i++) {
      const ch = cleanContent[i]
      if (escape) { escape = false; continue }
      if (ch === '\\') { escape = true; continue }
      if (ch === '"') { inString = !inString; continue }
      if (inString) continue
      if (ch === '{') depth++
      else if (ch === '}') {
        depth--
        if (depth === 0) { end = i + 1; break }
      }
    }
    if (end > start) {
      const jsonStr = cleanContent.substring(start, end)
      try {
        const obj = JSON.parse(jsonStr)
        if (obj.type === 'chart' && obj.data) {
          extraBlocks.push({
            type: 'chart',
            chartType: obj.chartType || 'line',
            data: obj.data,
          })
          cleanContent = cleanContent.substring(0, start) + cleanContent.substring(end)
          // 重置 regex lastIndex 因为内容已变
          chartPattern.lastIndex = 0
        }
      } catch {
          // 解析失败，跳过此 match 防止死循环
          chartPattern.lastIndex = match.index + match[0].length
        }
    }
    // Fallback: advance lastIndex to prevent infinite loop
    if (chartPattern.lastIndex <= start) {
      chartPattern.lastIndex = start + 1
    }
  }

  cleanContent = cleanContent.trim()
  if (!cleanContent && extraBlocks.length > 0) {
    cleanContent = '图表数据已生成，请查看下方图表。'
  }

  return { cleanContent, extraBlocks }
}

// 预处理后的内容
const sanitized = computed(() => sanitizeContent(props.content, props.blocks))

const renderedContent = computed(() => {
  const cleanContent = sanitized.value.cleanContent
  if (!cleanContent) return ''
  return marked(cleanContent, { breaks: true })
})

// 合并原有 blocks 和额外提取的 blocks
const allBlocks = computed(() => [...props.blocks, ...sanitized.value.extraBlocks])

function chartWithDefaultTitle(block: MessageBlock) {
  // IMPORTANT: never mutate block.data — create new object to avoid Vue reactive loops
  const src = block.data || {}
  const opt: any = { ...src }
  if (!opt.grid) opt.grid = { top: 50, bottom: 30, left: 60, right: 30 }
  if (!opt.tooltip) opt.tooltip = { trigger: src.xAxis ? 'axis' : 'item' }
  if (src.series && Array.isArray(src.series)) {
    opt.series = src.series.map((s: any) => ({ ...s, type: s.type || block.chartType || 'line' }))
  } else {
    opt.series = [{ type: block.chartType || 'bar', data: [] }]
  }
  return opt
}

function navigateTo(link: string) {
  router.push(link)
}

/* ── Table format helpers ── */

function isStatusValue(value: any): boolean {
  if (typeof value !== 'string') return false
  const keywords = ['正常', '告警', '预警', '偏高', '偏低', '缺货', '严重', '紧急', 'active', 'inactive', 'draft', 'completed', 'cancelled', 'approved']
  return keywords.some(k => value.includes(k))
}

function getStatusType(value: string): string {
  if (value.includes('正常') || value.includes('completed') || value.includes('active')) return 'success'
  if (value.includes('告警') || value.includes('严重') || value.includes('缺货') || value.includes('cancelled')) return 'danger'
  if (value.includes('预警') || value.includes('偏低') || value.includes('紧急') || value.includes('draft')) return 'warning'
  if (value.includes('偏高')) return 'info'
  if (value.includes('approved')) return 'primary'
  return 'info'
}

function formatCellValue(key: string, value: any): string {
  if (value === null || value === undefined) return '-'
  // Money fields
  const moneyKeys = ['price', 'amount', 'cost', 'total', 'credit', 'budget', 'fee', 'salary']
  if (typeof value === 'number' && moneyKeys.some(k => key.toLowerCase().includes(k))) {
    return '¥' + value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  // Percent fields
  const percentKeys = ['rate', 'percent', 'ratio']
  if (typeof value === 'number' && percentKeys.some(k => key.toLowerCase().includes(k))) {
    return value + '%'
  }
  // Numeric fields
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString('zh-CN')
    return value.toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 2 })
  }
  return String(value)
}

function getCellClass(key: string, value: any): string {
  const moneyKeys = ['price', 'amount', 'cost', 'total', 'credit']
  if (typeof value === 'number' && moneyKeys.some(k => key.toLowerCase().includes(k))) return 'cell-money'
  if (typeof value === 'number') return 'cell-number'
  return ''
}

function hasValidChartData(block: MessageBlock): boolean {
  const data = block.data
  if (!data) return false
  // Chart types with series (line, bar, pie, scatter, radar, gauge)
  if (data.series && Array.isArray(data.series) && data.series.length > 0) return true
  // Heatmap: series exists but data is inside series[0].data as [x, y, value] tuples
  if (data.series && Array.isArray(data.series) && data.series.length > 0 && data.series[0]?.data) return true
  // Some charts have data directly in xAxis/yAxis without series (shouldn't render)
  return false
}
</script>

<style scoped>
.chat-message { display: flex; gap: 10px; }
.chat-message.user { align-self: flex-end; flex-direction: row-reverse; max-width: 75%; }
.chat-message.assistant { align-self: flex-start; min-width: 320px; max-width: 680px; }

.msg-avatar {
  width: 36px; height: 36px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 13px; font-weight: 600;
  flex-shrink: 0; color: #fff;
}
.chat-message.user .msg-avatar { background: linear-gradient(135deg, #005BF5, #2e7bff); }
.chat-message.assistant .msg-avatar { background: linear-gradient(135deg, #55585F, #005BF5); }

.msg-body { flex: 1; min-width: 0; }
.msg-bubble {
  padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.7;
  max-width: 100%; overflow-wrap: break-word; word-break: break-word;
}
.chat-message.user .msg-bubble { background: var(--color-info-bg); border: 1px solid var(--color-info-light); }
.chat-message.assistant .msg-bubble { background: var(--bg-page); border: 1px solid var(--border-color); overflow: hidden; }

.msg-content h3 { margin: 14px 0 8px; font-size: 16px; }
.msg-content h4 { margin: 12px 0 6px; font-size: 15px; }
.msg-content ul, .msg-content ol { margin: 6px 0; padding-left: 24px; }
.msg-content li { margin: 2px 0; }
.msg-content p { margin: 4px 0; }
.msg-content a { color: var(--color-primary); text-decoration: underline; }
.msg-content code {
  background: rgba(0, 0, 0, 0.06); padding: 2px 6px; border-radius: 4px;
  font-size: 13px; font-family: 'Menlo', 'Consolas', monospace;
}
.msg-content pre {
  background: rgba(0, 0, 0, 0.06); padding: 12px; border-radius: 8px;
  overflow-x: auto; margin: 8px 0; max-width: 100%;
}
.msg-content pre code {
  background: none; padding: 0; font-size: 13px; line-height: 1.5;
}
.msg-content table {
  border-collapse: collapse; margin: 8px 0; width: 100%; font-size: 13px;
  table-layout: fixed; overflow-wrap: break-word; word-break: break-word;
}
.msg-content table th, .msg-content table td {
  border: 1px solid var(--border-color); padding: 6px 10px; text-align: left;
}
.msg-content table th {
  background: var(--table-header-bg); font-weight: 600;
}
.msg-content blockquote {
  border-left: 4px solid var(--color-primary); margin: 8px 0;
  padding: 4px 12px; color: var(--text-secondary);
}

.chart-container {
  margin: 12px 0;
  background: var(--bg-card);
  border-radius: 8px;
  padding: 8px;
  overflow: hidden;
  min-height: 280px;
  min-width: 400px;
}
.chart-render {
  width: 100% !important;
  height: 320px;
  min-height: 280px;
  min-width: 300px;
}
.block-table {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  max-width: 100%;
}
.block-table :deep(.el-table__body-wrapper) {
  overflow-x: auto;
}
.block-table :deep(th) {
  background: var(--table-header-bg) !important;
  font-weight: 600;
  color: var(--text-primary);
}
.block-table :deep(.el-table__row.enhanced-row:hover) {
  background-color: var(--table-hover) !important;
}
.block-table :deep(.enhanced-row) {
  transition: background-color 0.15s;
}
:deep(.cell-money) { color: var(--color-danger); font-weight: 600; }
:deep(.cell-number) { text-align: right; display: block; }

.block-actions { margin: 12px 0; }
.action-row { margin-bottom: 8px; }
.action-card {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 10px; background: var(--bg-card);
  border: 1px solid var(--color-primary); border-left: 4px solid var(--color-accent);
}
.action-btns { display: flex; gap: 8px; flex-shrink: 0; }

.action-status {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 8px; font-size: 13px;
}
.action-status.success { background: var(--color-success-bg); border: 1px solid var(--color-success-light); color: var(--color-success); }
.action-status.error { background: var(--color-danger-bg); border: 1px solid var(--color-danger-light); color: var(--color-danger); }
.is-loading { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
