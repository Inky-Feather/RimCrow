// src/directives/vPreview.js
import { useHoverStore } from '../stores/hoverStore'

export const vPreview = {
  // 当元素挂载到 DOM 时
  mounted(el, binding) {
    const store = useHoverStore()
    
    // 定义处理函数
    const handleEnter = (e) => {
      // binding.value 就是你传给指令的数据 (例如: modData)
      store.show(binding.value, e)
    }
    
    const handleMove = (e) => {
      store.updatePosition(e)
    }
    
    const handleLeave = () => {
      store.hide()
    }

    // 绑定事件
    el.addEventListener('mouseenter', handleEnter)
    el.addEventListener('mousemove', handleMove)
    el.addEventListener('mouseleave', handleLeave)

    // 将函数挂载到 el 上，方便在 unmounted 时移除
    el._vPreviewHandlers = { handleEnter, handleMove, handleLeave }
  },

  // (可选) 如果传入的数据动态改变了，且鼠标正停留在上面，可以实时更新
  updated(el, binding) {
    const store = useHoverStore()
    // 只有当数据真变了，且当前正在 hover 这个元素时才更新 store
    if (binding.value !== binding.oldValue && store.isHovering && store.data === binding.oldValue) {
      // 延迟更新，避免闪烁
      setTimeout(() => {
        store.data = binding.value
      }, 200)
    }
  },

  // 卸载时清理事件监听，防止内存泄漏
  unmounted(el) {
    const { handleEnter, handleMove, handleLeave } = el._vPreviewHandlers || {}
    if (handleEnter) {
      el.removeEventListener('mouseenter', handleEnter)
      el.removeEventListener('mousemove', handleMove)
      el.removeEventListener('mouseleave', handleLeave)
    }
    delete el._vPreviewHandlers
  }
}