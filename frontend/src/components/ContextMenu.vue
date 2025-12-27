<template>
  <Transition name="fade">
    <div 
      v-if="store.show"
      ref="menuRef"
      class="fixed z-[9999] min-w-[140px] bg-bg-deep/95 backdrop-blur-xl border border-white/10 rounded-lg shadow-2xl py-1 overflow-hidden"
      :style="{ left: positionX + 'px', top: positionY + 'px' }"
      @click.stop="store.close()"
      @contextmenu.prevent
    >
      <div 
        v-for="(item, idx) in store.items" 
        :key="idx"
      >
        <!-- 分割线 -->
        <div v-if="item.divider" class="h-[1px] bg-white/10 my-1 mx-2"></div>
        
        <!-- 菜单项 -->
        <div 
          v-else
          @click="item.action && item.action()"
          class="px-3 py-1.5 text-xs cursor-pointer flex items-center gap-2 transition-colors"
          :class="item.danger ? 'text-red-400 hover:bg-red-500/20' : 'text-text-main hover:bg-white/10'"
        >
          <span v-if="item.icon">{{ item.icon }}</span>
          {{ item.label }}
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useContextMenuStore } from '../stores/contextMenuStore'

const store = useContextMenuStore()
const menuRef = ref(null)

// 简单的防溢出逻辑：如果菜单超出屏幕，向左/向上显示
const positionX = computed(() => {
  const width = 140
  if (store.x + width > window.innerWidth) return store.x - width
  return store.x
})
const positionY = computed(() => {
  // 假设菜单高度大概 200，精确计算需要 nextTick 获取 ref 高度
  if (store.y + 200 > window.innerHeight) return store.y - 200
  return store.y
})

// 点击外部关闭
const handleClickOutside = (e) => {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    store.close()
  }
}

onMounted(() => window.addEventListener('click', handleClickOutside, true))
onUnmounted(() => window.removeEventListener('click', handleClickOutside, true))
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: scale(0.95); }
</style>