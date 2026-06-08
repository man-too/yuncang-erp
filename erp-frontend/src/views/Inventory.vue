<template>
  <div class="page-container">
    <el-card shadow="never" style="margin-bottom: 16px;">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">库存管理</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="filters.keyword" placeholder="产品名称/编码模糊搜索" clearable size="default" />
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.warehouse_id" placeholder="仓库" clearable style="width: 100%" size="default">
              <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.stock_status" placeholder="库存状态" clearable style="width: 100%" size="default">
              <el-option label="库存不足" value="low_stock" />
              <el-option label="库存过多" value="overstock" />
              <el-option label="正常" value="normal" />
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
          <el-col :span="6">
            <el-select v-model="filters.category_id" placeholder="产品分类" clearable style="width: 100%" size="default">
              <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-input v-model.number="filters.qty_min" placeholder="最小库存" type="number" clearable size="default" style="width: 100%" />
          </el-col>
          <el-col :span="4">
            <el-input v-model.number="filters.qty_max" placeholder="最大库存" type="number" clearable size="default" style="width: 100%" />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          批量删除 {{ selectedRows.length > 0 ? '(' + selectedRows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImport">导入</el-button>
        <el-button @click="openWarehouseDialog">新增仓库</el-button>
        <el-button type="warning" @click="showAlerts = !showAlerts">库存预警</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="stockList" v-loading="loading" stripe style="width: 100%"
                @selection-change="handleSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="product_code" label="产品编码" width="120" />
        <el-table-column prop="product_name" label="产品名称" min-width="150" />
        <el-table-column prop="warehouse_name" label="仓库" width="120" />
        <el-table-column prop="quantity" label="库存量" width="100" align="right" />
        <el-table-column prop="locked_quantity" label="锁定" width="80" align="right" />
        <el-table-column prop="available_quantity" label="可用" width="100" align="right" />
        <el-table-column prop="min_stock" label="最低库存" width="100" align="right" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.quantity <= row.min_stock" type="danger" size="small">库存不足</el-tag>
            <el-tag v-else-if="row.quantity >= row.max_stock" type="warning" size="small">库存过多</el-tag>
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="openAdjust(row)">编辑</el-button>
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
          @current-change="fetchStock"
        />
      </div>
    </el-card>

    <!-- 库存预警 -->
    <el-card v-if="showAlerts" shadow="never">
      <h3 style="margin-bottom: 16px;">库存预警列表</h3>
      <el-table :data="alerts" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="alert_type" label="类型" width="100" />
        <el-table-column prop="current_quantity" label="当前库存" width="100" />
        <el-table-column prop="ai_suggestion" label="AI建议" min-width="200" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_resolved ? 'success' : 'danger'" size="small">
              {{ row.is_resolved ? '已处理' : '未处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button v-if="!row.is_resolved" size="small" text @click="handleResolve(row.id)">编辑</el-button>
            <el-button size="small" type="danger" text @click="handleDeleteAlert(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增仓库 -->
    <el-dialog v-model="whDialogVisible" title="新增仓库" width="400px">
      <el-form :model="whForm" label-width="80px">
        <el-form-item label="编码" required><el-input v-model="whForm.code" /></el-form-item>
        <el-form-item label="名称" required><el-input v-model="whForm.name" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="whForm.address" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="whForm.manager" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="whDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateWarehouse">保存</el-button>
      </template>
    </el-dialog>

    <!-- 库存调整 -->
    <el-dialog v-model="adjustVisible" title="库存调整" width="400px">
      <el-form :model="adjustForm" label-width="100px">
        <el-form-item label="当前库存"><el-input :model-value="adjustForm.current_qty" disabled /></el-form-item>
        <el-form-item label="调整为" required><el-input-number v-model="adjustForm.new_quantity" :min="0" style="width: 100%" /></el-form-item>
        <el-form-item label="原因"><el-input v-model="adjustForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAdjust">确认调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { inventoryApi, productApi } from '@/api'

const stockList = ref<any[]>([])
const alerts = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const showAlerts = ref(false)
const whDialogVisible = ref(false)
const adjustVisible = ref(false)
const selectedRows = ref<any[]>([])
const tableRef = ref()

const warehouses = ref<any[]>([])
const categories = ref<any[]>([])
const filters = reactive({ keyword: '', warehouse_id: null, stock_status: '', category_id: null, qty_min: null, qty_max: null })

const whForm = reactive({ code: '', name: '', address: '', manager: '' })
const adjustForm = reactive({ product_id: 0, warehouse_id: 1, current_qty: 0, new_quantity: 0, remark: '' })

const handleSizeChange = (val: number) => {
  pageSize.value = val
  page.value = 1
  fetchStock()
}

const fetchStock = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.warehouse_id) params.warehouse_id = filters.warehouse_id
    if (filters.stock_status) params.stock_status = filters.stock_status
    if (filters.category_id) params.category_id = filters.category_id
    if (filters.qty_min) params.qty_min = filters.qty_min
    if (filters.qty_max) params.qty_max = filters.qty_max
    const res: any = await inventoryApi.stock(params)
    stockList.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchStock()
}

const handleReset = () => {
  filters.keyword = ''
  filters.warehouse_id = null
  filters.stock_status = ''
  filters.category_id = null
  filters.qty_min = null
  filters.qty_max = null
  page.value = 1
  fetchStock()
}

const handleSelectionChange = (rows: any[]) => {
  selectedRows.value = rows
}

const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定删除该库存记录吗？', '提示').then(async () => {
    await inventoryApi.delete(id)
    ElMessage.success('删除成功')
    fetchStock()
  }).catch(() => {})
}

const handleDeleteAlert = (id: number) => {
  ElMessageBox.confirm('确定删除该预警记录吗？', '提示').then(async () => {
    await inventoryApi.deleteAlert(id)
    ElMessage.success('删除成功')
    fetchAlerts()
  }).catch(() => {})
}

const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 条库存记录吗？`, '提示')
    for (const row of selectedRows.value) {
      await inventoryApi.delete(row.id)
    }
    ElMessage.success('批量删除成功')
    selectedRows.value = []
    fetchStock()
  } catch {
    // cancelled or error
  }
}

const handleImport = () => {
  ElMessage.info('导入功能开发中')
}

const fetchAlerts = async () => {
  try {
    const res: any = await inventoryApi.alerts({ resolved: false })
    alerts.value = res.items || res || []
  } catch {
    alerts.value = []
  }
}

const openWarehouseDialog = () => {
  whForm.code = ''; whForm.name = ''; whForm.address = ''; whForm.manager = ''
  whDialogVisible.value = true
}

const handleCreateWarehouse = async () => {
  try {
    await inventoryApi.warehouses.create(whForm)
    ElMessage.success('仓库创建成功')
    whDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  }
}

const openAdjust = (row: any) => {
  adjustForm.product_id = row.product_id
  adjustForm.warehouse_id = row.warehouse_id
  adjustForm.current_qty = row.quantity
  adjustForm.new_quantity = row.quantity
  adjustForm.remark = ''
  adjustVisible.value = true
}

const handleAdjust = async () => {
  try {
    await inventoryApi.adjust(adjustForm)
    ElMessage.success('调整成功')
    adjustVisible.value = false
    fetchStock()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '调整失败')
  }
}

const handleResolve = async (id: number) => {
  try {
    await inventoryApi.resolveAlert(id)
    ElMessage.success('已处理')
    fetchAlerts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '处理失败')
  }
}

onMounted(async () => {
  fetchStock()
  fetchAlerts()
  warehouses.value = (await inventoryApi.warehouses.list() as any) || []
  categories.value = (await productApi.categories.list() as any) || []
})
</script>

<style scoped>
.search-buttons {
  display: flex;
  gap: 10px;
}
</style>
