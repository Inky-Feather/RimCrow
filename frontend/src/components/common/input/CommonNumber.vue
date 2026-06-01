<!-- components/common/input/CommonNumber.vue -->
<template>
  <div class="mx-0 p-0" :class="mini?'flex items-center gap-1 min-w-fit':''">
    <label v-if="label" class="block text-xs shrink-0 text-text-dim uppercase font-bold tracking-widest px-1 mb-1">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-0.5 cursor-help italic underline hover:text-text-main">?</label>
    </label>
    <div class="flex items-center input-glass m-0 overflow-hidden" :class="mini?'flex-1 h-7 min-w-fit':'h-9'">
      <button @click="change(-1)" class="h-full w-1/5 border-r border-border-base/10 bg-bg-overlay/5 text-text-dim transition-colors hover:bg-accent-primary/12 hover:text-accent-primary">-</button>
      
      <input type="number" :value="modelValue" :min="min" :max="max" :step="step"
        @input="$emit('update:modelValue', Number($event.target.value))"
        class="flex-1 bg-transparent min-w-0 text-center text-sm text-text-main font-mono focus:outline-none [-moz-appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      
      <button @click="change(1)" class="h-full w-1/5 border-l border-border-base/10 bg-bg-overlay/5 text-text-dim transition-colors hover:bg-accent-primary/12 hover:text-accent-primary">+</button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  label: String,
  modelValue: Number,
  description: String,
  mini: { type: Boolean, default: false },
  step: { type: Number, default: 1 },
  max: { type: Number, default: Number.MAX_SAFE_INTEGER },
  min: { type: Number, default: Number.MIN_SAFE_INTEGER }
})
const emit = defineEmits(['update:modelValue'])

const change = (dir) => {
  let newValue = props.modelValue + (dir * props.step)
  if (newValue > props.max) newValue = props.max
  if (newValue < props.min) newValue = props.min

  emit('update:modelValue', newValue)
}
</script>
