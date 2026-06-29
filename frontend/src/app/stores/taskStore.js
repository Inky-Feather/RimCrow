import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { toUserMessage } from '../../shared/lib/common'

const TERMINAL_STATUSES = new Set(['success', 'failed', 'cancelled'])
const ACTIVE_STATUSES = new Set(['pending', 'running'])
const TASK_RETENTION_MS = 3000

const getTaskFailureMessage = (task = {}) => toUserMessage(
  task.message || task.metrics?.error || task.metrics?.original_error,
  '任务未成功完成。请检查网络连接、文件权限或稍后重试，详细原因已写入系统日志。',
)

export const useTaskStore = defineStore('tasks', () => {
  const taskMap = ref(new Map())
  const orderCounter = ref(0)
  const waiters = new Map()
  const cleanupTimers = new Map()

  const clearCleanupTimer = (taskId) => {
    const timer = cleanupTimers.get(taskId)
    if (timer) {
      clearTimeout(timer)
      cleanupTimers.delete(taskId)
    }
  }

  const removeTask = (taskId) => {
    clearCleanupTimer(taskId)
    taskMap.value.delete(taskId)
  }

  const notifyWaiters = (task) => {
    const entries = waiters.get(task.id)
    if (!entries || entries.length === 0) return
    waiters.delete(task.id)
    for (const entry of entries) {
      clearTimeout(entry.timer)
      if (task.status === 'success') {
        entry.resolve(task)
      } else {
        entry.reject(new Error(getTaskFailureMessage(task)))
      }
    }
  }

  const normalizeTask = (payload = {}, existing = null) => {
    const joinedAt = existing?.joinedAt ?? Number(payload.timestamp || Date.now())
    const order = existing?.order ?? (orderCounter.value += 1)
    const metrics = {
      ...(existing?.metrics || {}),
      ...(payload.metrics || {}),
    }
    const taskCreatedAt = Number(metrics.task_created_at || payload.timestamp || joinedAt || Date.now())
    const updatedAt = Number(payload.timestamp || metrics.task_updated_at || Date.now())
    metrics.task_created_at = taskCreatedAt
    metrics.task_updated_at = updatedAt
    return {
      ...(existing || {}),
      id: payload.id,
      type: String(payload.type || existing?.type || ''),
      status: String(payload.status || existing?.status || 'pending'),
      progress: Number(payload.progress ?? existing?.progress ?? 0),
      message: payload.message ?? existing?.message ?? '',
      metrics,
      joinedAt,
      updatedAt,
      order,
    }
  }

  const upsertTask = (payload = {}) => {
    if (!payload?.id) return null
    const existing = taskMap.value.get(payload.id) || null
    const task = normalizeTask(payload, existing)
    taskMap.value.set(task.id, task)

    if (TERMINAL_STATUSES.has(task.status)) {
      clearCleanupTimer(task.id)
      notifyWaiters(task)
      const timer = window.setTimeout(() => removeTask(task.id), TASK_RETENTION_MS)
      cleanupTimers.set(task.id, timer)
    } else {
      clearCleanupTimer(task.id)
    }

    return task
  }

  const createPlaceholderTask = ({ id, type, status = 'pending', progress = 0, message = '', metrics = {} }) => {
    return upsertTask({
      id,
      type,
      status,
      progress,
      message,
      metrics,
      timestamp: Date.now(),
    })
  }

  const tasks = computed(() => Array.from(taskMap.value.values()).sort((a, b) => {
    if (b.order !== a.order) return b.order - a.order
    return b.updatedAt - a.updatedAt
  }))

  const activeTasks = computed(() => tasks.value.filter(task => ACTIVE_STATUSES.has(task.status)))
  const latestTask = computed(() => tasks.value[0] || null)

  const getTask = (taskId) => taskMap.value.get(taskId) || null

  const getLatestTaskByType = (types) => {
    const targets = Array.isArray(types) ? types : [types]
    return tasks.value.find(task => targets.includes(task.type)) || null
  }

  const hasActiveTaskOfType = (types) => {
    const targets = Array.isArray(types) ? types : [types]
    return activeTasks.value.some(task => targets.includes(task.type))
  }

  const waitForTaskCompletion = (taskId, timeout = 600000) => {
    const currentTask = getTask(taskId)
    if (currentTask && TERMINAL_STATUSES.has(currentTask.status)) {
      if (currentTask.status === 'success') return Promise.resolve(currentTask)
      return Promise.reject(new Error(getTaskFailureMessage(currentTask)))
    }

    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        const entries = waiters.get(taskId) || []
        waiters.set(taskId, entries.filter(entry => entry.timer !== timer))
        reject(new Error('任务超时'))
      }, timeout)
      const entries = waiters.get(taskId) || []
      entries.push({ resolve, reject, timer })
      waiters.set(taskId, entries)
    })
  }

  const waitForLatestTaskByType = (types, { since = 0, timeout = 600000, startTimeout = 1500 } = {}) => {
    const targets = (Array.isArray(types) ? types : [types]).map(type => String(type || '')).filter(Boolean)
    const startedAfter = Math.max(0, Number(since || 0) - 500)
    const findTask = () => tasks.value.find(task => (
      targets.includes(task.type)
      && (!startedAfter || Number(task.joinedAt || task.metrics?.task_created_at || 0) >= startedAfter)
    )) || null
    const currentTask = findTask()
    if (currentTask?.id) return waitForTaskCompletion(currentTask.id, timeout)

    return new Promise((resolve, reject) => {
      const startedAt = Date.now()
      let timer = 0
      const tick = () => {
        const task = findTask()
        if (task?.id) {
          window.clearTimeout(timer)
          waitForTaskCompletion(task.id, timeout).then(resolve, reject)
          return
        }
        if (Date.now() - startedAt >= startTimeout) {
          resolve(null)
          return
        }
        timer = window.setTimeout(tick, 50)
      }
      tick()
    })
  }

  const settleActiveTasks = (types = null, { status = 'cancelled', message = '', metrics = {} } = {}) => {
    const normalizedTypes = types == null
      ? null
      : (Array.isArray(types) ? types : [types])
          .map(type => String(type || '').trim().toLowerCase())
          .filter(Boolean)

    let settledCount = 0
    for (const task of Array.from(taskMap.value.values())) {
      if (!ACTIVE_STATUSES.has(task.status)) continue
      if (normalizedTypes && !normalizedTypes.includes(task.type)) continue

      upsertTask({
        id: task.id,
        type: task.type,
        status,
        progress: task.progress ?? 0,
        message: message || task.message,
        metrics: {
          ...(task.metrics || {}),
          ...(metrics || {}),
        },
        timestamp: Date.now(),
      })
      settledCount += 1
    }

    return settledCount
  }

  return {
    // 状态
    taskMap, tasks, activeTasks, latestTask,
    // 写入与清理
    upsertTask, createPlaceholderTask, removeTask, settleActiveTasks,
    // 查询与等待
    getTask, getLatestTaskByType, hasActiveTaskOfType, waitForTaskCompletion, waitForLatestTaskByType,
  }
})
