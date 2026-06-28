<!-- components/common/input/CommonSelect.vue -->
<template>
  <div class="relative" :class="{'flex items-center' : mini}" ref="target">
    <!-- Label -->
    <label v-if="label" class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1" :class="[mini?'':'mb-1']"  @click="toggleMenu" >
      {{ label }}
      <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
    </label>
    
    <!-- 主输入区域 -->
    <div class="relative group">
      <input ref="inputRef" type="text" :value="displayLabel" :placeholder="placeholder" :readonly="!editable"
        :class="[ 'input-glass bg-white/5 border border-white/10 rounded-lg text-sm text-white transition-all duration-200 focus:outline-none focus:border-accent-primary/50 focus:shadow-[0_0_15px_rgba(6,182,212,0.15)] placeholder:text-white/20 placeholder:italic',
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
    <Transition name="dropdown">
      <div v-show="isOpen"
        class="absolute z-50 left-0 right-0 p-1 bg-[#1a1a1a]/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] max-h-60 overflow-y-auto custom-scrollbar flex flex-col gap-0.5"
        :class="[showBottom ? 'mt-2 top-full' : 'mb-2 bottom-full origin-bottom']"
        @mousedown.prevent 
      >
        <!-- 有选项时 -->
        <template v-if="filteredOptions.length > 0">
          <button v-for="(opt, index) in filteredOptions" :key="opt.value" ref="optionRefs" type="button" @click="selectOption(opt)"
            class="w-full flex items-center px-3 py-1 rounded-lg text-xs text-left transition-all duration-150"
            :class="[
              // 1. 选中状态
              isActive(opt.value) ? 'bg-accent-primary/20 text-accent-primary font-medium' : 'text-gray-300 hover:bg-white/10 hover:text-white',
              // 2. 键盘导航高亮
              { 'bg-white/5 ring-1 ring-white/10': index === highlightedIndex },
              // 3. 【新增】搜索匹配视觉区分：不匹配的项降低透明度
              isMatch(opt) ? 'opacity-100' : 'opacity-40 grayscale hover:opacity-80 hover:grayscale-0'
            ]"
          >
            <!-- 选中状态的小圆点 -->
            <div class="size-1.5 rounded-full mr-2.5 transition-all shrink-0"
              :class="isActive(opt.value) ? 'bg-accent-primary shadow-[0_0_8px_currentColor] scale-100' : 'scale-0'">
            </div>
            
            <span class="truncate flex-1">{{ opt.label }}</span>
            
            <!-- 如果有额外描述可以放在这里 -->
            <span v-if="opt.desc" class="text-xs text-white/30 ml-2">{{ opt.desc }}</span>
          </button>
        </template>

        <!-- 无匹配项 -->
        <div v-else class="py-3 text-center text-xs text-text-dim italic">
          {{ editable && displayLabel ? '按回车使用当前输入值' : '暂无选项' }}
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { onClickOutside } from '@vueuse/core'

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

// 显示在输入框中的文字
const displayLabel = computed(() => {
  // 1. 如果正在搜索(输入中)，显示搜索词
  if (isOpen.value && props.editable && internalSearch.value !== null) {
    return internalSearch.value
  }
  
  // 2. 尝试从选项中找到对应 Label
  const found = props.options.find(o => o.value === props.modelValue)
  if (found) return found.label

  // 3. 如果找不到且允许编辑，直接显示 modelValue
  // 4. 如果不允许编辑，且有值但不在列表中，显示 modelValue (容错)
  return props.modelValue || ''
})

// 过滤后的选项列表，将匹配项“置顶”
const filteredOptions = computed(() => {
  // 如果没开启编辑，或者没有输入内容，直接返回原列表
  if (!props.editable || !internalSearch.value) return props.options
  
  const query = internalSearch.value.toLowerCase()
  
  // 1. 拆分数组
  const matches = []
  const others = []

  props.options.forEach(opt => {
    const labelStr = String(opt.label).toLowerCase()
    const valueStr = String(opt.value).toLowerCase()

    // 匹配规则：包含即可（你可以根据需要改为 'startsWith'）
    if (labelStr.includes(query) || valueStr.includes(query)) {
      matches.push(opt)
    } else {
      others.push(opt)
    }
  })

  // 2. 聚合：匹配项在前，其他项在后
  return [...matches, ...others]
})

// --- 方法 ---
// 用于在模板中判断当前项是否匹配搜索词（用于控制高亮/置灰样式）
const isMatch = (opt) => {
  if (!props.editable || !internalSearch.value) return true
  const query = internalSearch.value.toLowerCase()
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
  }
  
  // 聚焦输入框
  nextTick(() => inputRef.value?.focus())
}

const closeMenu = () => {
  if (!isOpen.value) return
  isOpen.value = false
  highlightedIndex.value = -1
  internalSearch.value = null // 清空内部搜索状态
  emit('visible-change', false)
  inputRef.value?.blur()
}

// 2. 选中逻辑
const selectOption = (opt) => {
  emit('update:modelValue', opt.value)
  emit('change', opt) // 回传完整对象
  closeMenu()
}

// 3. 输入处理 (Editable)
const handleInput = (e) => {
  if (!props.editable) return
  const val = e.target.value
  internalSearch.value = val
  isOpen.value = true 
  
  // 输入时，永远将键盘导航索引重置为 0
  // 因为列表已经重排序了，第 0 项就是最匹配的那一项
  highlightedIndex.value = 0 
  
  emit('update:modelValue', val)
  // emit('change', { value: val, label: val, isCustom: true })
}

// 4. 失去焦点处理
// 使用 setTimeout 是为了让 click 事件先于 blur 执行
const handleBlur = () => {
  setTimeout(() => {
    emit('change', { value:  displayLabel.value, label: displayLabel.value, isCustom: true })
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

// 点击外部关闭
onClickOutside(target, () => closeMenu())

// 监听值变化，如果外部修改了值，重置内部搜索状态
watch(() => props.modelValue, () => {
  internalSearch.value = null
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