<!-- 聊天消息气泡：文字 + 图表 + 表格 + 操作按钮 -->
<template>
  <div :class="['chat-message', role]">
    <div class="msg-avatar">{{ role === 'user' ? '我' : 'AI' }}</div>
    <div class="msg-body">
      <div class="msg-bubble">
        <!-- 文字内容（简单 Markdown） -->
        <div class="msg-content" v-html="renderedContent" />

        <!-- 结构化 Blocks -->
        <div v-for="(block, bi) in blocks" :key="bi" class="msg-block">
          <!-- 图表 -->
          <div v-if="block.type === 'chart'" class="chart-container">
            <v-chart v-if="hasValidChartData(block)" :option="chartWithDefaultTitle(block)" autoresize style="height: 320px;" />
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
                    <p v-if="action.confirmDetail" style="margin:4px 0 0;font-size:13px;color:#909399;">
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
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                <span>{{ action.resultMessage }}</span>
                <el-button
                  v-if="action.resultLink" size="small" type="primary" link
                  @click="navigateTo(action.resultLink!)"
                >查看详情</el-button>
              </div>

              <!-- error -->
              <div v-else-if="action.status === 'error'" class="action-status error">
                <el-icon color="#f56c6c"><CircleClose /></el-icon>
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

const renderedContent = computed(() => {
  if (!props.content) return ''
  let html = props.content
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Headings: ### text / ## text
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  // List items: - text (wrap consecutive items in <ul>)
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Line breaks
  html = html.replace(/\n{2,}/g, '</p><p>')
  html = html.replace(/\n/g, '<br/>')
  // Wrap in paragraphs
  if (!html.startsWith('<h') && !html.startsWith('<ul') && !html.startsWith('<p')) {
    html = '<p>' + html + '</p>'
  }
  return html
})

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
  const percentKeys = ['rate', 'percent', 'ratio', 'score']
  if (typeof value === 'number' && (key.toLowerCase().includes('rate') || key.toLowerCase().includes('rate'))) {
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
  if (data.series && Array.isArray(data.series) && data.series.length > 0) return true
  return false
}
</script>

<style scoped>
.chat-message { display: flex; gap: 10px; max-width: 90%; }
.chat-message.user { align-self: flex-end; flex-direction: row-reverse; }
.chat-message.assistant { align-self: flex-start; }

.msg-avatar {
  width: 36px; height: 36px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 13px; font-weight: 600;
  flex-shrink: 0; color: #fff;
}
.chat-message.user .msg-avatar { background: linear-gradient(135deg, #409eff, #337ecc); }
.chat-message.assistant .msg-avatar { background: linear-gradient(135deg, #667eea, #764ba2); }

.msg-body { flex: 1; min-width: 0; }
.msg-bubble {
  padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.7;
}
.chat-message.user .msg-bubble { background: #ecf5ff; border: 1px solid #d9ecff; }
.chat-message.assistant .msg-bubble { background: #f5f7fa; border: 1px solid #e4e7ed; }

.msg-content h4 { margin: 12px 0 6px; font-size: 15px; }
.msg-content li { margin-left: 16px; }

.chart-container { margin: 12px 0; background: #fff; border-radius: 8px; padding: 8px; }
.block-table {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.block-table :deep(th) {
  background: #f5f7fa !important;
  font-weight: 600;
  color: #303133;
}
.block-table :deep(.el-table__row.enhanced-row:hover) {
  background-color: #f0f5ff !important;
}
.block-table :deep(.enhanced-row) {
  transition: background-color 0.15s;
}
:deep(.cell-money) { color: #f56c6c; font-weight: 600; }
:deep(.cell-number) { text-align: right; display: block; }

.block-actions { margin: 12px 0; }
.action-row { margin-bottom: 8px; }
.action-card {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 10px; background: #fff;
  border: 1px solid #409eff; border-left: 4px solid #409eff;
}
.action-btns { display: flex; gap: 8px; flex-shrink: 0; }

.action-status {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 8px; font-size: 13px;
}
.action-status.success { background: #f0f9eb; border: 1px solid #e1f3d8; color: #67c23a; }
.action-status.error { background: #fef0f0; border: 1px solid #fde2e2; color: #f56c6c; }
.is-loading { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
