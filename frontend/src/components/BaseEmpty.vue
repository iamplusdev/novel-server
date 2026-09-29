<script setup lang="ts">
/** 统一空状态：图标 + 标题 + 说明 + 可选行动按钮 */
import AppIcon from "@/components/AppIcon.vue";

withDefaults(
  defineProps<{
    icon?: string;
    title: string;
    description?: string;
    actionText?: string;
  }>(),
  { icon: "book", description: "", actionText: "" },
);

const emit = defineEmits<{ (e: "action"): void }>();
</script>

<template>
  <div class="base-empty">
    <div class="base-empty__icon">
      <AppIcon :name="icon" :size="28" />
    </div>
    <h3 class="base-empty__title">{{ title }}</h3>
    <p v-if="description" class="base-empty__desc muted">{{ description }}</p>
    <button v-if="actionText" type="button" class="primary-btn" @click="emit('action')">
      {{ actionText }}
    </button>
    <slot />
  </div>
</template>

<style scoped>
.base-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 24px;
  text-align: center;
  color: var(--color-text-2);
}

.base-empty__icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: var(--color-surface-2);
  color: var(--color-text-3);
  display: flex;
  align-items: center;
  justify-content: center;
}

.base-empty__title {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--color-text);
  font-weight: 600;
}

.base-empty__desc {
  margin: 0;
  max-width: 360px;
  line-height: 1.6;
}
</style>
