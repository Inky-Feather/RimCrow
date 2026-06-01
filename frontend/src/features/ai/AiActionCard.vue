<template>
  <div class="group/action rounded-xl border p-2.5 transition-all duration-300" :class="theme.card">
    <div class="mb-1 flex items-center justify-between">
      <span class="text-xs font-bold" :class="theme.title">{{ title }}</span>
    </div>
    <div v-if="hasPreviewParts" class="mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-relaxed" :class="theme.preview">
      <template v-for="part in previewParts" :key="part.key">
        <span v-if="part.type === 'text'" class="whitespace-pre-wrap">{{ part.text }}</span>
        <template v-else>
          <span v-for="item in part.items" :key="item.key" v-preview="item.previewData"
            class="inline-flex min-w-0 max-w-full items-center rounded-md border px-1.5 py-0.5 text-xs font-bold leading-tight"
            :class="subjectTheme(item).chip" >
            <span class="truncate">{{ item.display }}</span>
          </span>
        </template>
      </template>
    </div>
    <p v-else-if="preview" class="mb-2 text-shadow-2xs leading-relaxed" :class="theme.preview">
      {{ preview }}
    </p>
    <p v-else-if="description" class="mb-2 text-xs leading-relaxed text-text-dim">{{ description }}</p>

    <button @click="$emit('execute', action)"
      class="flex w-full items-center justify-center gap-1 rounded-lg border py-1.5 text-xs font-bold transition-all duration-300"
      :class="theme.button" >
      <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
      {{ executeLabel }}
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// -----------------------------------------------------------------
// Props / Emits
// -----------------------------------------------------------------
const props = defineProps({
  action: { type: Object, required: true },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  preview: { type: String, default: '' },
  previewParts: { type: Array, default: () => [] },
  executeLabel: { type: String, default: '执行操作' },
  tone: { type: String, default: 'accent' },
})

defineEmits(['execute'])

// -----------------------------------------------------------------
// 视觉映射 (View Theme)
// -----------------------------------------------------------------
const toneThemeMap = {
  accent: {
    card: 'bg-linear-to-b from-text-main/5 to-transparent border-border-base/10 hover:border-accent-special/50',
    title: 'text-accent-special',
    preview: 'text-text-soft',
    button: 'border-accent-special/20 bg-accent-special/10 text-accent-special hover:border-transparent hover:bg-accent-special hover:text-on-accent-special',
  },
  success: {
    card: 'bg-linear-to-b from-accent-success/10 to-transparent border-accent-success/22 hover:border-accent-success/45',
    title: 'text-accent-success',
    preview: 'text-text-soft',
    button: 'border-accent-success/25 bg-accent-success/12 text-accent-success hover:border-transparent hover:bg-accent-success hover:text-on-accent-success',
  },
  warn: {
    card: 'bg-linear-to-b from-accent-warn/10 to-transparent border-accent-warn/22 hover:border-accent-warn/45',
    title: 'text-accent-warn',
    preview: 'text-text-soft',
    button: 'border-accent-warn/25 bg-accent-warn/12 text-accent-warn hover:border-transparent hover:bg-accent-warn hover:text-on-accent-warn',
  },
  warning: {
    card: 'bg-linear-to-b from-accent-warning/10 to-transparent border-accent-warning/22 hover:border-accent-warning/45',
    title: 'text-accent-warning',
    preview: 'text-text-soft',
    button: 'border-accent-warning/25 bg-accent-warning/12 text-accent-warning hover:border-transparent hover:bg-accent-warning hover:text-on-accent-warning',
  },
  primary: {
    card: 'bg-linear-to-b from-accent-primary/10 to-transparent border-accent-primary/22 hover:border-accent-primary/45',
    title: 'text-accent-primary',
    preview: 'text-text-soft',
    button: 'border-accent-primary/25 bg-accent-primary/12 text-accent-primary hover:border-transparent hover:bg-accent-primary hover:text-on-accent-primary',
  },
  danger: {
    card: 'bg-linear-to-b from-accent-danger/10 to-transparent border-accent-danger/22 hover:border-accent-danger/45',
    title: 'text-accent-danger',
    preview: 'text-text-soft',
    button: 'border-accent-danger/25 bg-accent-danger/12 text-accent-danger hover:border-transparent hover:bg-accent-danger hover:text-on-accent-danger',
  },
}

const subjectToneMap = {
  special: {
    chip: 'border-accent-special/18 bg-accent-special/8 text-accent-special',
  },
  success: {
    chip: 'border-accent-success/18 bg-accent-success/8 text-accent-success',
  },
  warn: {
    chip: 'border-accent-warn/18 bg-accent-warn/8 text-accent-warn',
  },
  warning: {
    chip: 'border-accent-warning/18 bg-accent-warning/8 text-accent-warning',
  },
  primary: {
    chip: 'border-accent-primary/18 bg-accent-primary/8 text-accent-primary',
  },
  danger: {
    chip: 'border-accent-danger/18 bg-accent-danger/8 text-accent-danger',
  },
  neutral: {
    chip: 'border-border-base/10 bg-bg-overlay/5 text-text-main',
  },
}

// -----------------------------------------------------------------
// 计算属性 (Computed)
// -----------------------------------------------------------------
const theme = computed(() => toneThemeMap[props.tone] || toneThemeMap.accent)
const hasPreviewParts = computed(() => Array.isArray(props.previewParts) && props.previewParts.length > 0)
const subjectTheme = (item) => subjectToneMap[String(item?.tone || '').trim().toLowerCase()] || subjectToneMap.neutral
</script>
