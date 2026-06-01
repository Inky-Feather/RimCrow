<!-- components/common/input/CommonPathInput.vue -->
<template>
  <div class="space-y-1.5 w-full max-w-full overflow-hidden">
    <div class="flex justify-between items-center px-1">
      <label class="text-xs text-text-dim uppercase font-bold tracking-widest">{{ label }}
        <label v-if="description" v-tooltip="description" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
      </label>
      <button v-if="modelValue" @click="openInExplorer" 
        class="text-xs text-accent-primary/60 hover:text-accent-primary transition-colors hover:underline"
      >
        在资源管理器中打开
      </button>
    </div>
    
    <div :class="{' opacity-50 cursor-not-allowed pointer-events-none': readOnly}" class="flex items-center gap-1.5 group w-full">
      <!-- 路径显示区 -->
      <div class="relative flex-1 h-9 input-glass overflow-hidden flex items-center px-3 cursor-help min-w-0" v-tooltip="checkMsg || (modelValue || '未配置路径')" 
        :class="[ checkClassStyle ]">
        <!-- 固定前缀标签 -->
        <div class="shrink-0 mr-2 text-text-disabled italic text-xs font-mono uppercase select-none">Path</div>
        
        <!-- 手动输入框 -->
        <input type="text" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)"
          :placeholder="placeholder || '请输入或粘贴路径...'"
          class="flex-1 bg-transparent text-sm text-text-soft font-mono outline-none min-w-0 "
          :class="{ 'direction-rtl': !isFocused }"
          @focus="isFocused = true" @blur="isFocused = false; $emit('blur')"
        />

        <!-- 路径状态指示灯 -->
        <div class="shrink-0 size-1 rounded-full ml-2 transition-all duration-500"
          :class="[
            modelValue ? 'bg-accent-success shadow-[0_0_8px_rgba(var(--rgb-accent-success),0.5)]' : 'bg-accent-danger shadow-[0_0_8px_rgba(var(--rgb-accent-danger),0.5)]',
            modelValue ? 'opacity-100' : 'opacity-40 animate-pulse'
          ]"
          v-tooltip="modelValue ? '已填写路径' : '路径为空，可能导致功能失效'"
        ></div>
      </div>

      <!-- 浏览按钮 -->
      <button v-if="!readOnly" @click="$emit('browse')"
        class="input-addon-button flex h-9 w-9 items-center justify-center rounded-lg active:scale-90"
        v-tooltip="'通过文件浏览器选择'"
      >
        <svg class="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useAppStore } from '../../../stores/appStore'

const props = defineProps({
  label: String,
  fileType: String,
  modelValue: String,
  readOnly: Boolean,
  placeholder: String,
  description: String,
  check: Object,
})

defineEmits(['browse', 'update:modelValue', 'blur'])
const appStore = useAppStore()

// 焦点状态管理
const isFocused = ref(false)
const openInExplorer = () => {
  if (props.modelValue) {
    appStore.openPath(props.modelValue)
  }
}

const checkMsg = computed(() => {
  if (props.check) {
    // console.log(props.check)
    let msg = props.check['msg'] || ''
    if (props.check['type'] === 'success') msg='##'+msg+'##'
    else if (props.check['type'] === 'error') msg='!!'+msg+'\n请检查路径是否有效！'+'!!'
    else if (props.check['type'] === 'warn') msg='^^'+msg+'\n请检查路径是否正确！'+'^^'
    // console.log(msg)
    return msg
  }
  return ''
})

const checkClassStyle = computed(() => {
  if (props.check) {
    if (props.check['type'] === 'success') return 'border border-accent-success/70'
    else if (props.check['type'] === 'warn') return 'border border-accent-warn/80'
    else if (props.check['type'] === 'error') return 'border border-accent-danger/90'
  }
  return ''
})

</script>

<style scoped>
/* 
  非聚焦状态下从右往左显示（看到文件夹深层）
  聚焦状态下恢复标准显示，方便光标定位修改起始处 
*/
.direction-rtl {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: left; /* 保持左对齐文字，但从末尾截断 */
}
</style>
