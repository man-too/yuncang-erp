<template>
  <div class="page-container">
    <!-- 客户管理 -->
    <el-card shadow="never" style="margin-bottom: 16px;">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">客户管理</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="cFilters.keyword" placeholder="名称/编码模糊搜索" size="default" clearable />
          </el-col>
          <el-col :span="6">
            <el-input v-model="cFilters.contact" placeholder="联系人" size="default" clearable />
          </el-col>
          <el-col :span="6">
            <el-select v-model="cFilters.is_active" placeholder="状态" size="default" clearable style="width: 100%">
              <el-option label="全部" value="" />
              <el-option label="启用" :value="true" />
              <el-option label="禁用" :value="false" />
            </el-select>
          </el-col>
          <el-col :span="6" style="display: flex; justify-content: flex-end; align-items: center;">
            <div class="search-buttons">
              <el-button type="primary" size="small" @click="handleCustomerSearch">搜索</el-button>
              <el-button size="small" @click="handleCustomerReset">重置</el-button>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 12px;">
          <el-col :span="4">
            <el-input-number v-model="cFilters.credit_min" :min="0" :precision="2" placeholder="信用额度最低" size="default" style="width: 100%;" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="cFilters.credit_max" :min="0" :precision="2" placeholder="信用额度最高" size="default" style="width: 100%;" />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="danger" :disabled="selectedCRows.length === 0" @click="handleBatchDeleteCustomer">
          批量删除 {{ selectedCRows.length > 0 ? '(' + selectedCRows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImportCustomer">导入</el-button>
        <el-button type="primary" @click="openCreateCustomerDialog()">新增</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="customers" v-loading="cLoading" stripe
                @selection-change="handleCSelectionChange" ref="cTableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="code" label="编码" width="100" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="contact_person" label="联系人" width="100" />
        <el-table-column prop="phone" label="电话" width="130" />
        <el-table-column prop="credit_limit" label="信用额度" width="120" align="right" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditCustomerDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteCustomer(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 销售订单 -->
    <el-card shadow="never">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">销售订单</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="soFilters.keyword" placeholder="订单号搜索" size="default" clearable />
          </el-col>
          <el-col :span="6">
            <el-select v-model="soFilters.status" placeholder="状态" size="default" clearable style="width: 100%">
              <el-option label="全部" value="" />
              <el-option label="草稿" value="draft" />
              <el-option label="已审批" value="approved" />
              <el-option label="已完成" value="completed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select v-model="soFilters.customer_id" placeholder="客户" size="default" filterable clearable style="width: 100%">
              <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-col>
          <el-col :span="6" style="display: flex; justify-content: flex-end; align-items: center;">
            <div class="search-buttons">
              <el-button type="primary" size="small" @click="handleSOSearch">搜索</el-button>
              <el-button size="small" @click="handleSOReset">重置</el-button>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 12px;">
          <el-col :span="4">
            <el-input-number v-model="soFilters.amount_min" :min="0" :precision="2" placeholder="金额最低" size="default" style="width: 100%;" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="soFilters.amount_max" :min="0" :precision="2" placeholder="金额最高" size="default" style="width: 100%;" />
          </el-col>
          <el-col :span="8">
            <el-date-picker v-model="soFilters.date_range" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" size="default" style="width: 100%;" value-format="YYYY-MM-DD" />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="danger" :disabled="selectedSORows.length === 0" @click="handleBatchDeleteSO">
          批量删除 {{ selectedSORows.length > 0 ? '(' + selectedSORows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImportSO">导入</el-button>
        <el-button type="primary" @click="openSODialog()">新增</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="saleOrders" v-loading="loading" stripe
                @selection-change="handleSOSelectionChange" ref="soTableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="order_no" label="订单号" width="160" />
        <el-table-column label="客户" width="150">
          <template #default="{ row }">{{ getCustomerName(row.customer_id) }}</template>
        </el-table-column>
        <el-table-column prop="total_amount" label="金额" width="120" align="right" />
        <el-table-column prop="order_date" label="日期" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="soStatusType(row.status)" size="small">{{ soStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewSODetail(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteSO(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination - centered -->
      <div style="display: flex; justify-content: center; margin-top: 16px;">
        <el-pagination
          v-model:current-page="soPage"
          v-model:page-size="soPageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next, jumper"
          :total="soTotal"
          @size-change="handleSOSizeChange"
          @current-change="fetchSO"
        />
      </div>
    </el-card>

    <!-- 客户弹窗 -->
    <el-dialog v-model="cDialogVisible" :title="cIsEdit ? '编辑客户' : '新增客户'" width="500px">
      <el-form :model="cForm" label-width="100px">
        <el-form-item label="编码" required><el-input v-model="cForm.code" /></el-form-item>
        <el-form-item label="名称" required><el-input v-model="cForm.name" /></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="联系人"><el-input v-model="cForm.contact_person" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="电话"><el-input v-model="cForm.phone" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="地址"><el-input v-model="cForm.address" /></el-form-item>
        <el-form-item label="信用额度"><el-input-number v-model="cForm.credit_limit" :min="0" :precision="2" style="width: 100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveCustomer">保存</el-button>
      </template>
    </el-dialog>

    <!-- 创建销售订单弹窗 -->
    <el-dialog v-model="soDialogVisible" title="创建销售订单" width="700px">
      <el-form :model="soForm" label-width="100px">
        <el-form-item label="客户" required>
          <el-select v-model="soForm.customer_id" filterable style="width: 100%">
            <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="soForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <h3>订单明细</h3>
      <el-table :data="soForm.items" style="margin-bottom: 12px;">
        <el-table-column label="产品" width="200">
          <template #default="{ row, $index }">
            <el-select v-model="row.product_id" filterable @change="(val: number) => { const p = products.find(x => x.id === val); if(p) row.unit_price = p.sale_price }">
              <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="120">
          <template #default="{ row }"><el-input-number v-model="row.quantity" :min="1" style="width: 100px" /></template>
        </el-table-column>
        <el-table-column label="单价" width="120">
          <template #default="{ row }"><el-input-number v-model="row.unit_price" :min="0" :precision="2" style="width: 100px" /></template>
        </el-table-column>
        <el-table-column label="小计" width="100">
          <template #default="{ row }">{{ (row.quantity * row.unit_price).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }"><el-button type="danger" :icon="'Delete'" text @click="soForm.items.splice($index, 1)" /></template>
        </el-table-column>
      </el-table>
      <el-button @click="soForm.items.push({ product_id: null, quantity: 1, unit_price: 0 })">添加行</el-button>
      <template #footer>
        <el-button @click="soDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateSO">提交</el-button>
      </template>
    </el-dialog>

    <!-- 出库弹窗 -->
    <el-dialog v-model="outboundVisible" title="销售出库" width="400px">
      <el-form :model="outboundForm" label-width="100px">
        <el-form-item label="仓库" required>
          <el-select v-model="outboundForm.warehouse_id" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="outboundForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="outboundVisible = false">取消</el-button>
        <el-button type="primary" @click="handleOutbound">确认出库</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, shallowReactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { saleApi, productApi, inventoryApi } from '@/api'

const customers = ref<any[]>([])
const saleOrders = ref<any[]>([])
const products = ref<any[]>([])
const warehouses = ref<any[]>([])
const loading = ref(false)
const cLoading = ref(false)
const soPage = ref(1)
const soPageSize = ref(20)
const soTotal = ref(0)
const cDialogVisible = ref(false)
const cIsEdit = ref(false)
const cEditId = ref(0)
const soDialogVisible = ref(false)
const outboundVisible = ref(false)
const outboundOrderId = ref(0)
const selectedCRows = ref<any[]>([])
const selectedSORows = ref<any[]>([])
const cTableRef = ref()
const soTableRef = ref()

const cForm = shallowReactive({ code: '', name: '', contact_person: '', phone: '', email: '', address: '', tax_id: '', credit_limit: 0, remark: '' })
const soForm = shallowReactive({ customer_id: null, expected_delivery_date: null, remark: '', items: [] as any[] })
const outboundForm = shallowReactive({ warehouse_id: null, remark: '' })

// Filter state
const cFilters = shallowReactive({ keyword: '', contact: '', is_active: null, credit_min: null, credit_max: null })
const soFilters = shallowReactive({ keyword: '', status: '', customer_id: null, amount_min: null, amount_max: null, date_range: null })

const soStatusType = (s: string) => ({ draft: 'info', pending_approval: 'warning', approved: 'primary', partially_shipped: '', completed: 'success', cancelled: 'danger' }[s] || 'info')
const soStatusLabel = (s: string) => ({ draft: '草稿', pending_approval: '待审批', approved: '已审批', partially_shipped: '部分发货', completed: '已完成', cancelled: '已取消' }[s] || s)
const getCustomerName = (id: number) => customers.value.find(c => c.id === id)?.name || `#${id}`

const fetchCustomers = async (extraParams?: Record<string, any>) => {
  cLoading.value = true
  try {
    const params: Record<string, any> = { page: 1, page_size: 100 }
    if (cFilters.keyword) params.keyword = cFilters.keyword
    if (cFilters.contact) params.contact = cFilters.contact
    if (cFilters.is_active !== null && cFilters.is_active !== '') params.is_active = cFilters.is_active
    if (cFilters.credit_min !== null) params.credit_min = cFilters.credit_min
    if (cFilters.credit_max !== null) params.credit_max = cFilters.credit_max
    Object.assign(params, extraParams)
    const res: any = await saleApi.customers.list(params)
    customers.value = res.items || []
  } finally { cLoading.value = false }
}

const fetchSO = async (extraParams?: Record<string, any>) => {
  loading.value = true
  try {
    const params: Record<string, any> = { page: soPage.value, page_size: soPageSize.value }
    if (soFilters.keyword) params.keyword = soFilters.keyword
    if (soFilters.status) params.status = soFilters.status
    if (soFilters.customer_id !== null) params.customer_id = soFilters.customer_id
    if (soFilters.amount_min !== null) params.amount_min = soFilters.amount_min
    if (soFilters.amount_max !== null) params.amount_max = soFilters.amount_max
    if (soFilters.date_range) {
      params.date_from = soFilters.date_range[0]
      params.date_to = soFilters.date_range[1]
    }
    Object.assign(params, extraParams)
    const res: any = await saleApi.orders.list(params)
    saleOrders.value = res.items || []
    soTotal.value = res.total || 0
  } finally { loading.value = false }
}

const handleCSelectionChange = (rows: any[]) => {
  selectedCRows.value = rows
}

const handleSOSelectionChange = (rows: any[]) => {
  selectedSORows.value = rows
}

const handleDeleteCustomer = (id: number) => {
  ElMessageBox.confirm('确定删除该客户吗？', '提示').then(async () => {
    await saleApi.customers.delete(id)
    ElMessage.success('删除成功')
    fetchCustomers()
  }).catch(() => {})
}

const handleBatchDeleteCustomer = async () => {
  if (selectedCRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedCRows.value.length} 个客户吗？`, '提示')
    for (const row of selectedCRows.value) {
      await saleApi.customers.delete(row.id)
    }
    ElMessage.success('批量删除成功')
    selectedCRows.value = []
    fetchCustomers()
  } catch {
    // cancelled or error
  }
}

const handleDeleteSO = (id: number) => {
  ElMessageBox.confirm('确定删除该销售订单吗？', '提示').then(async () => {
    await saleApi.orders.delete(id)
    ElMessage.success('删除成功')
    fetchSO()
  }).catch(() => {})
}

const handleBatchDeleteSO = async () => {
  if (selectedSORows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedSORows.value.length} 个订单吗？`, '提示')
    for (const row of selectedSORows.value) {
      await saleApi.orders.delete(row.id)
    }
    ElMessage.success('批量删除成功')
    selectedSORows.value = []
    fetchSO()
  } catch {
    // cancelled or error
  }
}

const handleImportCustomer = () => {
  ElMessage.info('导入功能开发中')
}

const handleImportSO = () => {
  ElMessage.info('导入功能开发中')
}

const openCreateCustomerDialog = () => {
  cIsEdit.value = false
  cEditId.value = 0
  Object.assign(cForm, { code: '', name: '', contact_person: '', phone: '', email: '', address: '', tax_id: '', credit_limit: 0, remark: '' })
  cDialogVisible.value = true
}

const openEditCustomerDialog = (row: any) => {
  cIsEdit.value = true
  cEditId.value = row.id
  // No separate get API for customer, use row data but clear form first
  Object.assign(cForm, { code: '', name: '', contact_person: '', phone: '', email: '', address: '', tax_id: '', credit_limit: 0, remark: '' })
  Object.assign(cForm, row)
  cDialogVisible.value = true
}

const handleSaveCustomer = async () => {
  if (cIsEdit.value) {
    await saleApi.customers.update(cEditId.value, cForm)
  } else {
    await saleApi.customers.create(cForm)
  }
  ElMessage.success('保存成功')
  cDialogVisible.value = false
  fetchCustomers()
}

const handleCustomerSearch = () => {
  fetchCustomers()
}

const handleCustomerReset = () => {
  cFilters.keyword = ''
  cFilters.contact = ''
  cFilters.is_active = null
  cFilters.credit_min = null
  cFilters.credit_max = null
  fetchCustomers()
}

const handleSOSizeChange = (val: number) => {
  soPageSize.value = val
  soPage.value = 1
  fetchSO()
}

const handleSOSearch = () => {
  soPage.value = 1
  fetchSO()
}

const handleSOReset = () => {
  soFilters.keyword = ''
  soFilters.status = ''
  soFilters.customer_id = null
  soFilters.amount_min = null
  soFilters.amount_max = null
  soFilters.date_range = null
  soPage.value = 1
  fetchSO()
}

const openSODialog = () => {
  Object.assign(soForm, { customer_id: null, expected_delivery_date: null, remark: '', items: [] })
  soDialogVisible.value = true
}

const handleCreateSO = async () => {
  if (!soForm.customer_id || soForm.items.length === 0) {
    ElMessage.warning('请选择客户并添加明细')
    return
  }
  await saleApi.orders.create(soForm)
  ElMessage.success('创建成功')
  soDialogVisible.value = false
  fetchSO()
}

const openOutbound = (orderId: number) => {
  outboundOrderId.value = orderId
  outboundForm.warehouse_id = null
  outboundForm.remark = ''
  outboundVisible.value = true
}

const handleOutbound = async () => {
  if (!outboundForm.warehouse_id) { ElMessage.warning('请选择仓库'); return }
  await saleApi.outbound({ ...outboundForm, order_id: outboundOrderId.value })
  ElMessage.success('出库成功')
  outboundVisible.value = false
  fetchSO()
}

const viewSODetail = async (order: any) => {
  // 简单展示用
  ElMessage.info(`订单 ${order.order_no}: ¥${order.total_amount}`)
}

onMounted(async () => {
  const [prodRes, whRes] = await Promise.all([
    productApi.list({ page: 1, page_size: 100 }),
    inventoryApi.warehouses.list(),
  ]) as any[]
  products.value = prodRes.items || []
  warehouses.value = whRes || []
  fetchCustomers()
  fetchSO()
})
</script>

<style scoped>
.search-buttons {
  display: flex;
  gap: 10px;
}
</style>
