import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { productApi } from '@/api'
import type { usePurchaseDecisionStore } from '@/stores/purchaseDecision'

type PurchaseDecisionStore = ReturnType<typeof usePurchaseDecisionStore>

export function useProductDialog(store: PurchaseDecisionStore) {
  const dialogVisible = ref(false)
  const isEditing = ref(false)
  const editingProductId = ref(0)
  const productSearching = ref(false)
  const productOptions = ref<any[]>([])
  const formRef = ref<FormInstance>()
  const warehouses = ref<any[]>([])

  const dialogForm = ref({
    product_id: null as number | null,
    product_name: '', product_code: '',
    warehouse_id: null as number | null,
    specification: '', unit: '个',
  })

  const formRules: FormRules = {
    product_id: [{ required: true, message: '请选择产品', trigger: 'change' }],
    warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  }

  function openAddDialog() {
    isEditing.value = false
    editingProductId.value = 0
    dialogForm.value = {
      product_id: null, product_name: '', product_code: '',
      warehouse_id: warehouses.value[0]?.id || null,
      specification: '', unit: '个',
    }
    productOptions.value = []
    formRef.value?.resetFields()
    dialogVisible.value = true
  }

  function openEditDialog(row: any) {
    isEditing.value = true
    editingProductId.value = row.product_id
    dialogForm.value = {
      product_id: row.product_id,
      product_name: row.product_name,
      product_code: row.product_code,
      warehouse_id: row.warehouse_id,
      specification: row.specification || '',
      unit: row.unit || '个',
    }
    productOptions.value = [{ id: row.product_id, name: row.product_name, code: row.product_code }]
    formRef.value?.resetFields()
    dialogVisible.value = true
  }

  async function remoteSearchProducts(query: string) {
    if (!query || query.trim().length < 1) { productOptions.value = []; return }
    productSearching.value = true
    try {
      const res: any = await productApi.list({ keyword: query.trim(), page_size: 20 })
      productOptions.value = (res?.items || []).map((p: any) => ({
        id: p.id, name: p.name, code: p.code,
        specification: p.specification || '', unit: p.unit || '个',
        purchase_price: p.purchase_price || 0,
        min_stock: p.min_stock || 0, max_stock: p.max_stock || 0,
      }))
    } catch { productOptions.value = [] }
    finally { productSearching.value = false }
  }

  async function onDialogProductChange(productId: number) {
    const prod = productOptions.value.find(p => p.id === productId)
    if (!prod) return
    dialogForm.value.product_name = prod.name
    dialogForm.value.product_code = prod.code
    dialogForm.value.specification = prod.specification || ''
    dialogForm.value.unit = prod.unit || '个'
  }

  async function submitDialog() {
    const valid = await formRef.value?.validate().catch(() => false)
    if (!valid) return

    if (isEditing.value) {
      store.updateProduct(editingProductId.value, {
        warehouse_id: dialogForm.value.warehouse_id!,
        warehouse_name: warehouses.value.find((w: any) => w.id === dialogForm.value.warehouse_id)?.name || '',
        unit: dialogForm.value.unit,
        specification: dialogForm.value.specification,
      })
      ElMessage.success('修改已保存')
    } else {
      const matchedProd = productOptions.value.find(p => p.id === dialogForm.value.product_id)
      store.addToProducts({
        id: dialogForm.value.product_id!,
        name: dialogForm.value.product_name,
        code: dialogForm.value.product_code,
        warehouse_id: dialogForm.value.warehouse_id!,
        warehouse_name: warehouses.value.find((w: any) => w.id === dialogForm.value.warehouse_id)?.name || '默认仓库',
        current_qty: matchedProd?.current_qty || matchedProd?.quantity || 0,
        min_stock: matchedProd?.min_stock || 0,
        max_stock: matchedProd?.max_stock || 0,
        unit: dialogForm.value.unit,
        specification: dialogForm.value.specification,
        purchase_price: matchedProd?.purchase_price || 0,
      })
      ElMessage.success('产品已添加')
    }
    dialogVisible.value = false
  }

  return {
    dialogVisible,
    isEditing,
    editingProductId,
    productSearching,
    productOptions,
    formRef,
    warehouses,
    dialogForm,
    formRules,
    openAddDialog,
    openEditDialog,
    remoteSearchProducts,
    onDialogProductChange,
    submitDialog,
  }
}
