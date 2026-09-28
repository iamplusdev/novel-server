<script setup lang="ts">
/**
 * 登录页：P2 起接真实流程；P1 先占位保证路由可进入。
 */
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>爱小说 · 登录</template>
      <p class="muted">登录模块将在阶段 2 接入（登录 / 初始化 / 忘记密码）。</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 380px;
}
</style>
