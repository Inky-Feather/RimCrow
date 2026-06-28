// stores/confirmStore.js
import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export const useConfirmStore = defineStore('confirm', () => {
  const isVisible = ref(false)
  
  // 弹窗配置
  const state = reactive({
    type: 'info',      // 'info' | 'warning' | 'error' | 'success'
    mode: 'alert',     // 'alert' | 'confirm' | 'prompt'
    title: '',
    message: '',
    isHtml: false,     // 是否允许 HTML 内容
    inputValue: '',    // Prompt 模式下的输入值
    placeholder: '',
    confirmText: '确定',
    cancelText: '取消',
    targetRect: null,  // 目标元素的位置信息 (用于迷你弹窗)
    validation: null,  // 输入验证函数 (val) => boolean
  })

  // Promise 控制器
  let resolvePromise = null
  let rejectPromise = null

  /**
   * 打开弹窗的核心方法
   * @param {Object} options 配置项
   * @param {HTMLElement|Event} [target] 可选：触发源，传入则变为迷你跟随弹窗
   */
  const open = (options, target = null) => {
    // 1. 重置状态
    state.inputValue = ''
    state.placeholder = ''
    state.message = ''
    state.title = ''
    state.targetRect = null
    state.validation = null
    
    // 2. 合并配置
    Object.assign(state, {
      type: 'info',
      mode: 'alert',
      confirmText: '确定',
      cancelText: '取消',
      ...options
    })

    // 3. 计算位置 (如果是迷你模式)
    if (target) {
      const el = target instanceof Event ? target.target : target
      if (el && el.getBoundingClientRect) {
        state.targetRect = el.getBoundingClientRect()
      }
    }

    isVisible.value = true

    // 4. 返回 Promise
    return new Promise((resolve, reject) => {
      resolvePromise = resolve
      rejectPromise = reject
    })
  }

  // 确认操作
  const confirm = () => {
    if (state.mode === 'prompt') {
      // 验证逻辑
      if (state.validation && !state.validation(state.inputValue)) {
        // 可以加一个抖动动画逻辑，这里简化处理
        return
      }
      resolvePromise && resolvePromise(state.inputValue)
    } else {
      resolvePromise && resolvePromise(true)
    }
    isVisible.value = false
  }

  // 取消操作
  const cancel = () => {
    // Confirm/Prompt 模式下，取消通常意味着 Promise resolve(false) 或 reject
    // 这里我们约定：Confirm 返回 false，Prompt 返回 null
    if (state.mode === 'confirm') resolvePromise && resolvePromise(false)
    else resolvePromise && resolvePromise(null)
    
    isVisible.value = false
  }

  // 便捷方法
  const alert = (title, message, options) => open({ title, message, mode: 'alert', ...options })
  
  const confirmAction = (title, message, options) => open({ title, message, mode: 'confirm', type: 'warning', ...options })
  
  const prompt = (title, placeholder, options) => open({ title, placeholder, mode: 'prompt', ...options })
  
  // 迷你弹窗便捷入口
  const popover = (target, title, message) => open({ title, message, mode: 'confirm' }, target)

  return { 
    isVisible, state, 
    open, confirm, cancel,
    alert, confirmAction, prompt, popover
  }
})