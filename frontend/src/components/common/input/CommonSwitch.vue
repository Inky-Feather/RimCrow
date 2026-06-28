<!-- components/common/input/CommonSwitch.vue -->
<template>
  <div :aria-disabled="disabled" class="flex items-center justify-between py-2 px-3 aria-disabled:pointer-events-none aria-disabled:opacity-50" 
    :class="[mini?'':'input-glass']">
    <div class="flex flex-col">
      <span class="text-sm font-bold text-text-main tracking-wide">{{ label }}
        <label v-if="description && mini" v-tooltip="description" class="text-text-dim ml-1 italic cursor-help underline hover:text-text-main">?</label>
      </span>
      <span v-if="description && !mini" class="text-[0.7rem] text-text-dim mt-0.5">{{ description }}</span>
    </div>

    <button @click="$emit('update:modelValue', !modelValue)"
      class="relative shrink-0 rounded-full transition-all duration-300 overflow-hidden border border-text-main/10"
      :class="[modelValue ? 'bg-accent-primary/20 border-accent-primary/40 shadow-[0_0_10px_rgba(6,182,212,0.2)]' : 'bg-black/40',
        mini?'w-9.5 h-5':'w-10 h-6'
      ]"
    >
      <!-- 滑块轨迹指示灯 -->
      <div class="absolute rounded-full transition-all duration-300 ease-out"
        :class="[modelValue ? 'left-5 bg-accent-primary shadow-[0_0_8px_#06b6d4]' : 'left-1 bg-text-dim/40',
          mini?'top-[0.2rem] w-3 h-3':'top-1 h-3.5 w-3.5'
        ]">
      </div>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: String,
  description: String,
  modelValue: Boolean,
  mini: Boolean,
  disabled: Boolean
})
const emit = defineEmits(['update:modelValue'])

const switchValue = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
  }
})

</script>