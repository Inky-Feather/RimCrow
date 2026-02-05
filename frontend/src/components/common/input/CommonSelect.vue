<!-- components/common/input/CommonSelect.vue -->
<template>
  <div class="relative" :class="{'flex items-center' : mini}" ref="target">
    <label v-if="label" class="text-xs text-text-dim uppercase font-bold tracking-widest px-1">{{ label }}</label>
    
    <!-- 触发器 -->
    <button @click="isOpen = !isOpen" type="button"
      class="flex items-center justify-between pl-3 pr-2 input-glass text-sm"
      :class="{ 'border-accent-primary/50 shadow-[0_0_10px_rgba(6,182,212,0.1)]': isOpen, 'w-full h-9 ': !mini, 'py-0.5 flex-1':mini }"
    >
      <span v-if="selectedLabel" class="text-white truncate font-medium">{{ selectedLabel }}</span>
      <span v-else class="text-white/20 italic">{{ placeholder }}</span>
      
      <svg class="size-3.5 ml-1 text-text-dim transition-transform duration-300"
        :class="{ 'rotate-180 text-accent-primary': isOpen }"
        fill="none" viewBox="0 0 24 24" stroke="currentColor"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <!-- 下拉面板 -->
    <transition name="dropdown" >
      <div v-if="isOpen" class="absolute z-50 left-0 right-0  p-1 bg-bg-surface/90 backdrop-blur-2xl border border-white/10 rounded-xl shadow-[0_15px_50px_rgba(0,0,0,0.6)] max-h-60 overflow-y-auto custom-scrollbar"
        :class="[showBottom?'mt-1.5 top-full':'mb-1.5 bottom-full']">
        <button v-for="opt in options" :key="opt.value" @click="select(opt.value)"
          class="w-full flex items-center px-2 py-1 rounded-lg text-sm transition-all duration-200 group"
          :class="modelValue === opt.value ? 'bg-accent-primary/20 text-accent-primary' : 'text-text-dim hover:bg-white/5 hover:text-white'"
        >
          <!-- 选中指示点 -->
          <div class="size-1.5 rounded-full mr-1 transition-all"
            :class="modelValue === opt.value ? 'bg-accent-primary shadow-[0_0_8px_#06b6d4] scale-100' : 'bg-transparent scale-0'">
          </div>
          
          <span class="truncate">{{ opt.label }}</span>
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onClickOutside } from '@vueuse/core'

const props = defineProps({
  label: String,
  placeholder: { type: String, default: '请选择...' },
  modelValue: [String, Number, Boolean],
  mini: { type: Boolean, default: false },
  showBottom: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
  options: {
    type: Array,
    default: () => [] // 结构: { label: '中文', value: 'zh' }
  }
})

const emit = defineEmits(['update:modelValue'])

const isOpen = ref(false)
const target = ref(null)

// 自动处理点击外部关闭
onClickOutside(target, () => isOpen.value = false)

const selectedLabel = computed(() => {
  const found = props.options.find(o => o.value === props.modelValue)
  return found ? found.label : props.modelValue || null
})

const select = (val) => {
  emit('update:modelValue', val)
  isOpen.value = false
}
</script>

<style scoped>
.dropdown-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.dropdown-leave-active {
  transition: all 0.15s ease-in;
}
.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-10px) scale(0.98);
}
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-5px) scale(0.98);
}
</style>