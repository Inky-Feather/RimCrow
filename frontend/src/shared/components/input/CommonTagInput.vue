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
        <span v-for="tag in modelValue" :key="tag" v-tooltip="tagTooltip(tag)"
          class="flex items-center max-w-[49%] gap-1.5 px-2 py-0.5 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm text-accent-primary font-mono group animate-in">
          <span class="flex-1 truncate">{{ tagLabel(tag) }}</span>
          <button @click="remove(tag)" class="opacity-50 hover:opacity-100 hover:text-accent-danger transition-opacity">×</button>
        </span>
      </transition-group>

      <!-- 输入框 -->
      <div class="relative flex-1 flex" ref="tagInputContainer">
        <input 
          v-model="newTag"
          @input="handleInput"
          @keydown.up.prevent="navTag(-1)" 
          @keydown.down.prevent="navTag(1)" 
          @keydown.esc="closeSuggest" 
          @focus="handleFocus" 
          @blur="handleBlur"
          @keydown.enter.prevent="confirmAddTag"
          @keydown.backspace="handleBackspace"
          :placeholder="placeholder || t('ui.tag.placeholder', '输入并回车...')"
          class="flex-1 min-w-20 bg-transparent border-none outline-none text-sm text-text-main py-1 px-1"
        />
        
        <FixedPopover
          :is-open="showTagSuggest && filteredKnownTags.length > 0"
          :trigger-ref="tagInputContainer"
          :min-width="256"
          :max-width="384"
          :max-height="260"
          :z-index="100020"
          placement="auto"
          align="start"
          @request-close="closeSuggest"
        >
          <!-- 标签建议下拉框 -->
          <div class="popover-surface custom-scrollbar flex max-h-64 w-64 max-w-[min(24rem,calc(100vw-2rem))] flex-col gap-1 overflow-y-auto rounded-lg p-1 shadow-[0_18px_50px_var(--shadow-color)]" @mousedown.prevent>
          <button 
            v-for="(tag, idx) in filteredKnownTags" 
            :key="tag.value"  
            v-tooltip="tagTooltip(tag.value)"
            @mousedown="addTag(tag.value)" 
            class="flex min-h-8 shrink-0 flex-col items-start justify-center rounded px-2 py-1.5 text-left text-xs leading-4 transition-colors hover:bg-accent-primary/20 hover:text-accent-primary"
            :class="{'bg-accent-primary/10 text-accent-primary': idx === tagNavIndex}">
            <span class="max-w-full truncate font-bold">{{ tag.label }}</span>
          </button>
          </div>
        </FixedPopover>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import FixedPopover from '../popover/FixedPopover.vue'
import { sortByDisplayName } from '../../lib/common'
import { t } from '../../i18n.js'

const props = defineProps({
  label: String,
  modelValue: { type: Array, default: () => [] },
  placeholder: String,
  description: String,
  allTags: { type: Array, default: () => [] } // 支持 ['a', 'b'] 或 [{ label: 'A', value: 'a' }]
})

const emit = defineEmits(['update:modelValue'])

const newTag = ref('')
const showTagSuggest = ref(false)
const tagNavIndex = ref(-1)
const tagInputContainer = ref(null)

const normalizeTagText = (value = '') => String(value || '').trim()
const normalizeComparableTag = (value = '') => normalizeTagText(value).toLowerCase()

// 1. 归一化建议数据
const normalizedTags = computed(() => {
  return sortByDisplayName(
    props.allTags.map(item => {
      if (typeof item === 'string') {
        return { label: item, value: item }
      }
      const value = normalizeTagText(item?.value)
      const label = normalizeTagText(item?.label || value)
      if (!value) return null
      const searchText = [label, value]
        .map(normalizeComparableTag)
        .filter(Boolean)
        .join('\n')
      return { label, value, searchText }
    }).filter(Boolean),
    item => item?.label || item?.value
  )
})
const tagMap = computed(() => new Map(normalizedTags.value.map(tag => [normalizeComparableTag(tag.value), tag])))
const tagInfo = (value = '') => {
  const rawValue = normalizeTagText(value)
  return tagMap.value.get(normalizeComparableTag(rawValue)) || { label: rawValue, value: rawValue }
}
const tagLabel = (value = '') => tagInfo(value).label || normalizeTagText(value)
const tagTooltip = (value = '') => {
  const tag = tagInfo(value)
  return tag.label && tag.label !== tag.value ? `${tag.label}\n${tag.value}` : tag.value
}

// 2. 过滤建议列表 (排除已存在的，并进行模糊匹配)
const filteredKnownTags = computed(() => {
  const input = newTag.value.toLowerCase().trim()
  const usedValues = new Set((props.modelValue || []).map(normalizeComparableTag).filter(Boolean))
  return normalizedTags.value
    .filter(tag => !usedValues.has(normalizeComparableTag(tag.value))) // 排除已在结果中的
    .filter(tag => tag.searchText.includes(input))
})

// 添加标签核心逻辑
const addTag = (val) => {
  const targetValue = normalizeTagText(val)
  const usedValues = new Set((props.modelValue || []).map(normalizeComparableTag).filter(Boolean))
  if (targetValue && !usedValues.has(normalizeComparableTag(targetValue))) {
    emit('update:modelValue', [...props.modelValue, targetValue])
    newTag.value = ''
    tagNavIndex.value = -1
    showTagSuggest.value = false
  }
}

// 确认添加 (处理回车键)
const confirmAddTag = () => {
  // 只有显式导航选中过建议项时，回车才采纳建议；否则保留用户原始输入。
  if (showTagSuggest.value && tagNavIndex.value >= 0 && filteredKnownTags.value.length > tagNavIndex.value) {
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
  }
  const len = filteredKnownTags.value.length
  if (len === 0) return
  if (tagNavIndex.value < 0) {
    tagNavIndex.value = step > 0 ? 0 : len - 1
    return
  }
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
    closeSuggest()
  }, 200)
}

const closeSuggest = () => {
  showTagSuggest.value = false
  tagNavIndex.value = -1
}

const handleFocus = () => {
  showTagSuggest.value = true
  tagNavIndex.value = -1
}

const handleInput = () => {
  showTagSuggest.value = true
  tagNavIndex.value = -1
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
