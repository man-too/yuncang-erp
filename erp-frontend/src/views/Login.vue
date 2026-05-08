<template>
  <div class="login-container">
    <div class="login-card">
      <h2 style="text-align: center; margin-bottom: 24px;">供应链ERP管理系统</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="handleLogin">
            {{ isRegister ? '注册' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div style="text-align: center;">
        <el-link type="primary" @click="toggleMode">
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
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
</style>
