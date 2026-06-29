<!-- components/common/input/CommonSelect.vue -->
<template>
<div class="relative mx-0 p-0" :aria-disabled="disabled" :class="[{'flex items-center gap-1 min-w-0 max-w-full flex-1 basis-0' : mini}, disabled ? 'opacity-50' : '']">
    <!-- Label：点击时联动聚焦 -->
    <span v-if="label" class="block text-xs shrink-0 text-text-dim uppercase font-bold tracking-widest px-1 cursor-pointer hover:text-text-main transition-colors" 
      :class="[mini ? '' : 'mb-1']" @click="handleLabelClick" >
      {{ label }}
      <label v-if="description" v-tooltip="description" class="text-text-dim ml-0.5 cursor-help italic underline hover:text-text-main">?</label>
    </span>
    
    <!-- 主输入区域 -->
    <div class="relative group min-w-0 max-w-full flex items-center" :class="{ 'flex-1': mini }" >
      <input ref="inputRef" type="text" :value="inputValue" :placeholder="placeholder" :readonly="!editable" :disabled="disabled"
        :class="[ 'input-glass min-w-0 w-full truncate text-sm text-text-main focus:outline-none placeholder:text-text-disabled placeholder:italic',
           mini ? 'py-1 pl-2 pr-7 text-xs' : 'w-full h-9 px-3', editable ? 'cursor-text' : ' bg-bg-surface',
          { 'cursor-pointer': !editable && !disabled, 'cursor-text': editable && !disabled, 'cursor-not-allowed text-text-disabled': disabled }
        ]"
        @click="openMenu"
        @input="handleInput"
        @keydown="handleKeydown"
        @blur="handleBlur"
      />

      <!-- 右侧图标 (指示器) -->
      <div class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center pointer-events-none text-text-dim">
        <svg class="size-4 transition-transform duration-300" :class="{ 'rotate-180 text-accent-primary': isOpen }"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" >
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>

    <!-- 下拉面板 -->
    <FixedPopover
      :trigger-ref="inputRef" :is-open="isOpen"
      :placement="menuPlacement"
      close-on-other-popover
      @request-close="handlePopoverRequestClose"
    >
      <div @mousedown.prevent class="popover-surface inline-flex max-h-60 min-w-32 max-w-[min(50vw,24rem)] flex-col gap-0.5 overflow-y-auto rounded-xl p-1 custom-scrollbar">
        <!-- 有选项时 -->
        <!-- 体验优化：当有自定义输入且未完全匹配时，提示用户可以作为新值 -->
        <button v-if="showCustomHint" type="button" @click="commitInputValue"
          class="w-full flex items-center px-2 py-1.5 rounded-lg text-xs text-left bg-bg-overlay/5 border border-dashed border-border-base/18 text-accent-primary mb-1 hover:bg-accent-primary/10 transition-colors"
          :class="{'ring-1 ring-accent-primary/50': highlightedIndex === -1}" >
          <span class="mr-1.5 opacity-70">↵</span>
          使用 "<span class="font-bold">{{ internalSearch }}</span>"
        </button>
        <template v-if="filteredOptions.length > 0">
          <button v-for="(opt, index) in filteredOptions" :key="opt.value" :ref="(el) => setOptionRef(el, index)" type="button" @click="selectOption(opt)"
            class="w-full flex items-center px-2 py-1 rounded-lg text-xs text-left transition-all duration-150"
            :class="[
              // 1. 选中状态
              isActive(opt.value) ? 'bg-accent-primary/20 text-accent-primary font-medium' : 'text-text-soft hover:bg-bg-overlay/10 hover:text-text-main',
              // 2. 键盘导航高亮
              { 'bg-bg-overlay/10 ring-1 ring-border-base/18': index === highlightedIndex },
              // 3. 搜索匹配视觉区分：不匹配的项降低透明度
              isMatch(opt) ? 'opacity-100' : 'opacity-40 grayscale hover:opacity-80 hover:grayscale-0'
            ]"
          >
            <!-- 选中状态的小圆点 -->
            <div class="size-1.5 rounded-full mr-1.5 transition-all shrink-0"
              :class="isActive(opt.value) ? 'bg-accent-primary shadow-[0_0_8px_currentColor] scale-100' : 'scale-0'">
            </div>
            <!-- 如果有额外描述可以放在tooltip中 -->
            <label class="truncate flex-1 cursor-pointer" v-tooltip="opt.desc || opt.label">{{ opt.label }}</label>
          </button>
        </template>

        <div v-else-if="!showCustomHint" class="py-3 text-center text-xs text-text-dim italic">
          暂无选项
        </div>
      </div>
    </FixedPopover>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUpdate } from 'vue'
import FixedPopover from '../popover/FixedPopover.vue'

const props = defineProps({
  label: String,
  placeholder: { type: String, default: '请选择...' },
  description: String,
  modelValue: [String, Number, Boolean],
  options: { type: Array, default: () => [] }, // { label, value, ... }
  mini: { type: Boolean, default: false },
  showBottom: { type: Boolean, default: false }, // 默认向下展开
  editable: { type: Boolean, default: false }, // 是否可输入
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'change', 'visible-change'])

// --- 状态 ---
const isOpen = ref(false)
const inputRef = ref(null)
const optionRefs = ref([])
const highlightedIndex = ref(-1) // 键盘导航索引
const internalSearch = ref('') // 编辑模式下的搜索词

// --- 核心计算属性 ---

// 显示在输入框中的文字
const displayLabel = computed(() => {
  // 尝试从选项中找到对应 Label
  // 如果找不到且允许编辑，直接显示 modelValue
  // 如果不允许编辑，且有值但不在列表中，显示 modelValue (容错)
  const found = props.options.find(o => o.value === props.modelValue)
  return found ? found.label : (props.modelValue || '')
})
const inputValue = computed(() => {
  return (isOpen.value && props.editable) ? internalSearch.value : displayLabel.value
})
const menuPlacement = computed(() => (props.showBottom ? 'bottom' : 'auto'))
// 过滤后的选项列表，将匹配项“置顶”
const filteredOptions = computed(() => {
  // 如果没开启编辑，或者没有输入内容，直接返回原列表
  if (!props.editable || !internalSearch.value) return props.options
  // 安全处理：确保是字符串
  const query = String(internalSearch.value).toLowerCase().trim()
  if (!query) return props.options
  
  // 1. 拆分数组
  const matches = []
  const others = []

  props.options.forEach(opt => {
    const labelStr = String(opt.label).toLowerCase()
    const valueStr = String(opt.value).toLowerCase()

    // 如果 Label 或 Value 包含关键词
    if (labelStr.includes(query) || valueStr.includes(query)) {
      matches.push(opt)
    } else {
      others.push(opt)
    }
  })

  // 2. 排序：完全匹配 > 开头匹配 > 包含匹配
  matches.sort((a, b) => {
    const aLabel = String(a.label).toLowerCase()
    const bLabel = String(b.label).toLowerCase()
    
    if (aLabel === query) return -1
    if (bLabel === query) return 1
    if (aLabel.startsWith(query) && !bLabel.startsWith(query)) return -1
    if (!aLabel.startsWith(query) && bLabel.startsWith(query)) return 1
    return 0
  })

  // 3. 合并：匹配的在前，不匹配的在后（置灰显示）
  return [...matches, ...others]
})

// 检查是否显示"作为自定义值"的提示
const showCustomHint = computed(() => {
  if (!props.editable || !internalSearch.value) return false
  const query = String(internalSearch.value).trim()
  if (!query) return false
  // 如果已完全匹配列表中的某一项，则不显示自定义提示
  return !props.options.some(o => String(o.label) === query || String(o.value) === query)
})
// --- 方法 ---
// 用于在模板中判断当前项是否匹配搜索词（用于控制高亮/置灰样式）
const isMatch = (opt) => {
  if (!props.editable || !internalSearch.value) return true
  const query = String(internalSearch.value).toLowerCase().trim()
  if (!query) return true
  return String(opt.label).toLowerCase().includes(query) || String(opt.value).toLowerCase().includes(query)
}


// 1. 切换开关
const handleLabelClick = () => {
  if (props.disabled) return
  openMenu()
}

const openMenu = () => {
  if (props.disabled) return
  if (isOpen.value) return
  isOpen.value = true
  emit('visible-change', true) // 懒加载触发点
  
  // 如果是编辑模式，打开时重置搜索词为当前显示值，方便修改
  if (props.editable) {
    internalSearch.value = displayLabel.value // 或者设为 displayLabel.value 看需求
  } else {
    internalSearch.value = ''
  }
  // 聚焦输入框
  nextTick(() => inputRef.value?.focus())
}

const closeMenu = () => {
  if (!isOpen.value) return
  isOpen.value = false
  highlightedIndex.value = -1
  // 不在这里立即清空 internalSearch，可能会导致模板闪烁
  // 交给下一次 openMenu 处理
  emit('visible-change', false)
  // inputRef.value?.blur()
}

const finishEditingAndClose = () => {
  if (props.editable) commitInputValue()
  closeMenu()
}

// 2. 选中逻辑
const selectOption = (opt) => {
  emit('update:modelValue', opt.value)
  emit('change', opt) // 回传完整对象
  // 选中后清空搜索状态
  internalSearch.value = opt.label
  closeMenu()
}

// 3. 输入处理 (Editable)
const commitInputValue = () => {
  if (props.disabled) return
  if (!props.editable || internalSearch.value === null) return
  
  const val = String(internalSearch.value).trim()
  if (!val) {
    // 如果清空了输入，视业务需求决定是清空值还是保留。此处恢复为原值。
    internalSearch.value = displayLabel.value
    return
  }

  // 找是否有精确匹配的
  const exactMatch = props.options.find(
    o => String(o.label) === val || String(o.value) === val
  )

  if (exactMatch) {
    selectOption(exactMatch)
  } else {
    // 提交全新自定义值，【必须】更新 modelValue
    emit('update:modelValue', val)
    emit('change', { value: val, label: val, isCustom: true })
    closeMenu()
  }
}
const handleInput = (e) => {
  if (props.disabled) return
  if (!props.editable) return
  internalSearch.value = e.target.value
  if (!isOpen.value) isOpen.value = true
  
  // Bug 修复：用户打字时，不强制高亮第0项，而是将焦点设为 -1 (自由输入状态)
  highlightedIndex.value = -1 
}

const handleBlur = () => {
  if (props.disabled) return
  // 面板内容被 Teleport 到 body 后，输入框 blur 不再等于“用户已关闭菜单”。
  // 这里仅处理焦点离开输入框本身的场景，真正关闭交给 FixedPopover 的外部点击/Esc。
  if (!props.editable) return
  if (isOpen.value) {
    commitInputValue()
    closeMenu()
  }
}

// 5. 键盘导航
const handleKeydown = (e) => {
  if (!isOpen.value && e.key !== 'Tab') {
    if (e.key === 'Enter' || e.key === 'ArrowDown') {
      e.preventDefault()
      openMenu()
    }
    return
  }

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      if (highlightedIndex.value < filteredOptions.value.length - 1) {
        highlightedIndex.value++
        scrollToOption(highlightedIndex.value)
      }
      break
    case 'ArrowUp':
      e.preventDefault()
      // 如果按向上键超出了界限，回到输入框状态 (-1)
      if (highlightedIndex.value > -1) {
        highlightedIndex.value--
        if (highlightedIndex.value >= 0) scrollToOption(highlightedIndex.value)
      }
      break
    case 'Enter':
      e.preventDefault()
      if (highlightedIndex.value >= 0 && filteredOptions.value[highlightedIndex.value]) {
        // 用户明确用上下键选中了某一项
        selectOption(filteredOptions.value[highlightedIndex.value])
      } else if (props.editable) {
        // 否则当作自定义输入提交
        commitInputValue()
      } else {
        closeMenu()
      }
      break
    case 'Escape':
      e.preventDefault()
      closeMenu()
      break
    case 'Tab':
      finishEditingAndClose()
      break
  }
}

// 辅助：检查是否激活
const isActive = (val) => props.modelValue === val

// 辅助：滚动到指定选项
const scrollToOption = (index) => {
  nextTick(() => {
    // 简单的滚动逻辑，如果需要更精确可以用 Element.scrollIntoView
    const item = optionRefs.value[index]
    if (item && item.scrollIntoView) {
      item.scrollIntoView({ block: 'nearest' })
    }
  })
}

// 动态收集 ref 的函数
const setOptionRef = (el, index) => {
  if (el) {
    optionRefs.value[index] = el
  }
}
const handlePopoverRequestClose = () => {
  if (!isOpen.value) return
  if (props.editable) commitInputValue()
  closeMenu()
}
// 每次更新前清空，防止内存泄漏和死循环
onBeforeUpdate(() => {
  optionRefs.value = []
})
</script>

<style scoped>
/* 玻璃拟态输入框样式补充 */
.input-glass {
  backdrop-filter: blur(8px);
}

/* 下拉动画 */
.dropdown-enter-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.dropdown-leave-active {
  transition: all 0.15s ease-in;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}
</style>
