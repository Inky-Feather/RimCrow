// stores/hoverStore.js
import { defineStore } from 'pinia'
import { ref, markRaw } from 'vue'

export const useHoverStore = defineStore('hover', () => {
  // 意图显示状态 (鼠标是否在组件上)
  const isHovering = ref(false)
  const type = ref('preview') // 类型：'preview' | 'text'
  
  // 数据与坐标
  const data = ref(null)
  const targetX = ref(0)
  const targetY = ref(0)

  // 存组件和它的 props
  const customComponent = ref(null)
  const componentProps = ref({})

  /**
   * 显示悬浮面板
   * show 接收的参数 content 可以是：
   * 1. 字符串 (Tooltip)
   * 2. 对象 (标准 Preview)
   * 3. { component: MyCom, props: {...} } (自定义组件)
   */
  const show = (content, event) => {
    // 防止传入空数据报错
    if (!content) return
    // 情况 A: 自定义组件模式
    if (content && content.component) {
      // 必须用 markRaw 包裹组件定义！
      customComponent.value = markRaw(content.component)
      componentProps.value = content.props || {}
      type.value = 'component'
    } // 情况 B: 普通数据模式
    else if (typeof content === 'object') {
      data.value = content
      type.value = 'preview'
    } 
    // 情况 C: 纯文本模式
    else {
      data.value = content
      type.value = 'text'
    }
    isHovering.value = true
    if (event) updatePosition(event)
  }

  // 隐藏请求
  const hide = () => {
    isHovering.value = false
    // 不清空 data，防止淡出动画时内容突然消失
  }

  // 更新位置 (高频触发)
  const updatePosition = (event) => {
    targetX.value = event.clientX
    targetY.value = event.clientY
  }

  return { 
    isHovering, data, type, targetX, targetY, customComponent, componentProps,
    show, hide, updatePosition 
  }
})