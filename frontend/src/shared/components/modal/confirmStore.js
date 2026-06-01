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
    targetRect: null,  // 目标元素的位置信息 (用于迷弹窗)
    validation: null,  // 输入验证函数 (val) => boolean
    showDeleteOptions: false,
    forceDelete: false,
    trashOptionText: '移入回收站',
    forceOptionText: '强制删除',
    deleteOptionsHint: '',
    // actionButtons 是窗口级按钮，promptItems 是队列弹窗的逐项操作列表；老 confirm/alert 调用不传则保持原行为。
    actionButtons: [],
    promptItems: [],
    onPromptItemAction: null,
    isResolving: false,
  })

  // Promise 控制器
  let resolvePromise = null
  let rejectPromise = null

  /**
   * 打开弹窗的核心方法
   * @param {Object} options 配置项
   * @param {HTMLElement|Event} [target] 可选：触发源，传入则变为迷跟随弹窗
   */
  const open = (options, target = null) => {
    // 1. 重置状态
    state.inputValue = ''
    state.placeholder = ''
    state.message = ''
    state.title = ''
    state.targetRect = null
    state.validation = null
    state.showDeleteOptions = false
    state.forceDelete = false
    state.trashOptionText = '移入回收站'
    state.forceOptionText = '强制删除'
    state.deleteOptionsHint = ''
    state.actionButtons = []
    state.promptItems = []
    state.onPromptItemAction = null
    state.isResolving = false
    
    // 2. 合并配置
    Object.assign(state, {
      type: 'info',
      mode: 'alert',
      confirmText: '确定',
      cancelText: '取消',
      ...options
    })

    // 3. 计算位置 (如果是迷模式)
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
    if (state.isResolving) return
    if (state.mode === 'prompt') {
      // 验证逻辑
      if (state.validation && !state.validation(state.inputValue)) {
        return
      }
      resolvePromise && resolvePromise(state.inputValue)
    } else if (state.showDeleteOptions) {
      resolvePromise && resolvePromise({ confirmed: true, force: !!state.forceDelete })
    } else if (Array.isArray(state.actionButtons) && state.actionButtons.length > 0) {
      resolvePromise && resolvePromise(state.actionButtons[0]?.value ?? true)
    } else {
      resolvePromise && resolvePromise(true)
    }
    state.isResolving = true
    isVisible.value = false
  }

  const chooseAction = (value) => {
    if (state.isResolving) return
    state.isResolving = true
    resolvePromise && resolvePromise(value)
    isVisible.value = false
  }

  // 队列弹窗的单项按钮不直接 resolve 当前弹窗，由 promptQueueStore 决定移除条目或关闭弹窗。
  const choosePromptItemAction = async (itemId, actionId) => {
    if (state.isResolving) return
    if (typeof state.onPromptItemAction !== 'function') return
    await state.onPromptItemAction(itemId, actionId)
  }

  const closeSilently = () => {
    // 仅关闭弹窗，不注入确认/取消结果。
    // 用于“后台等待流程已自动完成，只需把弹窗收起来”的场景。
    isVisible.value = false
  }

  // 取消操作
  const cancel = () => {
    if (state.isResolving) return
    // Confirm/Prompt 模式下，取消通常意味着 Promise resolve(false) 或 reject
    // 这里约定：Confirm 返回 false，Prompt 返回 null
    if (state.mode === 'confirm' && state.showDeleteOptions) {
      resolvePromise && resolvePromise({ confirmed: false, force: !!state.forceDelete })
    } else if (state.mode === 'confirm') resolvePromise && resolvePromise(false)
    else resolvePromise && resolvePromise(null)
    
    state.isResolving = true
    isVisible.value = false
  }

  // 便捷方法
  const alert = (title, message, options) => open({ title, message, mode: 'alert', ...options })
  
  const confirmAction = (title, message, options) => open({ title, message, mode: 'confirm', type: 'warning', ...options })

  const confirmDeleteAction = (title, message, options) => open({
    title,
    message,
    mode: 'confirm',
    type: 'error',
    confirmText: '确认删除',
    cancelText: '取消',
    showDeleteOptions: true,
    trashOptionText: '移入回收站',
    forceOptionText: '强制删除',
    deleteOptionsHint: '默认移入系统回收站；选择强制删除后将直接彻底删除，无法恢复。',
    ...options,
  })
  
  const prompt = (title, placeholder, options) => open({ title, placeholder, mode: 'prompt', ...options })
  
  // 迷弹窗便捷入口
  const popover = (target, title, message) => open({ title, message, mode: 'confirm' }, target)

  return { 
    isVisible, state, 
    open, confirm, cancel, chooseAction, choosePromptItemAction, closeSilently,
    alert, confirmAction, confirmDeleteAction, prompt, popover
  }
})
