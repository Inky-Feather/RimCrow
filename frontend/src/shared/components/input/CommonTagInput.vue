<!-- components/common/input/CommonTagInput.vue -->
<template>
  <div class="w-full">
    <label class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1 mb-1">
      {{ label }}
      <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
    </label>
    
    <div class="input-glass p-1.5 flex flex-wrap gap-1.5 min-h-6 content-start focus-within:border-accent-primary/40">
      
      <!-- 已有 Tag -->
      <transition-group name="list">
        <span v-for="tag in modelValue" :key="tag" 
          class="flex items-center gap-1.5 px-2 py-0.5 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm text-accent-primary font-mono group animate-in">
          {{ tag }}
          <button @click="remove(tag)" class="opacity-50 hover:opacity-100 hover:text-text-main transition-opacity">×</button>
        </span>
      </transition-group>

      <!-- 输入框 -->
      <div class="relative flex-1 flex" ref="tagInputContainer">
        <input 
          v-model="newTag"
          @keydown.up.prevent="navTag(-1)" 
          @keydown.down.prevent="navTag(1)" 
          @keydown.esc="showTagSuggest = false" 
          @focus="showTagSuggest = true" 
          @blur="handleBlur"
          @keydown.enter.prevent="confirmAddTag"
          @keydown.backspace="handleBackspace"
          :placeholder="placeholder || '输入并回车...'"
          class="flex-1 min-w-20 bg-transparent border-none outline-none text-sm text-text-main py-1 px-1"
        />
        
        <!-- 标签建议下拉框 -->
        <div v-if="showTagSuggest && filteredKnownTags.length > 0" 
            class="popover-surface absolute bottom-full left-0 z-50 mb-1 flex max-h-40 w-48 flex-col overflow-y-auto rounded-lg p-1">
          <button 
            v-for="(tag, idx) in filteredKnownTags" 
            :key="tag.value"  
            @mousedown="addTag(tag.value)" 
            class="text-left px-2 py-1.5 text-xs rounded hover:bg-accent-primary/20 hover:text-accent-primary transition-colors truncate"
            :class="{'bg-accent-primary/10 text-accent-primary': idx === tagNavIndex}">
            <span class="font-bold">{{ tag.label }}</span>
            <span v-if="tag.label !== tag.value" class="opacity-50 ml-1">({{ tag.value }})</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  label: String,
  modelValue: { type: Array, default: () => [] },
  placeholder: String,
  description: String,
  allTags: { type: Array, default: () => [] } // 支持 ['a', 'b'] 或 [{label: 'A', value: 'a'}]
})

const emit = defineEmits(['update:modelValue'])

const newTag = ref('')
const showTagSuggest = ref(false)
const tagNavIndex = ref(0)
const tagInputContainer = ref(null)

// 1. 归一化建议数据
const normalizedTags = computed(() => {
  return props.allTags.map(item => {
    if (typeof item === 'string') {
      return { label: item, value: item }
    }
    return item
  })
})

// 2. 过滤建议列表 (排除已存在的，并进行模糊匹配)
const filteredKnownTags = computed(() => {
  const input = newTag.value.toLowerCase().trim()
  return normalizedTags.value
    .filter(t => !props.modelValue.includes(t.value)) // 排除已在结果中的
    .filter(t => 
      t.label.toLowerCase().includes(input) || 
      t.value.toLowerCase().includes(input)
    )
    .slice(0, 10) // 最多显示10个
})

// 添加标签核心逻辑
const addTag = (val) => {
  const targetValue = val?.trim()
  if (targetValue && !props.modelValue.includes(targetValue)) {
    emit('update:modelValue', [...props.modelValue, targetValue])
    newTag.value = ''
    tagNavIndex.value = 0
    showTagSuggest.value = false
  }
}

// 确认添加 (处理回车键)
const confirmAddTag = () => {
  // 如果下拉框显示且有选中项，优先添加选中项
  if (showTagSuggest.value && filteredKnownTags.value.length > 0 && tagNavIndex.value >= 0) {
    const selected = filteredKnownTags.value[tagNavIndex.value]
    addTag(selected.value)
  } else {
    // 否则直接添加输入框的内容
    addTag(newTag.value)
  }
}

// 键盘导航
const navTag = (step) => {
  if (!showTagSuggest.value) {
    showTagSuggest.value = true
    return
  }
  const len = filteredKnownTags.value.length
  if (len === 0) return
  tagNavIndex.value = (tagNavIndex.value + step + len) % len
}

// 移除标签
const remove = (tag) => {
  emit('update:modelValue', props.modelValue.filter(t => t !== tag))
}

// 处理退格键删除最后一个
const handleBackspace = () => {
  if (newTag.value === '' && props.modelValue.length > 0) {
    remove(props.modelValue[props.modelValue.length - 1])
  }
}

// 失去焦点处理 (使用 mousedown 替代 click 防止 blur 冲突)
const handleBlur = () => {
  // 延迟关闭，让点击建议列表的操作能够先触发
  setTimeout(() => {
    showTagSuggest.value = false
    tagNavIndex.value = 0
  }, 200)
}
</script>

<style scoped>
/* 简单的过渡动画 */
.list-enter-active,
.list-leave-active {
  transition: all 0.2s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: scale(0.9);
}
</style>
