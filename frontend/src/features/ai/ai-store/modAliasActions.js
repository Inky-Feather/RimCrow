import { computed } from 'vue'
import { checkResult, normalizeText, toast } from '../../../shared/lib/common'
import { normalizeNumber, normalizeTimestamp } from './factories'
import { useAppStore } from '../../../app/stores/appStore'

export const useModAliasActions = ({
  taskStore,
  modAliasTaskCompletionDataById, modAliasTaskCompletionWaiters, modAliasTaskRequestMetaById,
  modAliasReviewTaskPoolById, modAliasReviewTaskOrder,
  normalizeModAliasTaskInputItems, buildModSelectionAttachment,
  replaceGlobalAttachmentsByKind, removeGlobalAttachmentDraft,
} = {}) => {
  // -----------------------------------------------------------------
  // 任务输入与启动
  // -----------------------------------------------------------------
  const prepareModAliasTaskAttachment = ({ mods = [], ownerType = 'task', mode = 'single' } = {}) => {
    // 别名任务统一通过 mod_selection 附件传递输入对象，
    // 这样单模组重试和批量生成共用一套后端入口。
    const normalizedMods = normalizeModAliasTaskInputItems(mods)
    const draft = buildModSelectionAttachment({ mods: normalizedMods, ownerType, mode })
    const attachmentKeys = replaceGlobalAttachmentsByKind('mod_selection', [draft], {
      ownerType,
      taskPurpose: 'mod_alias_generation',
    })
    return { attachments: [draft], attachmentKeys, mods: normalizedMods }
  }

  const startModAliasGenerationTask = async ({ mods = [], ownerType = 'task', needsReview = false } = {}) => {
    /**
     * 发起模组别名生成任务。
     *
     * 这里负责把 UI 层输入统一改写成后端任务协议，并根据是否批量审阅
     * 记录对应的本地请求元数据。
     */
    if (!window.pywebview) return ''
    const appStore = useAppStore()
    if (!appStore.settings.ai.enabled) {
      toast.warning('AI 功能未启用。请先在设置中开启 AI 功能并完成模型配置。')
      return ''
    }
    const normalizedMods = normalizeModAliasTaskInputItems(mods)
    if (normalizedMods.length === 0) {
      toast.warning('没有可供处理的模组输入')
      return ''
    }
    const isBatch = normalizedMods.length > 1
    const normalizedNeedsReview = !!needsReview && isBatch
    const attachmentMode = isBatch ? 'multiple' : 'single'
    const prepared = prepareModAliasTaskAttachment({ mods: normalizedMods, ownerType, mode: attachmentMode })
    const payload = { attachments: prepared.attachments, needs_review: normalizedNeedsReview }
    const res = await window.pywebview.api.ai_start_task('task.mod_alias_generation', payload)
    if (!checkResult(res, '启动 AI 别名生成任务')) {
      prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)
      return ''
    }

    const taskId = normalizeText(res?.data?.task_id)
    if (!taskId) {
      prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)
      return ''
    }
    prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)

    modAliasTaskRequestMetaById[taskId] = {
      taskId,
      ownerType: normalizeText(ownerType, 'task'),
      createdAt: Date.now(),
      needsReview: normalizedNeedsReview,
      inputCount: normalizedMods.length,
      inputPackageIds: normalizedMods.map(item => item.package_id),
      title: normalizedMods.length > 1 ? 'AI 别名批量生成' : 'AI 别名生成',
    }

    taskStore.createPlaceholderTask({
      id: taskId,
      type: 'ai-task',
      status: 'pending',
      progress: 0,
      message: '任务已加入后台队列',
      metrics: {
        task_id: taskId,
        task_key: 'task.mod_alias_generation',
        title: modAliasTaskRequestMetaById[taskId].title,
        total: normalizedMods.length,
      },
    })
    return taskId
  }

  const requestSingleModAliasGenerationResult = async ({
    packageId = '', name = '', description = '', ownerType = 'review_modal',
  } = {}) => {
    /**
     * 以“单条立即返回”的方式请求一个模组的别名生成结果。
     *
     * 本质上仍走异步任务通道，只是前端在这里等待完成并提取第一条成功结果，
     * 方便检阅弹窗里的单项重试复用同一后端能力。
     */
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!normalizedPackageId) return null
    const taskId = await startModAliasGenerationTask({
      mods: [{ package_id: normalizedPackageId, name, description }],
      ownerType,
      needsReview: false,
    })
    if (!taskId) return null
    const completionPayload = await waitForModAliasTaskCompletion(taskId).catch(() => null)
    delete modAliasTaskCompletionDataById[taskId]
    const finalResults = Array.isArray(completionPayload?.results) ? completionPayload.results : []
    const first = finalResults.find(item => !item?._failed) || null
    return first && !first._failed ? first : null
  }

  // -----------------------------------------------------------------
  // 任务完成等待
  // -----------------------------------------------------------------
  const settleModAliasTaskCompletion = (taskId = '', payload = null) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return
    modAliasTaskCompletionDataById[normalizedTaskId] = payload
    const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
    modAliasTaskCompletionWaiters.delete(normalizedTaskId)
    waiters.forEach(resolve => {
      try {
        resolve(payload)
      } catch {
        // no-op
      }
    })
  }

  const waitForModAliasTaskCompletion = (taskId = '', timeout = 600000) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return Promise.resolve(null)
    if (Object.prototype.hasOwnProperty.call(modAliasTaskCompletionDataById, normalizedTaskId)) {
      return Promise.resolve(modAliasTaskCompletionDataById[normalizedTaskId] || null)
    }
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
        modAliasTaskCompletionWaiters.set(normalizedTaskId, waiters.filter(entry => entry !== wrappedResolve))
        resolve(null)
      }, timeout)
      const wrappedResolve = (payload) => {
        clearTimeout(timer)
        resolve(payload)
      }
      const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
      waiters.push(wrappedResolve)
      modAliasTaskCompletionWaiters.set(normalizedTaskId, waiters)
    })
  }

  // -----------------------------------------------------------------
  // 检阅结果归一化
  // -----------------------------------------------------------------
  const normalizeModAliasReviewResultItem = (item = {}, fallbackPackageId = '') => {
    const packageId = normalizeText(item?.package_id || fallbackPackageId).toLowerCase()
    if (!packageId) return null
    return {
      package_id: packageId,
      alias_name: normalizeText(item?.alias_name),
      notes: normalizeText(item?.notes),
      _failed: !!item?._failed,
      _attempt_count: normalizeNumber(item?._attempt_count, 0),
      _error: normalizeText(item?._error || item?.error || item?.message),
    }
  }

  const buildFailedModAliasReviewResultItem = (packageId = '', message = '') => {
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!normalizedPackageId) return null
    return {
      package_id: normalizedPackageId,
      alias_name: '',
      notes: '',
      _failed: true,
      _attempt_count: 0,
      _error: normalizeText(message),
    }
  }

  const normalizeModAliasReviewResultItems = ({ items = [], requestedPackageIds = [], fallbackError = '' } = {}) => {
    const requestedIds = [...new Set(
      (Array.isArray(requestedPackageIds) ? requestedPackageIds : [])
        .map(item => normalizeText(item).toLowerCase())
        .filter(Boolean)
    )]
    const requestedIdSet = new Set(requestedIds)
    const itemMap = new Map()
    ;(Array.isArray(items) ? items : []).forEach((rawItem) => {
      const normalized = normalizeModAliasReviewResultItem(rawItem)
      if (!normalized?.package_id) return
      if (requestedIdSet.size > 0 && !requestedIdSet.has(normalized.package_id)) return
      itemMap.set(normalized.package_id, normalized)
    })
    requestedIds.forEach((packageId) => {
      if (itemMap.has(packageId)) return
      const failedItem = buildFailedModAliasReviewResultItem(packageId, fallbackError)
      if (failedItem) itemMap.set(packageId, failedItem)
    })
    return Array.from(itemMap.values())
  }

  const createModAliasReviewTaskResult = (taskId = '', patch = {}) => ({
    taskId: normalizeText(taskId),
    title: normalizeText(patch?.title, '模组别名批量检阅'),
    status: normalizeText(patch?.status, 'success'),
    ownerType: normalizeText(patch?.ownerType, 'task'),
    createdAt: normalizeTimestamp(patch?.createdAt, Date.now()),
    completedAt: normalizeTimestamp(patch?.completedAt, Date.now()),
    inputCount: Math.max(0, normalizeNumber(patch?.inputCount, 0)),
    inputPackageIds: Array.isArray(patch?.inputPackageIds)
      ? [...new Set(patch.inputPackageIds.map(item => normalizeText(item).toLowerCase()).filter(Boolean))]
      : [],
    message: normalizeText(patch?.message),
    meta: patch?.meta && typeof patch.meta === 'object' ? { ...patch.meta } : {},
    items: Array.isArray(patch?.items) ? [...patch.items] : [],
  })

  const buildModAliasReviewTaskResult = ({ taskId = '', status = '', payload = {}, requestMeta = {}, message = '' } = {}) => {
    const meta = payload?.meta && typeof payload.meta === 'object' ? payload.meta : {}
    const requestedPackageIds = Array.isArray(requestMeta?.inputPackageIds) ? requestMeta.inputPackageIds : []
    const normalizedItems = normalizeModAliasReviewResultItems({
      items: Array.isArray(payload?.results) ? payload.results : [],
      requestedPackageIds,
      fallbackError: message || (status === 'error' ? '任务执行失败' : ''),
    })
    return {
      taskId: normalizeText(taskId),
      title: normalizeText(requestMeta?.title, '模组别名批量检阅'),
      status: normalizeText(status, 'success'),
      ownerType: normalizeText(requestMeta?.ownerType, 'task'),
      createdAt: normalizeTimestamp(meta?.created_at, requestMeta?.createdAt || Date.now()),
      completedAt: Date.now(),
      inputCount: normalizeNumber(meta?.input_total, requestMeta?.inputCount || normalizedItems.length),
      inputPackageIds: requestedPackageIds,
      message: normalizeText(message),
      meta: { ...meta, needs_review: true },
      items: normalizedItems,
    }
  }

  // -----------------------------------------------------------------
  // 检阅池
  // -----------------------------------------------------------------
  const getModAliasReviewTask = (taskId = '') => {
    const normalizedTaskId = normalizeText(taskId)
    return normalizedTaskId ? modAliasReviewTaskPoolById[normalizedTaskId] || null : null
  }

  const upsertModAliasReviewTask = (taskId = '', patch = {}) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return null
    const existing = getModAliasReviewTask(normalizedTaskId)
    const next = existing ? {
      ...existing, ...patch,
      taskId: normalizedTaskId,
      title: normalizeText(patch?.title, existing.title || '模组别名批量检阅'),
      status: normalizeText(patch?.status, existing.status || 'success'),
      ownerType: normalizeText(patch?.ownerType, existing.ownerType || 'task'),
      createdAt: normalizeTimestamp(patch?.createdAt, existing.createdAt || Date.now()),
      completedAt: normalizeTimestamp(patch?.completedAt, Date.now()),
      inputCount: Math.max(0, normalizeNumber(patch?.inputCount, existing.inputCount || 0)),
      inputPackageIds: Array.isArray(patch?.inputPackageIds)
        ? [...new Set(patch.inputPackageIds.map(item => normalizeText(item).toLowerCase()).filter(Boolean))]
        : [...(existing.inputPackageIds || [])],
      message: normalizeText(patch?.message, existing.message || ''),
      meta: { ...(existing.meta || {}), ...((patch?.meta && typeof patch.meta === 'object') ? patch.meta : {}) },
      items: Array.isArray(patch?.items) ? [...patch.items] : [...(existing.items || [])],
    } : createModAliasReviewTaskResult(normalizedTaskId, patch)
    modAliasReviewTaskPoolById[normalizedTaskId] = next
    if (!modAliasReviewTaskOrder.value.includes(normalizedTaskId)) {
      modAliasReviewTaskOrder.value.unshift(normalizedTaskId)
    }
    return next
  }

  const removeModAliasReviewTask = (taskId = '') => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId || !modAliasReviewTaskPoolById[normalizedTaskId]) return false
    delete modAliasReviewTaskPoolById[normalizedTaskId]
    modAliasReviewTaskOrder.value = modAliasReviewTaskOrder.value.filter(id => id !== normalizedTaskId)
    return true
  }

  const updateModAliasReviewTaskItem = (taskId = '', packageId = '', patch = {}) => {
    const task = getModAliasReviewTask(taskId)
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!task || !normalizedPackageId || !Array.isArray(task.items)) return false
    const index = task.items.findIndex(item => normalizeText(item?.package_id).toLowerCase() === normalizedPackageId)
    if (index < 0) return false
    const normalizedItem = normalizeModAliasReviewResultItem({ ...task.items[index], ...(patch || {}), package_id: normalizedPackageId })
    if (!normalizedItem) return false
    task.items.splice(index, 1, normalizedItem)
    task.completedAt = Date.now()
    return true
  }

  const removeModAliasReviewTaskItem = (taskId = '', packageId = '') => {
    const task = getModAliasReviewTask(taskId)
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!task || !normalizedPackageId || !Array.isArray(task.items)) return false
    const nextItems = task.items.filter(item => normalizeText(item?.package_id).toLowerCase() !== normalizedPackageId)
    if (nextItems.length === task.items.length) return false
    task.items = nextItems
    task.completedAt = Date.now()
    if (task.items.length === 0) removeModAliasReviewTask(taskId)
    return true
  }

  const clearModAliasReviewTaskPool = () => {
    Object.keys(modAliasReviewTaskPoolById).forEach((taskId) => {
      delete modAliasReviewTaskPoolById[taskId]
    })
    modAliasReviewTaskOrder.value = []
  }

  const pruneDuplicateModAliasReviewItems = (currentTaskId = '', packageIds = []) => {
    const duplicateIds = new Set((Array.isArray(packageIds) ? packageIds : []).map(item => normalizeText(item).toLowerCase()).filter(Boolean))
    if (duplicateIds.size === 0) return
    // 检阅池只保留每个模组的最新结果，避免旧任务和新任务同时修改同一条数据。
    modAliasReviewTaskOrder.value.slice().forEach((taskId) => {
      if (taskId === currentTaskId) return
      const task = getModAliasReviewTask(taskId)
      if (!task || !Array.isArray(task.items)) return
      const nextItems = task.items.filter(item => !duplicateIds.has(normalizeText(item?.package_id).toLowerCase()))
      if (nextItems.length === task.items.length) return
      task.items = nextItems
      task.completedAt = Date.now()
      if (task.items.length === 0) removeModAliasReviewTask(taskId)
    })
  }

  const modAliasReviewTasks = computed(() => modAliasReviewTaskOrder.value.map(taskId => modAliasReviewTaskPoolById[taskId] || null).filter(Boolean))
  const modAliasReviewItemCount = computed(() => modAliasReviewTasks.value.reduce((sum, task) => sum + (Array.isArray(task?.items) ? task.items.length : 0), 0))

  return {
    // 任务输入与启动
    prepareModAliasTaskAttachment, startModAliasGenerationTask, requestSingleModAliasGenerationResult,
    // 任务完成等待
    settleModAliasTaskCompletion, waitForModAliasTaskCompletion,
    // 检阅池状态
    modAliasReviewTasks, modAliasReviewItemCount, getModAliasReviewTask,
    // 检阅池修改
    updateModAliasReviewTaskItem, removeModAliasReviewTask, removeModAliasReviewTaskItem, clearModAliasReviewTaskPool,
    // 事件桥接内部复用
    buildModAliasReviewTaskResult, upsertModAliasReviewTask, pruneDuplicateModAliasReviewItems,
  }
}
