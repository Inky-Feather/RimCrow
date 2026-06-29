<template>
  <div class="w-full">
    <div v-if="label" class="mb-1 flex items-center justify-between px-1">
      <label class="text-xs text-text-dim uppercase font-bold tracking-widest">
        {{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
      </label>
      <AlertTriangle v-if="statusError" class="size-3.5 text-accent-warn" v-tooltip="statusError" />
    </div>

    <div class="relative flex items-center gap-2 w-full">
      <div class="relative flex-1 input-glass overflow-hidden flex items-center min-w-0">
        <input
          :type="inputType"
          :value="inputValue"
          :placeholder="effectivePlaceholder"
          :readonly="readonlySecret"
          class="w-full bg-transparent px-3 py-2 text-sm focus:outline-none font-mono"
          :class="readonlySecret ? 'cursor-text text-text-dim select-text' : 'text-text-main'"
          @input="handleInput"
        />

        <button
          v-if="showEyeButton"
          type="button"
          class="px-2 text-text-dim hover:text-accent-primary transition-colors disabled:pointer-events-none disabled:opacity-60"
          :disabled="loading"
          v-tooltip="readonlySecret ? (revealed ? '隐藏密钥' : '查看已保存密钥') : (showPassword ? '隐藏' : '显示')"
          @click="handleEyeClick"
        >
          <Loader2 v-if="loading" class="size-4 animate-spin" />
          <EyeOff v-else-if="showPassword || revealed" class="size-4" />
          <Eye v-else class="size-4" />
        </button>

        <button
          v-if="readonlySecret"
          type="button"
          class="px-2 text-text-dim hover:text-accent-warn transition-colors"
          v-tooltip="'清除已保存密钥'"
          @click="handleClear"
        >
          <Trash2 class="size-4" />
        </button>

        <button
          v-if="pendingClear"
          type="button"
          class="px-2 text-text-dim hover:text-accent-primary transition-colors"
          v-tooltip="'保留原值'"
          @click="$emit('preserve', secretKey)"
        >
          <Undo2 class="size-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Eye, EyeOff, Loader2, Trash2, Undo2 } from 'lucide-vue-next'

const props = defineProps({
  label: String,
  modelValue: [String, Number],
  placeholder: String,
  description: String,
  secretKey: { type: String, required: true },
  secretStatus: { type: Object, default: () => ({}) },
  preserved: { type: Boolean, default: false },
  revealSecret: { type: Function, default: null },
})

const emit = defineEmits(['update:modelValue', 'preserve', 'clear'])
const loading = ref(false)
const revealed = ref(false)
const showPassword = ref(false)
const localError = ref('')

const currentValue = computed(() => String(props.modelValue ?? ''))
const hasSaved = computed(() => !!props.secretStatus?.has_value)
const readonlySecret = computed(() => hasSaved.value && props.preserved)
const pendingClear = computed(() => hasSaved.value && !props.preserved && !currentValue.value)
const statusError = computed(() => localError.value || props.secretStatus?.error || '')
const savedLabel = computed(() => props.secretStatus?.hint ? `已保存 ${props.secretStatus.hint}` : '已保存密钥')
const inputValue = computed(() => (readonlySecret.value && !revealed.value ? savedLabel.value : currentValue.value))
const effectivePlaceholder = computed(() => {
  if (pendingClear.value) return '保存后会清除；也可以直接填写新密钥'
  return props.placeholder
})
const inputType = computed(() => {
  if (readonlySecret.value) return 'text'
  return showPassword.value ? 'text' : 'password'
})
const showEyeButton = computed(() => readonlySecret.value || !!currentValue.value)

const handleInput = (event) => {
  if (readonlySecret.value) return
  emit('update:modelValue', event.target.value)
}

const handleClear = () => {
  revealed.value = false
  emit('update:modelValue', '')
  emit('clear', props.secretKey)
}

const handleEyeClick = async () => {
  if (!readonlySecret.value) {
    showPassword.value = !showPassword.value
    return
  }
  if (revealed.value) {
    revealed.value = false
    emit('update:modelValue', '')
    return
  }
  if (!props.revealSecret || loading.value) return
  loading.value = true
  localError.value = ''
  try {
    const payload = await props.revealSecret(props.secretKey, { silent: true })
    const value = String(payload?.value || '')
    if (value) {
      revealed.value = true
      emit('update:modelValue', value)
      emit('preserve', props.secretKey)
      return
    }
    localError.value = '无法读取已保存密钥，保存时会保留原值'
    emit('preserve', props.secretKey)
  } finally {
    loading.value = false
  }
}

watch(() => props.preserved, (preserved) => {
  if (!preserved) revealed.value = false
})
</script>
