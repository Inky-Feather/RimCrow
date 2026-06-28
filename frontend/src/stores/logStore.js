import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { checkResult, normalizeText } from '../utils/common'
import { useAiStore } from './aiStore'

// -----------------------------------------------------------------
// 日志分析选择态 Store
// -----------------------------------------------------------------
// 这里不保存“日志内容本身”，只保存：
// 1. 当前来源(game/app)下的选中文件与错误项
// 2. 这些选择映射出的 AI 附件草稿
// 3. 与当前选择绑定的 token 预估与请求时序

const createEmptyTokenInfo = () => ({
  isLoading: false,
  estimated: 0,
  limit: 32000,
  isOverLimit: false,
  condensedData: null,
})

const createEmptySourceState = () => ({
  /** 创建单个日志来源(game/app)的默认选择态。 */
  selectedFile: '',
  selectedIds: [],
  selectedLogSnapshotsById: {},
  tokenInfo: createEmptyTokenInfo(),
  selectionRequestSeq: 0,
  attachmentKey: '',
})

const LOG_SOURCE_LABELS = {
  game: '游戏日志',
  app: '系统日志',
}

const cloneLogSnapshot = (log = {}) => ({
  /**
   * 对日志项做可持久化快照复制。
   *
   * 选择态需要跨列表刷新保留，不能继续持有原始响应对象引用；
   * 否则日志面板一刷新，选中的日志快照就会和最新数据互相污染。
   */
  ...log,
  raw_lines: Array.isArray(log?.raw_lines) ? [...log.raw_lines] : [],
  context: log?.context && typeof log.context === 'object'
    ? {
      ...log.context,
      relatedFiles: Array.isArray(log.context.relatedFiles) ? [...log.context.relatedFiles] : [],
      relatedModIds: Array.isArray(log.context.relatedModIds) ? [...log.context.relatedModIds] : [],
    }
    : undefined,
})

const buildSelectedIds = (selectedIds = [], selectedLogs = []) => {
  /**
   * 统一生成当前选择集合的 ID 列表。
   *
   * 组件层有时只传 id，有时直接传日志对象；这里集中兼容两种入口，
   * 避免调用方自己拼去重逻辑。
   */
  const fallbackIds = Array.isArray(selectedLogs)
    ? selectedLogs.map(log => normalizeText(log?.id)).filter(Boolean)
    : []
  const sourceIds = Array.isArray(selectedIds) && selectedIds.length > 0
    ? selectedIds.map(id => normalizeText(id)).filter(Boolean)
    : fallbackIds
  return [...new Set(sourceIds)]
}

export const useLogStore = defineStore('log', () => {
  const aiStore = useAiStore()
  let listenersInitialized = false

  // -----------------------------------------------------------------
  // 状态定义 (State / Refs)
  // -----------------------------------------------------------------
  const showSidebar = ref(false)
  const sourceStates = reactive({
    game: createEmptySourceState(),
    app: createEmptySourceState(),
  })

  // -----------------------------------------------------------------
  // 读取接口 (Getters / Computed)
  // -----------------------------------------------------------------
  const getSourceState = (sourceType = 'game') => {
    /** 读取指定来源的选择态；未知来源统一回退到 game。 */
    const normalizedSourceType = normalizeText(sourceType, 'game')
    return sourceStates[normalizedSourceType] || sourceStates.game
  }

  const getSourceLabel = (sourceType = 'game') => (
    LOG_SOURCE_LABELS[normalizeText(sourceType, 'game')] || '日志'
  )

  const getSelectedLogs = (sourceType = 'game') => {
    /** 按选中顺序返回当前来源下的日志快照列表。 */
    const state = getSourceState(sourceType)
    return state.selectedIds
      .map(id => state.selectedLogSnapshotsById[id])
      .filter(Boolean)
  }

  const selectedLogsBySource = computed(() => ({
    game: getSelectedLogs('game'),
    app: getSelectedLogs('app'),
  }))

  const tokenInfoBySource = computed(() => ({
    game: getSourceState('game').tokenInfo,
    app: getSourceState('app').tokenInfo,
  }))

  // -----------------------------------------------------------------
  // 附件同步 (Attachment Sync)
  // -----------------------------------------------------------------
  const setSelectedFile = (sourceType = 'game', filename = '') => {
    /** 更新当前来源的活动日志文件名。 */
    const state = getSourceState(sourceType)
    state.selectedFile = normalizeText(filename)
    return state.selectedFile
  }

  const removeSelectionAttachment = (sourceType = 'game') => {
    /** 从全局附件池移除当前来源绑定的日志附件。 */
    const state = getSourceState(sourceType)
    const attachmentKey = normalizeText(state.attachmentKey)
    if (attachmentKey) {
      aiStore.removeGlobalAttachmentDraft(attachmentKey)
      state.attachmentKey = ''
    }
  }

  const syncSelectionAttachment = (sourceType = 'game') => {
    // 这里把当前 UI 框选状态收口成全局附件草稿，
    // 这样 AI 侧边栏不需要理解日志面板内部结构，只消费统一附件协议。
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const state = getSourceState(normalizedSourceType)
    const selectedLogs = getSelectedLogs(normalizedSourceType)
    const normalizedFilename = normalizeText(state.selectedFile)

    if (!normalizedFilename || selectedLogs.length === 0) {
      removeSelectionAttachment(normalizedSourceType)
      return ''
    }

    const isGlobalSummary = selectedLogs.some(log => log?.id === 'global_mock')
    const selectedLineNumbers = [...new Set(
      selectedLogs.flatMap((log) => {
        const rawLines = Array.isArray(log?.raw_lines) ? log.raw_lines : []
        if (rawLines.length > 0) {
          return rawLines.map(line => Number(line)).filter(line => Number.isFinite(line) && line > 0)
        }
        const fallbackLine = Number(log?.line || log?.line_number || log?.raw_line || 0)
        return Number.isFinite(fallbackLine) && fallbackLine > 0 ? [fallbackLine] : []
      })
    )]

    const draft = aiStore.buildDiagnosisContextAttachment({
      sourceType: normalizedSourceType,
      filename: normalizedFilename,
      selectedLineNumbers,
      isGlobalSummary,
      selectedLogCount: selectedLogs.length,
      sourceLabel: getSourceLabel(normalizedSourceType),
      tokenInfo: state.tokenInfo,
    })

    state.attachmentKey = aiStore.upsertGlobalAttachmentDraft(draft, {
      binding: {
        type: 'log_selection',
        source_type: normalizedSourceType,
        filename: normalizedFilename,
      },
    })
    return state.attachmentKey
  }

  // -----------------------------------------------------------------
  // 选择态更新 (Selection State)
  // -----------------------------------------------------------------
  const setTokenInfo = (sourceType = 'game', tokenInfo = null, { syncAttachment = true } = {}) => {
    /**
     * 更新当前来源的 token 估算结果。
     *
     * 因为附件标签会显示 token 摘要，所以默认会同步刷新附件快照。
     */
    const state = getSourceState(sourceType)
    state.tokenInfo = tokenInfo
      ? { ...createEmptyTokenInfo(), ...(tokenInfo || {}) }
      : createEmptyTokenInfo()
    if (syncAttachment) {
      syncSelectionAttachment(sourceType)
    }
    return state.tokenInfo
  }

  const clearSelection = (sourceType = 'game', {
    preserveFile = true,
    removeAttachment = true,
    resetTokenInfo = true,
  } = {}) => {
    /**
     * 清空当前来源的日志选择态。
     *
     * 不同调用方对“是否保留当前文件、是否移除附件、是否清零 token”
     * 的要求不同，因此这里用参数化方式统一处理。
     */
    const state = getSourceState(sourceType)
    state.selectedIds = []
    state.selectedLogSnapshotsById = {}
    if (!preserveFile) {
      state.selectedFile = ''
    }
    if (resetTokenInfo) {
      state.tokenInfo = createEmptyTokenInfo()
    }
    if (removeAttachment) {
      removeSelectionAttachment(sourceType)
    }
  }

  const replaceSelection = ({
    sourceType = 'game',
    filename = '',
    selectedIds = [],
    selectedLogs = [],
    syncAttachment = true,
    resetTokenInfoWhenEmpty = true,
  } = {}) => {
    // 替换时优先复用已有 snapshot，原因是列表刷新后 log 对象引用会变化，
    // 但用户不应该因为数据重载就丢失选择态。
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const state = getSourceState(normalizedSourceType)
    if (filename !== undefined) {
      state.selectedFile = normalizeText(filename)
    }

    const nextSelectedIds = buildSelectedIds(selectedIds, selectedLogs)
    const nextSnapshots = {}

    nextSelectedIds.forEach((id) => {
      if (state.selectedLogSnapshotsById[id]) {
        nextSnapshots[id] = state.selectedLogSnapshotsById[id]
      }
    })

    ;(Array.isArray(selectedLogs) ? selectedLogs : []).forEach((log) => {
      const id = normalizeText(log?.id)
      if (!id || !nextSelectedIds.includes(id)) return
      nextSnapshots[id] = cloneLogSnapshot(log)
    })

    state.selectedIds = nextSelectedIds
    state.selectedLogSnapshotsById = nextSnapshots

    if (nextSelectedIds.length === 0) {
      if (resetTokenInfoWhenEmpty) {
        state.tokenInfo = createEmptyTokenInfo()
      }
      removeSelectionAttachment(normalizedSourceType)
      return []
    }

    if (syncAttachment) {
      syncSelectionAttachment(normalizedSourceType)
    }
    return getSelectedLogs(normalizedSourceType)
  }

  const refreshSelectedSnapshotsFromLoadedLogs = (sourceType = 'game', loadedLogs = []) => {
    /**
     * 用最新加载到的日志对象刷新已选中快照。
     *
     * 这样当日志面板重新拉取数据后，已选项的上下文细节也能同步更新，
     * 但不会打断用户当前的选择顺序。
     */
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const state = getSourceState(normalizedSourceType)
    if (!Array.isArray(loadedLogs) || loadedLogs.length === 0 || state.selectedIds.length === 0) {
      return getSelectedLogs(normalizedSourceType)
    }
    const nextSnapshots = { ...state.selectedLogSnapshotsById }
    let changed = false
    loadedLogs.forEach((log) => {
      const id = normalizeText(log?.id)
      if (!id || !state.selectedIds.includes(id)) return
      nextSnapshots[id] = cloneLogSnapshot(log)
      changed = true
    })
    if (changed) {
      state.selectedLogSnapshotsById = nextSnapshots
    }
    return getSelectedLogs(normalizedSourceType)
  }

  const beginSelectionRequest = (sourceType = 'game') => {
    /** 为当前来源开启一轮新的异步选择请求，并返回递增序号。 */
    const state = getSourceState(sourceType)
    state.selectionRequestSeq = Number(state.selectionRequestSeq || 0) + 1
    return state.selectionRequestSeq
  }

  const isCurrentSelectionRequest = (sourceType = 'game', requestSeq = 0) => (
    /** 判断某个异步响应是否仍对应当前最新选择。 */
    Number(getSourceState(sourceType).selectionRequestSeq || 0) === Number(requestSeq || 0)
  )

  const estimateSelectionTokenInfo = async ({
    sourceType = 'game',
    filename = '',
    logs = null,
    requestSeq = 0,
  } = {}) => {
    // token 估算是异步的，必须用 requestSeq 丢弃过时结果，
    // 否则快速切换文件或重选日志时会把旧响应写回当前面板。
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const normalizedFilename = normalizeText(filename, getSourceState(normalizedSourceType).selectedFile)
    const selectedLogs = Array.isArray(logs) ? logs : getSelectedLogs(normalizedSourceType)
    const allRawLines = [...new Set(
      selectedLogs.flatMap(log => Array.isArray(log?.raw_lines) ? log.raw_lines : [])
    )]

    if (!normalizedFilename || selectedLogs.length === 0 || allRawLines.length === 0 || !window.pywebview) {
      setTokenInfo(normalizedSourceType, createEmptyTokenInfo(), { syncAttachment: true })
      return createEmptyTokenInfo()
    }

    setTokenInfo(normalizedSourceType, {
      ...createEmptyTokenInfo(),
      isLoading: true,
    }, { syncAttachment: true })

    try {
      const res = await window.pywebview.api.ai_prepare_diagnosis({
        raw_lines: allRawLines,
        filename: normalizedFilename,
        log_source_type: normalizedSourceType,
      })
      if (requestSeq && !isCurrentSelectionRequest(normalizedSourceType, requestSeq)) {
        return null
      }
      if (!checkResult(res, 'Token检测')) {
        const emptyInfo = createEmptyTokenInfo()
        setTokenInfo(normalizedSourceType, emptyInfo, { syncAttachment: true })
        return emptyInfo
      }

      const nextTokenInfo = {
        isLoading: false,
        estimated: Number(res.data?.estimated_tokens || 0),
        limit: Number(res.data?.token_limit || 32000),
        isOverLimit: Boolean(res.data?.is_over_limit),
        condensedData: res.data?.condensed_data || null,
      }
      setTokenInfo(normalizedSourceType, nextTokenInfo, { syncAttachment: true })
      return nextTokenInfo
    } catch (error) {
      console.error('Token 计算失败:', error)
      if (requestSeq && !isCurrentSelectionRequest(normalizedSourceType, requestSeq)) {
        return null
      }
      const emptyInfo = createEmptyTokenInfo()
      setTokenInfo(normalizedSourceType, emptyInfo, { syncAttachment: true })
      throw error
    }
  }

  const scanGlobalErrorsSelection = async ({
    sourceType = 'game',
    filename = '',
    requestSeq = 0,
  } = {}) => {
    // 全局扫描会生成“压缩后的伪选择项”，本质上仍落回同一套 diagnosis_context 附件协议。
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const normalizedFilename = normalizeText(filename, getSourceState(normalizedSourceType).selectedFile)
    if (!normalizedFilename || !window.pywebview) {
      clearSelection(normalizedSourceType)
      return null
    }

    const placeholderLogs = [{ id: 'global_mock', raw_lines: [] }]
    replaceSelection({
      sourceType: normalizedSourceType,
      filename: normalizedFilename,
      selectedLogs: placeholderLogs,
      syncAttachment: true,
      resetTokenInfoWhenEmpty: false,
    })
    setTokenInfo(normalizedSourceType, {
      ...createEmptyTokenInfo(),
      isLoading: true,
    }, { syncAttachment: true })

    try {
      const res = await window.pywebview.api.ai_scan_global_errors({
        filename: normalizedFilename,
        log_source_type: normalizedSourceType,
      })
      if (requestSeq && !isCurrentSelectionRequest(normalizedSourceType, requestSeq)) {
        return null
      }
      if (!checkResult(res, '全局扫描')) {
        clearSelection(normalizedSourceType)
        return null
      }

      const diagnosisContext = res.data?.condensed_data || null
      const stats = diagnosisContext?.stats || {}
      const repeatCount = Number(stats.total_repeat_count || 0)
      replaceSelection({
        sourceType: normalizedSourceType,
        filename: normalizedFilename,
        selectedLogs: [{ id: 'global_mock', raw_lines: [], count: repeatCount }],
        syncAttachment: false,
        resetTokenInfoWhenEmpty: false,
      })

      const nextTokenInfo = {
        isLoading: false,
        estimated: Number(res.data?.estimated_tokens || 0),
        limit: Number(res.data?.token_limit || 32000),
        isOverLimit: Boolean(res.data?.is_over_limit),
        condensedData: diagnosisContext,
      }
      setTokenInfo(normalizedSourceType, nextTokenInfo, { syncAttachment: true })

      return {
        tokenInfo: nextTokenInfo,
        notice: String(res.data?.compression_notice || ''),
        condensedData: diagnosisContext,
      }
    } catch (error) {
      if (requestSeq && !isCurrentSelectionRequest(normalizedSourceType, requestSeq)) {
        return null
      }
      clearSelection(normalizedSourceType)
      throw error
    }
  }

  const markAttachmentConsumed = (sourceType = 'game', attachmentKey = '') => {
    /** 标记当前来源附件已被消费，避免旧 key 继续挂在本地状态上。 */
    const state = getSourceState(sourceType)
    const normalizedAttachmentKey = normalizeText(attachmentKey)
    if (!normalizedAttachmentKey || normalizedAttachmentKey === normalizeText(state.attachmentKey)) {
      state.attachmentKey = ''
    }
  }

  const handleAttachmentRemoved = (event) => {
    /**
     * 响应全局附件被删除的广播事件。
     *
     * 日志面板和 AI 面板都可能删除同一条诊断附件，因此这里需要反向
     * 清理本地选择态，保持两个界面一致。
     */
    const detail = event?.detail || {}
    const binding = detail?.meta?.binding || {}
    if (binding?.type !== 'log_selection') return
    const sourceType = normalizeText(binding?.source_type)
    if (!sourceType) return
    clearSelection(sourceType, {
      preserveFile: true,
      removeAttachment: false,
      resetTokenInfo: true,
    })
    markAttachmentConsumed(sourceType, detail?.key || '')
  }

  // -----------------------------------------------------------------
  // 生命周期 (Lifecycle)
  // -----------------------------------------------------------------
  const setupEventListeners = () => {
    /** 初始化与全局附件池相关的浏览器事件监听。 */
    if (listenersInitialized || typeof window === 'undefined') return
    listenersInitialized = true
    window.addEventListener('ai-attachment-removed', handleAttachmentRemoved)
  }

  setupEventListeners()

  return {
    showSidebar,
    sourceStates,
    selectedLogsBySource,
    tokenInfoBySource,
    getSourceState,
    getSourceLabel,
    getSelectedLogs,
    setSelectedFile,
    replaceSelection,
    clearSelection,
    refreshSelectedSnapshotsFromLoadedLogs,
    setTokenInfo,
    syncSelectionAttachment,
    removeSelectionAttachment,
    beginSelectionRequest,
    isCurrentSelectionRequest,
    estimateSelectionTokenInfo,
    scanGlobalErrorsSelection,
    markAttachmentConsumed,
    setupEventListeners,
  }
})
