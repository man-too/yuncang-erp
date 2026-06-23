<template>
  <el-container class="app-layout">
    <!-- 侧边栏 — 领星深色风格 #0b1019 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="app-sidebar">
      <div class="sidebar-logo" @click="router.push('/dashboard')">
        <span v-show="!isCollapse" class="sidebar-logo-text">供应链ERP</span>
        <span v-show="isCollapse" class="sidebar-logo-icon">ERP</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        class="sidebar-menu"
        router
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/supplier">
          <el-icon><Van /></el-icon>
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
      <!-- 顶部栏 — 白底+底边框 -->
      <el-header class="app-header">
        <div class="header-left">
          <el-button :icon="isCollapse ? Expand : Fold" text class="header-collapse-btn" @click="toggleCollapse" />
          <el-breadcrumb separator="/" class="header-breadcrumb">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown>
            <span class="header-user">
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
      <el-main class="app-main">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['AIDecision', 'Dashboard']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Expand, Fold } from '@element-plus/icons-vue'

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
/* ===================== Layout ===================== */
.app-layout {
  height: 100vh;
}

/* ===================== Sidebar ===================== */
.app-sidebar {
  background: var(--bg-sidebar);
  transition: width var(--transition-slow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-logo {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: var(--color-primary);
  border-bottom: 1px solid rgba(255, 255, 255, 0.10);
  flex-shrink: 0;
}

.sidebar-logo-text {
  color: var(--text-inverse);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.sidebar-logo-icon {
  color: var(--text-inverse);
  font-size: var(--font-size-lg);
}

.sidebar-menu {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  border-right: none;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 220px;
}

/* ===================== Header ===================== */
.app-header {
  background: var(--bg-header);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-lg);
  height: var(--header-height);
  border-bottom: 1px solid var(--border-light);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-breadcrumb {
  margin-left: var(--spacing-md);
}

.header-right {
  display: flex;
  align-items: center;
}

.header-user {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  color: var(--text-header-secondary);
  font-size: var(--font-size-sm);
}

.header-user:hover {
  color: var(--text-header);
}

/* ===================== Main ===================== */
.app-main {
  background: var(--bg-page);
  padding: var(--spacing-lg);
  overflow-y: auto;
  min-height: 0;
}
</style>
