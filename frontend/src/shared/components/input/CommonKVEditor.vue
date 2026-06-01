<!-- components/common/input/CommonKVEditor.vue -->
<template>
  <div class="space-y-2">
    <div class="flex justify-between items-center px-1">
      <label class="text-xs text-text-dim uppercase font-bold tracking-widest">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
      </label>
      <button @click="add" class="text-xs text-accent-primary hover:underline">+ 新增条目</button>
    </div>

    <div class="space-y-1.5">
      <div v-for="(val, key) in modelValue" :key="key" class="flex gap-1 group animate-in slide-in-from-left-2 duration-200">
        <input 
          :value="key"
          @change="updateKey(key, $event.target.value)"
          placeholder="域名"
          class="flex-1 bg-bg-inset/70 border border-border-base/5 rounded-l-md px-3 py-1.5 text-sm text-text-main font-mono focus:outline-none focus:border-accent-primary/40"
        />
        <input 
          :value="val"
          @input="updateValue(key, $event.target.value)"
          placeholder="IP"
          class="flex-1 bg-bg-inset/70 border border-border-base/5 rounded-r-md px-3 py-1.5 text-sm text-accent-primary font-mono focus:outline-none focus:border-accent-primary/40"
        />
        <button @click="remove(key)" class="px-2 text-text-dim hover:text-accent-danger transition-colors opacity-0 group-hover:opacity-100">
          <Trash2 class="size-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Trash2 } from 'lucide-vue-next'

const props = defineProps({
  label: String,
  modelValue: { type: Object, default: () => ({}) },
  description: String,
})
const emit = defineEmits(['update:modelValue'])

const updateKey = (oldKey, newKey) => {
  if (!newKey || newKey === oldKey) return
  const newData = { ...props.modelValue }
  newData[newKey] = newData[oldKey]
  delete newData[oldKey]
  emit('update:modelValue', newData)
}

const updateValue = (key, val) => {
  const newData = { ...props.modelValue }
  newData[key] = val
  emit('update:modelValue', newData)
}

const add = () => {
  emit('update:modelValue', { ...props.modelValue, '': '' })
}

const remove = (key) => {
  const newData = { ...props.modelValue }
  delete newData[key]
  emit('update:modelValue', newData)
}
</script>