<!-- components/common/input/CommonTagInput.vue -->
<template>
  <div class="w-full">
    <label class="block text-xs text-text-dim uppercase font-bold tracking-widest px-1 mb-1">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
    </label>
    <div class="input-glass p-1.5 flex flex-wrap gap-1.5 min-h-6 content-start focus-within:border-accent-primary/40">
      
      <!-- 已有 Tag -->
      <transition-group name="list">
        <span v-for="tag in modelValue" :key="tag" 
          class="flex items-center gap-1.5 px-2 py-0.5 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm text-accent-primary font-mono group animate-in">
          {{ tag }}
          <button @click="remove(tag)" class="opacity-50 hover:opacity-100 hover:text-text-main transition-opacity">×</button>
        </span>
      </transition-group>

      <!-- 输入框 -->
      <input v-model="newTag"
        @keydown.enter.prevent="add"
        @keydown.backspace="handleBackspace"
        placeholder="输入并回车..."
        class="flex-1 min-w-20 bg-transparent border-none outline-none text-sm text-text-main py-1 px-1"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  label: String,
  modelValue: { type: Array, default: () => [] },
  description: String,
})
const emit = defineEmits(['update:modelValue'])

const newTag = ref('')

const add = () => {
  const val = newTag.value.trim()
  if (val && !props.modelValue.includes(val)) {
    emit('update:modelValue', [...props.modelValue, val])
    newTag.value = ''
  }
}

const remove = (tag) => {
  emit('update:modelValue', props.modelValue.filter(t => t !== tag))
}

const handleBackspace = () => {
  if (newTag.value === '' && props.modelValue.length > 0) {
    remove(props.modelValue[props.modelValue.length - 1])
  }
}
</script>