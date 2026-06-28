<!-- components/common/ContextMenu/ContextMenu.vue -->
<template>
  <Teleport to="body">
    <Transition name="scale">
      <div v-if="menuStore.show" ref="menuRef"
        class="context-menu-surface fixed z-9999 min-w-[160px] py-[4px] rounded-xl border border-border-base/10 bg-glass-medium shadow-2xl backdrop-blur-xl ring-1 ring-border-base/5 shadow-black/40"
        :class="[enableTransition ? 'transition-[top,left] duration-300 cubic-bezier(0.16, 1, 0.3, 1)' : '']"
        :style="menuStyle" @contextmenu.prevent
      >
        <ContextMenuItem v-for="(item, idx) in visibleMenuItems" 
          :key="idx + '-' + menuStore.x + '-' + menuStore.y" :item="item" :path="String(idx)"
          @close-menu="menuStore.close()"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, provide } from 'vue'
import { onClickOutside, useWindowSize, useEventListener } from '@vueuse/core'
import { getVisibleMenuItems, useContextMenuStore } from './contextMenuStore' // 调整路径
import ContextMenuItem from './ContextMenuItem.vue'

const menuStore = useContextMenuStore()
const menuRef = ref(null)
const { width: winWidth, height: winHeight } = useWindowSize()
const enableTransition = ref(false)
// hidden 只控制渲染，不改变菜单数据本身，便于调用方在同一语义区块内保留完整结构。
const visibleMenuItems = computed(() => getVisibleMenuItems(menuStore.items))

// 实际渲染坐标 (防止溢出)
const actualX = ref(0)
const actualY = ref(0)
const hoveredMenuPath = ref('')
provide('context-menu-hover-path', {
  hoveredPath: hoveredMenuPath,
  setHoveredPath: (path = '') => {
    hoveredMenuPath.value = String(path || '')
  },
})
// 监听 menuStore 打开状态，进行坐标计算
watch([() => menuStore.show, () => menuStore.x, () => menuStore.y],
  async ([show, x, y]) => {
    if (show) {
      // 关键点1：如果是刚刚打开（之前是关闭的），先禁用过渡，防止从 0,0 飞过来
      // 可以通过判断 menuRef 是否存在来猜测，或者简单粗暴地每次计算前先关掉
      if (!menuRef.value) {
        enableTransition.value = false
      }
      await nextTick()
      enableTransition.value = true
      if (!menuRef.value) return

      const { offsetWidth, offsetHeight } = menuRef.value
      // 注意：这里使用传入的新 x, y 进行计算
      
      const margin = 8
      const maxX = Math.max(margin, winWidth.value - offsetWidth - margin)
      const maxY = Math.max(margin, winHeight.value - offsetHeight - margin)
      // 右键点靠近窗口边缘时仍要把菜单完整留在视口内，避免主菜单第一层就被裁掉。
      actualX.value = Math.max(margin, Math.min(x + offsetWidth > winWidth.value ? x - offsetWidth : x, maxX))
      actualY.value = Math.max(margin, Math.min(y + offsetHeight > winHeight.value ? y - offsetHeight : y, maxY))
      // 关键点2：坐标计算赋值完毕后，下一帧开启过渡
      // 这样后续的移动（第二次右键）就会有动画了
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
           enableTransition.value = true
        })
      })
    } else {
      // 关闭时重置
      enableTransition.value = false
      hoveredMenuPath.value = ''
    }
  }
)
// 监听全局右键事件
useEventListener(window, 'contextmenu', (e) => {
  // 只有当菜单显示时才处理
  if (!menuStore.show) return

  // 这里的逻辑很巧妙：
  // 如果在“触发组件”上右键，menuStore.open() 里调用了 event.stopPropagation()
  // 所以事件根本不会冒泡到 window，这行代码不会执行，菜单不会被误关闭。
  menuStore.close()
  
  // 【不显示浏览器默认菜单】
  e.preventDefault()
})

const menuStyle = computed(() => ({
  left: `${actualX.value}px`,
  top: `${actualY.value}px`,
}))

// 点击外部关闭
onClickOutside(menuRef, () => {
  menuStore.close()
}, {
  ignore: ['.context-submenu-surface']
})

// 监听 ESC 键关闭
useEventListener(window, 'keydown', (e) => {
  if (e.key === 'Escape' && menuStore.show) menuStore.close()
})
</script>

<style scoped>
/* 主菜单弹出动画：类似于 macOS 的弹出效果 */
.scale-enter-active {
  transition: opacity 0.15s ease-out, transform 0.15s cubic-bezier(0.16, 1, 0.3, 1);
}
.scale-leave-active {
  transition: opacity 0.1s ease-in, transform 0.1s ease-in;
}
.scale-enter-from,
.scale-leave-to {
  opacity: 0;
  transform: scale(0.9);
}
</style>
