// frontend/src/stores/workspaceStore.js
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { useAppStore } from '../../app/stores/appStore'
import { checkResult, toast } from '../../shared/lib/common'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { SOURCE_TYPE_MAP } from '../../shared/lib/constants'
import {
  dedupeNormalizedPackageIds, normalizeInstallSources,
  normalizePackageId, normalizeUrl, normalizeWorkshopId,
} from '../mod/lib/modIdentity'

export const useWorkspaceStore = defineStore('workspace', () => {
  const appStore = useAppStore()
  const confirmStore = useConfirmStore()
  const listenersReady = ref(false)
  const loadState = reactive({
    librariesLoaded: false,
    githubLoaded: false,
    collectionsLoaded: false,
  })

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
  // 只要 path 不为空，且没有标记 is_missing，就算已安装
  const installedAllIds = computed(() => {
    const all = [
      ...librariesMods.workshop,
      ...librariesMods.self,
      ...librariesMods.local
    ]
    return new Set(
      all
        .filter(m => m.path && !m.is_missing && normalizeWorkshopId(m.workshop_id))
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
  // 2. 缓存工坊数据库搜索状态
  const workshopSearch = reactive({
    query: '',
    page: 1,
    cursor: '*',
    nextCursor: '',
    hasMore: true, // 是否还有下一页
    results: [],
    total: 0,
    sourceMode: 'offline',
    onlineSort: 'relevance',
    isLoading: false,       // 首次加载/搜索加载
    isLoadMore: false,      // 滚动到底部加载更多
    // --- 详情区状态 ---
    selectedId: null,
    detailData: null,
    isDetailLoading: false,
    historyStack: [],       // 记录浏览路径: [id1, id2, id3]
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
    savedList: [],        // 后端获取的已订阅合集列表
    isLoading: false,     // 整体加载状态
    isParsing: false,     // 解析新合集时的 Loading 状态
    activeId: null,       // 当前选中的合集 ID
    activeDetails: null,  // 当前选中合集的详细信息 (包含 meta)
    activeChildren: [],   // 当前选中合集内的子 Mod 列表
    isChildrenLoading: false // 子列表加载状态
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

    console.log('[Workspace] 生命周期更新状态已合并:', normalizedUpdates.length, '条记录')
  }

  const refreshLifecycleUpdateStates = async () => {
    if (!window.pywebview) return true
    const res = await window.pywebview.api.lifecycle_check_updates()
    if (checkResult(res, '检查库内模组更新状态')) {
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
      const is_workshop = librariesMods.workshop.some(m => !m.is_missing && String(m.workshop_id) === wid)
      const is_self = librariesMods.self.some(m => !m.is_missing && String(m.workshop_id) === wid)
      // 本地目录用包名比对最准，没有包名回退使用 wid
      const is_local = librariesMods.local.some(m => !m.is_missing &&
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

    // 【监听 A】: self 域在线状态静默更新
    // payload 格式: { "12345": { title: "...", time_updated: 17000000, preview_url: "..." }, ... }
    window.addEventListener('workspace-online-update', (e) => {
      const onlineMap = e.detail
      console.log("[Workspace] 收到 Steam 在线状态批量推送[self]:", Object.keys(onlineMap).length, "条记录")
      // 该事件当前只服务 self 预热，避免把 self 的在线时间误覆盖到 workshop 域。
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
      console.log("[Workspace] 收到 Git 仓库在线状态推送:", Object.keys(updatedReposMap).length, "条记录")

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
    setupListeners()
    isFetching.value = true
    try {
      // 这个 API 现在只负责去读本地 SQLite 和内存缓存，响应时间应该 < 50ms
      const res = await window.pywebview.api.workspace_get_all_domains()
      if (checkResult(res, '获取所有库数据')) {
        // 直接替换数组引用
        librariesMods.local = res.data.local || []
        librariesMods.workshop = res.data.workshop || []
        librariesMods.self = res.data.self || []

        // 渲染完毕！如果后端在此接口中发现了需要触发的在线查询，
        // 后端会自己开启线程并发 `workspace-online-update` 事件。
        await refreshLifecycleUpdateStates()
        loadState.librariesLoaded = true
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

  const normalizeWorkshopSearchItem = (item = {}) => {
    const versionTags = normalizeVersionTags(item.tags)
    const gameVersions = normalizeVersionTags([
      ...(Array.isArray(item.game_versions) ? item.game_versions : []),
      ...versionTags,
    ])
    const author = Array.isArray(item.author)
      ? item.author.filter(Boolean).join(' / ')
      : String(item.author || '').trim()
    return {
      ...item,
      workshop_id: String(item.workshop_id || '').trim(),
      title: String(item.title || item.name || '').trim(),
      name: String(item.name || item.title || '未知模组').trim(),
      package_id: String(item.package_id || '').trim(),
      author,
      author_steam_id: String(item.author_steam_id || '').trim(),
      short_description: String(item.short_description || '').trim(),
      description: String(item.description || item.short_description || '').trim(),
      preview_url: String(item.preview_url || '').trim(),
      game_versions: gameVersions,
      tags: versionTags,
      // 关联项按照 Steam 返回的顺序号稳定排序，避免同一批数据每次展开顺序抖动。
      children: Array.isArray(item.children)
        ? [...item.children]
            .filter(child => child && child.workshop_id)
            .sort((left, right) => Number(left.sort_order || 0) - Number(right.sort_order || 0))
        : [],
      screenshots: Array.isArray(item.screenshots) ? item.screenshots : [],
      subscriptions: Number(item.subscriptions || 0),
      favorited: Number(item.favorited || 0),
      time_created: Number(item.time_created || 0),
      time_updated: Number(item.time_updated || 0),
      source: String(item.source || '').trim(),
    }
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

  // 搜索缓存工坊数据库 (支持重置或追加)
  const doWorkshopSearch = async (queryStr = '', isAppend = false) => {
    if (!window.pywebview) return
    // 防御性拦截
    if (workshopSearch.isLoading || workshopSearch.isLoadMore) return
    if (isAppend && !workshopSearch.hasMore) return
    // 状态设置
    if (isAppend) {
      workshopSearch.isLoadMore = true
      if (workshopSearch.sourceMode === 'offline') {
        workshopSearch.page += 1
      }
    } else {
      workshopSearch.isLoading = true
      workshopSearch.page = 1
      workshopSearch.cursor = '*'
      workshopSearch.nextCursor = ''
      workshopSearch.results = [] // 清空旧数据
    }
    workshopSearch.query = queryStr
    try {
      const res = workshopSearch.sourceMode === 'online'
        ? await window.pywebview.api.workshop_search_online(
            queryStr,
            isAppend ? workshopSearch.nextCursor || workshopSearch.cursor || '*' : '*',
            25,
            workshopSearch.onlineSort,
          )
        : await window.pywebview.api.workshop_search(queryStr, workshopSearch.page)
      if (checkResult(res, '工坊检索')) {
        const newItems = (res.data.items || []).map(normalizeWorkshopSearchItem)
        if (isAppend) {
          workshopSearch.results = mergeWorkshopSearchResults(workshopSearch.results, newItems)
        } else {
          workshopSearch.results = mergeWorkshopSearchResults([], newItems)
          workshopSearch.total = res.data.total
        }
        if (workshopSearch.sourceMode === 'online') {
          workshopSearch.cursor = String(res.data.cursor || workshopSearch.cursor || '*')
          workshopSearch.nextCursor = String(res.data.next_cursor || '')
          workshopSearch.hasMore = !!res.data.has_more
        } else {
          workshopSearch.hasMore = workshopSearch.results.length < res.data.total
        }
      }
    } finally {
      workshopSearch.isLoading = false
      workshopSearch.isLoadMore = false
    }
  }

  const setWorkshopSearchMode = async (mode) => {
    const normalizedMode = mode === 'online' ? 'online' : 'offline'
    if (workshopSearch.sourceMode === normalizedMode) return
    // 在线模式依赖用户本地保存的 Key，没有 Key 时直接阻止切换，避免进入空状态。
    if (normalizedMode === 'online' && !String(appStore.settings.steam_web_api_key || '').trim()) {
      toast.warning('请先在设置中填写 Steam Web API Key')
      return false
    }
    workshopSearch.sourceMode = normalizedMode
    workshopSearch.page = 1
    workshopSearch.cursor = '*'
    workshopSearch.nextCursor = ''
    workshopSearch.hasMore = true
    workshopSearch.results = []
    workshopSearch.total = 0
    workshopSearch.selectedId = null
    workshopSearch.detailData = null
    await doWorkshopSearch(workshopSearch.query || '', false)
    return true
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
    workshopSearch.isDetailLoading = true
    try {
      const res = await window.pywebview.api.workshop_get_details(workshop_id)
      if (checkResult(res, '获取云端详情')) {
        workshopSearch.detailData = normalizeWorkshopSearchItem(res.data)
      }
    } finally {
      workshopSearch.isDetailLoading = false
    }
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
      github.catalogError = res?.message || '获取推荐列表失败'
    } catch (error) {
      github.catalogError = String(error?.message || error || '获取推荐列表失败')
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
      toast.error("无效的合集 ID 或链接，请输入纯数字或包含 id=xxx 的链接")
      return false
    }
    if (collections.savedList.some(c => c.id === collId)) {
      toast.warning("该合集已在你的记录中！")
      return false
    }
    collections.isParsing = true
    toast.info("正在解析并接入合集数据...")
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
      toast.error(`移除失败: ${e.message}`)
    }
  }

  // 获取并展开选中合集的内部列表 (动态计算缺失状态)
  const selectCollection = async (coll) => {
    if (!window.pywebview) return
    collections.activeId = coll.id
    collections.activeDetails = coll || null
    collections.activeChildren = Array.isArray(coll?.children) ? [...coll.children] : []
    collections.isChildrenLoading = true

    // 这步会立即返回数据库里的旧数据 (或者为 null)
    try {
      const res = await window.pywebview.api.lifecycle_fetch_collection(coll.id)
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
      toast.error(`加载合集失败: ${e.message}`)
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
      const res = await window.pywebview.api.workspace_transfer_mods(path_hashs, target_store, mode)
      if(checkResult(res, "库间转移")) {
        await appStore.requestModScan()
      }
      appStore.isLoading = false
    }
  }

  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (workshop_id, on_steam=true) => {
    if(!workshop_id) return
    const steamUrl = on_steam ? `steam://url/CommunityFilePage/${workshop_id}` : `https://steamcommunity.com/sharedfiles/filedetails/?id=${workshop_id}`
    window.open(steamUrl, '_blank')
  }


  return {
    // 库矩阵状态
    librariesMods, isFetching, librariesSize, activeChildrenWithStatus,
    workshopSearch, timeline, subscribedWorkshopIds, installedAllIds, missingWorkshopIds, getModStatus, modTransfer,
    matrixFocusTarget, getMatrixSameItems, getMatrixConflictItems, jumpToMatrixItem,
    // 库数据与工坊时间线
    fetchLibrariesMods, refreshLifecycleUpdateStates, doWorkshopSearch, fetchWorkshopDetails, openTimeline, openTimelineGithub, setupListeners, setWorkshopSearchMode,
    // GitHub 数据
    github, fetchGithubRepos, fetchGithubProviderCatalog, fetchGithubTimeline, startGithubTimelinePolling, stopGithubTimelinePolling, selectGithubRepo, clearActiveGithubRepo,
    // 懒加载与来源映射
    getGithubOnlineVersion, getGithubRepoStatus, githubRepoNeedsUpdate, ensureLibrariesLoaded, ensureGithubLoaded, ensureCollectionsLoaded, ensureWorkspaceTabLoaded, refreshLoadedData, openSteamWorkshopUrl, getWorkshopDetailsByPackageIdsMap, getInstallSourcesByPackageIdsMap, getWorkshopIdsByPackageIdsMap, resolvePackageIdsToWorkshopIds, goBackWorkshopDetail,
    // 合集
    collections, fetchSavedCollections, addCollection, removeCollection, selectCollection,
  }
})
