<template>
  <div ref="targetRef" class="relative">
    <div class="mb-1 flex items-center justify-between px-1">
      <label class="text-xs font-bold uppercase tracking-widest text-text-dim">配色方案</label>
      <button type="button" class="text-xs font-bold text-accent-primary hover:text-text-main transition-colors" @click="$emit('create')">
        创建配色
      </button>
    </div>

    <button ref="triggerRef" type="button" class="input-glass flex h-11 w-full items-center justify-between gap-3 px-3 text-left text-sm text-text-main"
      @click="isOpen = !isOpen"
    >
      <span class="min-w-0 flex-1 truncate font-bold">{{ selectedTheme?.name || '未选择主题' }}</span>
      <ThemeSwatches :theme="selectedTheme" />
      <span class="text-text-dim transition-transform" :class="{ 'rotate-180': isOpen }">⌄</span>
    </button>

    <FixedPopover :triggerRef="triggerRef" :isOpen="isOpen">
      <div class="w-md max-h-90 overflow-y-auto rounded-2xl border border-text-main/10 bg-bg-surface/98 p-2 shadow-[0_18px_50px_rgba(0,0,0,0.55)] backdrop-blur-xl custom-scrollbar">
        <div v-for="theme in themes" :key="theme.id" role="button" tabindex="0"
          class="mb-1 flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left transition-all"
          :class="theme.id === modelValue ? 'border-accent-primary/50 bg-accent-primary/12' : 'border-text-main/8 bg-black/10 hover:border-text-main/18 hover:bg-text-main/6'"
          @click="selectTheme(theme.id)"
          @keydown.enter.prevent="selectTheme(theme.id)"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="truncate text-sm font-black text-text-main">{{ theme.name }}</span>
              <span class="rounded border border-text-main/10 px-1.5 py-0.5 text-[0.65rem] text-text-dim">
                {{ theme.builtin ? '内置' : '自定义' }}
              </span>
            </div>
            <div class="mt-1 font-mono text-[0.65rem] text-text-dim/70">{{ theme.id }}</div>
          </div>
          <ThemeSwatches :theme="theme" />
          <div v-if="!theme.builtin" class="flex shrink-0 gap-1">
            <button type="button" class="rounded-lg px-2 py-1 text-xs font-bold text-accent-primary hover:bg-accent-primary/15"
              @click.stop="$emit('edit', theme)"
            >编辑</button>
            <button type="button" class="rounded-lg px-2 py-1 text-xs font-bold text-accent-danger hover:bg-accent-danger/15"
              @click.stop="$emit('delete', theme)"
            >删除</button>
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
