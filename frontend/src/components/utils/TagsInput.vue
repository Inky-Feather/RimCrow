<template>
  <div 
    class="flex flex-wrap items-center gap-1.5 w-full px-2 py-1.5 rounded-lg bg-bg-deep/30 border transition-all cursor-text"
    :class="isFocused ? 'border-accent-primary bg-bg-deep/50' : 'border-white/10 hover:border-white/20'"
    @click="inputRef.focus()"
  >
    <!-- 渲染已生成的标签 -->
    <div 
      v-for="(tag, index) in modelValue" 
      :key="tag"
      class="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-bold animate-fade-in"
      :class="getTagStyle(tag)"
    >
      <span>{{ tag }}</span>
      <!-- 删除按钮 -->
      <button 
        @click.stop="removeTag(index)"
        class="hover:text-white/80 text-white/40 transition-colors"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>

    <!-- 输入框 -->
    <input
      ref="inputRef"
      v-model="inputValue"
      type="text"
      class="flex-1 min-w-[60px] bg-transparent border-none outline-none text-sm text-white placeholder:text-text-dim"
      :placeholder="modelValue.length > 0 ? '' : placeholder"
      @keydown.enter.prevent="addTag"
      @keydown.backspace="handleBackspace"
      @keydown.delete="handleBackspace"
      @focus="isFocused = true"
      @blur="isFocused = false"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // v-model 绑定的标签数组
  placeholder: { type: String, default: '输入搜索条件 (如 t:核心)...' }
})

const emit = defineEmits(['update:modelValue', 'search'])

const inputRef = ref(null)
const inputValue = ref('')
const isFocused = ref(false)

// 根据标签内容返回不同的颜色样式
const getTagStyle = (tag) => {
  if (tag.startsWith('t:') || tag.startsWith('tag:')) return 'bg-accent-primary/20 text-accent-primary border border-accent-primary/20'
  if (tag.startsWith('n:') || tag.startsWith('name:')) return 'bg-accent-success/20 text-accent-success border border-accent-success/20'
  if (tag.startsWith('a:') || tag.startsWith('author:')) return 'bg-accent-warning/20 text-accent-warning border border-accent-warning/20'
  // 默认样式
  return 'bg-white/10 text-text-main border border-white/10'
}

// 添加标签
const addTag = () => {
  const val = inputValue.value.trim()
  if (!val) return
  
  // 防止重复
  if (!props.modelValue.includes(val)) {
    const newTags = [...props.modelValue, val]
    emit('update:modelValue', newTags)
    emit('search', newTags) // 触发搜索事件
  }
  inputValue.value = ''
}

// 删除标签
const removeTag = (index) => {
  const newTags = [...props.modelValue]
  newTags.splice(index, 1)
  emit('update:modelValue', newTags)
  emit('search', newTags)
}

// 处理退格键（删除最后一个）
const handleBackspace = (e) => {
  if (inputValue.value === '' && props.modelValue.length > 0) {
    removeTag(props.modelValue.length - 1)
  }
}
</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}
</style>