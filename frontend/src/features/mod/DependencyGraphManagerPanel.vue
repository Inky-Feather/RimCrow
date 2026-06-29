<template>
  <Teleport to="body">
  <div class="fixed z-140 flex max-h-[76vh] w-100 max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-accent-primary/24 bg-glass-heavy shadow-[0_18px_70px_var(--shadow-color)] backdrop-blur-xl"
    :style="panelStyle">
    <div class="absolute -left-12 -top-16 size-36 rounded-full bg-accent-primary/10 blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-16 -right-10 size-32 rounded-full bg-accent-special/10 blur-3xl pointer-events-none"></div>

    <header class="relative z-10 flex items-start justify-between gap-2 border-b border-border-base/10 px-3 pt-2.5 pb-1">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5">
          <h3 class="truncate text-sm font-black text-text-main">依赖线管理</h3>
          <span class="rounded-full bg-accent-primary/14 px-1.5 py-0.5 text-[0.62rem] font-bold text-accent-primary">
            {{ visibleCount }} / {{ effectiveTotal }}
          </span>
        </div>
        <p class="mt-0.5 text-[0.68rem] text-text-dim">
          可见 {{ visibleCount }} 条，已隐藏 {{ hiddenGroups.length }} 条。
        </p>
        <p v-if="focusSourceId" class="mt-0.5 text-[0.62rem] font-bold text-accent-special">
          当前仅绘制 1 条，右键绘图区可恢复。
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-1.5">
        <button class="modal-close-button"
          aria-label="关闭依赖线管理"
          @click="$emit('close')">
          <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </header>

    <div class="relative z-10 space-y-2 px-2 py-2">
      <div class="flex items-center">
        <div class="grid grid-cols-2 gap-1 rounded-2xl bg-bg-inset/35 p-1">
          <button v-for="page in pages" :key="page.key"
            class="rounded-xl px-1 py-0.5 text-[0.68rem] font-bold transition-all"
            :class="activePage === page.key ? 'bg-accent-primary/16 text-accent-primary shadow-sm' : 'text-text-dim hover:text-text-main'"
            @click="activePage = page.key">
            <span class="block truncate">{{ page.label }}</span>
          </button>
        </div>

        <label class="flex-1 flex items-center gap-1.5 rounded-xl border border-border-base/10 bg-bg-inset/40 px-2.5 py-1.5 text-[0.68rem] text-text-dim focus-within:border-accent-primary/25 focus-within:text-text-main">
          <svg class="size-3 shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-4.35-4.35"/>
          </svg>
          <input v-model.trim="searchQuery" type="text" class="min-w-0 flex-1 bg-transparent text-[0.68rem] text-text-main outline-none"
            placeholder="搜索依赖源名称或包名">
        </label>

      </div>
      <div class="relative z-10 flex items-center justify-between gap-2 text-[0.65rem] text-text-dim">
        <span class="truncate">{{ activePageMeta.tip }}</span>
        <button v-if="activePage === 'hidden' && hiddenGroups.length > 0"
          class="shrink-0 rounded-lg border border-border-base/12 px-2 py-1 font-bold transition-all hover:border-accent-primary/25 hover:text-text-main"
          @click="$emit('restoreAll')">
          全部恢复
        </button>
      </div>
    </div>

    

    <div class="relative z-10 flex-1 overflow-y-auto px-2.5 py-2.5 custom-scrollbar">
      <div v-if="activeGroups.length > 0" class="grid grid-cols-2 gap-1.5">
        <button v-for="group in activeGroups" :key="`${activePage}-${group.id}`"
          class="flex min-w-0 items-start gap-1.5 rounded-2xl border px-2 py-1.5 text-left transition-all"
          :class="activePage === 'hidden'
            ? 'border-border-base/10 bg-bg-inset/16 opacity-85 hover:border-accent-special/25 hover:bg-bg-overlay/8 hover:opacity-100'
            : 'border-border-base/10 bg-bg-inset/24 hover:border-accent-primary/22 hover:bg-bg-overlay/8'"
          @click="$emit('toggleSource', group.id)">
          <span class="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-white/12" :style="{ backgroundColor: group.color || (activePage === 'hidden' ? '#475569' : '#64748b') }"></span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-[0.7rem] font-bold leading-tight text-text-main">{{ group.name }}</span>
            <span class="mt-0.5 block truncate text-[0.62rem] leading-tight text-text-dim">{{ group.id }}</span>
            <span v-if="activePage === 'hidden' && !group.inCurrentList" class="mt-0.5 block truncate text-[0.6rem] leading-tight text-accent-special">历史隐藏项</span>
          </span>
          <span class="shrink-0 text-right text-[0.62rem] leading-tight text-text-dim">
            {{ activePage === 'hidden' ? group.childCountLabel : `${group.childCount}项` }}
          </span>
        </button>
      </div>
      <div v-else class="rounded-2xl border border-dashed border-border-base/12 px-3 py-5 text-center text-[0.68rem] text-text-dim">
        {{ activePageMeta.emptyText }}
      </div>
    </div>
  </div>
  </Teleport>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  panelStyle: { type: Object, default: () => ({}) },
  visibleCount: { type: Number, default: 0 },
  effectiveTotal: { type: Number, default: 0 },
  focusSourceId: { type: String, default: '' },
  currentGroups: { type: Array, default: () => [] },
  hiddenGroups: { type: Array, default: () => [] },
})

defineEmits(['close', 'toggleSource', 'restoreAll'])

const searchQuery = ref('')
const activePage = ref('visible')

const matchesSearch = (group) => {
  const query = String(searchQuery.value || '').trim().toLowerCase()
  if (!query) return true
  return [group?.name, group?.id].some(value => String(value || '').toLowerCase().includes(query))
}

const filteredCurrentGroups = computed(() => props.currentGroups.filter(matchesSearch))
const filteredHiddenGroups = computed(() => props.hiddenGroups.filter(matchesSearch))
const pages = computed(() => ([
  { key: 'visible', label: '可见', count: filteredCurrentGroups.value.length },
  { key: 'hidden', label: '隐藏', count: filteredHiddenGroups.value.length },
]))
const activeGroups = computed(() => (
  activePage.value === 'hidden' ? filteredHiddenGroups.value : filteredCurrentGroups.value
))
const activePageMeta = computed(() => (
  activePage.value === 'hidden'
    ? {
      tip: '点击任意隐藏项可立即恢复显示。',
      emptyText: '当前没有符合搜索条件的隐藏依赖线。',
    }
    : {
      tip: '点击任意可见项可直接隐藏该依赖线。',
      emptyText: '当前没有符合搜索条件的可见依赖线。',
    }
))
</script>
