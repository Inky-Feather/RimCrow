
// directives/vTooltip.js
import { useHoverStore } from '../stores/hoverStore'

export const vTooltip = {
  mounted(el, binding) {
    const store = useHoverStore()
    
    // 优先使用指令的值，如果没有，尝试读取 title 属性
    let content = binding.value
    
    // 如果元素上有 title 属性，将其移除以防止原生 tooltip 出现，并存下来
    if (el.hasAttribute('title')) {
      content = content || el.getAttribute('title')
      el.removeAttribute('title')
    }

    // 如果没有内容，就不绑定事件
    if (!content) return

    // 缓存处理函数以便卸载
    el._vTooltipHandlers = {
      enter: (e) => store.show(content, e), // 第三个参数标记类型
      move: (e) => store.updatePosition(e),
      leave: () => store.hide()
    }

    el.addEventListener('mouseenter', el._vTooltipHandlers.enter)
    el.addEventListener('mousemove', el._vTooltipHandlers.move)
    el.addEventListener('mouseleave', el._vTooltipHandlers.leave)
  },

  unmounted(el) {
    if (el._vTooltipHandlers) {
      el.removeEventListener('mouseenter', el._vTooltipHandlers.enter)
      el.removeEventListener('mousemove', el._vTooltipHandlers.move)
      el.removeEventListener('mouseleave', el._vTooltipHandlers.leave)
    }
  }
}