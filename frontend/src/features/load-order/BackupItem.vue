<template>
  <div class="relative flex items-center py-1 px-2 rounded-lg group border transition-all duration-200 cursor-pointer select-none"
    :class="[isSelected ? 'bg-accent-primary/10 border-accent-primary/30 shadow-[inset_0_0_10px_rgba(var(--rgb-accent-primary),0.1)]' : 'bg-glass-medium border-border-base/5 hover:bg-bg-overlay/5 hover:border-border-base/18' ]"
    @click="$emit('select', item)"
    @contextmenu="$emit('menu', $event, item)">
    <!-- 中间信息 -->
    <div class="flex-1 min-w-0 flex flex-col justify-center">
      <!-- 距离时间/文件名 -->
      <div class="flex items-center gap-2">
        <!-- 左侧图标 -->
        <div v-if="!item.displayTitle" class="rounded-md px-1 py-0.5 w-17 flex items-center justify-center transition-colors text-[0.6rem] gap-0.5"
          :class="isSelected ? 'bg-accent-primary/30 text-accent-primary' : 'bg-accent-primary/20 text-text-dim group-hover:text-text-main'">
          <svg v-if="item.type === 'today'" class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          <svg v-else-if="item.type === 'earlier'" class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/><path d="M16 18h.01"/></svg>
          <svg v-else class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
          <span>{{ item.distanceNow }}</span>
        </div>
        <!-- 具体时间 -->
        <div class="flex-1 text-[0.8rem] text-text-dim truncate font-mono mt-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
          <span v-if="item.displayTitle" v-tooltip="item.displayTitle" class="text-sm font-medium truncate flex items-center gap-1" :class="isSelected ? 'text-text-main' : 'text-text-main'">
            <svg class="w-3 h-3 min-w-4 min-h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
            {{ item.displayTitle }}
            <span v-if="item.formatLabel" class="rounded bg-bg-inset/60 px-1.5 py-0.5 text-[0.7rem] font-bold uppercase tracking-wide text-accent-cool/80">
              {{ item.formatLabel }}
            </span>
          </span>
          <span>{{ item.displayTime }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧操作 (Hover显示) -->
    <div class="relative w-6 h-6 flex items-center justify-center">
      <div class="absolute -right-2 mr-1 overflow-visible gap-1 text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
        <button @click.stop="$emit('load', $event, item)" class=" z-10 h-6 px-3 relative rounded-md whitespace-nowrap cursor-pointer
          inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300
          text-text-dim bg-accent-primary/10
          hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100
          group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
          v-tooltip="'加载文件'">
          <span class="relative transition duration-300 only:-mx-6">
            <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
          </span>
        </button>
        <button @click.stop="$emit('menu', $event, item)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer
          inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300
          text-text-dim bg-bg-overlay/5
          hover:bg-bg-overlay/12 hover:text-text-main hover:scale-110 active:scale-100
          group-hover:bg-bg-overlay/10 group-hover:text-text-dim group-hover:shadow-2xl/20
          group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100"
          v-tooltip="'更多操作'">
          <span class="relative only:-mx-6">
            <MoreHorizontal class="size-4" />
          </span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { MoreHorizontal } from 'lucide-vue-next'

defineProps({
  item: { type: Object, required: true },
  isSelected: { type: Boolean, default: false },
})

defineEmits(['select', 'load', 'delete', 'remove', 'menu', 'exportOrder'])
</script>
