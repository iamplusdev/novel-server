<script setup lang="ts">
/** 关键词命中高亮：无 query 时按普通文本渲染 */
import { computed } from "vue";
import { highlightParts } from "@/utils/highlight";

const props = defineProps<{
  text: string;
  query?: string;
}>();

const parts = computed(() => highlightParts(props.text || "", props.query || ""));
</script>

<template>
  <template v-for="(part, i) in parts" :key="i">
    <mark v-if="part.hit" class="search-mark">{{ part.text }}</mark>
    <span v-else>{{ part.text }}</span>
  </template>
</template>

<style scoped>
.search-mark {
  padding: 0 1px;
  border-radius: 2px;
  background: var(--color-accent-soft);
  color: var(--color-accent);
}
</style>
