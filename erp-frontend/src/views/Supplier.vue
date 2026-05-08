<template>
  <div class="page-container">
    <el-card shadow="never">
      <!-- 1. 顶部标题区 -->
      <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <h2 style="margin: 0;">供应商管理</h2>
      </div>

      <!-- 2. 中部筛选区 -->
      <div class="filter-bar" style="background: #f5f7fa; padding: 16px; border-radius: 6px; margin-bottom: 16px;">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-input v-model="filters.keyword" placeholder="名称/编码模糊搜索" clearable size="default" />
          </el-col>
          <el-col :span="6">
            <el-select v-model="filters.status" placeholder="状态" clearable style="width: 100%" size="default">
              <el-option label="全部" value="" />
              <el-option label="启用" value="active" />
              <el-option label="停用" value="inactive" />
              <el-option label="待审核" value="pending" />
              <el-option label="黑名单" value="blacklisted" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-input v-model="filters.contact" placeholder="联系人" clearable size="default" />
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
            <el-input-number v-model="filters.min_rating" :min="0" :max="5" :step="0.5" placeholder="最低评分" style="width: 100%" />
          </el-col>
          <el-col :span="8">
            <el-date-picker
              v-model="filters.date_range"
              type="daterange"
              range-separator="至"
              start-placeholder="创建日期起"
              end-placeholder="创建日期止"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              size="default"
            />
          </el-col>
        </el-row>
      </div>

      <!-- 3. 功能按钮区 -->
      <div class="action-bar" style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          批量删除 {{ selectedRows.length > 0 ? '(' + selectedRows.length + ')' : '' }}
        </el-button>
        <el-button @click="handleImport">导入</el-button>
        <el-button type="primary" @click="openCreateDialog()">新增</el-button>
      </div>

      <!-- 4. 表格区域 -->
      <el-table :data="suppliers" v-loading="loading" stripe style="width: 100%"
                @selection-change="handleSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="code" label="编码" width="120" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="contact_person" label="联系人" width="120" />
        <el-table-column prop="phone" label="电话" width="140" />
        <el-table-column prop="delivery_lead_time" label="交期(天)" width="100" />
        <el-table-column prop="rating" label="评分" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'inactive' ? 'info' : 'warning'">
              {{ { active: '启用', inactive: '停用', pending: '待审核', blacklisted: '黑名单' }[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑供应商' : '新增供应商'" width="600px">
      <el-form ref="formRef" :model="form" label-width="100px">
        <el-form-item label="编码" prop="code" required>
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="联系人">
              <el-input v-model="form.contact_person" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="电话">
              <el-input v-model="form.phone" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="地址">
          <el-input v-model="form.address" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="交期(天)">
              <el-input-number v-model="form.delivery_lead_time" :min="1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="税号">
              <el-input v-model="form.tax_id" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="付款条件">
          <el-input v-model="form.payment_terms" />
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
import { ref, onMounted, shallowReactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { supplierApi } from '@/api'

const suppliers = ref<any[]>([])
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

const form = shallowReactive({
  code: '', name: '', contact_person: '', phone: '', email: '',
  address: '', tax_id: '', payment_terms: '', delivery_lead_time: 7, remark: '',
})

const filters = shallowReactive({
  keyword: '',
  status: '',
  contact: '',
  min_rating: null as number | null,
  date_range: null as [string, string] | null,
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
    if (filters.status) params.status = filters.status
    if (filters.contact) params.contact = filters.contact
    if (filters.min_rating !== null && filters.min_rating !== undefined) params.min_rating = filters.min_rating
    if (filters.date_range) {
      params.date_from = filters.date_range[0]
      params.date_to = filters.date_range[1]
    }
    const res: any = await supplierApi.list(params)
    suppliers.value = res.items || []
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
  filters.status = ''
  filters.contact = ''
  filters.min_rating = null
  filters.date_range = null
  page.value = 1
  fetchData()
}

const handleSelectionChange = (rows: any[]) => {
  selectedRows.value = rows
}

const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 个供应商吗？`, '提示')
    for (const row of selectedRows.value) {
      await supplierApi.delete(row.id)
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
  Object.assign(form, { code: '', name: '', contact_person: '', phone: '', email: '', address: '', tax_id: '', payment_terms: '', delivery_lead_time: 7, remark: '' })
  dialogVisible.value = true
}

const openEditDialog = async (row: any) => {
  isEdit.value = true
  editId.value = row.id
  try {
    const fresh: any = await supplierApi.get(row.id)
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
      await supplierApi.update(editId.value, form)
      ElMessage.success('更新成功')
    } else {
      await supplierApi.create(form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定删除该供应商吗？', '提示').then(async () => {
    await supplierApi.delete(id)
    ElMessage.success('删除成功')
    fetchData()
  }).catch(() => {})
}

onMounted(fetchData)
</script>

<style scoped>
.search-buttons {
  display: flex;
  gap: 10px;
}
</style>
