<!-- components/common/input/CommonNumber.vue -->
<template>
  <div class="">
    <label v-if="label" class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1 mb-1">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
    </label>
    <div class="flex items-center input-glass overflow-hidden h-9">
      <button @click="change(-1)" class="w-[20%] h-full hover:bg-white/5 text-text-dim hover:text-white transition-colors border-r border-white/5">-</button>
      
      <input type="number" :value="modelValue"
        @input="$emit('update:modelValue', Number($event.target.value))"
        class="flex-1 bg-transparent min-w-0 text-center text-sm text-white font-mono focus:outline-none [-moz-appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      
      <button @click="change(1)" class="w-[20%] h-full hover:bg-white/5 text-text-dim hover:text-white transition-colors border-l border-white/5">+</button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  label: String,
  modelValue: Number,
  description: String,
  step: { type: Number, default: 1 },
  max: { type: Number, default: Number.MAX_SAFE_INTEGER },
  min: { type: Number, default: Number.MIN_SAFE_INTEGER }
})
const emit = defineEmits(['update:modelValue'])

const change = (dir) => {
  if (props.modelValue + (dir * props.step) > props.max) return
  if (props.modelValue + (dir * props.step) < props.min) return
  emit('update:modelValue', props.modelValue + (dir * props.step))
}
</script>