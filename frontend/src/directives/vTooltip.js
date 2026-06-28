
// directives/vTooltip.js
import { useHoverStore } from '../stores/hoverStore'

export const vTooltip = {
  mounted(el, binding) {
    const store = useHoverStore()
    
    // 优先使用指令的值，如果没有，尝试读取 title 属性,将值存到 el 属性上，而不是锁死在下面事件函数的闭包里
    el._tipValue = binding.value
    
    // 如果元素上有 title 属性，将其移除以防止原生 tooltip 出现，并存下来
    if (el.hasAttribute('title')) {
      el._tipValue = el._tipValue || el.getAttribute('title')
      el.removeAttribute('title')
    }

    // 如果没有内容，就不绑定事件
    if (!el._tipValue) return

    // 定义处理函数
    const handleEnter = (e) => {
      // binding.value 就是你传给指令的数据 (例如: modData)
      store.show(el._tipValue, e)
    }
    
    const handleMove = (e) => {
      store.updatePosition(e)
    }
    
    const handleLeave = () => {
      store.hide()
    }

    // 缓存处理函数以便卸载
    el._vTooltipHandlers = {
      enter: handleEnter, // 第三个参数标记类型
      move: handleMove,
      leave: handleLeave
    }

    el.addEventListener('mouseenter', el._vTooltipHandlers.enter)
    el.addEventListener('mousemove', el._vTooltipHandlers.move)
    el.addEventListener('mouseleave', el._vTooltipHandlers.leave)
  },
   updated(el, binding) {
    // 更新元素上存储的值，供下次 enter 使用
    el._tipValue = binding.value

    // 实时响应：如果值变了，且当前 Tooltip 正在显示这个元素的内容
    if (binding.value !== binding.oldValue) {
      const store = useHoverStore()
      
      // 这里的逻辑是：如果 Store 当前显示的文字等于 旧值，
      // 说明现在的 Tooltip 很可能就是由这个元素触发的。
      // (加上 store.isHovering 判断更安全)
      if (store.isHovering && store.data === binding.oldValue) {
        // 延迟更新，避免闪烁
        setTimeout(() => {
          store.data = binding.value
        }, 200)
      }
    }
  },
  unmounted(el) {
    if (el._vTooltipHandlers) {
      el.removeEventListener('mouseenter', el._vTooltipHandlers.enter)
      el.removeEventListener('mousemove', el._vTooltipHandlers.move)
      el.removeEventListener('mouseleave', el._vTooltipHandlers.leave)
      delete el._vTooltipHandlers
      delete el._tipValue
    }
  }
}