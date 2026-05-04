// src/stores/textureStore.js
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useAppStore } from './appStore'
import { toast, checkResult } from '../utils/common'
import { useTaskStore } from './taskStore'

export const useTextureStore = defineStore('texture', () => {
  const appStore = useAppStore()
  const taskStore = useTaskStore()
  let toolStatusRefreshTimer = null

  const createEmptyTextureStat = () => ({
    mod_path: '',
    mod_name: '',
    source_total_count: 0,
    source_total_bytes: 0,
    output_total_count: 0,
    output_total_bytes: 0,
    current_output_count: 0,
    current_output_bytes: 0,
    generate_required_count: 0,
    skip_small_count: 0,
    unsupported_source_count: 0,
    unreadable_source_count: 0,
    scaled_count: 0,
    fallback_scaled_count: 0,
    keep_original_count: 0,
    source_vram_bytes_est: 0,
    output_vram_bytes_est: 0,
    vram_saving_bytes_est: 0,
    combined_total_bytes: 0,
    source_bytes_share_pct: 0,
    output_bytes_share_pct: 0,
    combined_bytes_share_pct: 0,
    scale_breakdown: [],
    projection_basis: [],
    engine_unsupported_preview: [],
    mod_count: 0,
  })

  const toInt = (value, fallback = 0) => {
    const num = Number(value)
    return Number.isFinite(num) ? num : fallback
  }

  const normalizeTextureStat = (raw = {}, { includeModCount = false } = {}) => {
    const base = createEmptyTextureStat()
    const sourceTotalCount = toInt(raw.source_total_count ?? raw.source_count ?? base.source_total_count)
    const sourceTotalBytes = toInt(raw.source_total_bytes ?? base.source_total_bytes)
    const outputTotalCount = toInt(raw.output_total_count ?? base.output_total_count)
    const outputTotalBytes = toInt(raw.output_total_bytes ?? base.output_total_bytes)
    const currentOutputCount = toInt(raw.current_output_count ?? raw.up_to_date_count ?? base.current_output_count)
    const currentOutputBytes = toInt(raw.current_output_bytes ?? base.current_output_bytes)

    const normalized = {
      ...base,
      ...raw,
      mod_path: String(raw.mod_path || base.mod_path),
      mod_name: String(raw.mod_name || base.mod_name),
      source_total_count: sourceTotalCount,
      source_total_bytes: sourceTotalBytes,
      output_total_count: outputTotalCount,
      output_total_bytes: outputTotalBytes,
      current_output_count: currentOutputCount,
      current_output_bytes: currentOutputBytes,
      generate_required_count: toInt(raw.generate_required_count ?? raw.pending_count ?? base.generate_required_count),
      skip_small_count: toInt(raw.skip_small_count ?? raw.skipped_small_count ?? base.skip_small_count),
      unsupported_source_count: toInt(raw.unsupported_source_count ?? raw.unsupported_count ?? base.unsupported_source_count),
      unreadable_source_count: toInt(raw.unreadable_source_count ?? base.unreadable_source_count),
      scaled_count: toInt(raw.scaled_count ?? base.scaled_count),
      fallback_scaled_count: toInt(raw.fallback_scaled_count ?? base.fallback_scaled_count),
      keep_original_count: toInt(raw.keep_original_count ?? base.keep_original_count),
      source_vram_bytes_est: toInt(raw.source_vram_bytes_est ?? base.source_vram_bytes_est),
      output_vram_bytes_est: toInt(raw.output_vram_bytes_est ?? base.output_vram_bytes_est),
      vram_saving_bytes_est: toInt(
        raw.vram_saving_bytes_est
        ?? (toInt(raw.source_vram_bytes_est ?? 0) - toInt(raw.output_vram_bytes_est ?? 0))
      ),
      combined_total_bytes: toInt(raw.combined_total_bytes ?? (sourceTotalBytes + outputTotalBytes)),
      source_bytes_share_pct: Number(raw.source_bytes_share_pct ?? base.source_bytes_share_pct) || 0,
      output_bytes_share_pct: Number(raw.output_bytes_share_pct ?? base.output_bytes_share_pct) || 0,
      combined_bytes_share_pct: Number(raw.combined_bytes_share_pct ?? base.combined_bytes_share_pct) || 0,
      scale_breakdown: Array.isArray(raw.scale_breakdown) ? raw.scale_breakdown : [],
      projection_basis: Array.isArray(raw.projection_basis) ? raw.projection_basis : [],
      engine_unsupported_preview: Array.isArray(raw.engine_unsupported_preview) ? raw.engine_unsupported_preview : [],
    }

    if (includeModCount) {
      normalized.mod_count = toInt(raw.mod_count ?? base.mod_count)
    } else {
      delete normalized.mod_count
    }
    return normalized
  }

  const normalizeTextureRows = (rows = []) => (
    Array.isArray(rows) ? rows.map(item => normalizeTextureStat(item)) : []
  )

  // === 状态 State ===
  const isAnalyzing = ref(false)
  const isOptimizing = ref(false)
  const currentTaskId = ref('')
  const currentAnalysisTaskId = ref('')
  const currentOptimizationTaskId = ref('')
  const lastFinishedProgress = ref(null)
  const lastTargetPackageIds = ref([])
  const lastOptimizationAction = ref('')
  
  // 核心数据源
  const modsData = ref([])        // 分析后返回的所有 Mod 数据
  const globalSummary = ref(normalizeTextureStat({}, { includeModCount: true }))

  const buildProgressState = (task) => {
    if (!task) {
      return {
        percent: 0,
        message: '就绪',
        details: {
          local_started_at: 0,
          local_finished_at: 0,
          local_total_elapsed_ms: 0,
          local_status: '',
        }
      }
    }
    const startedAt = Number(task.metrics?.task_created_at || task.joinedAt || 0)
    const finishedAt = ['success', 'failed', 'cancelled'].includes(task.status) ? Number(task.updatedAt || 0) : 0
    const totalElapsedMs = finishedAt
      ? Number(task.metrics?.elapsed_ms || Math.max(0, finishedAt - startedAt))
      : Math.max(0, Date.now() - startedAt)
    return {
      percent: Number(task.progress || 0),
      message: task.message || '处理中...',
      details: {
        ...(task.metrics || {}),
        local_started_at: startedAt,
        local_finished_at: finishedAt,
        local_total_elapsed_ms: totalElapsedMs,
        local_status: task.status,
      }
    }
  }

  const currentTask = computed(() => {
    const taskId = currentOptimizationTaskId.value || currentAnalysisTaskId.value || currentTaskId.value
    return (
      (taskId ? taskStore.getTask(taskId) : null)
      || taskStore.getLatestTaskByType(['texture-opt', 'texture-opt-analyze'])
      || null
    )
  })

  const progressState = computed(() => {
    const task = currentTask.value
    return task ? buildProgressState(task) : (lastFinishedProgress.value || buildProgressState(null))
  })

  // 视图控制
  const viewMode = ref('ALL') // 'ALL' | 'PNG' | 'DDS'
  
  // 工具就绪状态
  const toolStatus = ref({
    available: false,
    resolved_path: '',
    message: ''
  })

  // === 动作 Actions ===
  const bindTaskId = (payload, kind) => {
    const taskId = payload?.task_id || payload?.id || ''
    currentTaskId.value = taskId
    lastFinishedProgress.value = null
    if (kind === 'analyze') {
      currentAnalysisTaskId.value = taskId
    } else if (kind === 'optimize') {
      currentOptimizationTaskId.value = taskId
    }
    return taskId
  }

  const applyReturnedTaskState = (payload) => {
    if (!payload) return
    const task = taskStore.upsertTask({
      id: payload.task_id || payload.id,
      type: payload.type || (payload.action === 'analyze' ? 'texture-opt-analyze' : 'texture-opt'),
      status: payload.status || 'pending',
      progress: payload.progress || 0,
      message: payload.message || '',
      metrics: payload.metrics || {},
      timestamp: payload.updated_at || Date.now(),
    })
    if (task && ['success', 'failed', 'cancelled'].includes(task.status)) {
      lastFinishedProgress.value = buildProgressState(task)
    }
  }

  const markTaskCancelling = () => {
    const task = currentTask.value
    if (!task) return
    taskStore.upsertTask({
      ...task,
      status: 'running',
      message: '正在尝试中止任务...',
      metrics: {
        ...(task.metrics || {}),
        phase: 'cancelling',
      },
      timestamp: Date.now(),
    })
  }

  const applySnapshotPayload = (payload = {}) => {
    const summary = payload?.summary
    const finalMods = payload?.final_mods
    const mods = payload?.mods

    if (summary && typeof summary === 'object') {
      globalSummary.value = normalizeTextureStat(summary, { includeModCount: true })
    }
    if (Array.isArray(finalMods)) {
      modsData.value = normalizeTextureRows(finalMods)
      return
    }
    if (Array.isArray(mods)) {
      modsData.value = normalizeTextureRows(mods)
    }
  }

  const upsertCurrentEntry = (entry) => {
    if (!entry) return
    const currentEntry = normalizeTextureStat(entry)
    const existingIdx = modsData.value.findIndex(item => item.mod_path === currentEntry.mod_path)
    if (existingIdx !== -1) {
      modsData.value[existingIdx] = currentEntry
    } else {
      modsData.value.push(currentEntry)
    }
  }

  const bindIncomingTaskIfNeeded = (payload) => {
    const { id, type } = payload || {}
    if (!id) return false
    if (id === currentAnalysisTaskId.value || id === currentOptimizationTaskId.value || id === currentTaskId.value) {
      return true
    }

    if (type === 'texture-opt-analyze' && isAnalyzing.value && !currentAnalysisTaskId.value) {
      currentAnalysisTaskId.value = id
      currentTaskId.value = id
      return true
    }

    if (type === 'texture-opt' && isOptimizing.value && !currentOptimizationTaskId.value) {
      currentOptimizationTaskId.value = id
      currentTaskId.value = id
      return true
    }

    return false
  }

  const isToddsDownloadPayload = (payload = {}) => {
    const filename = String(payload.metrics?.filename || '').toLowerCase()
    const filePath = String(payload.metrics?.file_path || '').toLowerCase()
    return filename.startsWith('todds_') || filePath.includes('todds')
  }

  const scheduleToolStatusRefresh = (attempt = 0) => {
    if (toolStatusRefreshTimer) {
      clearTimeout(toolStatusRefreshTimer)
      toolStatusRefreshTimer = null
    }
    toolStatusRefreshTimer = window.setTimeout(async () => {
      await checkToolStatus()
      if (!toolStatus.value.available && attempt < 5) {
        scheduleToolStatusRefresh(attempt + 1)
      }
    }, attempt === 0 ? 900 : 1200)
  }

  // 1. 检查后端工具状态
  const checkToolStatus = async () => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.texture_get_env_status(appStore.settings.texture_opt)
      if (checkResult(res, "检查贴图工具", false)) {
        toolStatus.value = res.data
      }
    } catch (e) {
      console.error(e)
    }
  }

  // 2. 触发自动下载工具
  const downloadTool = async () => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      const res = await window.pywebview.api.texture_prepare_download(appStore.settings.texture_opt)
      if (res.status === 'success') {
        if (!res.data.already_ready) {
          toast.info("已启动 todds 下载任务，请留意底部状态栏。")
          scheduleToolStatusRefresh(0)
        } else {
          toast.success("todds 已就绪，无需下载")
          await checkToolStatus()
        }
      } else {
        toast.error(res.message)
      }
    } finally {
      appStore.isLoading = false
    }
  }

  // 3. 启动分析 (扫描)
  const startAnalysis = async (packageIds) => {
    if (!window.pywebview || packageIds.length === 0) return
    isAnalyzing.value = true
    lastTargetPackageIds.value = [...packageIds]
    currentOptimizationTaskId.value = ''
    modsData.value = []
    try {
      const res = await window.pywebview.api.texture_analyze_mods(packageIds, appStore.settings.texture_opt)
      if (checkResult(res, "启动贴图分析", false)) {
        bindTaskId(res.data, 'analyze')
        applyReturnedTaskState(res.data)
        applySnapshotPayload(res.data)
      } else {
        isAnalyzing.value = false
      }
    } catch (e) {
      isAnalyzing.value = false
    }
  }

  // 4. 启动优化/清理
  const startOptimization = async (packageIds, action = 'optimize') => {
    if (!window.pywebview || packageIds.length === 0) return
    isOptimizing.value = true
    lastTargetPackageIds.value = [...packageIds]
    lastOptimizationAction.value = action
    currentAnalysisTaskId.value = ''
    try {
      const res = await window.pywebview.api.texture_start_task(packageIds, action, appStore.settings.texture_opt)
      if (checkResult(res, "启动优化任务", false)) {
        bindTaskId(res.data, 'optimize')
        applyReturnedTaskState(res.data)
        applySnapshotPayload(res.data)
      } else {
        isOptimizing.value = false
      }
    } catch (e) {
      isOptimizing.value = false
    }
  }

  const cancelCurrentTask = async () => {
    if (!window.pywebview) return
    const task = currentTask.value
    if (!task) return
    try {
      const ok = await appStore.cancelTaskByProgress(task)
      if (ok) {
        markTaskCancelling()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleDownloadEvent = (payload) => {
    if (!payload || payload.status !== 'success') return
    if (!isToddsDownloadPayload(payload)) return
    scheduleToolStatusRefresh(0)
  }

  // 5. 接收 EventBus 推流 (此函数将在 App.vue 初始化时挂载)
  const handleProgressEvent = (payload) => {
    const { id, type, status, progress, message, metrics } = payload
    const isKnownTask = bindIncomingTaskIfNeeded(payload)
    
    // 如果不是当前任务，忽略
    if (!isKnownTask) return

    const hasSnapshotPayload =
      (metrics.summary && typeof metrics.summary === 'object')
      || Array.isArray(metrics.final_mods)
      || Array.isArray(metrics.mods)
    if (hasSnapshotPayload) {
      applySnapshotPayload(metrics)
    }

    if (metrics.current_entry) {
      upsertCurrentEntry(metrics.current_entry)
    }
    if (Array.isArray(metrics.final_mods)) {
      modsData.value = normalizeTextureRows(metrics.final_mods)
    }

    // 处理分析进度
    if (type === 'texture-opt-analyze') {
      if (status === 'success' || status === 'failed' || status === 'cancelled') {
        lastFinishedProgress.value = buildProgressState(currentTask.value || taskStore.getTask(id))
        isAnalyzing.value = false
        currentAnalysisTaskId.value = ''
        if (!currentOptimizationTaskId.value) {
          currentTaskId.value = ''
        }
      }
    }

    // 处理优化进度
    if (type === 'texture-opt') {
      if (status === 'success' || status === 'failed' || status === 'cancelled') {
        lastFinishedProgress.value = buildProgressState(currentTask.value || taskStore.getTask(id))
        isOptimizing.value = false
        currentOptimizationTaskId.value = ''
        if (!currentAnalysisTaskId.value) {
          currentTaskId.value = ''
        }
        const shouldRefreshAnalyze =
          status === 'success'
          && metrics.refresh_after_analyze === true
          && !isAnalyzing.value
          && lastOptimizationAction.value !== 'optimize'
          && lastTargetPackageIds.value.length > 0
        if (shouldRefreshAnalyze) {
          startAnalysis([...lastTargetPackageIds.value])
        }
      }
    }
  }

  return {
    isAnalyzing, isOptimizing, currentTaskId, currentAnalysisTaskId, currentOptimizationTaskId,
    modsData, globalSummary, progressState, viewMode, toolStatus,
    checkToolStatus, downloadTool, startAnalysis, startOptimization, cancelCurrentTask, handleProgressEvent, handleDownloadEvent
  }
})
