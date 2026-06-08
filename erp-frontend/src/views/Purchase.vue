<template>
  <div class="page-container">
    <el-card shadow="never">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">采购管理</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="filters.keyword" placeholder="订单号搜索" clearable size="default" />
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.status" placeholder="订单状态" clearable style="width: 100%" size="default">
              <el-option label="全部" value="" />
              <el-option label="草稿" value="draft" />
              <el-option label="待审批" value="pending_approval" />
              <el-option label="已审批" value="approved" />
              <el-option label="部分收货" value="partially_received" />
              <el-option label="已完成" value="completed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.supplier_id" placeholder="供应商" clearable filterable style="width: 100%" size="default">
              <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-col>
          <el-col :span="6" style="display: flex; justify-content: flex-end; align-items: center;">
            <div class="search-buttons">
              <el-button type="primary" size="small" @click="handleSearch">搜索</el-button>
              <el-button size="small" @click="handleReset">重置</el-button>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 12px;">
          <el-col :span="4">
            <el-input-number v-model="filters.amount_min" :min="0" placeholder="最小金额" style="width: 100%" controls-position="right" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="filters.amount_max" :min="0" placeholder="最大金额" style="width: 100%" controls-position="right" />
          </el-col>
          <el-col :span="8">
            <el-date-picker v-model="filters.date_range" type="daterange" range-separator="至" start-placeholder="下单日期起" end-placeholder="下单日期止" style="width: 100%" size="default" value-format="YYYY-MM-DD" />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          批量删除 {{ selectedRows.length > 0 ? '(' + selectedRows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImport">导入</el-button>
        <el-button type="primary" @click="openCreateDialog">新增</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="orders" v-loading="loading" stripe style="width: 100%"
                @selection-change="handleSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="order_no" label="订单号" width="160" />
        <el-table-column label="供应商" width="150">
          <template #default="{ row }">{{ getSupplierName(row.supplier_id) }}</template>
        </el-table-column>
        <el-table-column prop="total_amount" label="金额" width="120" align="right" />
        <el-table-column prop="order_date" label="下单日期" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="viewDetail(row)">编辑</el-button>
            <el-button size="small" type="danger" text @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination - centered -->
      <div style="display: flex; justify-content: center; margin-top: 16px;">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="fetchData"
        />
      </div>
    </el-card>

    <!-- 创建订单弹窗 -->
    <el-dialog v-model="createVisible" title="创建采购订单" width="700px">
      <el-form :model="poForm" label-width="100px">
        <el-form-item label="供应商" required>
          <el-select v-model="poForm.supplier_id" filterable style="width: 100%">
            <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计到货">
          <el-date-picker v-model="poForm.expected_delivery_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="poForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <h3 style="margin-bottom: 12px;">订单明细</h3>
      <el-table :data="poForm.items" style="margin-bottom: 12px;">
        <el-table-column label="产品" width="200">
          <template #default="{ row, $index }">
            <el-select v-model="row.product_id" filterable @change="(val: number) => onProductSelect($index, val)">
              <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="1" style="width: 100px" />
          </template>
        </el-table-column>
        <el-table-column label="单价" width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :precision="2" style="width: 100px" />
          </template>
        </el-table-column>
        <el-table-column label="小计" width="100">
          <template #default="{ row }">{{ (row.quantity * row.unit_price).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }">
            <el-button type="danger" :icon="'Delete'" text @click="poForm.items.splice($index, 1)" />
          </template>
        </el-table-column>
      </el-table>
      <el-button @click="addItem">添加行</el-button>

      <div style="text-align: right; margin-top: 12px; font-size: 16px; font-weight: bold;">
        合计: ¥{{ totalAmount.toFixed(2) }}
      </div>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreateOrder">提交</el-button>
      </template>
    </el-dialog>

    <!-- 入库弹窗 -->
    <el-dialog v-model="inboundVisible" title="采购入库" width="400px">
      <el-form :model="inboundForm" label-width="100px">
        <el-form-item label="仓库" required>
          <el-select v-model="inboundForm.warehouse_id" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="inboundForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inboundVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleInbound">确认入库</el-button>
      </template>
    </el-dialog>

    <!-- 订单详情弹窗 -->
    <el-dialog v-model="detailVisible" title="订单详情" width="700px">
      <template v-if="currentOrder">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="订单号">{{ currentOrder.order_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusLabel(currentOrder.status) }}</el-descriptions-item>
          <el-descriptions-item label="总金额">¥{{ currentOrder.total_amount }}</el-descriptions-item>
          <el-descriptions-item label="下单日期">{{ currentOrder.order_date }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ currentOrder.remark || '无' }}</el-descriptions-item>
        </el-descriptions>
        <h3 style="margin: 16px 0 12px;">明细</h3>
        <el-table :data="orderItems" stripe>
          <el-table-column prop="product_id" label="产品ID" width="80" />
          <el-table-column prop="quantity" label="数量" width="80" />
          <el-table-column prop="unit_price" label="单价" width="100" />
          <el-table-column prop="total_price" label="小计" width="100" />
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { purchaseApi, supplierApi, productApi, inventoryApi } from '@/api'

const orders = ref<any[]>([])
const suppliers = ref<any[]>([])
const products = ref<any[]>([])
const warehouses = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const createVisible = ref(false)
const inboundVisible = ref(false)
const inboundOrderId = ref(0)
const detailVisible = ref(false)
const currentOrder = ref<any>(null)
const orderItems = ref<any[]>([])
const selectedRows = ref<any[]>([])
const tableRef = ref()

const filters = reactive({
  keyword: '',
  status: '',
  supplier_id: null,
  amount_min: null,
  amount_max: null,
  date_range: null,
})

const poForm = reactive({
  supplier_id: null,
  expected_delivery_date: null,
  remark: '',
  items: [] as any[],
})

const inboundForm = reactive({
  warehouse_id: null,
  remark: '',
})

const totalAmount = computed(() =>
  poForm.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0)
)

const handleSearch = () => {
  page.value = 1
  fetchData()
}

const handleReset = () => {
  filters.keyword = ''
  filters.status = ''
  filters.supplier_id = null
  filters.amount_min = null
  filters.amount_max = null
  filters.date_range = null
  page.value = 1
  fetchData()
}

const addItem = () => {
  poForm.items.push({ product_id: null, quantity: 1, unit_price: 0 })
}

const onProductSelect = (index: number, productId: number) => {
  const prod = products.value.find(p => p.id === productId)
  if (prod) {
    poForm.items[index].unit_price = prod.purchase_price || 0
  }
}

const statusType = (s: string) => ({
  draft: 'info', pending_approval: 'warning', approved: 'primary',
  partially_received: '', completed: 'success', cancelled: 'danger',
}[s] || 'info')

const statusLabel = (s: string) => ({
  draft: '草稿', pending_approval: '待审批', approved: '已审批',
  partially_received: '部分收货', completed: '已完成', cancelled: '已取消',
}[s] || s)

const getSupplierName = (id: number) => suppliers.value.find(s => s.id === id)?.name || `#${id}`

const handleSizeChange = (val: number) => {
  pageSize.value = val
  page.value = 1
  fetchData()
}

const buildFilterParams = () => {
  const params: any = { page: page.value, page_size: pageSize.value }
  if (filters.keyword) params.keyword = filters.keyword
  if (filters.status) params.status = filters.status
  if (filters.supplier_id) params.supplier_id = filters.supplier_id
  if (filters.amount_min !== null) params.amount_min = filters.amount_min
  if (filters.amount_max !== null) params.amount_max = filters.amount_max
  if (filters.date_range) {
    params.date_from = filters.date_range[0]
    params.date_to = filters.date_range[1]
  }
  return params
}

const fetchData = async () => {
  loading.value = true
  try {
    const orderRes: any = await purchaseApi.list(buildFilterParams())
    orders.value = orderRes.items || []
    total.value = orderRes.total || 0
  } finally {
    loading.value = false
  }
}

const fetchDropdowns = async () => {
  try {
    const [supRes, prodRes, whRes] = await Promise.all([
      supplierApi.list({ page: 1, page_size: 100 }),
      productApi.list({ page: 1, page_size: 100 }),
      inventoryApi.warehouses.list(),
    ]) as any[]
    suppliers.value = supRes.items || []
    products.value = prodRes.items || []
    warehouses.value = whRes || []
  } catch {
    // 下拉数据加载失败不影响主表
  }
}

const handleSelectionChange = (rows: any[]) => {
  selectedRows.value = rows
}

const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定删除该采购订单吗？', '提示').then(async () => {
    await purchaseApi.delete(id)
    ElMessage.success('删除成功')
    fetchData()
  }).catch(() => {})
}

const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 个订单吗？`, '提示')
    for (const row of selectedRows.value) {
      await purchaseApi.delete(row.id)
    }
    ElMessage.success('批量删除成功')
    selectedRows.value = []
    fetchData()
  } catch {
    // cancelled or error
  }
}

const handleImport = () => {
  ElMessage.info('导入功能开发中')
}

const openCreateDialog = () => {
  Object.assign(poForm, { supplier_id: null, expected_delivery_date: null, remark: '', items: [] })
  createVisible.value = true
}

const handleCreateOrder = async () => {
  if (!poForm.supplier_id || poForm.items.length === 0) {
    ElMessage.warning('请选择供应商并添加明细')
    return
  }
  saving.value = true
  try {
    await purchaseApi.create(poForm)
    ElMessage.success('创建成功')
    createVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

const handleApprove = async (id: number) => {
  await purchaseApi.approve(id)
  ElMessage.success('审批通过')
  fetchData()
}

const openInbound = (orderId: number) => {
  inboundOrderId.value = orderId
  inboundForm.warehouse_id = null
  inboundForm.remark = ''
  inboundVisible.value = true
}

const handleInbound = async () => {
  if (!inboundForm.warehouse_id) {
    ElMessage.warning('请选择仓库')
    return
  }
  saving.value = true
  try {
    await purchaseApi.inbound({ ...inboundForm, order_id: inboundOrderId.value })
    ElMessage.success('入库成功')
    inboundVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

const viewDetail = async (order: any) => {
  try {
    const res: any = await purchaseApi.get(order.id)
    currentOrder.value = res.order
    orderItems.value = res.items || []
    detailVisible.value = true
  } catch (_) {}
}

onMounted(() => {
  fetchDropdowns()
  fetchData()
})
</script>

<style scoped>
.search-buttons {
  display: flex;
  gap: 10px;
}
</style>
