import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { useGuideStore } from '../../guide/guideStore'

export function useModListViewport({
  props,
  appStore,
  modStore,
  vListRef,
  visibleList,
  itemHeight,
  isDragging,
  finishDragSession,
  dispatchSyntheticDragEnd,
  cancelActiveDrag,
}) {
  // 点击列表区域时自动获取焦点，确保按键生效
  const focusContainer = (e) => {
    e.currentTarget.focus()
  }

  /**
   * 3. 键盘导航核心函数
   * @param {number} direction -1 为向上，1 为向下
   */
  const handleKeyNav = (direction) => {
    const list = visibleList.value // 当前可见的 ID 数组
    if (!list.length) return
    // 确定当前选中的索引
    const currentId = modStore.lastSelectedMod?.package_id
    const currentIndex = list.indexOf(currentId)
    // 计算下一个索引
    let nextIndex = currentIndex + direction
    // 边界保护：循环选择或停止
    if (nextIndex < 0) nextIndex = 0
    if (nextIndex >= list.length) nextIndex = list.length - 1
    if (nextIndex === currentIndex) return
    const nextId = list[nextIndex]
    // 4. 更新 Store 选中状态
    // 建议：键盘导航通常视为单选，所以传入 [nextId]
    modStore.selectMods([nextId], nextId)
    // 5. 同步滚动 (关键点)
    const vList = vListRef.value
    if (vList) {
      const currentOffset = vList.getOffset()
      const viewHeight = vList.$el.clientHeight // 视口高度
      // 计算目标项的像素区间
      const itemTop = nextIndex * itemHeight.value
      const itemBottom = itemTop + itemHeight.value
      // 策略 A: 保持相对位置不变 (最丝滑)
      // 逻辑：直接按位移滚动。如果向上移，offset 就减一个 itemHeight
      vList.scrollToOffset(currentOffset + (direction * itemHeight.value))
      // 策略 B: 只有当超出视口时才滚动 (标准做法)
      /*
      if (itemTop < currentOffset) {
        // 超出顶部
        vList.scrollToOffset(itemTop)
      } else if (itemBottom > currentOffset + viewHeight) {
        // 超出底部
        vList.scrollToOffset(itemBottom - viewHeight)
      }
      */
    }
  }

  const handleDirectiveNavigate = (nextId, nextIndex, direction) => {
    const vList = vListRef.value
    if (vList) {
      const currentOffset = vList.getOffset()
      // 策略 A: 保持相对位置不变的无缝滚动（推荐，因为 itemHeight 计算精确）
      vList.scrollToOffset(currentOffset + (direction * itemHeight.value))
      // 如果你喜欢系统原生那种“到底部才滚动页面”的感觉，可以使用策略 B：
      /*
      const viewHeight = vList.$el.clientHeight
      const itemTop = nextIndex * itemHeight.value
      const itemBottom = itemTop + itemHeight.value

      if (itemTop < currentOffset) {
        vList.scrollToOffset(itemTop)
      } else if (itemBottom > currentOffset + viewHeight) {
        vList.scrollToOffset(itemBottom - viewHeight)
      }
      */
    }
  }

  // --- 记录滚动位置 ---
  // v-if 切换到 loading 时，该组件内部的 v-else 块会触发卸载
  // 这是抓取当前滚动位置的最后机会
  onBeforeUnmount(() => {
    if (isDragging.value) {
      finishDragSession({ suppressDrop: true })
      dispatchSyntheticDragEnd()
    }
    savePosition()
  })

  const savePosition = () => {
    // 只有当虚拟列表存在且不在加载状态时才记录
    if (vListRef.value) {
      const offset = vListRef.value.getOffset()
      if (offset > 0) {
        appStore.recordScroll(props.listId, offset)
        // console.log(`[Scroll] Saved ${props.listId}: ${offset}`)
      }
    }
  }

  // --- 恢复滚动位置 ---
  onMounted(() => {
    // 如果组件挂载时不是加载状态，说明数据已经在那了，直接尝试恢复
    if (!appStore.isLoading) {
      restorePosition()
    }
  })

  // --- 监听加载状态变化 ---
  watch(() => appStore.isLoading, async (loading) => {
    // console.log(`[Scroll] Loading state changed to ${loading}`)
    if (loading) {
      await cancelActiveDrag()
      // 刚开始加载：如果在外面手动触发加载，这里也是一个记录点
      // 但注意：如果是 v-if 切换，组件可能已经开始销毁流程了
      savePosition()
    } else {
      // 加载完成：等待 DOM 渲染
      await nextTick()
      restorePosition()
      useGuideStore()
    }
  })

  const restorePosition = () => {
    const savedOffset = appStore.getScroll(props.listId)
    if (savedOffset > 0 && vListRef.value) {
      // 虚拟列表恢复位置的“黄金组合”：nextTick + 微小延迟
      nextTick(() => {
        setTimeout(() => {
          vListRef.value?.scrollToOffset(savedOffset)
          // console.log(`[Scroll] Restored ${props.listId}: ${savedOffset}`)
        }, 30) // 30ms 足够让大部分虚拟列表完成初始化计算
      })
    }
  }

  return {
    focusContainer,
    handleKeyNav,
    handleDirectiveNavigate,
    savePosition,
    restorePosition,
  }
}
