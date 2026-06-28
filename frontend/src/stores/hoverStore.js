// stores/hoverStore.js
import { defineStore } from 'pinia'
import { ref, markRaw } from 'vue'
import { useAppStore } from './appStore'

export const useHoverStore = defineStore('hover', () => {
  // 意图显示状态 (鼠标是否在组件上)
  const isHovering = ref(false)
  const type = ref('preview') // 类型：'preview' | 'text'
  const isHtml = ref(false) // 标记内容是否为原始 HTML
  
  // 数据与坐标
  const data = ref(null)
  const targetX = ref(0)
  const targetY = ref(0)

  // 存组件和它的 props
  const customComponent = ref(null)
  const componentProps = ref({})
  const activeTarget = ref(null) // 新增：记录当前触发源

  // 内部计时器
  let timer = null
  const DELAY_MS = 500 // 延时时长 (建议大于 CSS transition 时间)

  /**
   * 显示悬浮面板
   * show 接收的参数 content 可以是：
   * 1. 字符串 (Tooltip)
   * 2. 对象 (标准 Preview)
   * 3. { component: MyCom, props: {...} } (自定义组件)
   */
  const show = (content, event) => {
    // 【关键修复】: 在创建新计时器前，必须清除旧的！
    // 否则快速切换目标时，旧的计时器会变成“僵尸”，在hide之后依然触发显示
    if (timer) clearTimeout(timer)
    // 防止传入空数据报错
    if (!content) return
    // console.log('show', content, event)
    // 记录触发源 (可以是 DOM 元素或者一个唯一标识)
    activeTarget.value = event?.currentTarget || true 
    // 延迟显示，避免立即显示导致的闪烁
    timer = setTimeout(() => {
      // 重置 html 标记
      isHtml.value = false 
      const appStore = useAppStore()
      // 情况 A: 自定义组件模式
      if (content && content.component) {
        // 必须用 markRaw 包裹组件定义！
        customComponent.value = markRaw(content.component)
        componentProps.value = content.props || {}
        type.value = 'component'
      }
      // 情况 B: 传入的是配置对象 { content: '...', html: true }
      else if (content && typeof content === 'object' && content.content) {
        data.value = content.content
        // 如果标记了 html: true，则开启 HTML 模式
        if (content.html) isHtml.value = true
        
        // 如果传入了 type (比如 'preview')，则使用传入的，否则默认为 text
        type.value = content.type || 'text' 
      }
      // 情况 C: 传入的是普通对象 (Mod数据预览) 且设置中允许显示悬浮面板
      else if (typeof content === 'object') {
        if (!appStore.settings.ui.show_mod_hover_panel) return
        data.value = content
        type.value = 'preview'
      } 
      // 情况 D: 纯文本
      else {
        data.value = content
        type.value = 'text'
      }
      isHovering.value = true
    }, DELAY_MS)
    if (event) updatePosition(event)
  }

  // 隐藏请求
  const hide = (target = null) => {
    // 如果传入了 target，只有当 target 匹配当前活跃源时才关闭
    // 这能防止：元素 A 消失触发 hide，但鼠标其实已经瞬间移动到元素 B 上了
    if (target && activeTarget.value !== target) return
    // 清除任何正在等待显示的计时器 (防止移出后，之前的计时器还在跑，导致突然弹出来)s
    if (timer) {
      clearTimeout(timer)
      timer = null // 建议置空
    }
    isHovering.value = false
    activeTarget.value = null
    // 不清空 data，防止淡出动画时内容突然消失
  }

  // 更新位置 (高频触发)
  const updatePosition = (event) => {
    targetX.value = event.clientX
    targetY.value = event.clientY
  }

  return { 
    isHovering, data, type, isHtml, targetX, targetY, customComponent, componentProps,
    show, hide, updatePosition 
  }
})