<template>
  <!-- 容器 -->
  <div class="relative grid items-center bg-text-main/10 backdrop-blur-2xl rounded-[9px] w-full max-w-md select-none">
    
    <!-- 滑动滑块 (Indicator) -->
    <!-- 
       1. 宽度 = 100% / 选项数量
       2. 位置 = 当前索引 * 100% (相对于自身宽度位移)
    -->
    <div class="absolute top-0.5 bottom-0.5 left-0.5 bg-accent-highlight/60 rounded-[7px] border-[0.5px] border-black/5
             shadow-[0px_3px_8px_rgba(0,0,0,0.12),0px_3px_1px_rgba(0,0,0,0.04)]
             transition-transform duration-200 ease-out z-0"
      :style="{
        width: `calc((100% - 4px) / ${options.length})`,
        transform: `translateX(${currentIndex * 100}%)`
      }"
    ></div>

    <!-- 选项列表 -->
    <div class="relative z-10 flex w-full h-7">
      <button v-for="(item, index) in options" :key="index" type="button" @click="selectItem(item)"
        class="flex-1 px-2 flex items-center justify-center text-sm font-medium transition-colors duration-200 outline-none focus-visible:ring-2 focus-visible:ring-black/20 rounded-[7px]"
        :class="[ modelValue === item 
            ? 'text-text-main opacity-100 font-bold' 
            : 'text-text-main opacity-60 hover:opacity-100'
        ]"
      >
        {{ item.title }}
      </button>
    </div>

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

// 计算当前选中项的索引，用于控制滑块位置
const currentIndex = computed(() => {
  const idx = props.options.findIndex(opt => opt.id === props.modelValue)
  return idx === -1 ? 0 : idx
})

// 点击事件
const selectItem = (item) => {
  emit('update:modelValue', item.id)
  emit('change', item.id)
}
</script>