<script setup lang="ts">
// 根组件：承载路由出口；按需引入下用 ConfigProvider 提供中文语言包
import zhCn from "element-plus/es/locale/lang/zh-cn";
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>
