<template>
  <!-- 外层横向排列，加 gap 控制图标与内容间距。 -->
  <div class="bg-bg-overlay/5 rounded-lg p-1 flex items-center border border-border-base/5 gap-0">
    <!-- 图标插槽：flex-shrink-0 防止图标被压缩，可选插槽无内容时不占业务状态。 -->
    <slot />
    <div class="flex flex-col items-center flex-1 min-w-10">
      <span class="text-lg font-bold leading-none" :class="highlight && value > 0 ? 'text-accent-primary' : 'text-text-dim'">{{ value }}</span>
      <span class="text-[0.7rem] text-text-dim uppercase scale-90">{{ label }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: Number, default: 0 },
  highlight: { type: Boolean, default: false },
})
</script>
