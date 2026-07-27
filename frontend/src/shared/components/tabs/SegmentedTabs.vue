<template>
  <!-- 容器 -->
  <div class="relative grid items-center overflow-hidden bg-bg-overlay/10 backdrop-blur-2xl rounded-[9px] w-full select-none"
    :style="{ gridTemplateColumns: `repeat(${optionCount}, minmax(0, 1fr))` }">
    
    <!-- 滑动滑块 (Indicator) -->
    <!-- 1. 宽度 = 100% / 选项数量 2. 位置 = 当前索引 * 100% (相对于自身宽度位移) -->
    <div class="absolute top-0.5 bottom-0.5 left-0.5 bg-accent-highlight/60 rounded-md border border-border-base/10
             shadow-[0px_2px_2px_var(--shadow-color),0px_1px_1px_var(--shadow-color)]
             transition-transform duration-200 ease-out z-0"
      :style="{
        width: `calc((100% - 4px) / ${optionCount})`,
        transform: `translateX(${currentIndex * 100}%)`
      }"
    ></div>

    <button v-for="(item, index) in options" :key="index" type="button" @click="selectItem(item)"
      class="relative z-10 h-7 min-w-0 overflow-hidden px-1.5 flex items-center justify-center font-medium leading-none transition-colors duration-200 outline-none focus-visible:ring-2 focus-visible:ring-black/20 rounded-[7px]"
      :class="[ modelValue === item.id
          ? 'text-text-main opacity-100 font-bold'
          : 'text-text-main opacity-60 hover:opacity-100'
      ]"
      :title="item.title"
      :style="{ fontSize: getTitleFontSize(item.title) }"
    >
      <span class="block min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">{{ item.title }}</span>
    </button>

  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 传入的选项列表，例如 ['Profile', 'Settings', 'Notifications']
  options: {
    type: Array,
    required: true,
    default: () => []
  },
  // 当前选中的值 (v-model)
  modelValue: {
    type: [String, Number],
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const optionCount = computed(() => Math.max(1, props.options.length))

// 计算当前选中项的索引，用于控制滑块位置
const currentIndex = computed(() => {
  const idx = props.options.findIndex(opt => opt.id === props.modelValue)
  return idx === -1 ? 0 : idx
})

const getTitleFontSize = (title = '') => {
  const length = String(title || '').trim().length
  if (length > 18) return '0.62rem'
  if (length > 12) return '0.68rem'
  if (length > 8) return '0.75rem'
  return '0.875rem'
}

// 点击事件
const selectItem = (item) => {
  emit('update:modelValue', item.id)
  emit('change', item.id)
}
</script>
