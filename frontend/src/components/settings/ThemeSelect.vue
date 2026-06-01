<template>
  <div ref="targetRef" class="relative">
    <div class="mb-1 flex items-center justify-between px-1">
      <label class="text-xs font-bold uppercase tracking-widest text-text-dim">配色方案</label>
      <button type="button" class="text-xs font-bold text-accent-primary hover:text-text-main transition-colors" @click="$emit('create')">
        创建配色
      </button>
    </div>

    <button ref="triggerRef" type="button" class="input-glass flex h-9 w-full items-center justify-between gap-3 px-3 bg-glass-light text-left text-sm text-text-main"
      @click="isOpen = !isOpen" >
      <span class="min-w-0 flex-1 truncate font-bold">{{ selectedTheme?.name || '未选择主题' }}</span>
      <ThemeSwatches :theme="selectedTheme" />
      <svg class="size-4 transition-transform duration-300" :class="{ 'rotate-180 text-accent-primary': isOpen }" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" >
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <FixedPopover :triggerRef="triggerRef" :isOpen="isOpen">
      <div class="w-md max-h-90 overflow-y-auto rounded-2xl border border-border-base/10 bg-glass-heavy p-2 shadow-[0_18px_50px_var(--shadow-color)] backdrop-blur-xl custom-scrollbar">
        <div v-for="theme in themes" :key="theme.id" role="button" tabindex="0"
          class="relative mb-1 flex w-full items-center gap-3 group rounded-xl border px-3 py-2 text-left transition-all"
          :class="theme.id === modelValue ? 'border-accent-primary/50 bg-accent-primary/12' : 'border-border-base/10 bg-glass-medium hover:border-border-base/18 hover:bg-bg-overlay/5'"
          @click="selectTheme(theme.id)"
          @keydown.enter.prevent="selectTheme(theme.id)" >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="truncate text-sm font-black text-text-main">{{ theme.name }}</span>
              <span class="rounded border border-border-base/10 px-1.5 py-0.5 text-[0.65rem] text-text-dim">
                {{ theme.builtin ? '内置' : '自定义' }}
              </span>
            </div>
            <div class="mt-1 font-mono text-[0.65rem] text-text-dim">{{ theme.id }}</div>
          </div>
          <ThemeSwatches :theme="theme" />

          <div v-if="!theme.builtin" class="absolute shrink-0 gap-1 opacity-0 group-hover:opacity-100 right-3 bg-bg-surface/60 px-2 py-1 rounded-md shadow-sm/20 backdrop-blur-sm border border-border-base/5">
            <button type="button" class="rounded-lg px-2 py-1 text-xs font-bold text-accent-primary hover:bg-accent-primary/15"
              @click.stop="$emit('edit', theme)" >编辑</button>
            <button type="button" class="rounded-lg px-2 py-1 text-xs font-bold text-accent-danger hover:bg-accent-danger/15"
              @click.stop="$emit('delete', theme)" >删除</button>
          </div>

        </div>
      </div>
    </FixedPopover>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import FixedPopover from '../common/FixedPopover.vue'
import ThemeSwatches from './ThemeSwatches.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  themes: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'create', 'edit', 'delete'])

const isOpen = ref(false)
const targetRef = ref(null)
const triggerRef = ref(null)

const selectedTheme = computed(() => props.themes.find(theme => theme.id === props.modelValue) || props.themes[0])

const selectTheme = (themeId) => {
  emit('update:modelValue', themeId)
  isOpen.value = false
}

onClickOutside(targetRef, () => {
  isOpen.value = false
})
</script>
