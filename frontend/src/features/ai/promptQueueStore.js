import { defineStore } from 'pinia'
import { ref } from 'vue'
import { toast, toUserMessage } from '../../shared/lib/common'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'

// 队列只接收规范化后的动作，避免不同检查模块各自拼 Confirm 参数造成弹窗行为不一致。
const normalizeAction = (action = {}) => ({
  id: String(action.id || action.value || '').trim(),
  label: String(action.label || '').trim(),
  kind: String(action.kind || 'secondary').trim(),
})

// 每个条目保留 raw 原始对象，按钮回调可以继续使用后端返回的完整业务数据。
const normalizePromptItem = (item = {}) => ({
  id: String(item.id || item.key || '').trim(),
  title: String(item.title || item.name || '').trim(),
  description: String(item.description || item.message || '').trim(),
  descriptionFormat: String(item.descriptionFormat || item.description_format || 'text').trim().toLowerCase(),
  meta: Array.isArray(item.meta) ? item.meta.map(value => String(value || '').trim()).filter(Boolean) : [],
  status: 'pending',
  statusMessage: '',
  actions: (item.actions || []).map(normalizeAction).filter(action => action.id && action.label),
  raw: item.raw || item,
})

// prompt 代表一个“类别弹窗”，例如工具环境、外部库更新、SteamCMD 模组更新。
const normalizePrompt = (prompt = {}) => {
  const normalized = {
    id: String(prompt.id || `prompt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`),
    category: String(prompt.category || 'general'),
    title: String(prompt.title || '系统提示'),
    message: String(prompt.message || ''),
    type: String(prompt.type || 'warning'),
    priority: Number(prompt.priority || 100),
    items: (prompt.items || []).map(normalizePromptItem).filter(item => item.id && item.title),
    bulkActions: (prompt.bulkActions || []).map(normalizeAction).filter(action => action.id && action.label),
    onItemAction: typeof prompt.onItemAction === 'function' ? prompt.onItemAction : null,
    onBulkAction: typeof prompt.onBulkAction === 'function' ? prompt.onBulkAction : null,
  }
  // 提交集合是队列层的幂等锁：条目一旦被单项/批量操作领取，后续点击就不能再次领取。
  normalized.submittedItemIds = new Set()
  normalized.isBulkSubmitting = false
  return normalized
}

// 统一启动期/维护期提示入口：同一时间只打开一个 Confirm，后续提示按优先级排队。
export const usePromptQueueStore = defineStore('promptQueue', () => {
  const queue = ref([])
  const activePrompt = ref(null)
  const isDraining = ref(false)

  const sortQueue = () => {
    queue.value = [...queue.value].sort((left, right) => {
      if (left.priority !== right.priority) return left.priority - right.priority
      return left.id.localeCompare(right.id)
    })
  }

  const isItemActionable = (prompt, item) => {
    return !!item && item.status === 'pending' && !prompt.submittedItemIds.has(item.id)
  }

  // 条目移除必须发生在点击同步阶段，避免用户随后点“全部处理”时再次提交同一条任务。
  const removePromptItem = (prompt, itemId) => {
    const index = prompt.items.findIndex(candidate => candidate.id === itemId)
    if (index >= 0) prompt.items.splice(index, 1)
  }

  const closePromptIfEmpty = (prompt, confirmStore) => {
    if (prompt.items.length === 0 && confirmStore.isVisible && !confirmStore.state.isResolving) {
      confirmStore.chooseAction({ scope: 'prompt-complete' })
    }
  }

  // 入队：将一个类别弹窗添加到队列，按优先级排序。
  const enqueue = (prompt) => {
    const normalized = normalizePrompt(prompt)
    if (normalized.items.length === 0) return Promise.resolve('')
    // 返回 Promise 方便调用方等待本类别弹窗被处理完，但不会要求业务方直接控制弹窗生命周期。
    return new Promise((resolve) => {
      normalized.resolve = resolve
      queue.value = [...queue.value, normalized]
      sortQueue()
      void drain()
    })
  }

  // 单项任务在条目移除后后台派发；结果交给任务管理器或 toast，不再阻塞当前弹窗。
  const runItemAction = async (prompt, item, actionId) => {
    const targetAction = item.actions.find(action => action.id === actionId)
    if (!targetAction) return false
    item.status = 'submitted'
    item.statusMessage = '已提交处理'
    try {
      if (prompt.onItemAction) {
        await prompt.onItemAction(item.raw, actionId, item)
      }
      return true
    } catch (error) {
      item.status = 'failed'
      console.warn('提示队列单项处理失败:', error)
      item.statusMessage = toUserMessage(error?.message || error, '处理失败。请检查网络连接、文件权限或稍后重试，详细原因已写入系统日志。')
      toast.error(item.statusMessage)
      return false
    }
  }

  // 批量任务只领取仍处于 pending 的条目，和单项点击共享 submittedItemIds 幂等锁。
  const runBulkAction = async (prompt, actionId) => {
    const targetAction = prompt.bulkActions.find(action => action.id === actionId)
    if (!targetAction) return
    if (prompt.isBulkSubmitting) return
    prompt.isBulkSubmitting = true
    const targets = prompt.items.filter(item => isItemActionable(prompt, item))
    targets.forEach(item => {
      prompt.submittedItemIds.add(item.id)
      item.status = 'submitted'
      item.statusMessage = '已提交处理'
    })
    prompt.items.splice(0, prompt.items.length)
    try {
      if (targets.length === 0) return
      if (prompt.onBulkAction) {
        await prompt.onBulkAction(actionId, targets.map(item => item.raw), prompt)
      }
    } catch (error) {
      console.warn('提示队列批量处理失败:', error)
      toast.error(toUserMessage(error?.message || error, `${targetAction.label}失败。请检查网络连接、文件权限或稍后重试，详细原因已写入系统日志。`))
    } finally {
      prompt.isBulkSubmitting = false
    }
  }

  // 打开类别弹窗：根据类别弹窗回调函数执行具体操作，更新状态并通知外部。
  const openPrompt = async (prompt) => {
    const confirmStore = useConfirmStore()
    const result = await confirmStore.open({
      title: prompt.title,
      message: prompt.message,
      type: prompt.type,
      mode: 'confirm',
      promptItems: prompt.items,
      // 单项操作点击即领取并移除，具体任务结果由任务栏/toast 呈现，弹窗只负责不重复提交。
      onPromptItemAction: async (itemId, actionId) => {
        const itemIndex = prompt.items.findIndex(candidate => candidate.id === itemId)
        const item = prompt.items[itemIndex]
        if (!isItemActionable(prompt, item)) return
        prompt.submittedItemIds.add(item.id)
        item.status = 'submitted'
        item.statusMessage = '已提交处理'
        removePromptItem(prompt, item.id)
        closePromptIfEmpty(prompt, confirmStore)
        void runItemAction(prompt, item, actionId)
      },
      // 底部按钮是窗口级操作：点击后关闭当前弹窗，再执行批量动作并继续处理队列。
      actionButtons: prompt.bulkActions.map(action => ({
        label: action.label,
        kind: action.kind,
        value: { scope: 'bulk', action: action.id },
      })),
    })
    if (result?.scope === 'bulk') {
      await runBulkAction(prompt, result.action)
    }
  }

  // 处理队列：从队列中取一个类别弹窗，打开并处理，直到队列为空。
  const drain = async () => {
    if (isDraining.value) return
    isDraining.value = true
    try {
      while (queue.value.length > 0) {
        // 每轮只取一个弹窗，保证多个启动提示不会互相覆盖。
        const [nextPrompt, ...remaining] = queue.value
        queue.value = remaining
        activePrompt.value = nextPrompt
        await openPrompt(nextPrompt)
        nextPrompt.resolve?.(nextPrompt.id)
        activePrompt.value = null
      }
    } finally {
      activePrompt.value = null
      isDraining.value = false
    }
  }

  return {
    // 队列状态
    queue, activePrompt, isDraining,
    // 队列操作
    enqueue, drain,
  }
})
