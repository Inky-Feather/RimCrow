// src/stores/textureStore.js
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useAppStore } from '../../app/stores/appStore'
import { toast, checkResult } from '../../shared/lib/common'
import { useTaskStore } from '../../app/stores/taskStore'

export const useTextureStore = defineStore('texture', () => {
  const appStore = useAppStore()
  const taskStore = useTaskStore()
  let toolStatusRefreshTimer = null

  const createEmptyTextureStat = () => ({
    mod_path: '',
    mod_name: '',
    package_id: '',
    store: '',
    path_hash: '',
    mod_instance_key: '',
    source_total_count: 0,
    source_total_bytes: 0,
    output_total_count: 0,
    output_total_bytes: 0,
    current_output_count: 0,
    current_output_bytes: 0,
    external_orphan_output_count: 0,
    external_orphan_output_bytes: 0,
    generate_required_count: 0,
    excluded_count: 0,
    skip_small_count: 0,
    skipped_mask_count: 0,
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
      package_id: String(raw.package_id || base.package_id),
      store: String(raw.store || base.store),
      path_hash: String(raw.path_hash || base.path_hash),
      mod_instance_key: String(raw.mod_instance_key || raw.path_hash || raw.mod_path || base.mod_instance_key),
      source_total_count: sourceTotalCount,
      source_total_bytes: sourceTotalBytes,
      output_total_count: outputTotalCount,
      output_total_bytes: outputTotalBytes,
      current_output_count: currentOutputCount,
      current_output_bytes: currentOutputBytes,
      external_orphan_output_count: toInt(raw.external_orphan_output_count ?? base.external_orphan_output_count),
      external_orphan_output_bytes: toInt(raw.external_orphan_output_bytes ?? base.external_orphan_output_bytes),
      generate_required_count: toInt(raw.generate_required_count ?? raw.pending_count ?? base.generate_required_count),
      excluded_count: toInt(raw.excluded_count ?? base.excluded_count),
      skip_small_count: toInt(raw.skip_small_count ?? raw.skipped_small_count ?? base.skip_small_count),
      skipped_mask_count: toInt(raw.skipped_mask_count ?? base.skipped_mask_count),
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

  const sumScaleBreakdown = (rows = []) => {
    const counts = new Map()
    rows.forEach(row => {
      ;(Array.isArray(row.scale_breakdown) ? row.scale_breakdown : []).forEach(item => {
        if (!item || typeof item !== 'object') return
        const kind = String(item.kind || 'keep_original')
        const label = String(item.label || '原尺寸')
        const key = `${kind}\n${label}`
        counts.set(key, {
          kind,
          label,
          count: (counts.get(key)?.count || 0) + toInt(item.count),
        })
      })
    })
    const order = { scaled: 0, fallback: 1, keep_original: 2 }
    return Array.from(counts.values())
      .filter(item => item.count > 0)
      .sort((a, b) => (
        (order[a.kind] ?? 99) - (order[b.kind] ?? 99)
        || b.count - a.count
        || a.label.localeCompare(b.label)
      ))
  }

  const rebuildSummaryFromRows = (rows = []) => {
    const summary = createEmptyTextureStat()
    summary.mod_count = rows.length
    const numericKeys = Object.keys(summary).filter(key => (
      typeof summary[key] === 'number'
      && !['mod_count', 'source_bytes_share_pct', 'output_bytes_share_pct', 'combined_bytes_share_pct'].includes(key)
    ))
    rows.forEach(row => {
      numericKeys.forEach(key => {
        summary[key] += toInt(row[key])
      })
    })
    summary.scale_breakdown = sumScaleBreakdown(rows)
    summary.combined_total_bytes = summary.source_total_bytes + summary.output_total_bytes
    summary.vram_saving_bytes_est = summary.source_vram_bytes_est - summary.output_vram_bytes_est
    summary.engine_unsupported_preview = rows
      .flatMap(row => Array.isArray(row.engine_unsupported_preview) ? row.engine_unsupported_preview : [])
      .slice(0, 12)
    return normalizeTextureStat(summary, { includeModCount: true })
  }

  const normalizeFailedItem = (raw = {}) => ({
    package_id: String(raw.package_id || ''),
    mod_path: String(raw.mod_path || ''),
    mod_name: String(raw.mod_name || ''),
    rel_path: String(raw.rel_path || ''),
    error: String(raw.error || ''),
    todds_log_path: String(raw.todds_log_path || ''),
  })

  const normalizeResultHistoryItem = (raw = {}) => ({
    ...raw,
    task_id: String(raw.task_id || ''),
    action: String(raw.action || ''),
    result_path: String(raw.result_path || ''),
    summary: normalizeTextureStat(raw.summary || {}, { includeModCount: true }),
    mods: normalizeTextureRows(raw.mods || []),
    failed_items: Array.isArray(raw.failed_items) ? raw.failed_items.map(normalizeFailedItem) : [],
    mod_paths: Array.isArray(raw.mod_paths) ? raw.mod_paths.map(item => String(item || '')) : [],
    mod_targets: Array.isArray(raw.mod_targets) ? raw.mod_targets.map(item => normalizeTextureStat(item || {})) : [],
    todds_log_path: String(raw.todds_log_path || ''),
    created_at: Number(raw.created_at || 0),
    updated_at: Number(raw.updated_at || 0),
  })

  const getRowKey = (item = {}) => (
    String(item.mod_instance_key || item.path_hash || item.mod_path || '')
  )

  // === 状态 State ===
  const isAnalyzing = ref(false)
  const isOptimizing = ref(false)
  const currentTaskId = ref('')
  const currentAnalysisTaskId = ref('')
  const currentOptimizationTaskId = ref('')
  const lastFinishedProgress = ref(null)
  const lastTargetPackageIds = ref([])
  const lastTargetScope = ref('active')
  const lastOptimizationAction = ref('')

  // 核心数据源
  const modsData = ref([])        // 分析后返回的所有 Mod 数据
  const globalSummary = ref(normalizeTextureStat({}, { includeModCount: true }))
  const resultHistory = ref([])
  const textureExclusions = ref({ schema_version: 1, mods: [], files: [] })
  const isResultDrawerOpen = ref(false)
  const selectedResultPath = ref('')

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
    const currentKey = getRowKey(currentEntry)
    const existingIdx = modsData.value.findIndex(item => getRowKey(item) === currentKey)
    if (existingIdx !== -1) {
      modsData.value[existingIdx] = currentEntry
    } else {
      modsData.value.push(currentEntry)
    }
  }

  const cleanedGenerateRequiredCount = (row) => {
    const mode = String(appStore.settings?.texture_opt?.process_mode || 'scaled_only_overwrite')
    const scaled = toInt(row.scaled_count) + toInt(row.fallback_scaled_count)
    const original = toInt(row.keep_original_count)
    if (mode === 'scaled_only_overwrite') return scaled
    return scaled + original
  }

  const clearGeneratedOutputsFromCurrentRows = () => {
    const targetIds = new Set(lastTargetPackageIds.value.map(item => String(item || '').trim().toLowerCase()).filter(Boolean))
    const shouldUpdateAll = lastTargetScope.value === 'all' || targetIds.size === 0
    let changed = false
    const nextRows = modsData.value.map(row => {
      const packageId = String(row.package_id || '').trim().toLowerCase()
      if (!shouldUpdateAll && !targetIds.has(packageId)) return row
      changed = true
      const next = {
        ...row,
        output_total_count: 0,
        output_total_bytes: 0,
        current_output_count: 0,
        current_output_bytes: 0,
        external_orphan_output_count: 0,
        external_orphan_output_bytes: 0,
        output_vram_bytes_est: 0,
      }
      next.generate_required_count = cleanedGenerateRequiredCount(next)
      next.action_required_count = next.generate_required_count
      next.combined_total_bytes = toInt(next.source_total_bytes)
      next.vram_saving_bytes_est = toInt(next.source_vram_bytes_est)
      next.output_bytes_share_pct = 0
      return normalizeTextureStat(next)
    })
    if (!changed) return
    modsData.value = nextRows
    globalSummary.value = rebuildSummaryFromRows(nextRows)
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
  const startAnalysis = async (packageIds, targetScope = 'active') => {
    if (!window.pywebview || (targetScope !== 'all' && packageIds.length === 0)) return
    isAnalyzing.value = true
    lastTargetPackageIds.value = [...packageIds]
    lastTargetScope.value = targetScope
    currentOptimizationTaskId.value = ''
    modsData.value = []
    try {
      const res = await window.pywebview.api.texture_analyze_mods(packageIds, {
        ...appStore.settings.texture_opt,
        target_scope: targetScope,
      })
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
  const startOptimization = async (packageIds, action = 'optimize', targetScope = 'active', extraOptions = {}) => {
    if (!window.pywebview || (action !== 'clean_generated' && targetScope !== 'all' && packageIds.length === 0)) return
    isOptimizing.value = true
    lastTargetPackageIds.value = [...packageIds]
    lastTargetScope.value = targetScope
    lastOptimizationAction.value = action
    currentAnalysisTaskId.value = ''
    try {
      const res = await window.pywebview.api.texture_start_task(packageIds, action, {
        ...appStore.settings.texture_opt,
        ...extraOptions,
        target_scope: targetScope,
      })
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

  const applyExclusionsPayload = (payload = {}) => {
    textureExclusions.value = {
      schema_version: Number(payload.schema_version || 1),
      mods: Array.isArray(payload.mods) ? payload.mods.map(item => ({
        package_id: String(item.package_id || ''),
        updated_at: Number(item.updated_at || 0),
      })) : [],
      files: Array.isArray(payload.files) ? payload.files.map(item => ({
        mod_path: String(item.mod_path || ''),
        rel_path: String(item.rel_path || ''),
        updated_at: Number(item.updated_at || 0),
      })) : [],
    }
  }

  const loadResultHistory = async () => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.texture_get_result_history(3)
      if (!checkResult(res, "读取贴图结果历史", false)) return
      resultHistory.value = Array.isArray(res.data) ? res.data.map(normalizeResultHistoryItem) : []
      if (!selectedResultPath.value || !resultHistory.value.some(item => item.result_path === selectedResultPath.value)) {
        selectedResultPath.value = resultHistory.value[0]?.result_path || ''
      }
    } catch (e) {
      console.error(e)
    }
  }

  const loadExclusions = async () => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.texture_get_exclusions()
      if (!checkResult(res, "读取贴图排除规则", false)) return
      applyExclusionsPayload(res.data)
    } catch (e) {
      console.error(e)
    }
  }

  const isModExcluded = (packageId) => {
    const normalized = String(packageId || '').trim().toLowerCase()
    return !!normalized && textureExclusions.value.mods.some(item => String(item.package_id || '').trim().toLowerCase() === normalized)
  }

  const isFileExcluded = (modPath, relPath) => {
    const normalizedModPath = String(modPath || '').trim().toLowerCase()
    const normalizedRelPath = String(relPath || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').toLowerCase()
    return !!normalizedModPath && !!normalizedRelPath && textureExclusions.value.files.some(item => (
      String(item.mod_path || '').trim().toLowerCase() === normalizedModPath
      && String(item.rel_path || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').toLowerCase() === normalizedRelPath
    ))
  }

  const toggleModExclusion = async (packageId, exclude) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.texture_toggle_mod_exclusion(packageId, !!exclude)
    if (!checkResult(res, exclude ? "添加模组排除" : "移除模组排除", false)) return false
    applyExclusionsPayload(res.data)
    return true
  }

  const toggleFileExclusion = async (modPath, relPath, exclude) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.texture_toggle_file_exclusion(modPath, relPath, !!exclude)
    if (!checkResult(res, exclude ? "添加文件排除" : "移除文件排除", false)) return false
    applyExclusionsPayload(res.data)
    return true
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
        if (status === 'success' && metrics.task_action === 'clean_generated') {
          clearGeneratedOutputsFromCurrentRows()
        }
        lastFinishedProgress.value = buildProgressState(currentTask.value || taskStore.getTask(id))
        isOptimizing.value = false
        selectedResultPath.value = String(metrics.result_path || selectedResultPath.value || '')
        loadResultHistory()
        currentOptimizationTaskId.value = ''
        if (!currentAnalysisTaskId.value) {
          currentTaskId.value = ''
        }
        const shouldRefreshAnalyze =
          status === 'success'
          && metrics.refresh_after_analyze === true
          && !isAnalyzing.value
          && lastOptimizationAction.value !== 'optimize'
          && (lastTargetScope.value === 'all' || lastTargetPackageIds.value.length > 0)
        if (shouldRefreshAnalyze) {
          startAnalysis([...lastTargetPackageIds.value], lastTargetScope.value)
        }
      }
    }
  }

  return {
    // 任务状态
    isAnalyzing, isOptimizing, currentTaskId, currentAnalysisTaskId, currentOptimizationTaskId,
    // 数据与视图状态
    modsData, globalSummary, progressState, viewMode, toolStatus,
    resultHistory, textureExclusions, isResultDrawerOpen, selectedResultPath,
    // 任务动作
    checkToolStatus, downloadTool, startAnalysis, startOptimization, cancelCurrentTask, handleProgressEvent, handleDownloadEvent,
    // 结果与排除项
    loadResultHistory, loadExclusions, isModExcluded, isFileExcluded, toggleModExclusion, toggleFileExclusion, getRowKey,
  }
})
