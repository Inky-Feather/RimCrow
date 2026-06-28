<!-- components/common/ContextMenu/ContextMenuItem.vue -->
<template>
  <div ref="itemRef" class="group relative px-[4px] py-[4px] transition-all duration-200"
    :class="[item.type === 'grid' ? 'w-full min-w-[200px]' : 'max-w-[200px]']"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
  >
    <!-- 1. 分割线 -->
    <div v-if="item.divider" class="h-px bg-text-dim/30 my-0 mx-[6px]"></div>

    <!-- 2. Grid 面板模式 (嵌入式网格) -->
    <div v-else-if="item.type === 'grid'" class="px-1 py-1">
      <!-- 可选的小标题 -->
      <div v-if="item.label" class="text-[10px] text-text-dim px-1 mb-[6px] font-bold tracking-wider uppercase opacity-60">
        {{ item.label }}
      </div>
      
      <div class="flex flex-wrap gap-[4px]">
        <button v-for="(subItem, idx) in item.children" :key="idx" @click.stop="handleClick(subItem)"
          v-tooltip="subItem.tooltip || subItem.label || ''"
          class="relative flex items-center justify-center transition-all duration-200 active:scale-95 border group/btn select-none overflow-hidden"
          :class="[
            // 样式分支 A: 颜色块 (有 label 时不显示)
            !subItem.label ? 'aspect-square w-[33px] rounded-md' : '',
            // 样式分支 B: 标签块 (有 label 时显示)
            subItem.label ? 'px-[4px] py-[4px] rounded-md text-[11px] min-w-[35px]' : '',
            // 通用状态样式
            subItem.active ? 'ring-2 ring-text-main z-10 border-transparent bg-text-main/20' : 'border-text-main/10 hover:border-text-main/30 bg-text-main/5 hover:bg-text-main/10',
            // 禁用状态
            subItem.disabled ? 'opacity-40 cursor-not-allowed grayscale' : 'hover:scale-105',
            // 全选状态 (Solid)
            subItem.state === 'all' ? 'ring-2 ring-text-main z-10 border-transparent bg-text-main/20' : '',
            // 半选状态 (Dashed / Dimmed)
            subItem.state === 'some' ? 'ring-1 ring-text-main/50 border-text-main/30 bg-text-main/10' : ''
          ]"
          :style="{ backgroundColor: subItem.bgColor || subItem.color || 'transparent' }"
        >
          <!-- 选中状态指示器 (钩号) -->
          <svg v-if="subItem.active" 
            class="absolute inset-0 m-auto text-text-main drop-shadow-md pointer-events-none" 
            :class="subItem.color ? 'w-[16px] h-[16px]' : 'w-full h-full opacity-10'" 
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline>
          </svg>

          <div v-if="subItem.state === 'all'" class="absolute top-0 right-0 rounded-full text-accent-cool bg-bg-deep/50 drop-shadow-md pointer-events-none">◉</div>
          <div v-if="subItem.state === 'some'" class="absolute top-0 right-0 rounded-full text-accent-primary bg-bg-deep/50 drop-shadow-md pointer-events-none">⊙</div>
          
          <!-- 内容渲染 -->
          <template v-if="subItem.label">
            <!-- 优先显示图标 -->
            <component v-if="subItem.icon" :is="subItem.icon" class="w-[15px] h-[15px] opacity-80 group-hover/btn:opacity-100" />
            <!-- 其次显示 Label (如果也有图标，加个间距) -->
            <span v-if="subItem.label" :class="{'ml-[5px]': subItem.icon}" class="truncate max-w-[80px]"
              :style="{'color': subItem.color || 'currentColor'}">
              {{ subItem.label }}
             </span>
          </template>
          
          <!-- 颜色块模式下的特殊图标 (比如清除颜色的 X) -->
          <component v-else-if="subItem.icon" :is="subItem.icon" class="w-[16px] h-[16px] text-text-main/50 group-hover/btn:text-text-main" />
        </button>
      </div>
    </div>

    <!-- 3. 普通菜单项 -->
    <button v-else :disabled="item.disabled" @click.stop="handleClick(item)"
      class="flex w-full cursor-default items-center justify-between rounded-md px-[5px] py-[4px] text-[13px] font-medium transition-all duration-200 outline-none
      disabled:cursor-not-allowed disabled:opacity-40
      bg-transparent hover:bg-bg-highlight focus:bg-bg-highlight "
      :class="[levelClass(), activeSubMenu ? 'bg-bg-highlight' : '']"
    >
      <!-- 左侧：图标 + 文字 -->
      <div class="flex items-center gap-[5px] overflow-hidden">
        <component :is="item.icon" v-if="item.icon" class="size-[15px] opacity-70" />
        <!-- 文字内容靠左自动省略 -->
        <span class="truncate">{{ item.label }}</span>
      </div>

      <!-- 右侧：快捷键 或 箭头 -->
      <div class="ml-[22px] flex items-center gap-[7px] opacity-60">
        <span v-if="item.shortcut" class="text-[11px] tracking-widest font-sans">{{ item.shortcut }}</span>
        <!-- 有子菜单且不是 Grid 模式时显示箭头 -->
        <svg v-if="item.children && item.type !== 'grid'" class="size-[13px] -mr-[2px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
      </div>
    </button>

    <!-- 递归子菜单 (仅针对非 Grid 类型的子菜单) -->
    <Transition name="submenu">
      <div v-if="item.children && activeSubMenu && item.type !== 'grid'" ref="subMenuRef"
        class="absolute z-50 min-w-fit rounded-xl border border-text-dim/30 bg-bg-surface/90 p-[1px] backdrop-blur-lg shadow-xl shadow-black/40"
        :class="subMenuPositionClass" >
        <ContextMenuItem v-for="(subItem, idx) in item.children" :key="idx"
          :item="subItem" @close-menu="$emit('close-menu')" />
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useWindowSize } from '@vueuse/core'

const props = defineProps({
  item: { type: Object, required: true }
})

const emit = defineEmits(['close-menu'])

const itemRef = ref(null)
const subMenuRef = ref(null)
const activeSubMenu = ref(false)
const subMenuSide = ref('right') // 'right' | 'left'
const subMenuVerticalAlign = ref('top') // 'top' | 'bottom'
const { width: windowWidth, height: windowHeight } = useWindowSize()

// 样式映射
const levelClass = () => {
  const level = props.item.level || 'default'
  const classMap = {
    'default': 'text-text-main',
    'success': 'text-accent-success hover:bg-accent-success/20!',
    'warning': 'text-accent-warning hover:bg-accent-warning/20!',
    'warn': 'text-accent-warn hover:bg-accent-warn/20!',
    'error': 'text-red-500 hover:bg-red-500/20!',
    'danger': 'text-accent-danger hover:bg-accent-danger/20!',
  }
  return classMap[level]
}

// 统一点击处理
const handleClick = (targetItem) => {
  if (targetItem.disabled) return
  
  // 如果是普通父菜单（非 Grid），不执行动作，仅用于展开
  if (targetItem.children && targetItem.type !== 'grid') return 

  if (targetItem.action) {
    targetItem.action()
  }
  emit('close-menu') // 关闭整个菜单
}

// 鼠标进入：计算子菜单应该显示在左边还是右边
let hoverTimer = null
const handleMouseEnter = () => {
  if (props.item.disabled || !props.item.children || props.item.type === 'grid') return
  
  clearTimeout(hoverTimer)
  activeSubMenu.value = true

  nextTick(() => {
    if (!itemRef.value || !subMenuRef.value) return
    const parentRect = itemRef.value.getBoundingClientRect()
    // 动态计算方向：如果右侧放不下，就放左侧
    // 预估子菜单宽度 (Grid 可能会比较宽)
    const subWidth = subMenuRef.value.offsetWidth || 200
    const subHeight = subMenuRef.value.offsetHeight || 0 // 获取子菜单高度

    // X轴方向判断，如果右侧空间不足，显示在左侧
    if (parentRect.right + subWidth > windowWidth.value) {
      subMenuSide.value = 'left'
    } else {
      subMenuSide.value = 'right'
    }
    // Y轴方向判断 (新增逻辑)
    // 如果 [父元素顶部 + 子菜单高度] 超过了 [屏幕高度 - 底部安全距离(10px)]
    // 则该子菜单向上展开（底部对齐）
    if (parentRect.top + subHeight > windowHeight.value - 10) {
      subMenuVerticalAlign.value = 'bottom'
    } else {
      subMenuVerticalAlign.value = 'top'
    }
  })
}

// 鼠标离开：延迟关闭，防止鼠标划过间隙时消失
const handleMouseLeave = () => {
  if (props.item.type === 'grid') return // Grid 不需要关闭逻辑
  hoverTimer = setTimeout(() => {
    activeSubMenu.value = false
  }, 200)
}

// 动态计算子菜单位置类名
const subMenuPositionClass = computed(() => {
  let classes = []
  // X轴
  if (subMenuSide.value === 'right') {
    classes.push('left-[98%] -ml-[1px]')
  } else {
    classes.push('right-[98%] -mr-[1px]')
  }
  // Y轴 
  if (subMenuVerticalAlign.value === 'bottom') {
    // 底部对齐：子菜单底部与父菜单项底部对齐
    classes.push('bottom-0 origin-bottom-left')
  } else {
    // 顶部对齐：子菜单顶部与父菜单项顶部对齐
    classes.push('top-0 origin-top-left')
  }
  return classes.join(' ')
})
</script>
<style scoped>
/* 子菜单过渡动画 */
.submenu-enter-active, .submenu-leave-active {
  transition: opacity 0.15s ease, transform 0.15s cubic-bezier(0.16, 1, 0.3, 1);
}
.submenu-enter-from, .submenu-leave-to {
  opacity: 0;
  transform: scale(0.95) translateX(-5px);
}
</style>