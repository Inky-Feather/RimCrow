<!-- components/common/input/CommonNumber.vue -->
<template>
  <div class="">
    <label v-if="label" class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1 mb-1">{{ label }}</label>
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
  step: { type: Number, default: 1 }
})
const emit = defineEmits(['update:modelValue'])

const change = (dir) => {
  emit('update:modelValue', props.modelValue + (dir * props.step))
}
</script>