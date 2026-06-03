<template>
  <div>
    <h2 style="margin-bottom: 16px;">工作台</h2>
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="6" v-for="card in statCards" :key="card.title">
        <el-card shadow="hover" style="margin-bottom: 12px;">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-size: 12px; color: #999;">{{ card.title }}</div>
              <div style="font-size: 28px; font-weight: bold;">{{ card.value }}</div>
            </div>
            <el-icon :size="36" :color="card.color">
              <component :is="card.icon" />
            </el-icon>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>AI 决策概览</template>
          <div v-if="aiHistory.length === 0" style="text-align: center; color: #999; padding: 40px 0;">
            暂无 AI 决策数据，前往 <router-link to="/ai-decision">AI 智能决策</router-link> 页面生成
          </div>
          <el-timeline v-else>
            <el-timeline-item
              v-for="item in aiHistory"
              :key="item.id"
              :timestamp="item.created_at"
              :type="item.confidence > 0.7 ? 'primary' : 'warning'"
            >
              <strong>{{ item.title }}</strong>
              <p style="font-size: 12px; color: #666;">{{ item.summary }}</p>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>快速入口</template>
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <el-button type="primary" @click="$router.push('/purchase')">创建采购订单</el-button>
            <el-button type="success" @click="$router.push('/sales')">创建销售订单</el-button>
            <el-button type="warning" @click="$router.push('/inventory')">查看库存预警</el-button>
            <el-button type="info" @click="$router.push('/product')">管理产品</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { supplierApi, productApi, purchaseApi, aiApi } from '@/api'

const statCards = ref([
  { title: '供应商数量', value: 0, icon: 'Truck', color: '#1B3A5C' },
  { title: '产品数量', value: 0, icon: 'Box', color: '#3B8C5C' },
  { title: '采购订单', value: 0, icon: 'ShoppingCart', color: '#C88C34' },
  { title: 'AI 建议', value: 0, icon: 'MagicStick', color: '#C0393C' },
])

const aiHistory = ref<any[]>([])

onMounted(async () => {
  try {
    const [suppliers, products, orders, aiDash] = await Promise.all([
      supplierApi.list({ page: 1, page_size: 1 }),
      productApi.list({ page: 1, page_size: 1 }),
      purchaseApi.list({ page: 1, page_size: 1 }),
      aiApi.dashboard(),
    ]) as any[]

    statCards.value[0].value = suppliers.total || 0
    statCards.value[1].value = products.total || 0
    statCards.value[2].value = orders.total || 0
    statCards.value[3].value = aiDash?.total_decisions || 0

    const history: any = await aiApi.history({ limit: 5 })
    aiHistory.value = history || []
  } catch (_) {}
})
</script>
