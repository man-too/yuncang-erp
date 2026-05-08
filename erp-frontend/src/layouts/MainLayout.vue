<template>
  <el-container style="height: 100vh">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" style="background: rgba(64, 158, 255, 0.15); backdrop-filter: blur(8px); transition: width 0.3s">
      <div class="logo" @click="router.push('/dashboard')">
        <span v-show="!isCollapse" style="color: #1a3a5c; font-size: 18px; font-weight: bold;">📦 供应链ERP</span>
        <span v-show="isCollapse" style="color: #1a3a5c; font-size: 18px;">📦</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        background-color="rgba(64, 158, 255, 0.15)"
        text-color="#1a3a5c"
        active-text-color="#409EFF"
        router
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/supplier">
          <el-icon><Truck /></el-icon>
          <span>供应商管理</span>
        </el-menu-item>
        <el-menu-item index="/product">
          <el-icon><Box /></el-icon>
          <span>产品管理</span>
        </el-menu-item>
        <el-menu-item index="/purchase">
          <el-icon><ShoppingCart /></el-icon>
          <span>采购管理</span>
        </el-menu-item>
        <el-menu-item index="/inventory">
          <el-icon><Coin /></el-icon>
          <span>库存管理</span>
        </el-menu-item>
        <el-menu-item index="/sales">
          <el-icon><Shop /></el-icon>
          <span>销售管理</span>
        </el-menu-item>
        <el-menu-item index="/ai-decision">
          <el-icon><MagicStick /></el-icon>
          <span>AI 智能决策</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部栏 -->
      <el-header style="background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); display: flex; align-items: center; justify-content: space-between; padding: 0 20px;">
        <div style="display: flex; align-items: center;">
          <el-button :icon="isCollapse ? 'Expand' : 'Fold'" text @click="toggleCollapse" />
          <el-breadcrumb separator="/" style="margin-left: 16px;">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <el-dropdown>
            <span style="cursor: pointer; display: flex; align-items: center; gap: 4px;">
              <el-icon><User /></el-icon>
              {{ username }}
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 主内容 -->
      <el-main style="background: #f0f5ff; padding: 16px; overflow-y: auto;">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'

const router = useRouter()
const route = useRoute()
const isCollapse = ref(false)
const username = ref(localStorage.getItem('username') || '管理员')

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value
}

const logout = () => {
  ElMessageBox.confirm('确定退出登录吗？', '提示').then(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    router.push('/login')
  }).catch(() => {})
}
</script>

<style scoped>
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
</style>
