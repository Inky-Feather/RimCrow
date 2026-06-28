<!-- components/common/input/CommonSelect.vue -->
<template>
  <div class="relative" :class="{'flex items-center' : mini}" ref="target">
    <!-- Label -->
    <span v-if="label" class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1" :class="[mini?'':'mb-1']"  @click="toggleMenu" >
      {{ label }}
      <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
    </span>
    
    <!-- 主输入区域 -->
    <div class="relative group">
      <input ref="inputRef" type="text" :value="inputValue" :placeholder="placeholder" :readonly="!editable"
        :class="[ 'input-glass bg-text-main/5 border border-text-main/10 rounded-lg text-sm text-text-main transition-all duration-200 focus:outline-none focus:border-accent-primary/50 focus:shadow-[0_0_15px_rgba(6,182,212,0.15)] placeholder:text-text-main/20 placeholder:italic',
          mini ? 'py-1 px-2 text-xs' : 'w-full h-9 px-3',
          { 'cursor-pointer': !editable, 'cursor-text': editable }
        ]"
        @click="toggleMenu"
        @input="handleInput"
        @keydown="handleKeydown"
        @blur="handleBlur"
      />

      <!-- 右侧图标 (指示器) -->
      <div class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center pointer-events-none text-text-dim">
        <svg class="size-4 transition-transform duration-300"
          :class="{ 'rotate-180 text-accent-primary': isOpen }"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>

    <!-- 下拉面板 -->
    <FixedPopover :triggerRef="inputRef" :isOpen="isOpen">
      <div @mousedown.prevent class="p-1 bg-bg-surface backdrop-blur-xl border border-text-main/10 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] max-h-60 overflow-y-auto custom-scrollbar flex flex-col gap-0.5">
        <!-- 有选项时 -->
        <template v-if="filteredOptions.length > 0">
          <button v-for="(opt, index) in filteredOptions" :key="opt.value" :ref="(el) => setOptionRef(el, index)" type="button" @click="selectOption(opt)"
            class="w-full flex items-center px-3 py-1 rounded-lg text-xs text-left transition-all duration-150"
            :class="[
              // 1. 选中状态
              isActive(opt.value) ? 'bg-accent-primary/20 text-accent-primary font-medium' : 'text-gray-300 hover:bg-text-main/10 hover:text-text-main',
              // 2. 键盘导航高亮
              { 'bg-text-main/5 ring-1 ring-text-main/10': index === highlightedIndex },
              // 3. 搜索匹配视觉区分：不匹配的项降低透明度
              isMatch(opt) ? 'opacity-100' : 'opacity-40 grayscale hover:opacity-80 hover:grayscale-0'
            ]"
          >
            <!-- 选中状态的小圆点 -->
            <div class="size-1.5 rounded-full mr-2.5 transition-all shrink-0"
              :class="isActive(opt.value) ? 'bg-accent-primary shadow-[0_0_8px_currentColor] scale-100' : 'scale-0'">
            </div>
            <!-- 如果有额外描述可以放在tooltip中 -->
            <label class="truncate flex-1" v-tooltip="opt.desc || opt.label">{{ opt.label }}</label>
          </button>
        </template>

        <!-- 无匹配项 -->
        <div v-else class="py-3 text-center text-xs text-text-dim italic">
          {{ editable && displayLabel ? '按回车使用当前输入值' : '暂无选项' }}
        </div>
      </div>
    </FixedPopover>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUpdate } from 'vue'
import { onClickOutside } from '@vueuse/core'
import FixedPopover from '../FixedPopover.vue'

const props = defineProps({
  label: String,
  placeholder: { type: String, default: '请选择...' },
  description: String,
  modelValue: [String, Number, Boolean],
  options: { type: Array, default: () => [] }, // { label, value, ... }
  mini: { type: Boolean, default: false },
  showBottom: { type: Boolean, default: false }, // 默认向下展开
  editable: { type: Boolean, default: false }, // 是否可输入
})

const emit = defineEmits(['update:modelValue', 'change', 'visible-change'])

// --- 状态 ---
const isOpen = ref(false)
const target = ref(null)
const inputRef = ref(null)
const optionRefs = ref([])
const highlightedIndex = ref(-1) // 键盘导航索引
const internalSearch = ref('') // 编辑模式下的搜索词

// --- 核心计算属性 ---

const inputValue = computed(() => {
  if (isOpen.value && props.editable) {
    return internalSearch.value
  }
  return displayLabel.value
})
// 显示在输入框中的文字
const displayLabel = computed(() => {
  // 尝试从选项中找到对应 Label
  const found = props.options.find(o => o.value === props.modelValue)
  if (found) return found.label

  // 如果找不到且允许编辑，直接显示 modelValue
  // 如果不允许编辑，且有值但不在列表中，显示 modelValue (容错)
  return props.modelValue || ''
})

// 过滤后的选项列表，将匹配项“置顶”
const filteredOptions = computed(() => {
  // 如果没开启编辑，或者没有输入内容，直接返回原列表
  if (!props.editable || !internalSearch.value) return props.options
  // 安全处理：确保是字符串
  const query = (internalSearch.value || '').toString().toLowerCase().trim()
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

// --- 方法 ---
// 用于在模板中判断当前项是否匹配搜索词（用于控制高亮/置灰样式）
const isMatch = (opt) => {
  if (!props.editable || !internalSearch.value) return true
  const query = (internalSearch.value || '').toString().toLowerCase().trim()
  if (!query) return true
  return String(opt.label).toLowerCase().includes(query) || 
        String(opt.value).toLowerCase().includes(query)
}


// 1. 切换开关
const toggleMenu = () => {
  if (isOpen.value) {
    closeMenu()
  } else {
    openMenu()
  }
}

const openMenu = () => {
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

// 2. 选中逻辑
const selectOption = (opt) => {
  emit('update:modelValue', opt.value)
  emit('change', opt) // 回传完整对象
  // 选中后清空搜索状态
  internalSearch.value = opt.label
  closeMenu()
}

// 3. 输入处理 (Editable)
const handleInput = (e) => {
  if (!props.editable) return
  const val = e.target.value
  internalSearch.value = val
  if (!isOpen.value) isOpen.value = true
  
  // 输入时，永远将键盘导航索引重置为 0
  // 因为列表已经重排序了，第 0 项就是最匹配的那一项
  highlightedIndex.value = 0 
  
  // emit('update:modelValue', val)
  // emit('change', { value: val, label: val, isCustom: true })
}

// 4. 失去焦点处理
// 使用 setTimeout 是为了让 click 事件先于 blur 执行
const handleBlur = () => {
  setTimeout(() => {
    if (!isOpen.value) return; // 如果已经通过 selectOption 关闭了，就不再处理
    // 只有在弹窗仍然打开，并且是编辑模式时，才强制提交用户手打的值
    if (isOpen.value && props.editable && internalSearch.value !== null) {
      // 如果能在当前过滤列表找到精确匹配，那就直接选它
      const exactMatch = filteredOptions.value.find(o => o.label === internalSearch.value || o.value === internalSearch.value)
      if (exactMatch) {
        emit('update:modelValue', exactMatch.value)
        emit('change', exactMatch)
      } else {
        // 否则作为一个全新的自定义值抛出
        emit('change', { value: internalSearch.value, label: internalSearch.value, isCustom: true })
      }
    }
    closeMenu()
  }, 200)
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
      if (highlightedIndex.value > 0) {
        highlightedIndex.value--
        scrollToOption(highlightedIndex.value)
      }
      break
    case 'Enter':
      e.preventDefault()
      if (highlightedIndex.value >= 0 && filteredOptions.value[highlightedIndex.value]) {
        selectOption(filteredOptions.value[highlightedIndex.value])
      } else if (props.editable && internalSearch.value) {
        // 如果没有高亮选项，但按了回车，且是编辑模式，确认当前输入值
        closeMenu()
      }
      break
    case 'Escape':
      e.preventDefault()
      closeMenu()
      break
    case 'Tab':
      closeMenu()
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
// 点击外部关闭
onClickOutside(target, () => closeMenu())
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