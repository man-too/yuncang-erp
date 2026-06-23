<template>
  <div class="page-container">
    <el-card shadow="never">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">产品管理</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="filters.keyword" placeholder="名称/编码/规格模糊搜索" clearable size="default" />
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.category_id" placeholder="选择分类" clearable style="width: 100%" size="default">
              <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.is_active" placeholder="状态" clearable style="width: 100%" size="default">
              <el-option label="启用" :value="true" />
              <el-option label="禁用" :value="false" />
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
            <el-input v-model="filters.unit" placeholder="单位" clearable size="default" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="filters.price_min" :min="0" placeholder="最低采购价" style="width: 100%" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="filters.price_max" :min="0" placeholder="最高采购价" style="width: 100%" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="filters.sale_price_min" :min="0" placeholder="最低销售价" style="width: 100%" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="filters.sale_price_max" :min="0" placeholder="最高销售价" style="width: 100%" />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="primary" plain :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          批量删除 {{ selectedRows.length > 0 ? '(' + selectedRows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImport">导入</el-button>
        <el-button type="primary" @click="openCreateDialog()">新增</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="products" v-loading="loading" stripe style="width: 100%"
                @selection-change="handleSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="code" label="编码" width="120" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="specification" label="规格" width="120" />
        <el-table-column prop="unit" label="单位" width="60" />
        <el-table-column prop="purchase_price" label="采购价" width="100" align="right" />
        <el-table-column prop="sale_price" label="销售价" width="100" align="right" />
        <el-table-column prop="min_stock" label="最低库存" width="100" align="right" />
        <el-table-column prop="max_stock" label="最高库存" width="100" align="right" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" text @click="handleDelete(row.id)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑产品' : '新增产品'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="编码" required>
              <el-input v-model="form.code" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="规格">
              <el-input v-model="form.specification" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单位">
              <el-input v-model="form.unit" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="采购价">
              <el-input-number v-model="form.purchase_price" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="销售价">
              <el-input-number v-model="form.sale_price" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="成本价">
              <el-input-number v-model="form.cost_price" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最低库存">
              <el-input-number v-model="form.min_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最高库存">
              <el-input-number v-model="form.max_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="条码">
          <el-input v-model="form.barcode" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { productApi } from '@/api'

const categories = ref<any[]>([])
const products = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const selectedRows = ref<any[]>([])
const tableRef = ref()

const filters = reactive({
  keyword: '',
  category_id: null,
  is_active: null,
  unit: '',
  price_min: null,
  price_max: null,
  sale_price_min: null,
  sale_price_max: null,
})

const form = reactive({
  code: '', name: '', specification: '', unit: '个',
  purchase_price: 0, sale_price: 0, cost_price: 0,
  min_stock: 0, max_stock: 0, barcode: '', remark: '',
})

const handleSizeChange = (val: number) => {
  pageSize.value = val
  page.value = 1
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.category_id !== null) params.category_id = filters.category_id
    if (filters.is_active !== null) params.is_active = filters.is_active
    if (filters.unit) params.unit = filters.unit
    if (filters.price_min !== null) params.price_min = filters.price_min
    if (filters.price_max !== null) params.price_max = filters.price_max
    if (filters.sale_price_min !== null) params.sale_price_min = filters.sale_price_min
    if (filters.sale_price_max !== null) params.sale_price_max = filters.sale_price_max
    const res: any = await productApi.list(params)
    products.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchData()
}

const handleReset = () => {
  filters.keyword = ''
  filters.category_id = null
  filters.is_active = null
  filters.unit = ''
  filters.price_min = null
  filters.price_max = null
  filters.sale_price_min = null
  filters.sale_price_max = null
  page.value = 1
  fetchData()
}

const handleSelectionChange = (rows: any[]) => {
  selectedRows.value = rows
}

const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 个产品吗？`, '提示')
    for (const row of selectedRows.value) {
      await productApi.delete(row.id)
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
  isEdit.value = false
  editId.value = 0
  Object.assign(form, { code: '', name: '', specification: '', unit: '个', purchase_price: 0, sale_price: 0, cost_price: 0, min_stock: 0, max_stock: 0, barcode: '', remark: '' })
  dialogVisible.value = true
}

const openEditDialog = async (row: any) => {
  isEdit.value = true
  editId.value = row.id
  try {
    const fresh: any = await productApi.get(row.id)
    Object.assign(form, fresh)
  } catch {
    ElMessage.error('获取数据失败')
  }
  dialogVisible.value = true
}

const handleSave = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await productApi.update(editId.value, form)
      ElMessage.success('更新成功')
    } else {
      await productApi.create(form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定删除该产品吗？', '提示').then(async () => {
    await productApi.delete(id)
    ElMessage.success('删除成功')
    fetchData()
  }).catch(() => {})
}

onMounted(() => {
  fetchData()
  productApi.categories.list().then((res: any) => {
    categories.value = res.items || res || []
  })
})
</script>

<style scoped>
.search-buttons {
  display: flex;
  gap: 10px;
}
</style>
