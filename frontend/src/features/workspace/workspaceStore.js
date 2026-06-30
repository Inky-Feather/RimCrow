// frontend/src/stores/workspaceStore.js
import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'
import { useAppStore } from '../../app/stores/appStore'
import { checkResult, toast, toUserMessage } from '../../shared/lib/common'
import { startupPerfMark, startupPerfMeasure } from '../../shared/lib/startupPerf'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { RIMWORLD_STEAM_APP_ID, SOURCE_TYPE_MAP } from '../../shared/lib/constants'
import { matchesTranslationSourceDetection } from '../../shared/lib/translationDetection'
import {
  dedupeNormalizedPackageIds, normalizeInstallSources,
  normalizePackageId, normalizeUrl, normalizeWorkshopId,
} from '../mod/lib/modIdentity'
import { hasWorkshopSearchText, resolveWorkshopDays, resolveWorkshopSort } from './workshopSearchOptions'
import { isMatrixModAvailable } from './lib/matrixItemState'

export const useWorkspaceStore = defineStore('workspace', () => {
  const appStore = useAppStore()
  const confirmStore = useConfirmStore()
  const listenersReady = ref(false)
  const workshopSearchModeTouched = ref(false)
  const loadState = reactive({
    librariesLoaded: false,
    githubLoaded: false,
    collectionsLoaded: false,
  })
  const startupWorkshopChangeState = reactive({
    detected: false,
    prompted: false,
    changes: [],
  })
  const startupInventoryDialog = reactive({
    visible: false,
    title: '',
    message: '',
    groups: [],
    targets: [],
    pendingActions: [],
    resolve: null,
  })
  const STARTUP_INVENTORY_ACK_KEY = 'rimcrow.startupInventoryPromptAck.v1'
  const LEGACY_STARTUP_INVENTORY_ACK_KEY = 'rmm.startupInventoryPromptAck.v1'

  const storeSortOrder = {
    workshop: 0,
    self: 1,
    local: 2
  }
  const sortMatrixTargets = (items = []) => {
    return [...items].sort((a, b) => {
      const storeDiff = (storeSortOrder[a.store] ?? 99) - (storeSortOrder[b.store] ?? 99)
      if (storeDiff !== 0) return storeDiff
      return String(a.name || a.package_id || '').localeCompare(String(b.name || b.package_id || ''))
    })
  }

  // 1. 已订阅的工坊 ID (仅统计创意工坊域)
  const subscribedWorkshopIds = computed(() => {
    return new Set(
      librariesMods.workshop
        .filter(m => m.steam_status?.is_subscribed && normalizeWorkshopId(m.workshop_id))
        .map(m => String(m.workshop_id))
    )
  })
  // 2. 缺失的工坊 ID (仅统计创意工坊域)
  const missingWorkshopIds = computed(() => {
    return new Set(
      librariesMods.workshop
        .filter(m => m.is_missing && normalizeWorkshopId(m.workshop_id))
        .map(m => String(m.workshop_id))
    )
  })
  // 3. 全局已安装的 ID (工坊 + 管理器 + 本地)
  // 只有存在有效路径且没有缺失/删除状态，才算已安装。
  const installedAllIds = computed(() => {
    const all = [
      ...librariesMods.workshop,
      ...librariesMods.self,
      ...librariesMods.local
    ]
    return new Set(
      all
        .filter(m => isMatrixModAvailable(m) && normalizeWorkshopId(m.workshop_id))
        .map(m => String(m.workshop_id))
    )
  })
  // 4. 提供一个快捷判断函数供 WorkshopBrowser 使用
  const getModStatus = (workshopId) => {
    const wid = normalizeWorkshopId(workshopId)
    if (!wid) {
      return {
        isSubscribed: false,
        isInstalled: false,
        isMissing: false
      }
    }
    return {
      isSubscribed: subscribedWorkshopIds.value.has(wid),
      isInstalled: installedAllIds.value.has(wid),
      isMissing: missingWorkshopIds.value.has(wid)
    }
  }

  // 1. 三个库的数据
  const librariesMods = reactive({
    local: [],
    workshop: [],
    self: [],
  })
  const librariesSize = computed(() => {
    const results ={
      workshop: 0,
      self: 0,
      local: 0,
      total: 0,
    }
    results.workshop = librariesMods.workshop.length > 0 ? librariesMods.workshop.reduce((acc, mod) => acc + (mod.file_size || 0), 0) : 0
    results.self = librariesMods.self.length > 0 ? librariesMods.self.reduce((acc, mod) => acc + (mod.file_size || 0), 0) : 0
    results.local = librariesMods.local.length > 0 ? librariesMods.local.reduce((acc, mod) => acc + (mod.file_size || 0), 0) : 0
    results.total = results.workshop + results.self + results.local
    return results
  })
  // 2. 工坊检索状态
  // 普通模式走外置缓存库和旧版详情接口；增强模式走 Steam Web API。
  // 两种模式的请求能力不同，但对前端列表和详情页要归一成同一套字段结构。
  const hasSteamWebApiKey = () => (
    !!String(appStore.settings.steam_web_api_key || '').trim()
    || !!appStore.settings?._secret_status?.['steam.web_api_key']?.has_value
  )
  // 增强模式必须同时满足“开关已开”和“Key 已填写”；任一条件缺失都回到普通模式。
  const isEnhancedWorkshopSearchEnabled = () => !!appStore.settings.enable_steam_enhanced_api && hasSteamWebApiKey()
  const canUseCollectionOnlineSearch = () => !!window.pywebview && hasSteamWebApiKey()
  const getPreferredWorkshopSearchEnhanced = () => isEnhancedWorkshopSearchEnabled()
  const getDefaultWorkshopSort = (isEnhancedMode) => (isEnhancedMode ? 'popular' : 'latest')
  const initialWorkshopEnhanced = appStore.settingsReady ? getPreferredWorkshopSearchEnhanced() : true
  const workshopSearch = reactive({
    query: '',
    page: 1,
    cursor: '*',
    nextCursor: '',
    hasMore: true, // 是否还有下一页
    hasSearched: false,
    results: [],
    total: 0,
    // 设置由后端异步注入；未就绪时先保持“优先增强”的展示意图，但不发任何请求。
    isModeReady: !!appStore.settingsReady,
    isEnhancedMode: initialWorkshopEnhanced,
    sort: getDefaultWorkshopSort(initialWorkshopEnhanced),
    advancedOpen: false,
    queryTokens: [],
    queryLogic: 'AND',
    // 增强模式参数：其它搜索条件统一由 TagSearch token 编译，避免隐藏字段影响结果。
    language: '',
    days: 7,
    searchTextTarget: 0,
    languageOptions: [{ label: '跟随界面语言', value: '', code: '', name: 'Auto' }],
    isLanguageOptionsLoaded: false,
    dlcOptions: [],
    isDlcOptionsLoaded: false,
    isLoading: false,       // 首次加载/搜索加载
    isLoadMore: false,      // 滚动到底部加载更多
    // --- 详情区状态 ---
    selectedId: null,
    detailData: null,
    detailTranslationLanguage: 'follow_ui',
    isTranslating: false,
    translatingByWorkshopId: {},
    isDetailLoading: false,
    relatedLoading: { dependencies: false, dependents: false, same_author: false },
    relatedErrors: { dependencies: '', dependents: '', same_author: '' },
    relatedMeta: {
      dependencies: { total: 0, hasMore: false },
      dependents: { total: 0, hasMore: false },
      same_author: { total: 0, hasMore: false },
    },
    historyStack: [],       // 记录浏览路径: [id1, id2, id3]
    transientList: {
      active: false,
      kind: '',
      title: '',
      sourceId: '',
      authorSteamId: '',
      items: [],
      total: 0,
      cursor: '*',
      nextCursor: '',
      hasMore: false,
      page: 1,
      isLoading: false,
      isLoadMore: false,
    },
  })
  // 3. 时间线抽屉状态
  const timeline = reactive({
    isOpen: false,
    workshopId: null, // workshop_id / repo_url
    modName: '',
    logs: [],
    isLoading: false
  })
  // 4. 已订阅合集抽屉状态
  const collections = reactive({
    activeView: 'saved',
    savedList: [],        // 后端获取的已订阅合集列表
    isLoading: false,     // 整体加载状态
    isParsing: false,     // 解析新合集时的 Loading 状态
    activeId: null,       // 当前选中的合集 ID
    activeDetails: null,  // 当前选中合集的详细信息 (包含 meta)
    activeChildren: [],   // 当前选中合集内的子 Mod 列表
    isChildrenLoading: false, // 子列表加载状态
    searchQuery: '',
    searchTokens: [],
    searchLogic: 'AND',
    searchSort: 'popular',
    searchDays: 7,
    searchCursor: '*',
    searchNextCursor: '',
    searchHasMore: true,
    searchResults: [],
    searchTotal: 0,
    isSearchLoading: false,
    isSearchLoadMore: false,
  })
  // 5. Git 仓库订阅状态
  const github = reactive({
    subscribedRepos: [],
    recommendedRepos: [],
    catalogMeta: {},
    isLoading: false,
    isCatalogLoading: false,
    catalogLoaded: false,
    catalogError: '',
    activeRepo: null,     // 当前查看的 repo
    repoTimelines: [],    // 当前选中仓库的日志
    previewInfo: null,    // 解析新链接时的预览信息
  })
  const githubTimelinePollTimer = ref(null)
  const githubTimelinePollSeq = ref(0)

  const isFetching = ref(false)
  const matrixFocusTarget = ref(null)
  const matrixFilterTarget = ref(null)
  const workspaceTargetTab = ref('')
  let workshopSearchReadyPromise = null

  const allLibraryMods = computed(() => [
    ...librariesMods.workshop,
    ...librariesMods.self,
    ...librariesMods.local
  ])
  const matrixModsByPathHash = computed(() => {
    const map = new Map()
    allLibraryMods.value.forEach(mod => {
      if (mod?.path_hash) {
        map.set(mod.path_hash, mod)
      }
    })
    return map
  })
  const matrixModsByPackageId = computed(() => {
    const map = new Map()
    allLibraryMods.value.forEach(mod => {
      const pkgId = normalizePackageId(mod?.package_id)
      if (!pkgId) return
      if (!map.has(pkgId)) map.set(pkgId, [])
      map.get(pkgId).push(mod)
    })
    return map
  })
  const matrixSameMap = computed(() => {
    const sameMap = new Map()
    const pushRelation = (targetMap, source, target) => {
      if (!source?.path_hash || !target?.path_hash || source.path_hash === target.path_hash) return

      const existing = targetMap.get(source.path_hash) || []
      if (!existing.some(item => item.path_hash === target.path_hash)) {
        targetMap.set(source.path_hash, [...existing, target])
      }
    }

    matrixModsByPackageId.value.forEach(group => {
      for (let i = 0; i < group.length; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const source = group[i]
          const target = group[j]
          if (source.store !== target.store) {
            pushRelation(sameMap, source, target)
            pushRelation(sameMap, target, source)
          }
        }
      }
    })

    sameMap.forEach((targets, pathHash) => sameMap.set(pathHash, sortMatrixTargets(targets)))
    return sameMap
  })
  const matrixConflictMap = computed(() => {
    const conflictMap = new Map()
    const pushRelation = (targetMap, source, target) => {
      if (!source?.path_hash || !target?.path_hash || source.path_hash === target.path_hash) return

      const existing = targetMap.get(source.path_hash) || []
      if (!existing.some(item => item.path_hash === target.path_hash)) {
        targetMap.set(source.path_hash, [...existing, target])
      }
    }

    matrixModsByPackageId.value.forEach(group => {
      for (let i = 0; i < group.length; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const source = group[i]
          const target = group[j]
          if (source.store === target.store) {
            pushRelation(conflictMap, source, target)
            pushRelation(conflictMap, target, source)
          }
        }
      }
    })

    conflictMap.forEach((targets, pathHash) => conflictMap.set(pathHash, sortMatrixTargets(targets)))
    return conflictMap
  })
  const getMatrixSameItems = (pathHash) => matrixSameMap.value.get(pathHash) || []
  const getMatrixConflictItems = (pathHash) => matrixConflictMap.value.get(pathHash) || []
  const getGithubOnlineVersion = (repo) => {
    if (!repo?.online_info) return ''
    if (repo.install_type === 'zip') {
      return String(repo.online_info.catalog_signature || '').trim()
    }
    if (repo.install_type === 'release') {
      return String(repo.online_info.latest_release_tag || '').trim()
    }
    return String(repo.online_info.latest_source_version || '').trim()
  }
  const parseGithubSourceVersion = (value) => {
    const raw = String(value || '').trim()
    const [branch, marker = ''] = raw.split('@')
    const time = Date.parse(marker)
    return {
      raw,
      branch: branch || '',
      marker,
      time: Number.isFinite(time) ? time : 0,
    }
  }
  const githubRepoNeedsUpdate = (repo) => {
    const status = getGithubRepoStatus(repo)
    return status.key === 'upgrade'
  }
  const getGithubRepoStatus = (repo) => {
    if (!repo) return { key: 'unknown', label: '状态未知', tone: 'text-text-dim', version: '' }
    const localVersion = String(repo?.installed_version || '').trim()
    const onlineVersion = getGithubOnlineVersion(repo)
    if (repo.local_folder && repo.local_exists === false) {
      return { key: 'missing', label: '本地文件缺失', tone: 'text-accent-danger', version: localVersion }
    }
    if (!localVersion) return { key: 'not_deployed', label: '未部署', tone: 'text-text-dim', version: onlineVersion }
    if (!onlineVersion) return { key: 'installed', label: '已安装', tone: 'text-accent-success', version: localVersion }
    if (repo?.install_type === 'source') {
      const localSource = parseGithubSourceVersion(localVersion)
      const onlineSource = parseGithubSourceVersion(onlineVersion)
      if (localSource.branch && onlineSource.branch && localSource.branch !== onlineSource.branch) {
        return { key: 'branch_changed', label: '跟踪分支不同', tone: 'text-accent-warn', version: onlineVersion }
      }
      if (localSource.time && onlineSource.time) {
        if (onlineSource.time > localSource.time) return { key: 'upgrade', label: '可升级', tone: 'text-accent-warn', version: onlineVersion }
        return { key: 'current', label: '已是最新', tone: 'text-accent-success', version: onlineVersion }
      }
    }
    if (localVersion !== onlineVersion) return { key: 'upgrade', label: '可升级', tone: 'text-accent-warn', version: onlineVersion }
    return { key: 'current', label: '已是最新', tone: 'text-accent-success', version: onlineVersion }
  }
  const applyGithubRepoComputedState = (repo) => {
    if (!repo) return repo
    repo.online_info = repo.online_info || repo.online_info_cache || {}
    repo.status = getGithubRepoStatus(repo)
    repo.has_update = repo.status.key === 'upgrade'
    return repo
  }
  const stopGithubTimelinePolling = () => {
    if (githubTimelinePollTimer.value) {
      clearInterval(githubTimelinePollTimer.value)
      githubTimelinePollTimer.value = null
    }
  }
  const clearActiveGithubRepo = () => {
    stopGithubTimelinePolling()
    github.activeRepo = null
    github.repoTimelines = []
  }
  const fetchGithubTimeline = async (url) => {
    if (!window.pywebview || !url) return
    const res = await window.pywebview.api.github_get_timeline(url)
    if (checkResult(res, '获取 Git 仓库模组时间线')) {
      if (github.activeRepo?.repo_url !== url) return
      github.repoTimelines = res.data
    }
  }
  const startGithubTimelinePolling = async (repoUrl, options = {}) => {
    if (!repoUrl) return
    const intervalMs = Number(options.intervalMs || 4000)
    const maxPolls = Number(options.maxPolls || 15)
    let pollCount = 0
    let inFlight = false
    const pollSeq = Date.now()

    githubTimelinePollSeq.value = pollSeq
    stopGithubTimelinePolling()

    const pollOnce = async () => {
      if (inFlight) return
      if (githubTimelinePollSeq.value !== pollSeq) return
      if (github.activeRepo?.repo_url !== repoUrl) {
        stopGithubTimelinePolling()
        return
      }

      inFlight = true
      try {
        await fetchGithubTimeline(repoUrl)
        pollCount += 1
        if (pollCount >= maxPolls) {
          stopGithubTimelinePolling()
        }
      } finally {
        inFlight = false
      }
    }

    await pollOnce()
    if (github.activeRepo?.repo_url !== repoUrl) return
    githubTimelinePollTimer.value = setInterval(pollOnce, intervalMs)
  }
  const selectGithubRepo = async (repo) => {
    stopGithubTimelinePolling()
    github.previewInfo = null
    github.activeRepo = repo ? applyGithubRepoComputedState(repo) : null
    github.repoTimelines = []
    if (github.activeRepo?.repo_url) {
      await fetchGithubTimeline(github.activeRepo.repo_url)
    }
  }
  const jumpToMatrixItem = (pathHash) => {
    const target = matrixModsByPathHash.value.get(pathHash)
    if (!target) return false
    matrixFocusTarget.value = {
      pathHash,
      store: target.store,
      stamp: Date.now()
    }
    return true
  }
  const normalizeSizeRefreshPathKey = (path = '') => String(path || '').trim().replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  const applyStartupInventorySummary = (summary = {}) => {
    // 启动轻量接口已经在后端完成变更判断，这里只接入现有提示和扫描路径。
    startupWorkshopChangeState.detected = true
    startupWorkshopChangeState.prompted = false
    startupWorkshopChangeState.changes = Array.isArray(summary?.events) ? summary.events : []
    return startupWorkshopChangeState.changes
  }
  const STARTUP_EVENT_GROUPS = [
    ['deleted', '已删除模组', '库存记录还在，但本地文件夹已不存在。确认无误后可清理残留记录。'],
    ['missing', '缺失模组', '仍在工坊订阅列表中，但本地文件不完整或不存在。订阅内容很多时，Steam 同步队列可能漏掉少量项目导致文件缺失；工坊订阅超过 1000 项时更容易遇到。可重新下载补齐。'],
    ['changed', '已变更模组', '工坊内容已被作者更新。建议重新扫描，刷新大小、时间和状态。'],
  ]
  const STARTUP_EVENT_FILTER_MAP = {
    deleted: 'deleted',
    missing: 'missing',
    changed: 'change',
  }
  const formatStartupEventNames = (changes = [], status = '', limit = 8) => {
    const targets = (Array.isArray(changes) ? changes : []).filter(item => item?.status === status)
    const shown = targets.slice(0, limit).map(item => `· ${item.name}`).join('\n')
    const more = targets.length > limit ? `\n等 ${targets.length} 个模组。` : ''
    return shown ? `${shown}${more}` : ''
  }
  const formatStartupWorkshopChangeNames = (changes = [], limit = 8) => formatStartupEventNames(changes, 'changed', limit)
  const formatStartupInventorySummary = (changes = [], beforeScan = false) => {
    const prefix = beforeScan ? '检测到库存可能有变化。' : '库存检测完成。'
    const counts = STARTUP_EVENT_GROUPS
      .map(([status, title]) => {
        const count = (Array.isArray(changes) ? changes : []).filter(item => item?.status === status).length
        return count ? `${title} ${count} 项` : ''
      })
      .filter(Boolean)
    return counts.length ? `${prefix}\n${counts.join('，')}。` : prefix
  }
  const resolveStartupMissingWorkshopIds = (changes = []) => [...new Set((Array.isArray(changes) ? changes : [])
    .filter(item => item?.status === 'missing')
    .map(item => normalizeWorkshopId(item?.workshopId))
    .filter(Boolean))]
  const getStartupEventGroupConfig = (status = '') => STARTUP_EVENT_GROUPS.find(([key]) => key === status)
  const getStartupEventGroupLabel = (status = '') => getStartupEventGroupConfig(status)?.[1] || '库存状态'
  const buildStartupInventoryDialogItems = (changes = []) => (Array.isArray(changes) ? changes : []).map((item, index) => {
    const workshopId = normalizeWorkshopId(item?.workshopId)
    const status = String(item?.status || '').trim()
    return {
      id: `${status}:${item?.pathHash || workshopId || index}`,
      title: item?.name || workshopId || '未知模组',
      description: item?.path || (workshopId ? `Workshop ID: ${workshopId}` : ''),
      meta: [getStartupEventGroupLabel(status), workshopId ? `Workshop ID: ${workshopId}` : ''].filter(Boolean),
      status,
      workshopId,
      raw: item,
    }
  })
  const buildStartupInventoryDialogGroups = (items = []) => STARTUP_EVENT_GROUPS
    .map(([status, title, description]) => {
      const groupItems = items.filter(item => item?.status === status)
      return groupItems.length ? { id: status, title, description, items: groupItems } : null
    })
    .filter(Boolean)
  const resolveStartupInventoryFilterState = (changes = []) => {
    const statuses = new Set((Array.isArray(changes) ? changes : []).map(item => item?.status).filter(Boolean))
    const status = STARTUP_EVENT_GROUPS.find(([key]) => statuses.has(key))?.[0]
    return STARTUP_EVENT_FILTER_MAP[status] || 'default'
  }
  const resolveStartupWorkshopChangePathHashes = (changes = []) => {
    const targets = Array.isArray(changes) ? changes : []
    const byPath = new Map()
    const byWorkshopId = new Map()
    ;[...librariesMods.workshop, ...librariesMods.self, ...librariesMods.local].forEach(mod => {
      const pathKey = normalizeSizeRefreshPathKey(mod?.path)
      const workshopId = normalizeWorkshopId(mod?.workshop_id)
      if (pathKey && mod?.path_hash) byPath.set(`${mod.store || ''}:${pathKey}`, mod.path_hash)
      if (workshopId && mod?.path_hash) byWorkshopId.set(`${mod.store || ''}:${workshopId}`, mod.path_hash)
    })
    return [...new Set(targets.map(item => {
      const pathKey = normalizeSizeRefreshPathKey(item?.path)
      const workshopId = normalizeWorkshopId(item?.workshopId)
      const store = item?.store || ''
      return (pathKey && byPath.get(`${store}:${pathKey}`)) || (workshopId && byWorkshopId.get(`${store}:${workshopId}`)) || String(item?.pathHash || '').trim()
    }).filter(Boolean))]
  }
  const openWorkspaceForStartupChanges = async (changes = startupWorkshopChangeState.changes) => {
    appStore.uiState.showWorkspace = true
    workspaceTargetTab.value = 'library'
    await ensureWorkspaceTabLoaded('library')
    const pathHashes = resolveStartupWorkshopChangePathHashes(changes)
    matrixFilterTarget.value = {
      store: 'all',
      pathHashes,
      filterState: resolveStartupInventoryFilterState(changes),
      stamp: Date.now(),
    }
    if (pathHashes.length === 1) {
      window.setTimeout(() => {
        jumpToMatrixItem(pathHashes[0])
      }, 0)
    }
    return true
  }
  const getStartupEventFingerprint = (item = {}) => [
    item.status || '',
    item.store || '',
    item.workshopId || '',
    item.pathHash || '',
    normalizeSizeRefreshPathKey(item.path),
    item.downloadTime || 0,
  ].join('|')
  const loadStartupPromptAck = () => {
    try {
      const saved = localStorage.getItem(STARTUP_INVENTORY_ACK_KEY) || localStorage.getItem(LEGACY_STARTUP_INVENTORY_ACK_KEY) || '[]'
      return new Set(JSON.parse(saved))
    } catch {
      return new Set()
    }
  }
  const saveStartupPromptAck = (items = []) => {
    const ack = loadStartupPromptAck()
    items.forEach(item => {
      const key = getStartupEventFingerprint(item)
      if (key) ack.add(key)
    })
    localStorage.setItem(STARTUP_INVENTORY_ACK_KEY, JSON.stringify([...ack].slice(-1000)))
    localStorage.removeItem(LEGACY_STARTUP_INVENTORY_ACK_KEY)
  }
  const getPromptableStartupEvents = (changes = []) => {
    const targets = (Array.isArray(changes) ? changes : []).filter(item => item?.status)
    if (!appStore.settings?.startup_inventory_prompt_new_only) return targets
    const ack = loadStartupPromptAck()
    return targets.filter(item => !ack.has(getStartupEventFingerprint(item)))
  }
  const cleanupDeletedStartupRecords = async (changes = [], options = {}) => {
    const deletedHashes = [...new Set((Array.isArray(changes) ? changes : [])
      .filter(item => item?.status === 'deleted')
      .map(item => String(item?.pathHash || '').trim())
      .filter(pathHash => pathHash && !pathHash.startsWith('ghost_')))]
    if (!deletedHashes.length || !window.pywebview) return false

    if (options.confirm !== false) {
      const check = await confirmStore.confirmAction(
        '清理已删除记录',
        `确定要清理这些已删除/失效的库存记录吗？（${deletedHashes.length} 项）\n这不会删除任何文件，也不会清理用户标签、笔记和分组。`,
        { type: 'warning' }
      )
      if (!check) return false
    }

    const res = await window.pywebview.api.mods_delete(deletedHashes, false, false)
    if (!checkResult(res, '清理已删除记录')) return false
    toast.success(`已清理 ${res.data?.success_count || deletedHashes.length} 条已删除记录`)
    await fetchLibrariesMods()
    await appStore.refreshModCoreData('清理库存记录后同步模组数据', {
      preserveListState: true,
      refreshRules: false,
      refreshBackups: false,
      refreshWorkspaceLibraries: false,
    })
    return true
  }
  const removeStartupInventoryDialogItems = (itemIds = []) => {
    const ids = new Set(itemIds)
    startupInventoryDialog.groups.forEach(group => {
      group.items = group.items.filter(item => !ids.has(item.id))
    })
    startupInventoryDialog.groups = startupInventoryDialog.groups.filter(group => group.items.length > 0)
    if (startupInventoryDialog.groups.length === 0) closeStartupInventoryDialog()
  }
  const closeStartupInventoryDialog = () => {
    startupInventoryDialog.visible = false
    saveStartupPromptAck(startupInventoryDialog.targets)
    if (typeof startupInventoryDialog.resolve === 'function') {
      startupInventoryDialog.resolve(true)
      startupInventoryDialog.resolve = null
    }
  }
  const runStartupInventoryDialogAction = async (actionId, items = [], options = {}) => {
    const targets = (Array.isArray(items) ? items : []).map(item => item?.raw || item).filter(Boolean)
    if (!targets.length) return false
    const pendingTarget = options.pendingTarget || 'default'
    const pendingKey = `${actionId}:${pendingTarget}`
    if (startupInventoryDialog.pendingActions.includes(pendingKey)) return false
    startupInventoryDialog.pendingActions = [...startupInventoryDialog.pendingActions, pendingKey]
    try {
      let ok = false
      if (actionId === 'download_missing') {
        const workshopIds = resolveStartupMissingWorkshopIds(targets)
        if (!workshopIds.length) {
          toast.warning('没有可下载的工坊缺失项')
          return false
        }
        ok = await appStore.downloadWorkshopItemsViaSteam(workshopIds, { highPriority: true, waitSeconds: 30 })
      } else if (actionId === 'cleanup_deleted') {
        ok = await cleanupDeletedStartupRecords(targets, { confirm: false })
      }
      if (ok) {
        const handledIds = (Array.isArray(items) ? items : []).map(item => item?.id).filter(Boolean)
        removeStartupInventoryDialogItems(handledIds)
      }
      return ok
    } finally {
      startupInventoryDialog.pendingActions = startupInventoryDialog.pendingActions.filter(key => key !== pendingKey)
    }
  }
  const openStartupInventoryDialogDetails = async (status) => {
    const targets = startupInventoryDialog.targets.filter(item => item?.status === status)
    closeStartupInventoryDialog()
    if (targets.length) await openWorkspaceForStartupChanges(targets)
  }
  const showStartupWorkshopChangesPrompt = async (changes = startupWorkshopChangeState.changes, options = {}) => {
    const targets = getPromptableStartupEvents(changes)
    if (!targets.length || startupWorkshopChangeState.prompted) return false
    startupWorkshopChangeState.prompted = true
    const items = buildStartupInventoryDialogItems(targets)
    startupInventoryDialog.title = options?.beforeScan ? '检测到库存状态变化' : '库存状态已刷新'
    startupInventoryDialog.message = formatStartupInventorySummary(targets, !!options?.beforeScan)
    startupInventoryDialog.targets = targets
    startupInventoryDialog.groups = buildStartupInventoryDialogGroups(items)
    startupInventoryDialog.pendingActions = []
    startupInventoryDialog.visible = true
    return new Promise(resolve => {
      startupInventoryDialog.resolve = resolve
    })
  }

  const applyLifecycleUpdateState = (updates = []) => {
    const normalizedUpdates = Array.isArray(updates) ? updates : []
    const updateMap = new Map(
      normalizedUpdates
        .map(item => {
          const wid = normalizeWorkshopId(item?.workshop_id)
          return wid ? [wid, item] : null
        })
        .filter(Boolean)
    )

    const resetState = (modList) => {
      modList.forEach(mod => {
        mod.has_update = false
        delete mod.update_info
      })
    }

    const applyState = (modList, source) => {
      modList.forEach(mod => {
        const wid = normalizeWorkshopId(mod?.workshop_id)
        if (!wid) return
        const updateInfo = updateMap.get(wid)
        if (!updateInfo || updateInfo.source !== source) return
        mod.has_update = true
        mod.update_info = updateInfo
      })
    }

    resetState(librariesMods.workshop)
    resetState(librariesMods.self)
    applyState(librariesMods.workshop, 'workshop')
    applyState(librariesMods.self, 'self')

    console.debug('[Workspace] 生命周期更新状态已合并:', normalizedUpdates.length, '条记录')
  }

  const refreshLifecycleUpdateStates = async () => {
    if (!window.pywebview) return true
    const res = await startupPerfMeasure('workspace.lifecycle_check_updates', () => window.pywebview.api.lifecycle_check_updates())
    if (checkResult(res, '检查库内模组更新状态')) {
      startupPerfMark('workspace.lifecycle_updates_received', { updates: res.data?.updates?.length || 0 })
      applyLifecycleUpdateState(res.data?.updates || [])
      return true
    }
    return false
  }

  // 响应式计算 Mod 状态
  const activeChildrenWithStatus = computed(() => {
    return collections.activeChildren.map(child => {
      const wid = String(child.workshop_id)
      const pid = child.package_id ? String(child.package_id).toLowerCase() : null
      const is_workshop = librariesMods.workshop.some(m => isMatrixModAvailable(m) && String(m.workshop_id) === wid)
      const is_self = librariesMods.self.some(m => isMatrixModAvailable(m) && String(m.workshop_id) === wid)
      // 本地目录用包名比对最准，没有包名回退使用 wid
      const is_local = librariesMods.local.some(m => isMatrixModAvailable(m) &&
          ((pid && m.package_id?.toLowerCase() === pid) || (m.workshop_id && String(m.workshop_id) === wid))
      )
      return {
        ...child,
        is_workshop,
        is_self,
        is_local,
        is_installed: is_workshop || is_self || is_local
      }
    })
  })

  // --- Actions ---
  const ensureLibrariesLoaded = async ({ force = false } = {}) => {
    if (loadState.librariesLoaded && !force) return true
    return await fetchLibrariesMods()
  }
  const ensureGithubLoaded = async ({ force = false } = {}) => {
    if (loadState.githubLoaded && !force) return true
    return await fetchGithubRepos()
  }
  const ensureCollectionsLoaded = async ({ force = false } = {}) => {
    if (loadState.collectionsLoaded && !force) return true
    return await fetchSavedCollections()
  }
  // 工作区按标签懒加载，避免应用启动时把所有工作区接口提前打满。
  const ensureWorkspaceTabLoaded = async (tabId, options = {}) => {
    const normalizedTabId = String(tabId || 'library').trim().toLowerCase()
    if (normalizedTabId === 'library') return await ensureLibrariesLoaded(options)
    if (normalizedTabId === 'github') return await ensureGithubLoaded(options)
    if (normalizedTabId === 'collection') return await ensureCollectionsLoaded(options)
    return true
  }

  // 仅刷新当前已经加载过的数据区，避免全局刷新时再次触发未打开页面的预热请求。
  const refreshLoadedData = async ({ librariesOnly = false } = {}) => {
    const jobs = []
    if (loadState.librariesLoaded) jobs.push(fetchLibrariesMods())
    if (!librariesOnly && loadState.githubLoaded) jobs.push(fetchGithubRepos())
    if (!librariesOnly && loadState.collectionsLoaded) jobs.push(fetchSavedCollections())
    if (jobs.length === 0) return true
    await Promise.all(jobs)
    return true
  }
  // 监听后端推送
  const setupListeners = () => {
    if (listenersReady.value) return
    listenersReady.value = true

    // 【监听 A】: Steam 公开详情静默更新
    // payload 格式: { "12345": { title: "...", time_updated: 17000000, preview_url: "..." }, ... }
    window.addEventListener('workspace-online-update', (e) => {
      const onlineMap = e.detail || {}
      console.debug("工作区收到 Steam 在线状态批量推送:", Object.keys(onlineMap).length, "条记录")
      const mergeOnlineData = (modList) => {
        modList.forEach(mod => {
          const wid = String(mod.workshop_id)
          if (onlineMap[wid]) {
            const onlineInfo = onlineMap[wid]
            mod.online_info = onlineInfo
            const localTime = mod.steam_status?.time_downloaded ||
                              mod.steam_status?.installed_version_time || 0
            mod.has_update = onlineInfo.time_updated > (localTime + 3600 * 1000)
          }
        })
      }
      mergeOnlineData(librariesMods.self)
      // 普通工坊搜索页也复用这条公开详情推送：只合并展示字段，不改变请求模式。
      workshopSearch.results = mergeWorkshopOnlineMapIntoItems(workshopSearch.results, onlineMap)
      workshopSearch.transientList.items = mergeWorkshopOnlineMapIntoItems(workshopSearch.transientList.items, onlineMap)
      if (workshopSearch.detailData?.workshop_id && onlineMap[workshopSearch.detailData.workshop_id]) {
        mergeWorkshopDetailData(onlineMap[workshopSearch.detailData.workshop_id])
      }
      const current = workshopSearch.detailData || {}
      const related = current.related || {}
      if (Object.keys(onlineMap).length && Object.keys(related).length) {
        workshopSearch.detailData = normalizeWorkshopSearchItem({
          ...current,
          related: {
            ...related,
            dependencies: mergeWorkshopOnlineMapIntoItems(related.dependencies || [], onlineMap),
            dependents: mergeWorkshopOnlineMapIntoItems(related.dependents || [], onlineMap),
            same_author: mergeWorkshopOnlineMapIntoItems(related.same_author || [], onlineMap),
            collection_children: mergeWorkshopOnlineMapIntoItems(related.collection_children || [], onlineMap),
          },
        })
      }
    })
    // 【监听 A2】: 缺失工坊项可用性探查。只更新运行时标签，不改变库存状态。
    window.addEventListener('workspace-missing-workshop-probe', (e) => {
      const probeMap = e.detail || {}
      librariesMods.workshop.forEach(mod => {
        const wid = normalizeWorkshopId(mod?.workshop_id)
        if (!wid || !probeMap[wid]) return
        const probe = probeMap[wid]
        mod.workshop_online_status = probe.status || 'unknown'
        mod.workshop_online_result = probe.result ?? null
        if (probe.online_info) mod.online_info = probe.online_info
      })
    })
    // 【监听 B】: Git 仓库在线状态静默更新
    // payload 格式: { "https://host/group/repo": { latest_release_tag: "v1.2", ... }, ... }
    window.addEventListener('github-online-update', (e) => {
      const updatedReposMap = e.detail
      console.debug("工作区收到 Git 仓库在线状态推送:", Object.keys(updatedReposMap).length, "条记录")

      github.subscribedRepos.forEach(repo => {
        if (updatedReposMap[repo.repo_url]) {
          const freshInfo = updatedReposMap[repo.repo_url]
          repo.online_info = freshInfo
          applyGithubRepoComputedState(repo)
        }
      })
      if (github.activeRepo?.repo_url && updatedReposMap[github.activeRepo.repo_url]) {
        applyGithubRepoComputedState(github.activeRepo)
      }
    })
    // 监听合集更新
    window.addEventListener('workspace-collection-updated', (e) => {
      const updated = e.detail // { id, data: { collection, children, ... } }
      // 如果当前用户正在看的正是这个合集，立即无感替换数据
    if (collections.activeId === updated.id) {
      collections.activeDetails = {
        ...(collections.activeDetails || {}),
        ...(updated.data.collection || {})
      }
      collections.activeChildren = updated.data.children || []
      collections.isChildrenLoading = false // 后台更新完毕，取消 loading
    }
      // 同时更新右侧合集列表中的统计数字
      const target = collections.savedList.find(c => c.id === updated.id)
      if (target) {
        Object.assign(target, {
          total: updated.data.total,
          preview_url: updated.data.collection.preview_url,
          title: updated.data.collection.title,
          description: updated.data.collection.description,
          time_updated: updated.data.collection.time_updated
        })
        target.children = updated.data.children // 保存 children 供列表计算
      }
    })
  }

  // 拉取无遮蔽的三个库全量数据
  const fetchLibrariesMods = async () => {
    if (!window.pywebview) return
    startupPerfMark('workspace.fetch_libraries_start')
    setupListeners()
    isFetching.value = true
    try {
      // 这个 API 现在只负责去读本地 SQLite 和内存缓存，响应时间应该 < 50ms
      const res = await startupPerfMeasure('workspace.get_all_domains', () => window.pywebview.api.workspace_get_all_domains())
      if (checkResult(res, '获取所有库数据')) {
        // 直接替换数组引用
        librariesMods.local = res.data.local || []
        librariesMods.workshop = res.data.workshop || []
        librariesMods.self = res.data.self || []
        startupPerfMark('workspace.libraries_assigned', {
          local: librariesMods.local.length,
          workshop: librariesMods.workshop.length,
          self: librariesMods.self.length,
        })

        // 渲染完毕！如果后端在此接口中发现了需要触发的在线查询，
        // 后端会自己开启线程并发 `workspace-online-update` 事件。
        await refreshLifecycleUpdateStates()
        loadState.librariesLoaded = true
        startupPerfMark('workspace.fetch_libraries_done')
        return true
      }
    } finally {
      isFetching.value = false
    }
    return false
  }

  const versionTagPattern = /^\d+(?:\.\d+)+$/
  const normalizeVersionTags = (values = []) => {
    const seen = new Set()
    return (Array.isArray(values) ? values : [])
      .map(value => String(value || '').trim())
      .filter(value => {
        if (!value || !versionTagPattern.test(value) || seen.has(value)) return false
        seen.add(value)
        return true
      })
  }

  const normalizeWorkshopQueryValue = (value = '') => String(value ?? '').trim()
  const mergeUniqueWorkshopTerms = (...groups) => {
    const seen = new Set()
    return groups.flat().map(normalizeWorkshopQueryValue).filter(value => {
      const key = value.toLowerCase()
      if (!value || seen.has(key)) return false
      seen.add(key)
      return true
    })
  }
  // Steam 的文本搜索最终只认 AND / OR / NOT；前端输入只暴露 + / | / -。
  // 这里保留括号并在请求前转换，避免用户输入原始 AND/OR/NOT 时被误识别为运算符。
  const tokenizeSteamSymbolSearchText = (value = '') => {
    const text = normalizeWorkshopQueryValue(value)
    const tokens = []
    let buffer = ''
    const flush = () => {
      const term = buffer.trim()
      if (term) tokens.push({ type: 'term', value: term })
      buffer = ''
    }

    for (let index = 0; index < text.length; index += 1) {
      const char = text[index]
      const prev = index > 0 ? text[index - 1] : ''
      const next = index < text.length - 1 ? text[index + 1] : ''
      const prevIsBoundary = index === 0 || /\s/.test(prev) || ['(', '+', '|', '-'].includes(prev)
      const nextIsBoundary = !next || /\s/.test(next) || ['(', ')', '+', '|', '-'].includes(next)
      const isMinusOperator = char === '-' && (prevIsBoundary || nextIsBoundary)
      const isOperator = char === '+' || char === '|' || isMinusOperator
      if (isOperator || char === '(' || char === ')') {
        flush()
        tokens.push({ type: char === '(' || char === ')' ? 'paren' : 'operator', value: char })
        continue
      }
      buffer += char
    }
    flush()
    return tokens
  }
  const neutralizeRawSteamOperatorWords = (value = '') => (
    String(value || '').replace(/\b(AND|OR|NOT)\b/g, matched => matched.toLowerCase())
  )
  const convertSteamSymbolSearchText = (value = '') => {
    const text = normalizeWorkshopQueryValue(value)
    if (!/[+|()]/.test(text) && !/(^|\s)-\S|-\s+\S/.test(text)) return neutralizeRawSteamOperatorWords(text)
    const tokens = tokenizeSteamSymbolSearchText(text)
    const output = []
    let previousWasOperand = false
    tokens.forEach(token => {
      if (token.type === 'term') {
        output.push(neutralizeRawSteamOperatorWords(token.value))
        previousWasOperand = true
        return
      }
      if (token.type === 'paren') {
        output.push(token.value)
        previousWasOperand = token.value === ')'
        return
      }
      if (token.value === '+') {
        if (previousWasOperand) output.push('AND')
        previousWasOperand = false
        return
      }
      if (token.value === '|') {
        if (previousWasOperand) output.push('OR')
        previousWasOperand = false
        return
      }
      if (token.value === '-') {
        if (previousWasOperand) output.push('AND')
        output.push('NOT')
        previousWasOperand = false
      }
    })
    return output.join(' ').replace(/\(\s+/g, '(').replace(/\s+\)/g, ')').replace(/\s+/g, ' ').trim()
  }
  const buildSteamExcludedText = (value = '') => {
    const converted = convertSteamSymbolSearchText(value)
    if (!converted) return ''
    return /(\s|\(|\)|\bAND\b|\bOR\b|\bNOT\b)/.test(converted) ? `NOT (${converted})` : `NOT ${converted}`
  }
  const buildWorkshopSearchTextQuery = (textTerms = [], excludedTextTerms = [], logic = 'AND') => {
    const positiveTerms = mergeUniqueWorkshopTerms(textTerms).map(convertSteamSymbolSearchText).filter(Boolean)
    const negativeTerms = mergeUniqueWorkshopTerms(excludedTextTerms).map(buildSteamExcludedText).filter(Boolean)
    const operator = String(logic || 'AND').toUpperCase() === 'OR' ? ' OR ' : ' AND '
    const positiveQuery = positiveTerms.join(operator)
    const negativeQuery = negativeTerms.join(' AND ')
    return [positiveQuery, negativeQuery].filter(Boolean).join(' ').trim()
  }
  const compileWorkshopQueryTokens = () => {
    const compiled = {
      textTerms: [],
      excludedTextTerms: [],
      requiredTags: [],
      excludedTags: [],
      requiredDlcAppids: [],
      excludedDlcAppids: [],
      dependencyWorkshopIds: [],
      excludedDependencyWorkshopIds: [],
      author: '',
    }

    for (const token of workshopSearch.queryTokens || []) {
      const value = normalizeWorkshopQueryValue(token?.value)
      if (!value) continue
      if (token.type === 'text') {
        ;(token.exclude ? compiled.excludedTextTerms : compiled.textTerms).push(value)
        continue
      }
      if (token.key === 'text') {
        ;(token.exclude ? compiled.excludedTextTerms : compiled.textTerms).push(value)
      } else if (token.key === 'tag') {
        ;(token.exclude ? compiled.excludedTags : compiled.requiredTags).push(value)
      } else if (token.key === 'dlc') {
        ;(token.exclude ? compiled.excludedDlcAppids : compiled.requiredDlcAppids).push(value)
      } else if (token.key === 'dependency') {
        ;(token.exclude ? compiled.excludedDependencyWorkshopIds : compiled.dependencyWorkshopIds).push(value)
      } else if (token.key === 'author' && !token.exclude) {
        compiled.author = value
      }
    }

    return {
      ...compiled,
      query: buildWorkshopSearchTextQuery(compiled.textTerms, compiled.excludedTextTerms, workshopSearch.queryLogic),
      requiredTags: mergeUniqueWorkshopTerms(compiled.requiredTags),
      excludedTags: mergeUniqueWorkshopTerms(compiled.excludedTags),
      requiredDlcAppids: mergeUniqueWorkshopTerms(compiled.requiredDlcAppids),
      excludedDlcAppids: mergeUniqueWorkshopTerms(compiled.excludedDlcAppids),
      dependencyWorkshopIds: mergeUniqueWorkshopTerms(compiled.dependencyWorkshopIds),
      excludedDependencyWorkshopIds: mergeUniqueWorkshopTerms(compiled.excludedDependencyWorkshopIds),
    }
  }

  const compileCollectionQueryTokens = () => {
    const compiled = {
      textTerms: [],
      excludedTextTerms: [],
      requiredTags: [],
      excludedTags: [],
    }

    for (const token of collections.searchTokens || []) {
      const value = normalizeWorkshopQueryValue(token?.value)
      if (!value) continue
      if (token.type === 'text') {
        ;(token.exclude ? compiled.excludedTextTerms : compiled.textTerms).push(value)
      } else if (token.key === 'text') {
        ;(token.exclude ? compiled.excludedTextTerms : compiled.textTerms).push(value)
      } else if (token.key === 'tag') {
        ;(token.exclude ? compiled.excludedTags : compiled.requiredTags).push(value)
      }
    }

    return {
      ...compiled,
      query: buildWorkshopSearchTextQuery(compiled.textTerms, compiled.excludedTextTerms, collections.searchLogic),
      requiredTags: mergeUniqueWorkshopTerms(compiled.requiredTags),
      excludedTags: mergeUniqueWorkshopTerms(compiled.excludedTags),
    }
  }

  const buildWorkshopSearchFilters = (compiledTokens = compileWorkshopQueryTokens()) => {
    const isEnhancedMode = workshopSearch.isEnhancedMode
    const tokenMatchAll = String(workshopSearch.queryLogic || 'AND').toUpperCase() !== 'OR'
    const hasText = hasWorkshopSearchText(workshopSearch.queryTokens)
    const requestSort = isEnhancedMode ? resolveWorkshopSort(workshopSearch.sort, hasText) : workshopSearch.sort
    const commonFilters = {
      sort: requestSort || (isEnhancedMode ? 'popular' : 'latest'),
      author: compiledTokens.author,
      required_tags: compiledTokens.requiredTags,
      excluded_tags: compiledTokens.excludedTags,
      match_all_tags: tokenMatchAll,
      required_dlc_appids: compiledTokens.requiredDlcAppids,
      child_publishedfileid: compiledTokens.dependencyWorkshopIds[0] || '',
    }
    if (!isEnhancedMode) return commonFilters
    const enhancedFilters = {
      ...commonFilters,
      language: workshopSearch.language || appStore.settings.language || '',
      appid: RIMWORLD_STEAM_APP_ID,
      type: 0,
      return_vote_data: true,
      strip_description_bbcode: false,
      excluded_appids_required_for_use: compiledTokens.excludedDlcAppids,
    }
    const resolvedDays = resolveWorkshopDays(workshopSearch.sort, workshopSearch.days, hasText)
    if (resolvedDays !== undefined) enhancedFilters.days = resolvedDays
    enhancedFilters.search_text_target = Number(workshopSearch.searchTextTarget || 0)
    return enhancedFilters
  }

  const isWorkshopSearchDebugEnabled = () => import.meta.env.DEV || !!appStore.settings.debug_mode

  const logWorkshopSearchDebug = (payload = {}) => {
    if (!isWorkshopSearchDebugEnabled()) return
    console.groupCollapsed(`[RimCrow 工坊搜索] ${payload.isEnhancedMode ? '增强模式' : '普通模式'} ${payload.isAppend ? '追加结果' : '发起搜索'}`)
    console.info('请求参数', payload.request)
    console.info('响应数据', payload.response)
    console.info('结果项目', payload.items)
    console.groupEnd()
  }

  const mergeWorkshopItemPatch = (item = {}, patch = {}) => {
    if (!item?.workshop_id || !patch || typeof patch !== 'object') return item
    return normalizeWorkshopSearchItem({
      ...item,
      ...patch,
      related: {
        ...(item.related || {}),
        ...(patch.related || {}),
      },
    })
  }

  const mergeWorkshopOnlineMapIntoItems = (items = [], onlineMap = {}) => (
    items.map(item => {
      const workshopId = String(item?.workshop_id || '').trim()
      return workshopId && onlineMap[workshopId] ? mergeWorkshopItemPatch(item, onlineMap[workshopId]) : item
    })
  )

  const mergeWorkshopItemIntoList = (items = [], patch = {}) => {
    const workshopId = String(patch?.workshop_id || '').trim()
    if (!workshopId || !Array.isArray(items)) return items
    return items.map(item => String(item?.workshop_id || '').trim() === workshopId ? mergeWorkshopItemPatch(item, patch) : item)
  }

  const mergeWorkshopPatchIntoLoadedLists = (patch = {}) => {
    const workshopId = String(patch?.workshop_id || '').trim()
    if (!workshopId) return null
    const normalized = normalizeWorkshopSearchItem(patch)
    workshopSearch.results = mergeWorkshopItemIntoList(workshopSearch.results, normalized)
    workshopSearch.transientList.items = mergeWorkshopItemIntoList(workshopSearch.transientList.items, normalized)
    const related = workshopSearch.detailData?.related || {}
    for (const key of ['dependencies', 'dependents', 'same_author', 'collection_children']) {
      if (Array.isArray(related[key])) {
        related[key] = mergeWorkshopItemIntoList(related[key], normalized)
      }
    }
    return normalized
  }

  const preheatNormalWorkshopPublicDetails = async (items = []) => {
    if (!window.pywebview || workshopSearch.isEnhancedMode) return
    const workshopIds = [...new Set(
      items.map(item => String(item?.workshop_id || '').trim()).filter(Boolean)
    )]
    if (!workshopIds.length) return
    try {
      await window.pywebview.api.workshop_preheat_public_details(workshopIds)
    } catch (error) {
      console.debug('[Workspace] 普通工坊公开详情预热失败:', error)
    }
  }

  const normalizeWorkshopRelationItem = (value = {}, fallback = {}) => {
    if (typeof value === 'string' || typeof value === 'number') {
      return {
        workshop_id: String(value || '').trim(),
        title: String(fallback.title || fallback.name || '').trim(),
        name: String(fallback.name || fallback.title || '').trim(),
        preview_url: String(fallback.preview_url || '').trim(),
      }
    }
    return {
      ...value,
      workshop_id: String(value.workshop_id || value.publishedfileid || fallback.workshop_id || '').trim(),
      title: String(value.title || value.name || fallback.title || fallback.name || '').trim(),
      name: String(value.name || value.title || fallback.name || fallback.title || '').trim(),
      preview_url: String(value.preview_url || fallback.preview_url || '').trim(),
    }
  }

  const dedupeWorkshopRelations = (items = [], currentId = '') => {
    const seen = new Set()
    return items
      .map(item => normalizeWorkshopRelationItem(item))
      .filter(item => {
        const workshopId = item.workshop_id
        if (!workshopId || workshopId === currentId || seen.has(workshopId)) return false
        seen.add(workshopId)
        return true
      })
  }

  const buildUnifiedWorkshopRelations = (item = {}, currentId = '') => {
    const manifestDependencies = Object.entries(item.dependencies_mods || {}).map(([workshopId, name]) => (
      normalizeWorkshopRelationItem(workshopId, { name, title: name })
    ))
    const onlineDependencies = Array.isArray(item.dependencies_mods_online) ? item.dependencies_mods_online : []
    const children = Array.isArray(item.children) ? item.children : []
    const existingDependencies = Array.isArray(item.related?.dependencies) ? item.related.dependencies : []
    const existingCollectionChildren = Array.isArray(item.related?.collection_children) ? item.related.collection_children : []
    const isCollection = item.item_type === 'collection'
    // Steam 的 children 字段在不同类型下语义不同：
    // 普通物品表示依赖父项，合集表示包含的子项，因此必须按 item_type 分流。
    const dependencies = isCollection ? manifestDependencies : [...existingDependencies, ...manifestDependencies, ...onlineDependencies, ...children]
    return {
      dependencies: dedupeWorkshopRelations(dependencies, currentId),
      dependents: dedupeWorkshopRelations(item.related?.dependents || item.dependents_mods || [], currentId),
      same_author: dedupeWorkshopRelations(item.related?.same_author || item.same_author_mods || [], currentId),
      collection_children: isCollection ? dedupeWorkshopRelations([...existingCollectionChildren, ...children], currentId) : [],
    }
  }

  const resolveWorkshopItemType = (item = {}) => {
    const itemType = String(item.item_type || '').trim().toLowerCase()
    return ['mod', 'collection', 'other'].includes(itemType) ? itemType : 'mod'
  }

  const normalizeWorkshopStats = (item = {}) => {
    const stats = item.stats && typeof item.stats === 'object' ? item.stats : {}
    return {
      subscriptions: Number(stats.subscriptions || 0),
      favorited: Number(stats.favorited || 0),
      votes_up: Number(stats.votes_up || 0),
      votes_down: Number(stats.votes_down || 0),
      vote_score: Number(stats.vote_score || 0),
      num_reports: Number(stats.num_reports || 0),
      num_comments_public: Number(stats.num_comments_public || 0),
    }
  }

  const normalizeTranslationLanguage = (value = '') => String(value || '').trim()
  const normalizeDetailTranslationLanguage = (value = '') => {
    const code = normalizeTranslationLanguage(value)
    return code === 'auto' ? 'follow_ui' : code
  }
  const getWorkshopDetailTranslationSettings = () => appStore.getTranslationFeatureSettings('workshop_detail')
  const getUiTranslationLanguage = () => normalizeTranslationLanguage(appStore.settings.language || 'zh-CN')
  const getDefaultTranslationLanguage = () => {
    const configured = normalizeTranslationLanguage(getWorkshopDetailTranslationSettings().target_language)
    return !configured || configured === 'follow_ui' ? getUiTranslationLanguage() : configured
  }
  const getDefaultTranslationSelection = () => {
    const configured = normalizeTranslationLanguage(getWorkshopDetailTranslationSettings().target_language)
    return configured || 'follow_ui'
  }
  const getInitialWorkshopDetailTranslationLanguage = () => (
    getWorkshopDetailTranslationSettings().prefer_ui_language_translation === false ? '' : 'follow_ui'
  )
  const getDefaultWorkshopDisplayTranslationLanguage = () => (
    getWorkshopDetailTranslationSettings().prefer_ui_language_translation === false ? '' : getDefaultTranslationSelection()
  )
  const getResolvedTranslationLanguage = (language = '') => {
    const code = normalizeDetailTranslationLanguage(language)
    return code === 'follow_ui' ? getUiTranslationLanguage() : code
  }
  const getTranslationLanguageLabel = (language = '') => {
    const code = normalizeDetailTranslationLanguage(language)
    if (!code) return '原文'
    if (code === 'follow_ui') return `跟随界面语言（${getTranslationLanguageLabel(getUiTranslationLanguage())}）`
    const option = workshopSearch.languageOptions.find(item => item.code === code || item.value === code)
    return option?.label || code
  }
  const getWorkshopTranslationEntry = (translations = {}, language = '') => {
    const code = getResolvedTranslationLanguage(language)
    const value = code && translations && typeof translations === 'object' ? translations[code] : null
    return value && typeof value === 'object' && (value.title || value.description) ? value : null
  }
  const shouldSkipWorkshopAutoTranslate = (item = {}) => {
    const sourceText = [
      item?.original_title || item?.title || item?.name || '',
      item?.original_description || item?.description || item?.short_description || '',
    ].join('\n')
    return matchesTranslationSourceDetection(sourceText, getWorkshopDetailTranslationSettings().source_detection)
  }
  const pickWorkshopTranslation = (translations = {}, sourceHash = '', language = getDefaultWorkshopDisplayTranslationLanguage()) => {
    if (!translations || typeof translations !== 'object') return {}
    const explicitLanguage = normalizeDetailTranslationLanguage(language)
    if (!explicitLanguage) return {}
    const lang = getResolvedTranslationLanguage(explicitLanguage)
    const value = getWorkshopTranslationEntry(translations, lang)
    if (value) {
      return {
        ...value,
        language: lang,
        is_stale: !!(sourceHash && value.source_hash && value.source_hash !== sourceHash),
      }
    }
    return {}
  }

  const refreshWorkshopTranslationDisplays = () => {
    workshopSearch.results = workshopSearch.results.map(item => normalizeWorkshopSearchItem(item))
    workshopSearch.transientList.items = workshopSearch.transientList.items.map(item => normalizeWorkshopSearchItem(item))
    if (workshopSearch.detailData) {
      const related = workshopSearch.detailData.related || {}
      workshopSearch.detailData = normalizeWorkshopSearchItem({
        ...workshopSearch.detailData,
        related: {
          ...related,
          dependencies: (related.dependencies || []).map(item => normalizeWorkshopSearchItem(item)),
          dependents: (related.dependents || []).map(item => normalizeWorkshopSearchItem(item)),
          same_author: (related.same_author || []).map(item => normalizeWorkshopSearchItem(item)),
          collection_children: (related.collection_children || []).map(item => normalizeWorkshopSearchItem(item)),
        },
      })
    }
  }

  watch(
    () => [
      appStore.getTranslationFeatureSettings('workshop_detail').prefer_ui_language_translation,
      appStore.getTranslationFeatureSettings('workshop_detail').target_language,
      appStore.settings.language,
    ],
    ([enabled]) => {
      const current = normalizeDetailTranslationLanguage(workshopSearch.detailTranslationLanguage)
      if (enabled === false && current === 'follow_ui') {
        setWorkshopDetailTranslationLanguage('')
      } else if (enabled !== false && !current) {
        setWorkshopDetailTranslationLanguage('follow_ui')
      }
      refreshWorkshopTranslationDisplays()
    }
  )

  const normalizeWorkshopSearchItem = (item = {}) => {
    const rawTags = Array.isArray(item.tags)
      ? item.tags.map(tag => String(tag || '').trim()).filter(Boolean)
      : []
    const versionTags = normalizeVersionTags(rawTags)
    const gameVersions = normalizeVersionTags([
      ...(Array.isArray(item.game_versions) ? item.game_versions : []),
      ...versionTags,
    ])
    const profileName = String(item.author_profile?.name || '').trim()
    const rawAuthor = Array.isArray(item.author)
      ? item.author.filter(Boolean).join(' / ')
      : String(item.author || '').trim()
    const author = profileName || rawAuthor
    const workshopId = String(item.workshop_id || '').trim()
    const itemType = resolveWorkshopItemType(item)
    const stats = normalizeWorkshopStats(item)
    const translations = item.translations && typeof item.translations === 'object' ? item.translations : {}
    const sourceHash = String(item.translation_source_hash || '').trim()
    const preferredTranslation = pickWorkshopTranslation(translations, sourceHash)
    const rawTitle = String(item.original_title || item.title || item.name || '').trim()
    const rawDescription = String(item.original_description || item.description || item.short_description || '').trim()
    // 翻译只生成展示字段，原文字段保持稳定；详情页、缓存刷新和过期判断仍依赖原文。
    // 列表显示使用默认翻译设置，不能复用详情页手动“原文/译文”切换状态。
    const displayTitle = String(preferredTranslation.title || rawTitle).trim()
    const displayDescription = String(preferredTranslation.description || rawDescription || item.short_description || '').trim()
    const children = Array.isArray(item.children)
      ? [...item.children]
          .filter(child => child && child.workshop_id)
          .sort((left, right) => Number(left.sort_order || 0) - Number(right.sort_order || 0))
      : []
    const normalizedItem = {
      ...item,
      workshop_id: workshopId,
      title: rawTitle,
      name: String(item.name || rawTitle || '未知模组').trim(),
      original_title: rawTitle,
      package_id: String(item.package_id || '').trim(),
      author,
      author_steam_id: String(item.author_steam_id || '').trim(),
      author_label: author || String(item.author_steam_id || '').trim(),
      author_profile: item.author_profile || null,
      short_description: String(item.short_description || '').trim(),
      description: rawDescription,
      original_description: rawDescription,
      display_title: displayTitle,
      display_description: displayDescription,
      shows_translated_title: !!(preferredTranslation.title && displayTitle && rawTitle && displayTitle !== rawTitle),
      preview_url: String(item.preview_url || '').trim(),
      game_versions: gameVersions,
      tags: rawTags,
      children,
      screenshots: Array.isArray(item.screenshots) ? item.screenshots : [],
      stats,
      kv_tags: Array.isArray(item.kv_tags) ? item.kv_tags : [],
      status: item.status && typeof item.status === 'object' ? item.status : {},
      item_type: itemType,
      translations,
      translation_source_hash: sourceHash,
      current_translation_language: String(preferredTranslation.language || '').trim(),
      translation_is_stale: !!preferredTranslation.is_stale,
      time_created: Number(item.time_created || 0),
      time_updated: Number(item.time_updated || 0),
      source: String(item.source || '').trim(),
    }
    normalizedItem.related = buildUnifiedWorkshopRelations(normalizedItem, workshopId)
    return normalizedItem
  }

  const mergeWorkshopSearchResults = (currentItems = [], nextItems = []) => {
    const seenIds = new Set()
    return [...currentItems, ...nextItems].filter(item => {
      const workshopId = String(item?.workshop_id || '').trim()
      if (!workshopId || seenIds.has(workshopId)) return false
      seenIds.add(workshopId)
      return true
    })
  }

  const findWorkshopListItem = (workshopId) => {
    const normalizedId = String(workshopId || '').trim()
    if (!normalizedId) return null
    const related = workshopSearch.detailData?.related || {}
    return [
      ...(workshopSearch.transientList.active ? workshopSearch.transientList.items : []),
      ...workshopSearch.results,
      ...(related.dependencies || []),
      ...(related.dependents || []),
      ...(related.same_author || []),
      ...(related.collection_children || []),
    ].find(item => item.workshop_id === normalizedId) || null
  }

  const mergeWorkshopDetailData = (nextData = {}) => {
    const current = workshopSearch.detailData || {}
    const normalized = normalizeWorkshopSearchItem({
      ...current,
      ...nextData,
      related: {
        ...(current.related || {}),
        ...(nextData.related || {}),
      },
    })
    workshopSearch.detailData = normalized
    // 详情翻译接口只返回当前详情对象；列表项是独立旧对象，必须同步补丁，否则左侧仍显示原文。
    workshopSearch.results = mergeWorkshopItemIntoList(workshopSearch.results, normalized)
    workshopSearch.transientList.items = mergeWorkshopItemIntoList(workshopSearch.transientList.items, normalized)
    for (const key of ['dependencies', 'dependents', 'same_author', 'collection_children']) {
      if (Array.isArray(workshopSearch.detailData.related?.[key])) {
        workshopSearch.detailData.related[key] = mergeWorkshopItemIntoList(workshopSearch.detailData.related[key], normalized)
      }
    }
    return normalized
  }

  const applyWorkshopRelatedItems = (key, responseData = {}) => {
    const items = (responseData.items || []).map(normalizeWorkshopSearchItem)
    const current = workshopSearch.detailData || {}
    const relationKey = key === 'dependencies' && responseData.source === 'steam_collection_children'
      ? 'collection_children'
      : key
    const related = {
      ...(current.related || {}),
      [relationKey]: mergeWorkshopSearchResults([], items),
    }
    workshopSearch.detailData = normalizeWorkshopSearchItem({ ...current, related })
    const total = Number(responseData.total || items.length || 0)
    workshopSearch.relatedMeta[key] = {
      total,
      hasMore: total > items.length,
    }
    return items
  }

  const buildOnlineRelationFilters = () => ({
    language: workshopSearch.language || appStore.settings.language || '',
    return_vote_data: true,
    // 详情页三路关联会在同一批结果收齐后统一补作者信息，避免每路请求都查一次作者。
    skip_author_profiles: true,
  })

  const getWorkshopRelationLabel = (kind) => ({
    dependencies: '依赖项目',
    dependents: '生态关联',
    same_author: '同作者作品',
  }[kind] || '')

  const getWorkshopTransientListTitle = (kind, sourceItem = {}) => {
    const kindLabel = getWorkshopRelationLabel(kind)
    if (!kindLabel) return ''
    if (kind === 'same_author') {
      const authorName = String(
        sourceItem.author || sourceItem.author_profile?.name || workshopSearch.detailData?.author || workshopSearch.detailData?.author_profile?.name || ''
      ).trim()
      return `${kindLabel}: ${authorName || '未知作者'}`
    }
    const title = String(sourceItem.title || sourceItem.name || workshopSearch.detailData?.title || sourceItem.workshop_id || workshopSearch.selectedId || '').trim()
    return `${kindLabel}: ${title}`
  }

  const mergeAuthorProfilesIntoWorkshopItems = (items = [], authorMap = {}) => (
    items.map(item => {
      const authorId = String(item?.author_steam_id || '').trim()
      const profile = authorMap[authorId]
      if (!profile) return item
      return {
        ...item,
        author_profile: profile,
        author: item.author || profile.name || '',
      }
    })
  )

  const fetchWorkshopAuthorProfilesForItems = async (items = []) => {
    // 作者资料接口需要 API Key；普通模式只展示外置库作者名，不做在线作者补全。
    if (!window.pywebview || !workshopSearch.isEnhancedMode) return {}
    const authorIds = [...new Set(
      items
        .map(item => String(item?.author_steam_id || '').trim())
        .filter(Boolean)
    )]
    if (!authorIds.length) return {}
    const res = await window.pywebview.api.workshop_get_author_profiles(authorIds)
    return checkResult(res, '获取作者信息', false, { silent: true }) ? (res.data || {}) : {}
  }

  const syncWorkshopRelatedAuthorProfiles = async (workshopId) => {
    const current = workshopSearch.detailData || {}
    const related = current.related || {}
    const allItems = [
      ...(related.dependencies || []),
      ...(related.dependents || []),
      ...(related.same_author || []),
      ...(related.collection_children || []),
    ]
    const authorMap = await fetchWorkshopAuthorProfilesForItems(allItems)
    if (workshopSearch.selectedId !== workshopId || Object.keys(authorMap).length === 0) return
    workshopSearch.detailData = normalizeWorkshopSearchItem({
      ...current,
      related: {
        ...related,
        dependencies: mergeAuthorProfilesIntoWorkshopItems(related.dependencies || [], authorMap),
        dependents: mergeAuthorProfilesIntoWorkshopItems(related.dependents || [], authorMap),
        same_author: mergeAuthorProfilesIntoWorkshopItems(related.same_author || [], authorMap),
        collection_children: mergeAuthorProfilesIntoWorkshopItems(related.collection_children || [], authorMap),
      },
    })
  }

  const fetchWorkshopRelatedData = async (workshopId) => {
    if (!window.pywebview) return
    const currentDetail = workshopSearch.detailData || {}
    const isEnhancedMode = workshopSearch.isEnhancedMode
    // 两种模式共用前端展示结构，但请求源严格分离：
    // 普通模式只走外置缓存库；增强模式走 Steam Web API 的 QueryFiles/GetDetails/GetUserFiles。
    const relationJobs = [
      {
        key: 'dependencies',
        label: currentDetail.item_type === 'collection' ? '合集子项' : getWorkshopRelationLabel('dependencies'),
        run: () => isEnhancedMode
          ? window.pywebview.api.workshop_get_dependencies_enhanced(workshopId, currentDetail)
          : window.pywebview.api.workshop_get_dependencies(workshopId),
      },
      {
        key: 'dependents',
        label: getWorkshopRelationLabel('dependents'),
        run: () => isEnhancedMode
          ? window.pywebview.api.workshop_search_dependents_enhanced(workshopId, '*', 20, buildOnlineRelationFilters())
          : window.pywebview.api.workshop_search_dependents(workshopId, 1, 20),
      },
      {
        key: 'same_author',
        label: getWorkshopRelationLabel('same_author'),
        run: () => isEnhancedMode
          ? window.pywebview.api.workshop_get_same_author_enhanced(workshopId, currentDetail.author_steam_id || '', 1, 20, buildOnlineRelationFilters())
          : window.pywebview.api.workshop_get_same_author(workshopId, 1, 20),
      },
    ]

    relationJobs.forEach(job => {
      workshopSearch.relatedLoading[job.key] = true
      workshopSearch.relatedErrors[job.key] = ''
    })

    await Promise.all(relationJobs.map(async (job) => {
      try {
        const res = await job.run()
        if (workshopSearch.selectedId !== workshopId) return
        if (checkResult(res, `获取${job.label}`, false, { silent: true })) {
          applyWorkshopRelatedItems(job.key, res.data || {})
        } else {
          workshopSearch.relatedErrors[job.key] = toUserMessage(res?.message, `${job.label}加载失败。请检查网络连接、Steam 服务状态或稍后重试。`)
        }
      } catch (error) {
        if (workshopSearch.selectedId === workshopId) {
          console.warn(`获取${job.label}失败:`, error)
          workshopSearch.relatedErrors[job.key] = toUserMessage(error?.message || error, `${job.label}加载失败。请检查网络连接、Steam 服务状态或稍后重试。`)
        }
      } finally {
        if (workshopSearch.selectedId === workshopId) {
          workshopSearch.relatedLoading[job.key] = false
        }
      }
    }))
    if (isEnhancedMode) {
      await syncWorkshopRelatedAuthorProfiles(workshopId)
    } else {
      const current = workshopSearch.detailData || {}
      const related = current.related || {}
      await preheatNormalWorkshopPublicDetails([
        current,
        ...(related.dependencies || []),
        ...(related.dependents || []),
        ...(related.same_author || []),
        ...(related.collection_children || []),
      ])
    }
  }

  const syncWorkshopSearchSort = (isEnhancedMode) => {
    const enhancedSorts = new Set(['relevance', 'popular', 'latest', 'created', 'subscriptions', 'votes_up', 'rating'])
    const normalSorts = new Set(['latest', 'subscriptions', 'name', 'author'])
    if (isEnhancedMode) {
      const hasText = hasWorkshopSearchText(workshopSearch.queryTokens)
      if (!enhancedSorts.has(workshopSearch.sort) || (workshopSearch.sort === 'relevance' && !hasText)) workshopSearch.sort = hasText ? 'relevance' : 'popular'
    }
    if (!isEnhancedMode && !normalSorts.has(workshopSearch.sort)) workshopSearch.sort = 'latest'
  }

  const applyWorkshopSearchMode = (enabled) => {
    const isEnhancedMode = !!enabled
    const changed = workshopSearch.isEnhancedMode !== isEnhancedMode
    workshopSearch.isEnhancedMode = isEnhancedMode
    syncWorkshopSearchSort(isEnhancedMode)
    workshopSearch.isModeReady = true
    return changed
  }

  // 排序默认只跟随“是否存在文本搜索”的状态变化：
  // 无文本进入有文本时切到最相关；有文本清空时切到最热门；其它时候保留用户手动排序。
  watch(
    () => hasWorkshopSearchText(workshopSearch.queryTokens),
    (hasText, hadText) => {
      if (!workshopSearch.isEnhancedMode || hasText === hadText) return
      workshopSearch.sort = hasText ? 'relevance' : 'popular'
    }
  )

  watch(
    () => hasWorkshopSearchText(collections.searchTokens),
    (hasText, hadText) => {
      if (hasText === hadText) return
      collections.searchSort = hasText ? 'relevance' : 'popular'
    }
  )

  const resetWorkshopSearchResults = () => {
    workshopSearch.page = 1
    workshopSearch.cursor = '*'
    workshopSearch.nextCursor = ''
    workshopSearch.hasMore = true
    workshopSearch.results = []
    workshopSearch.total = 0
    workshopSearch.selectedId = null
    workshopSearch.detailData = null
    workshopSearch.detailTranslationLanguage = getInitialWorkshopDetailTranslationLanguage()
    closeWorkshopTransientList()
  }

  const resetWorkshopRelatedState = () => {
    workshopSearch.relatedLoading = { dependencies: false, dependents: false, same_author: false }
    workshopSearch.relatedErrors = { dependencies: '', dependents: '', same_author: '' }
    workshopSearch.relatedMeta = {
      dependencies: { total: 0, hasMore: false },
      dependents: { total: 0, hasMore: false },
      same_author: { total: 0, hasMore: false },
    }
  }

  const closeWorkshopTransientList = () => {
    Object.assign(workshopSearch.transientList, {
      active: false,
      kind: '',
      title: '',
      sourceId: '',
      authorSteamId: '',
      items: [],
      total: 0,
      cursor: '*',
      nextCursor: '',
      hasMore: false,
      page: 1,
      isLoading: false,
      isLoadMore: false,
    })
  }

  // 搜索缓存工坊数据库 (支持重置或追加)
  const doWorkshopSearch = async (queryStr = '', isAppend = false) => {
    if (!window.pywebview) return
    if (!workshopSearch.isModeReady && !(await ensureWorkshopSearchReady())) return
    // 防御性拦截
    if (workshopSearch.isLoading || workshopSearch.isLoadMore) return
    if (isAppend && !workshopSearch.hasMore) return
    // 状态设置
    if (isAppend) {
      workshopSearch.isLoadMore = true
      if (!workshopSearch.isEnhancedMode) {
        workshopSearch.page += 1
      }
    } else {
      workshopSearch.isLoading = true
      workshopSearch.page = 1
      workshopSearch.cursor = '*'
      workshopSearch.nextCursor = ''
      workshopSearch.results = [] // 清空旧数据
    }
    const compiledTokens = compileWorkshopQueryTokens()
    const normalizedQuery = queryStr || compiledTokens.query
    workshopSearch.query = normalizedQuery
    workshopSearch.hasSearched = true
    try {
      const isEnhancedMode = workshopSearch.isEnhancedMode
      if (isEnhancedMode) {
        await loadSteamLanguageOptions()
      }
      const filters = buildWorkshopSearchFilters(compiledTokens)
      // 主搜索的请求层分界：普通模式不读 API Key，只查缓存库；增强模式才调用 QueryFiles。
      const request = isEnhancedMode
        ? {
            api: 'workshop_search_enhanced',
            args: [normalizedQuery, isAppend ? workshopSearch.nextCursor || workshopSearch.cursor || '*' : '*', 100, filters.sort, filters],
          }
        : {
            api: 'workshop_search',
            args: [normalizedQuery, workshopSearch.page, filters],
          }
      const res = isEnhancedMode
        ? await window.pywebview.api.workshop_search_enhanced(...request.args)
        : await window.pywebview.api.workshop_search(...request.args)
      if (checkResult(res, '工坊检索')) {
        const newItems = (res.data.items || []).map(normalizeWorkshopSearchItem)
        if (isAppend) {
          workshopSearch.results = mergeWorkshopSearchResults(workshopSearch.results, newItems)
        } else {
          workshopSearch.results = mergeWorkshopSearchResults([], newItems)
          workshopSearch.total = res.data.total
        }
        if (isEnhancedMode) {
          workshopSearch.cursor = String(res.data.cursor || workshopSearch.cursor || '*')
          workshopSearch.nextCursor = String(res.data.next_cursor || '')
          workshopSearch.hasMore = !!res.data.has_more
        } else {
          workshopSearch.hasMore = workshopSearch.results.length < res.data.total
        }
        logWorkshopSearchDebug({
          isEnhancedMode,
          isAppend,
          request,
          response: res,
          items: newItems,
        })
      } else {
        logWorkshopSearchDebug({
          isEnhancedMode,
          isAppend,
          request,
          response: res,
          items: [],
        })
      }
    } finally {
      workshopSearch.isLoading = false
      workshopSearch.isLoadMore = false
    }
  }

  const setWorkshopSearchMode = async (enabled, options = {}) => {
    const isEnhancedMode = !!enabled
    if (workshopSearch.isModeReady && workshopSearch.isEnhancedMode === isEnhancedMode) return true
    // 增强模式依赖用户本地保存的 Key，没有 Key 时直接阻止切换，避免进入空状态。
    if (isEnhancedMode && !isEnhancedWorkshopSearchEnabled()) {
      toast.warning('请先在设置中启用工坊增强信息并填写 Steam Web API Key')
      return false
    }
    if (!options.auto) workshopSearchModeTouched.value = true
    applyWorkshopSearchMode(isEnhancedMode)
    resetWorkshopSearchResults()
    await doWorkshopSearch('', false)
    return true
  }

  const syncWorkshopSearchModeFromSettings = async (options = {}) => {
    // 设置未从后端注入前，不把默认空 Key 判定为普通模式；否则首屏会先闪出“最近更新”。
    if (!appStore.settingsReady) return false
    const wasReady = workshopSearch.isModeReady
    const shouldRefresh = !!options.refresh || (wasReady && workshopSearch.hasSearched)
    const preferredEnhanced = getPreferredWorkshopSearchEnhanced()
    const nextEnhanced = workshopSearchModeTouched.value && !workshopSearch.isEnhancedMode
      ? false
      : preferredEnhanced
    const changed = applyWorkshopSearchMode(nextEnhanced)
    if (changed) resetWorkshopSearchResults()
    if (changed && shouldRefresh) await doWorkshopSearch('', false)
    return true
  }

  const ensureWorkshopSearchReady = async (options = {}) => {
    if (workshopSearch.isModeReady) return true
    if (appStore.settingsReady) return await syncWorkshopSearchModeFromSettings(options)
    // 工坊页可能早于后端初始设置渲染；这里等待设置到达，避免抢跑到普通模式。
    if (!workshopSearchReadyPromise) {
      workshopSearchReadyPromise = new Promise(resolve => {
        const stop = watch(
          () => !!appStore.settingsReady,
          async (ready) => {
            if (!ready) return
            stop()
            workshopSearchReadyPromise = null
            resolve(await syncWorkshopSearchModeFromSettings(options))
          },
          { immediate: true }
        )
      })
    }
    return await workshopSearchReadyPromise
  }

  watch(
    () => [
      !!appStore.settingsReady,
      !!appStore.settings?.enable_steam_enhanced_api,
      String(appStore.settings?.steam_web_api_key || '').trim(),
      !!appStore.settings?._secret_status?.['steam.web_api_key']?.has_value,
    ],
    () => { void syncWorkshopSearchModeFromSettings() },
    { immediate: true }
  )

  const loadSteamLanguageOptions = async () => {
    if (!window.pywebview || workshopSearch.isLanguageOptionsLoaded) return
    const res = await window.pywebview.api.workshop_get_language_options()
    if (checkResult(res, '获取 Steam 语言列表')) {
      workshopSearch.languageOptions = Array.isArray(res.data) && res.data.length ? res.data : workshopSearch.languageOptions
      workshopSearch.isLanguageOptionsLoaded = true
    }
  }

  const loadTranslationProviders = async () => {
    return appStore.ensureTranslationProviders()
  }

  const loadWorkshopDlcOptions = async () => {
    if (!window.pywebview || workshopSearch.isDlcOptionsLoaded) return
    const res = await window.pywebview.api.workshop_get_dlc_options()
    if (checkResult(res, '获取 DLC 选项')) {
      workshopSearch.dlcOptions = Array.isArray(res.data) ? res.data : []
      workshopSearch.isDlcOptionsLoaded = true
    }
  }

  const refreshWorkshopDetailTranslation = () => {
    if (!workshopSearch.detailData) return null
    workshopSearch.detailData = normalizeWorkshopSearchItem({ ...workshopSearch.detailData })
    return workshopSearch.detailData
  }

  const setWorkshopDetailTranslationLanguage = (language = 'follow_ui') => {
    workshopSearch.detailTranslationLanguage = normalizeDetailTranslationLanguage(language)
    return refreshWorkshopDetailTranslation()
  }

  const translateWorkshopDetail = async ({ language = '', displayLanguage = undefined, force = false } = {}) => {
    const requestDetail = workshopSearch.detailData ? { ...workshopSearch.detailData } : null
    const requestWorkshopId = String(requestDetail?.workshop_id || '').trim()
    if (!window.pywebview || !requestWorkshopId || workshopSearch.translatingByWorkshopId[requestWorkshopId]) return null
    const targetLanguage = getResolvedTranslationLanguage(language || getDefaultTranslationSelection())
    if (!targetLanguage) return null
    const provider = normalizeTranslationLanguage(getWorkshopDetailTranslationSettings().provider || 'ai.default')
    workshopSearch.translatingByWorkshopId[requestWorkshopId] = true
    workshopSearch.isTranslating = true
    try {
      const res = await window.pywebview.api.workshop_translate_detail(
        requestWorkshopId,
        targetLanguage,
        requestDetail,
        !!force,
        provider,
      )
      if (!checkResult(res, '翻译工坊说明')) return null
      const payload = res.data || {}
      const responseWorkshopId = String(payload.workshop_id || requestWorkshopId).trim()
      if (responseWorkshopId !== requestWorkshopId) return null
      const patch = {
        workshop_id: requestWorkshopId,
        translations: payload.translations || {
          ...(requestDetail.translations || {}),
          [targetLanguage]: payload.translation,
        },
        translation_source_hash: payload.source_hash || requestDetail.translation_source_hash || '',
      }
      if (workshopSearch.selectedId !== requestWorkshopId) {
        return mergeWorkshopPatchIntoLoadedLists(patch)
      }
      workshopSearch.detailTranslationLanguage = normalizeDetailTranslationLanguage(displayLanguage === undefined ? language || getDefaultTranslationSelection() : displayLanguage)
      const normalized = mergeWorkshopDetailData(patch)
      toast.success(force ? '已重新翻译说明' : '已翻译说明', { timeout: 1500 })
      return normalized
    } finally {
      delete workshopSearch.translatingByWorkshopId[requestWorkshopId]
      workshopSearch.isTranslating = !!workshopSearch.translatingByWorkshopId[String(workshopSearch.selectedId || '').trim()]
    }
  }

  const clearWorkshopDetailTranslation = async ({ language = '', displayLanguage = undefined } = {}) => {
    const requestDetail = workshopSearch.detailData ? { ...workshopSearch.detailData } : null
    const requestWorkshopId = String(requestDetail?.workshop_id || '').trim()
    if (!window.pywebview || !requestWorkshopId) return null
    const targetLanguage = getResolvedTranslationLanguage(language || workshopSearch.detailTranslationLanguage)
    if (!targetLanguage) return null
    const res = await window.pywebview.api.workshop_clear_detail_translation(
      requestWorkshopId,
      targetLanguage,
    )
    if (!checkResult(res, '清理工坊翻译')) return null
    const payload = res.data || {}
    const responseWorkshopId = String(payload.workshop_id || requestWorkshopId).trim()
    if (responseWorkshopId !== requestWorkshopId) return null
    const patch = {
      workshop_id: requestWorkshopId,
      translations: payload.translations || {},
    }
    if (workshopSearch.selectedId !== requestWorkshopId) {
      return mergeWorkshopPatchIntoLoadedLists(patch)
    }
    const normalized = mergeWorkshopDetailData(patch)
    workshopSearch.detailTranslationLanguage = normalizeDetailTranslationLanguage(displayLanguage === undefined ? language || workshopSearch.detailTranslationLanguage : displayLanguage)
    if (!getWorkshopTranslationEntry(normalized.translations, targetLanguage)) {
      workshopSearch.detailTranslationLanguage = ''
    }
    toast.success('已清理翻译', { timeout: 1500 })
    return normalized
  }

  const toggleWorkshopDetailTranslation = async () => {
    const current = workshopSearch.detailData
    if (!current) return null
    const currentSelection = normalizeDetailTranslationLanguage(workshopSearch.detailTranslationLanguage)
    const currentLanguage = getResolvedTranslationLanguage(currentSelection)
    if (currentSelection && getWorkshopTranslationEntry(current.translations, currentLanguage)) {
      return setWorkshopDetailTranslationLanguage('')
    }
    const nextSelection = getDefaultTranslationSelection()
    const targetLanguage = getResolvedTranslationLanguage(nextSelection)
    if (getWorkshopTranslationEntry(current.translations, targetLanguage)) {
      return setWorkshopDetailTranslationLanguage(nextSelection)
    }
    return translateWorkshopDetail({ language: targetLanguage, displayLanguage: nextSelection })
  }

  // 获取云端详情 (包含网页抓取截图)
  // isNavigate: 是否是通过点击“推荐卡片”触发的内部跳转
  const fetchWorkshopDetails = async (workshop_id, isNavigate = false) => {
    if (!window.pywebview || workshopSearch.selectedId === workshop_id) return
    // 如果是点击左侧主列表，清空历史记录，重新开始
    if (!isNavigate) {
      workshopSearch.historyStack = []
    } else if (workshopSearch.selectedId) {
      // 如果是内部跳转，将当前 ID 压入栈中
      workshopSearch.historyStack.push(workshopSearch.selectedId)
    }
    workshopSearch.selectedId = workshop_id
    workshopSearch.detailTranslationLanguage = getInitialWorkshopDetailTranslationLanguage()
    workshopSearch.isTranslating = !!workshopSearch.translatingByWorkshopId[String(workshop_id || '').trim()]
    workshopSearch.isDetailLoading = true
    resetWorkshopRelatedState()
    const currentDetail = findWorkshopListItem(workshop_id)
    workshopSearch.detailData = normalizeWorkshopSearchItem(currentDetail || { workshop_id, title: String(workshop_id || '') })
    try {
      // 先加载当前项本体并立即展示，再并发加载依赖项目、生态关联、同作者作品。
      const res = workshopSearch.isEnhancedMode
        ? await window.pywebview.api.workshop_get_enhanced_details(workshop_id, currentDetail || null)
        : await window.pywebview.api.workshop_get_details(workshop_id)
      if (workshopSearch.selectedId !== workshop_id) return
      if (checkResult(res, '获取云端详情')) {
        mergeWorkshopDetailData(res.data)
        const displayLanguage = normalizeDetailTranslationLanguage(workshopSearch.detailTranslationLanguage)
        const targetLanguage = getResolvedTranslationLanguage(displayLanguage)
        if (
          getWorkshopDetailTranslationSettings().auto_translate_missing
          && displayLanguage
          && targetLanguage
          && !shouldSkipWorkshopAutoTranslate(workshopSearch.detailData)
          && !getWorkshopTranslationEntry(workshopSearch.detailData?.translations, targetLanguage)
        ) {
          void translateWorkshopDetail({ language: targetLanguage, displayLanguage })
        }
      }
    } finally {
      if (workshopSearch.selectedId === workshop_id) {
        workshopSearch.isDetailLoading = false
      }
    }
    void fetchWorkshopRelatedData(workshop_id)
  }
  const openWorkshopTransientList = async (kind, sourceItem = {}) => {
    if (!window.pywebview) {
      return false
    }
    const kindLabel = getWorkshopRelationLabel(kind)
    if (!kindLabel) return false
    const sourceId = String(sourceItem.workshop_id || workshopSearch.selectedId || '').trim()
    if (!sourceId) return false
    Object.assign(workshopSearch.transientList, {
      active: true,
      kind,
      title: getWorkshopTransientListTitle(kind, { ...sourceItem, workshop_id: sourceId }),
      sourceId,
      authorSteamId: String(sourceItem.author_steam_id || workshopSearch.detailData?.author_steam_id || '').trim(),
      items: [],
      total: 0,
      cursor: '*',
      nextCursor: '',
      hasMore: true,
      page: 1,
      isLoading: false,
      isLoadMore: false,
    })
    return await loadWorkshopTransientList(false)
  }

  const loadWorkshopTransientList = async (isAppend = false) => {
    const state = workshopSearch.transientList
    if (!window.pywebview || !state.active || state.isLoading || state.isLoadMore) return false
    if (isAppend && !state.hasMore) return false
    if (isAppend) {
      state.isLoadMore = true
    } else {
      state.isLoading = true
      state.items = []
      state.page = 1
      state.cursor = '*'
      state.nextCursor = ''
      state.hasMore = true
    }
    try {
      const isEnhancedMode = workshopSearch.isEnhancedMode
      const kindLabel = getWorkshopRelationLabel(state.kind)
      let res = null
      if (state.kind === 'same_author') {
        res = isEnhancedMode
          ? await window.pywebview.api.workshop_get_same_author_enhanced(state.sourceId, state.authorSteamId, isAppend ? state.page + 1 : 1, 100, buildOnlineRelationFilters())
          : await window.pywebview.api.workshop_get_same_author(state.sourceId, isAppend ? state.page + 1 : 1, 100)
      } else if (state.kind === 'dependents') {
        res = isEnhancedMode
          ? await window.pywebview.api.workshop_search_dependents_enhanced(state.sourceId, isAppend ? state.nextCursor || state.cursor || '*' : '*', 100, buildOnlineRelationFilters())
          : await window.pywebview.api.workshop_search_dependents(state.sourceId, isAppend ? state.page + 1 : 1, 100)
      } else {
        return false
      }
      if (checkResult(res, `加载${kindLabel}`)) {
        const items = (res.data.items || []).map(normalizeWorkshopSearchItem)
        let nextItems = isAppend ? mergeWorkshopSearchResults(state.items, items) : mergeWorkshopSearchResults([], items)
        if (isEnhancedMode) {
          const authorMap = await fetchWorkshopAuthorProfilesForItems(nextItems)
          nextItems = mergeAuthorProfilesIntoWorkshopItems(nextItems, authorMap)
        }
        state.items = nextItems
        state.total = Number(res.data.total || state.items.length || 0)
        if (state.kind === 'same_author' || !isEnhancedMode) {
          state.page = Number(res.data.page || (isAppend ? state.page + 1 : 1))
        } else {
          state.cursor = String(res.data.cursor || state.cursor || '*')
          state.nextCursor = String(res.data.next_cursor || '')
        }
        state.hasMore = Number(res.data.total || 0) > state.items.length
        return true
      }
    } finally {
      state.isLoading = false
      state.isLoadMore = false
    }
    return false
  }

  // 详情页后退功能
  const goBackWorkshopDetail = async () => {
    if (workshopSearch.historyStack.length === 0) return
    const prevId = workshopSearch.historyStack.pop()
    await fetchWorkshopDetails(prevId, true)
    // 抵消刚刚 push 进去的动作
    workshopSearch.historyStack.pop()
  }

  const normalizeGitTimelinePath = (value = '') => String(value || '').trim().replace(/\\/g, '/').replace(/\/+/g, '/').replace(/\/$/g, '').toLowerCase()
  const getGitTimelinePathSegments = (value = '') => normalizeGitTimelinePath(value).split('/').filter(Boolean)
  const getGitTimelineFolder = (value = '') => {
    const segments = getGitTimelinePathSegments(value)
    return segments.length ? segments[segments.length - 1] : ''
  }
  const findGithubRepoForTimelineTarget = (target) => {
    const targetMod = target && typeof target === 'object' ? target : null
    const targetPath = targetMod ? targetMod.path : target
    const targetUrls = [
      targetMod?.repo_url,
      targetMod?.repoUrl,
      targetMod?.url,
    ].map(value => normalizeUrl(value)).filter(Boolean)
    const targetSegments = getGitTimelinePathSegments(targetPath)

    return github.subscribedRepos.find(repo => {
      const repoUrl = normalizeUrl(repo?.repo_url)
      if (repoUrl && targetUrls.includes(repoUrl)) return true
      const repoFolder = getGitTimelineFolder(repo?.local_folder || (repo?.repo_name ? `_GH_${repo.repo_name}` : ''))
      return !!repoFolder && targetSegments.includes(repoFolder)
    }) || null
  }

  // 打开并加载模组变更时间线
  const openTimeline = async (workshopId, modName, is_steamcmd=false) => {
    if (!window.pywebview) return
    timeline.isOpen = true
    timeline.workshopId = workshopId
    timeline.modName = modName
    timeline.isLoading = true
    timeline.logs = []
    try {
      const res = await window.pywebview.api.workspace_get_mod_timeline(workshopId, is_steamcmd)
      if (checkResult(res, '获取模组变更时间线')) {
        timeline.logs = res.data
      }
    } finally {
      timeline.isLoading = false
    }
  }
  // 打开并加载 Git 仓库模组变更时间线
  const openTimelineGithub = async (target) => {
    if (!window.pywebview || !target) return
    let repo = findGithubRepoForTimelineTarget(target)
    if (!repo && await fetchGithubRepos()) {
      repo = findGithubRepoForTimelineTarget(target)
    }
    if (!repo) {
      toast.warning('未找到该订阅')
      return
    }
    if (!repo.repo_url) {
      toast.warning('订阅记录缺少仓库地址，无法获取时间线')
      return
    }
    timeline.isOpen = true
    timeline.workshopId = repo.repo_url
    timeline.modName = repo.repo_name
    timeline.isLoading = true
    timeline.logs = []
    try {
      const res = await window.pywebview.api.github_get_timeline(repo.repo_url)
      if (checkResult(res, '获取 Git 仓库模组时间线')) {
        timeline.logs = res.data
      }
    } finally {
      timeline.isLoading = false
    }
  }

  // 拉取 Git 仓库订阅列表，拉取所有订阅记录
  const fetchGithubRepos = async () => {
    if (!window.pywebview) return
    setupListeners()
    github.isLoading = true
    try {
      const activeRepoUrl = github.activeRepo?.repo_url || ''
      // 瞬间返回带缓存的数据
      const res = await window.pywebview.api.github_get_subscribed()
      if (checkResult(res, '获取 Git 仓库订阅')) {
        github.subscribedRepos = (res.data || []).map(repo => applyGithubRepoComputedState(repo))
        github.activeRepo = activeRepoUrl
          ? github.subscribedRepos.find(repo => repo.repo_url === activeRepoUrl) || null
          : null
        if (!github.activeRepo) {
          stopGithubTimelinePolling()
          github.repoTimelines = []
        }
        loadState.githubLoaded = true
        return true
      }
    } finally {
      github.isLoading = false
    }
    return false
  }

  // 拉取 Git 推荐来源，用于在订阅页展示可选项目。
  const fetchGithubProviderCatalog = async ({ force = false, url = '' } = {}) => {
    if (!window.pywebview) return false
    if (github.catalogLoaded && !force) return true
    github.isCatalogLoading = true
    github.catalogError = ''
    try {
      const res = await window.pywebview.api.github_get_provider_catalog(url, !!force)
      if (checkResult(res, '获取 Git 仓库推荐列表')) {
        github.recommendedRepos = Array.isArray(res.data?.items) ? res.data.items : []
        github.catalogMeta = {
          source_url: res.data?.source_url || '',
          sources: Array.isArray(res.data?.sources) ? res.data.sources : [],
          total: Number(res.data?.total || 0),
          fetched_at: Number(res.data?.fetched_at || 0),
          is_stale: !!res.data?.is_stale,
          warning: res.data?.warning || '',
        }
        github.catalogLoaded = true
        return true
      }
      github.catalogError = toUserMessage(res?.message, '获取推荐列表失败。请检查网络连接、代理设置和推荐源地址。')
    } catch (error) {
      console.warn('获取 Git 推荐列表失败:', error)
      github.catalogError = toUserMessage(error?.message || error, '获取推荐列表失败。请检查网络连接、代理设置和推荐源地址。')
      throw error
    } finally {
      github.isCatalogLoading = false
    }
    return false
  }

  // 初始化拉取本地数据库中的合集列表
  const fetchSavedCollections = async () => {
    if (!window.pywebview) return
    setupListeners()
    collections.isLoading = true
    try {
      // 假设你后端新增了获取列表的 API
      const res = await window.pywebview.api.collection_get_all()
      if (checkResult(res, '获取合集记录')) {
        collections.savedList = res.data || []
        loadState.collectionsLoaded = true
        return true
      }
    } finally {
      collections.isLoading = false
    }
    return false
  }

  // 接入(解析并保存)新合集
  const addCollection = async (inputUrl) => {
    if (!window.pywebview || !inputUrl) return false
    // 智能提取 ID
    const match = inputUrl.match(/id=(\d+)/) || inputUrl.match(/(\d+)/)
    const collId = match ? match[1] : inputUrl.trim()
    if (!/^\d+$/.test(collId)) {
      toast.error("合集 ID 或链接无效，请输入纯数字 ID，或粘贴包含 id=xxx 的 Steam 合集链接。")
      return false
    }
    if (collections.savedList.some(c => c.id === collId)) {
      toast.warning("该合集已在你的记录中。")
      return false
    }
    collections.isParsing = true
    toast.info("正在解析并接入合集数据。")
    try {
      // 调用专门的同步接口
      const res = await window.pywebview.api.collection_add(collId)
      if (checkResult(res, '解析并接入合集',true)) {
        collections.savedList.unshift(res.data)
        // 立刻自动选中
        await selectCollection(res.data)
        return true
      }
    } finally {
      collections.isParsing = false
    }
    return false
  }

  // 移除合集记录
  const removeCollection = async (collId) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.collection_remove(collId)
      if (checkResult(res, '移除合集')) {
        collections.savedList = collections.savedList.filter(c => c.id !== collId)
        if (collections.activeId === collId) {
          collections.activeId = null
          collections.activeDetails = null
          collections.activeChildren = []
        }
        toast.success("已从记录中移除该合集")
      }
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, '移除合集失败。可能是后端服务暂时不可用或本地记录无法写入，详细原因已写入系统日志。'))
    }
  }

  // 获取并展开选中合集的内部列表 (动态计算缺失状态)
  const selectCollection = async (coll) => {
    if (!window.pywebview) return
    const collId = String(coll?.id || coll?.workshop_id || '').trim()
    if (!collId) return
    collections.activeId = collId
    collections.activeDetails = { ...(coll || {}), id: collId }
    collections.activeChildren = Array.isArray(coll?.children) ? [...coll.children] : []
    collections.isChildrenLoading = true

    // 这步会立即返回数据库里的旧数据 (或者为 null)
    try {
      const res = await window.pywebview.api.lifecycle_fetch_collection(collId)
      if (res.status === 'success' && res.data) {
        collections.activeDetails = res.data.collection
        collections.activeChildren = res.data.children
        // 如果后端判定是强力缓存且不过期，取消 loading
        if (res.data.is_cache) {
          collections.isChildrenLoading = false
        }
      } else if (res.status !== 'success') {
        collections.isChildrenLoading = false
      }
    } catch (e) {
      collections.isChildrenLoading = false
      toast.error(toUserMessage(e?.message || e, '加载合集失败。可能是网络连接、Steam 服务或本地缓存暂时不可用，请稍后重试。'))
    }
    // 如果没有缓存，loading 继续保持 true，等待 EventBus 触发
  }

  const normalizeWorkshopDetail = (detail = {}) => {
    const packageId = normalizePackageId(detail.package_id || detail.package_id_raw)
    const workshopId = normalizeWorkshopId(detail.workshop_id)
    if (!packageId || !workshopId) return null
    return {
      packageId,
      workshopId,
      title: String(detail.name || packageId).trim(),
      author: Array.isArray(detail.author) ? detail.author.filter(Boolean) : [],
      url: String(detail.url || '').trim(),
      previewUrl: String(detail.preview_url || '').trim(),
      supportedVersions: Array.isArray(detail.game_versions) ? detail.game_versions.filter(Boolean) : [],
      isReplacementDerived: !!detail.is_replacement_derived,
      selectionReason: String(detail.selection_reason || '').trim(),
      candidateCount: Number(detail.candidate_count || 0),
    }
  }

  const normalizeWorkshopLookupDisplay = (payload = {}) => {
    const displayDetail = payload?.display?.selected || payload
    return normalizeWorkshopDetail(displayDetail)
  }

  const getWorkshopDetailsByPackageIdsMap = async (packageIds) => {
    if (!window.pywebview) return {}
    const normalizedPackageIds = dedupeNormalizedPackageIds(packageIds)
    if (normalizedPackageIds.length === 0) return {}
    const res = await window.pywebview.api.get_workshop_details_by_package_ids(normalizedPackageIds)
    if (checkResult(res, '根据包名获取工坊详情')) {
      return Object.fromEntries(
        Object.entries(res.data || {})
          .map(([packageId, detail]) => [normalizePackageId(packageId), normalizeWorkshopLookupDisplay(detail)])
          .filter(([packageId, detail]) => packageId && detail)
      )
    }
    return {}
  }

  const getInstallSourcesByPackageIdsMap = async (packageIds) => {
    if (!window.pywebview) return {}
    const normalizedPackageIds = dedupeNormalizedPackageIds(packageIds)
    if (normalizedPackageIds.length === 0) return {}
    const res = await window.pywebview.api.get_install_sources_by_package_ids(normalizedPackageIds)
    if (checkResult(res, '根据包名获取安装来源')) {
      return Object.fromEntries(
        Object.entries(res.data || {}).map(([packageId, payload]) => {
          const normalizedPackageId = normalizePackageId(packageId)
          return [normalizedPackageId, {
            packageId: normalizedPackageId,
            originalSources: normalizeInstallSources(payload?.original_sources, normalizedPackageId),
            replacementSources: normalizeInstallSources(payload?.replacement_sources, normalizedPackageId),
          }]
        }).filter(([packageId]) => packageId)
      )
    }
    return {}
  }

  // 根据包名获取创意工坊ID映射
  const getWorkshopIdsByPackageIdsMap = async (packageIds) => {
    const detailsMap = await getWorkshopDetailsByPackageIdsMap(packageIds)
    if (detailsMap && typeof detailsMap === 'object') {
      return Object.fromEntries(
        Object.entries(detailsMap)
          .map(([packageId, detail]) => [normalizePackageId(packageId), normalizeWorkshopId(detail?.workshopId)])
          .filter(([packageId, workshopId]) => packageId && workshopId)
      )
    }
    return {}
  }
  const resolvePackageIdsToWorkshopIds = async (packageIds) => (
    [...new Set(
      Object.values(await getWorkshopIdsByPackageIdsMap(packageIds))
        .map(normalizeWorkshopId)
        .filter(Boolean)
    )]
  )

  const modTransfer = async (path_hashs, target_store, mode) => {
    const check = await confirmStore.confirmAction(
      '确认转移',
      (`确定要将选中的模组 ${mode === 'move' ? '移动' : '复制'} 到 [${SOURCE_TYPE_MAP[target_store]}] 库吗？`+ (target_store=='workshop'?'\n注意：转移到创意工坊目录后可能会被Steam再次改变':'')),
      { type: 'info' }
    )
    if(check) {
      appStore.isLoading = true
      try {
        const res = await window.pywebview.api.workspace_transfer_mods(path_hashs, target_store, mode)
        if(checkResult(res, "库间转移")) {
          await appStore.requestModScan({ preserveListState: true, forceCoreRefresh: true })
        }
      } finally {
        appStore.isLoading = false
      }
    }
  }

  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (workshop_id, on_steam=true) => {
    if(!workshop_id) return
    const steamUrl = on_steam ? `steam://url/CommunityFilePage/${workshop_id}` : `https://steamcommunity.com/sharedfiles/filedetails/?id=${workshop_id}`
    window.open(steamUrl, '_blank')
  }

  const searchCollectionsOnline = async (queryStr = '', isAppend = false) => {
    // 合集搜索当前只提供增强模式入口；没有 Key 时不退回普通物品搜索，避免类型语义混淆。
    if (!canUseCollectionOnlineSearch()) {
      toast.warning('合集搜索需要填写 Steam Web API Key')
      return false
    }
    if (collections.isSearchLoading || collections.isSearchLoadMore) return false
    if (isAppend && !collections.searchHasMore) return false
    if (isAppend) {
      collections.isSearchLoadMore = true
    } else {
      collections.isSearchLoading = true
      collections.searchCursor = '*'
      collections.searchNextCursor = ''
      collections.searchResults = []
      collections.searchHasMore = true
    }
    const compiledTokens = compileCollectionQueryTokens()
    const normalizedQuery = String(queryStr || compiledTokens.query || '').trim()
    collections.searchQuery = normalizedQuery
    try {
      await loadSteamLanguageOptions()
      const filters = {
        language: workshopSearch.language || appStore.settings.language || '',
        return_vote_data: true,
        required_tags: compiledTokens.requiredTags,
        excluded_tags: compiledTokens.excludedTags,
        match_all_tags: String(collections.searchLogic || 'AND').toUpperCase() !== 'OR',
      }
      const collectionHasText = hasWorkshopSearchText(collections.searchTokens)
      const resolvedDays = resolveWorkshopDays(collections.searchSort, collections.searchDays, collectionHasText)
      if (resolvedDays !== undefined) filters.days = resolvedDays
      const cursor = isAppend ? collections.searchNextCursor || collections.searchCursor || '*' : '*'
      const requestSort = resolveWorkshopSort(collections.searchSort, collectionHasText)
      const res = await window.pywebview.api.workshop_search_collections_enhanced(normalizedQuery, cursor, 50, requestSort, filters)
      if (checkResult(res, '在线合集搜索')) {
        const items = (res.data.items || []).map(normalizeWorkshopSearchItem)
        collections.searchResults = isAppend ? mergeWorkshopSearchResults(collections.searchResults, items) : items
        collections.searchTotal = res.data.total || 0
        collections.searchCursor = String(res.data.cursor || collections.searchCursor || '*')
        collections.searchNextCursor = String(res.data.next_cursor || '')
        collections.searchHasMore = !!res.data.has_more
        return true
      }
    } finally {
      collections.isSearchLoading = false
      collections.isSearchLoadMore = false
    }
    return false
  }

  const activateCollectionSearchView = async () => {
    if (!canUseCollectionOnlineSearch()) {
      toast.warning('合集搜索需要填写 Steam Web API Key')
      return false
    }
    collections.activeView = 'search'
    if (collections.searchResults.length || collections.isSearchLoading || collections.isSearchLoadMore) return true

    collections.searchTokens = []
    collections.searchLogic = 'AND'
    collections.searchSort = 'popular'
    collections.searchDays = 7
    return searchCollectionsOnline('', false)
  }


  return {
    // 库矩阵状态
    librariesMods, isFetching, librariesSize, activeChildrenWithStatus,
    workshopSearch, timeline, subscribedWorkshopIds, installedAllIds, missingWorkshopIds, getModStatus, modTransfer,
    matrixFocusTarget, matrixFilterTarget, workspaceTargetTab, getMatrixSameItems, getMatrixConflictItems, jumpToMatrixItem,
    applyStartupInventorySummary, formatStartupWorkshopChangeNames, showStartupWorkshopChangesPrompt, openWorkspaceForStartupChanges,
    startupInventoryDialog, closeStartupInventoryDialog, runStartupInventoryDialogAction, openStartupInventoryDialogDetails,
    // 库数据与工坊时间线
    fetchLibrariesMods, refreshLifecycleUpdateStates, doWorkshopSearch, fetchWorkshopDetails, loadSteamLanguageOptions, loadTranslationProviders, loadWorkshopDlcOptions, openTimeline, openTimelineGithub, setupListeners, setWorkshopSearchMode, syncWorkshopSearchModeFromSettings, ensureWorkshopSearchReady,
    openWorkshopTransientList, loadWorkshopTransientList, closeWorkshopTransientList,
    // GitHub 数据
    github, fetchGithubRepos, fetchGithubProviderCatalog, fetchGithubTimeline, startGithubTimelinePolling, stopGithubTimelinePolling, selectGithubRepo, clearActiveGithubRepo,
    // 懒加载与来源映射
    getGithubOnlineVersion, getGithubRepoStatus, githubRepoNeedsUpdate, ensureLibrariesLoaded, ensureGithubLoaded, ensureCollectionsLoaded, ensureWorkspaceTabLoaded, refreshLoadedData, openSteamWorkshopUrl, getWorkshopDetailsByPackageIdsMap, getInstallSourcesByPackageIdsMap, getWorkshopIdsByPackageIdsMap, resolvePackageIdsToWorkshopIds, goBackWorkshopDetail,
    getDefaultTranslationLanguage, getDefaultTranslationSelection, getResolvedTranslationLanguage, getTranslationLanguageLabel, getWorkshopTranslationEntry, shouldSkipWorkshopAutoTranslate, setWorkshopDetailTranslationLanguage, translateWorkshopDetail, clearWorkshopDetailTranslation, toggleWorkshopDetailTranslation,
    // 合集
    collections, fetchSavedCollections, addCollection, removeCollection, selectCollection, searchCollectionsOnline, activateCollectionSearchView,
  }
})
