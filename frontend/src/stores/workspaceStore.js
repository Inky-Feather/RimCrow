// frontend/src/stores/workspaceStore.js
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { useAppStore } from './appStore'
import { checkResult } from '../utils/tools'
import { createToastInterface } from 'vue-toastification'
import { useConfirmStore } from './confirmStore'

export const useWorkspaceStore = defineStore('workspace', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
const confirmStore = useConfirmStore()
  
  // 1. 已订阅的工坊 ID (仅统计创意工坊域)
  const subscribedWorkshopIds = computed(() => {
    return new Set(
      librariesMods.workshop
        .filter(m => m.steam_status?.is_subscribed)
        .map(m => String(m.workshop_id))
    )
  })
  // 2. 缺失的工坊 ID (仅统计创意工坊域)
  const missingWorkshopIds = computed(() => {
    return new Set(
      librariesMods.workshop
        .filter(m => m.is_missing)
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
      all.filter(m => m.path && !m.is_missing).map(m => String(m.workshop_id))
    )
  })
  // 4. 提供一个快捷判断函数供 NexusBrowser 使用
  const getModStatus = (workshopId) => {
    const wid = String(workshopId)
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
  const nexusSearch = reactive({
    query: '',
    page: 1,
    hasMore: true, // 是否还有下一页
    results: [],
    total: 0,
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
    modId: null, // workshop_id
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
  // 5. GitHub 订阅状态
  const github = reactive({
    subscribedRepos: [],
    isLoading: false,
    activeRepo: null,     // 当前查看的 repo
    repoTimelines: [],    // 当前选中仓库的日志
    previewInfo: null,    // 解析新链接时的预览信息
  })

  const isFetching = ref(false)

  // --- Actions ---
  // 初始化数据
  const initData = async () => {
    console.log("初始化 Workspace 数据...")
    setupListeners() // 必须先挂载监听器，防止后端推送太快漏接
    // 并发拉取基础数据，让 UI 瞬间填满
    await Promise.all([
      fetchLibrariesMods(),
      fetchGithubRepos(),
      fetchSavedCollections() 
    ])
  }
  // 监听后端推送
  const setupListeners = () => {
    // 【监听 A】: 三域列表的在线状态静默更新
    // payload 格式: { "12345": { title: "...", time_updated: 17000000, preview_url: "..." }, ... }
    window.addEventListener('workspace-online-update', (e) => {
      const onlineMap = e.detail
      console.log("[Workspace] 收到 Steam 在线状态批量推送:", Object.keys(onlineMap).length, "条记录")
      // 定义合并逻辑：寻找对应 ID 的 Mod 并注入在线数据
      const mergeOnlineData = (modList) => {
        modList.forEach(mod => {
          const wid = String(mod.workshop_id)
          if (onlineMap[wid]) {
            const onlineInfo = onlineMap[wid]
            // 将云端详情挂载到 mod 对象上
            mod.online_info = onlineInfo
            // 实时计算更新标记 (核心逻辑)
            // 获取本地的下载时间或安装时间
            const localTime = mod.steam_status?.time_downloaded || 
                              mod.steam_status?.installed_version_time || 0
            // 如果云端更新时间 > 本地时间 + 1小时容差，标记为有更新
            mod.has_update = onlineInfo.time_updated > (localTime + 3600 * 1000)
          }
        })
      }
      // 执行合并 (由于 librariesMods 是 reactive，修改内部对象会触发 Vue 重新渲染对应 DOM)
      mergeOnlineData(librariesMods.workshop)
      mergeOnlineData(librariesMods.self)
    })
    // 【监听 B】: GitHub 在线状态静默更新
    // payload 格式: { "https://github.com/...": { latest_release_tag: "v1.2", ... }, ... }
    window.addEventListener('github-online-update', (e) => {
      const updatedReposMap = e.detail
      console.log("[Workspace] 收到 GitHub 在线状态推送:", Object.keys(updatedReposMap).length, "条记录")

      github.subscribedRepos.forEach(repo => {
        if (updatedReposMap[repo.repo_url]) {
          const freshInfo = updatedReposMap[repo.repo_url]
          
          // 比较本地记录的 tag 和线上最新的 tag，判断是否需要更新
          // 假设你本地记录当前安装版本的字段叫 installed_tag (如果没有请在模型里加一个或用其他方式判定)
          const localTag = repo.installed_tag || '' 
          const onlineTag = freshInfo.latest_release_tag || ''
          
          repo.online_info = freshInfo
          repo.has_update = (onlineTag !== '' && localTag !== onlineTag)
        }
      })
    })
    // 监听合集更新
    window.addEventListener('workspace-collection-updated', (e) => {
    const updated = e.detail // { id, data: { collection, children, ... } }
    // 如果当前用户正在看的正是这个合集，立即无感替换数据
    if (collections.activeId === updated.id) {
      collections.activeDetails = updated.data.collection
      collections.activeChildren = updated.data.children
      collections.isChildrenLoading = false
    }
    // 同时更新右侧合集列表中的统计数字
    const target = collections.savedList.find(c => c.id === updated.id)
    if (target) {
      Object.assign(target, {
        total: updated.data.total,
        need_download: updated.data.need_download,
        preview_url: updated.data.collection.preview_url,
        title: updated.data.collection.title
      })
    }
    const self_workshop_ids = librariesMods.self.map(mod => mod.workshop_id)
    const workshop_workshop_ids = librariesMods.workshop.map(mod => mod.workshop_id)
    const local_package_ids = librariesMods.local.map(mod => mod.package_id)

    collections.activeChildren.forEach(child => {
      child.is_self = self_workshop_ids.includes(child.workshop_id)
      child.is_workshop = workshop_workshop_ids.includes(child.workshop_id)
      child.is_local = local_package_ids.includes(child.package_id)
    })
  })
  }

  // 拉取无遮蔽的三个库全量数据
  const fetchLibrariesMods = async () => {
    if (!window.pywebview) return
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
      }
    } finally {
      isFetching.value = false
    }
  }

  // 搜索缓存工坊数据库 (支持重置或追加)
  const doNexusSearch = async (queryStr = '', isAppend = false) => {
    if (!window.pywebview) return
    // 防御性拦截
    if (nexusSearch.isLoading || nexusSearch.isLoadMore) return
    if (isAppend && !nexusSearch.hasMore) return
    // 状态设置
    if (isAppend) {
      nexusSearch.isLoadMore = true
      nexusSearch.page += 1
    } else {
      nexusSearch.isLoading = true
      nexusSearch.page = 1
      nexusSearch.results = [] // 清空旧数据
    }
    nexusSearch.query = queryStr
    try {
      const res = await window.pywebview.api.nexus_search(queryStr, nexusSearch.page)
      if (checkResult(res, '工坊检索')) {
        const newItems = res.data.items || []
        if (isAppend) {
          // 核心修复：不要用 push！使用展开运算符创建新数组引用！
          // nexusSearch.results.push(...newItems)
          nexusSearch.results = [...nexusSearch.results, ...newItems] 
        } else {
          nexusSearch.results = newItems
          nexusSearch.total = res.data.total
        }
        // 判断是否还有下一页
        nexusSearch.hasMore = nexusSearch.results.length < res.data.total
      }
    } finally {
      nexusSearch.isLoading = false
      nexusSearch.isLoadMore = false
    }
  }
  // 获取云端详情 (包含网页抓取截图)
  // isNavigate: 是否是通过点击“推荐卡片”触发的内部跳转
  const fetchNexusDetails = async (workshop_id, isNavigate = false) => {
    if (!window.pywebview || nexusSearch.selectedId === workshop_id) return
    // 如果是点击左侧主列表，清空历史记录，重新开始
    if (!isNavigate) {
      nexusSearch.historyStack = []
    } else if (nexusSearch.selectedId) {
      // 如果是内部跳转，将当前 ID 压入栈中
      nexusSearch.historyStack.push(nexusSearch.selectedId)
    }
    nexusSearch.selectedId = workshop_id
    nexusSearch.isDetailLoading = true
    try {
      const res = await window.pywebview.api.nexus_get_details(workshop_id)
      if (checkResult(res, '获取云端详情')) {
        nexusSearch.detailData = res.data
      }
    } finally {
      nexusSearch.isDetailLoading = false
    }
  }
  // 详情页后退功能
  const goBackNexusDetail = async () => {
    if (nexusSearch.historyStack.length === 0) return
    const prevId = nexusSearch.historyStack.pop()
    await fetchNexusDetails(prevId, true)
    // 抵消刚刚 push 进去的动作
    nexusSearch.historyStack.pop() 
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
  // 打开并加载 Github 模组变更时间线
  const openTimelineGithub = async (path) => {
    if (!window.pywebview) return
    timeline.isOpen = true
    console.log("打开Github时间线", path, github.subscribedRepos)
    const repo = github.subscribedRepos.find(repo => path.includes(repo.local_folder))
    if (!repo) {
      toast.warning('未找到该订阅')
      return
    }
    timeline.workshopId = repo.repo_url
    timeline.modName = repo.repo_name
    timeline.isLoading = true
    timeline.logs = []
    try {
      const res = await window.pywebview.api.github_get_timeline(repo.repo_url)
      if (checkResult(res, '获取Github模组时间线')) {
        timeline.logs = res.data
      }
    } finally {
      timeline.isLoading = false
    }
  }

  // 拉取 GitHub 订阅列表，拉取所有订阅记录
  const fetchGithubRepos = async () => {
    if (!window.pywebview) return
    github.isLoading = true
    try {
      // 瞬间返回带缓存的数据
      const res = await window.pywebview.api.github_get_subscribed()
      if (checkResult(res, '获取Github订阅')) {
        github.subscribedRepos = res.data || []
      }
    } finally {
      github.isLoading = false
    }
  }
  // 加载Github模组时间线
  const fetchGithubTimeline = async (url) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.github_get_timeline(url)
    if (checkResult(res, '获取Github模组时间线')) {
      github.repoTimelines = res.data
    }
  }

  // 初始化拉取本地数据库中的合集列表
  const fetchSavedCollections = async () => {
    if (!window.pywebview) return
    collections.isLoading = true
    try {
      // 假设你后端新增了获取列表的 API
      const res = await window.pywebview.api.collection_get_all()
      if (checkResult(res, '获取合集记录')) {
        collections.savedList = res.data || []
      }
    } finally {
      collections.isLoading = false
    }
  }

  // 接入(解析并保存)新合集
  const addCollection = async (inputUrl) => {
    if (!window.pywebview || !inputUrl) return
    // 智能提取 ID
    const match = inputUrl.match(/id=(\d+)/) || inputUrl.match(/(\d+)/)
    const collId = match ? match[1] : inputUrl.trim()
    if (!/^\d+$/.test(collId)) {
      toast.error("无效的合集 ID 或链接，请输入纯数字或包含 id=xxx 的链接")
      return
    }
    if (collections.savedList.some(c => c.id === collId)) {
      toast.warning("该合集已在你的记录中！")
      return
    }
    collections.isParsing = true
    toast.info("正在解析并接入合集数据...")
    try {
      const res = await window.pywebview.api.collection_add_and_fetch(collId)
      if (checkResult(res, '解析并接入合集')) {
        // 假设后端返回了保存成功的合集概览对象
        const newColl = {
          id: collId,
          title: res.data.collection?.title || `合集 ${collId}`,
          preview_url: res.data.collection?.preview_url,
          total: res.data.total || 0,
          need_download: res.data.need_download || 0
        }
        collections.savedList.unshift(newColl)
        toast.success("合集编队接入成功！")
        // 可选：自动选中刚添加的合集
        selectCollection(newColl)
      }
    } finally {
      collections.isParsing = false
    }
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
    collections.isChildrenLoading = true
    
    // 这步会立即返回数据库里的旧数据 (或者为 null)
    const res = await window.pywebview.api.lifecycle_fetch_collection(coll.id)
    if (res.status === 'success' && res.data) {
      collections.activeDetails = res.data.collection
      collections.activeChildren = res.data.children
      // 如果返回的是缓存，我们依然保持 loading 状态（或者显示一个“同步中”的小标志）
      if (!res.data.is_cache) {
        collections.isChildrenLoading = false
      }
    }
  }

  // 根据包名获取创意工坊ID映射
  const getWorkshopIdsByPackageIdsMap = async (packageIds) => {
    if (!window.pywebview) return
    if (!packageIds) return []
    const res = await window.pywebview.api.get_workshop_ids_by_package_ids_map(packageIds)
    if (checkResult(res, '根据包名获取创意工坊ID')) {
      return res.data || {}
    }
    
    return []
  }

  const modTransfer = async (path_hashs, target_store, mode) => {
    const check = await confirmStore.confirmAction(
      '确认转移',
      `确定要将选中的模组 ${mode === 'move' ? '移动' : '复制'} 到 [${target_store === 'local' ? '游戏本地' : '管理器'}] 库吗？`,
      { type: 'info' }
    )
    if(check) {
      appStore.isLoading = true
      const res = await window.pywebview.api.workspace_transfer_mods(path_hashs, target_store, mode)
      if(appStore.checkResult(res, "库间转移")) {
        // 成功后刷新三大库数据
        fetchLibrariesMods()
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
    librariesMods, isFetching, librariesSize,
    nexusSearch, timeline, subscribedWorkshopIds, installedAllIds, missingWorkshopIds, getModStatus, modTransfer,
    fetchLibrariesMods, doNexusSearch, fetchNexusDetails, openTimeline, openTimelineGithub, setupListeners,
    github, fetchGithubRepos, fetchGithubTimeline, initData, openSteamWorkshopUrl, getWorkshopIdsByPackageIdsMap, goBackNexusDetail,
    collections, fetchSavedCollections, addCollection, removeCollection, selectCollection
  }
})