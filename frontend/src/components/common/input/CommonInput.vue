<!-- components/common/input/CommonInput.vue -->
<template>
  <div class=" w-full">
    <div v-if="label" class="flex justify-between items-center  px-1 mb-1">
      <label class="text-xs text-text-dim uppercase font-bold tracking-widest">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
      </label>
      <slot name="extra"></slot>
    </div>
    
    <div class="relative group flex items-center gap-2 w-full">
      <div class="relative flex-1 input-glass overflow-hidden flex items-center min-w-0">
        <!-- 前置图标插槽 -->
        <div v-if="$slots.icon" class="pl-3 text-text-dim">
          <slot name="icon"></slot>
        </div>

        <input :type="isPassword && !showPassword ? 'password' : 'text'"
          :value="modelValue"
          @input="$emit('update:modelValue', $event.target.value)"
          :placeholder="placeholder"
          :readonly="readonly"
          class="w-full bg-transparent px-3 py-2 text-sm text-white focus:outline-none font-mono"
        />

        <!-- 密码切换按钮 -->
        <button v-if="isPassword" @click="showPassword = !showPassword" 
          class="pr-3 text-text-dim hover:text-accent-primary transition-colors">
          <component :is="showPassword ? EyeOff : Eye" class="size-4" />
        </button>
      </div>

      <!-- 路径浏览按钮 -->
      <button v-if="isPath" @click="$emit('browse')"
        class="shrink-0 p-2.5 bg-white/5 hover:bg-accent-primary/20 border border-white/10 hover:border-accent-primary/50 rounded-lg text-text-dim hover:text-accent-primary transition-all active:scale-95"
        v-tooltip="'浏览路径'">
        <svg class="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2-2z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'

defineProps({
  label: String,
  modelValue: [String, Number],
  placeholder: String,
  isPassword: { type: Boolean, default: false },
  isPath: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  description: String,
})

defineEmits(['update:modelValue', 'browse'])
const showPassword = ref(false)
</script>