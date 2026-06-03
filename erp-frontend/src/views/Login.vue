<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-brand">
        <div class="login-brand-icon">📦</div>
        <h1 class="login-brand-name">供应链ERP</h1>
      </div>
      <h2 class="login-title">{{ isRegister ? '创建账号' : '登录系统' }}</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="login-submit" @click="handleLogin">
            {{ isRegister ? '注册' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <el-link type="primary" :underline="false" @click="toggleMode">
          {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
        </el-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowReactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api'
import type { FormInstance } from 'element-plus'

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)
const isRegister = ref(false)

const form = shallowReactive({
  username: 'admin',
  password: 'admin123',
  email: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const toggleMode = () => {
  isRegister.value = !isRegister.value
}

const handleLogin = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (isRegister.value) {
      await authApi.register({
        ...form,
        display_name: form.username,
      })
      ElMessage.success('注册成功，请登录')
      isRegister.value = false
    } else {
      const res: any = await authApi.login({
        username: form.username,
        password: form.password,
      })
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('username', form.username)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ===================== Container ===================== */
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--bg-sidebar);
  background-image:
    radial-gradient(circle at 15% 30%, rgba(255, 255, 255, 0.03) 0%, transparent 50%),
    radial-gradient(circle at 85% 70%, rgba(200, 152, 60, 0.06) 0%, transparent 50%),
    radial-gradient(circle at 50% 50%, rgba(30, 58, 95, 0.4) 0%, transparent 70%);
}

/* ===================== Card ===================== */
.login-card {
  width: 420px;
  padding: 44px 40px 36px;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--border-light);
}

/* ===================== Brand Section ===================== */
.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 28px;
}

.login-brand-icon {
  font-size: 40px;
  line-height: 1;
  margin-bottom: var(--spacing-sm);
}

.login-brand-name {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0;
  letter-spacing: 1px;
}

/* ===================== Title ===================== */
.login-title {
  text-align: center;
  margin-bottom: 28px;
  color: var(--text-regular);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  position: relative;
}

.login-title::after {
  content: '';
  display: block;
  width: 36px;
  height: 3px;
  background: var(--color-accent);
  margin: 10px auto 0;
  border-radius: 2px;
}

/* ===================== Submit Button ===================== */
.login-submit {
  width: 100%;
  margin-top: var(--spacing-sm);
}

/* ===================== Footer ===================== */
.login-footer {
  text-align: center;
  margin-top: var(--spacing-sm);
}
</style>
