<template>
  <div v-if="theme" class="flex shrink-0 items-center gap-1">
    <span v-for="color in colors" :key="color" class="size-4 rounded-full border border-border-base/18 shadow-sm"
      :style="{ backgroundColor: color }"
    ></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  theme: { type: Object, default: null },
})

const colors = computed(() => {
  const tokens = props.theme?.tokens || {}
  return [
    tokens.bg?.deep,
    tokens.bg?.surface,
    tokens.text?.main,
    tokens.accent?.primary,
    tokens.accent?.special,
    tokens.accent?.success,
    tokens.accent?.warn,
    tokens.accent?.danger,
  ].filter(Boolean)
})
</script>
