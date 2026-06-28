<!-- utils/SearchTag.vue -->
<template>
  <div class="max-w-20 mt-0.5 flex items-center h-min py-0 px-0.5 mr-1 rounded-md text-xs border transition-colors select-none group"
       :class="tagStyle">
    
    <!-- 排除标记 -->
    <span v-if="tag.exclude" class="text-accent-danger font-bold">-</span>
    
    <!-- 键 -->
    <span v-if="tag.key" class="opacity-70">{{ tag.originalKey }}:</span>
    
    <!-- 值区域 -->
    <div v-tooltip="tag.value" class="flex-1 font-medium truncate min-w-0 relative">
      <!-- 编辑模式 -->
      <input v-if="isEditing" v-model="localValue" ref="inputRef" type="text" 
             class="min-w-20 w-full bg-transparent outline-none p-0 border-none text-current placeholder-current font-medium leading-none"
             @blur="handleCancel"
             @keyup.enter="handleSave"
             @keyup.esc="handleCancel"
      />
      <!-- 展示模式 -->
      <span v-else @dblclick="$emit('edit-start')" class="cursor-text block truncate">
        {{ tag.value }}
      </span>
    </div>

    <!-- 删除按钮 -->
    <button @click.stop="$emit('remove')"
            class="w-0 group-hover:w-4 overflow-hidden transition-all duration-200 text-current hover:text-accent-danger flex items-center justify-end">
      <svg class="shrink-0 size-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
    </button>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'

const props = defineProps({
  tag: { type: Object, required: true },
  isEditing: { type: Boolean, default: false }
})

const emit = defineEmits(['remove', 'edit-start', 'update-value', 'edit-cancel'])

const inputRef = ref(null)
const localValue = ref('')

// 计算样式（逻辑从父组件移过来）
// 注意：需要把父组件的 colorPalette 逻辑也移过来，或者通过 Props 传入颜色类名
// 这里为了演示，假设把 getTagStyle 逻辑封装到了一个单独的 js 文件，或者直接复制过来
const tagStyle = computed(() => {
    const colorPalette = [
        { bg: 'bg-accent-cool/10', border: 'border-accent-cool/20', text: 'text-accent-cool' },
        { bg: 'bg-accent-success/10', border: 'border-accent-success/20', text: 'text-accent-success' },
        { bg: 'bg-accent-special/10', border: 'border-accent-special/20', text: 'text-accent-special' },
        { bg: 'bg-accent-warn/10', border: 'border-accent-warn/20', text: 'text-accent-warn' },
        { bg: 'bg-accent-highlight/10', border: 'border-accent-highlight/20', text: 'text-accent-highlight' },
        { bg: 'bg-accent-primary/10', border: 'border-accent-primary/20', text: 'text-accent-primary' },
    ]
    const hashString = (str) => {
        let hash = 0;
        for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
        return Math.abs(hash);
    }

    if (props.tag.exclude) return 'bg-accent-danger/10 border-accent-danger/20 text-accent-danger'
    if (!props.tag.key) return 'bg-bg-overlay/5 border-border-base/10 text-text-soft'
    
    const index = hashString(props.tag.key) % colorPalette.length
    const theme = colorPalette[index]
    return `${theme.bg} ${theme.border} ${theme.text}`
})

// 自动聚焦逻辑：当变为编辑状态时，聚焦输入框
watch(() => props.isEditing, (newVal) => {
  if (newVal) {
    localValue.value = props.tag.value
    nextTick(() => {
      inputRef.value?.focus()
    })
  }
})

const handleSave = () => {
  // 如果值没变或为空，由父组件决定是否删除或保留
  emit('update-value', localValue.value) 
}

const handleCancel = () => {
  emit('edit-cancel')
}
</script>
