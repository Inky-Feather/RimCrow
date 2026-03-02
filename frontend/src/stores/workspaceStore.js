// frontend/src/stores/workspaceStore.js
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { useAppStore } from './appStore'
import { checkResult } from '../utils/tools'
import { createToastInterface } from 'vue-toastification'

export const useWorkspaceStore = defineStore('workspace', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  
  // 1. 三个库的数据
  const librariesMods = reactive({
    local: [],
    workshop: [],
    self: []
  })
  const librariesSize = computed(() => {
    const results ={
      workshop: 0,
      self: 0,
      local: 0,
      total: 0,
    }
    results.workshop = librariesMods.workshop.length > 0 ? librariesMods.workshop.reduce((acc, mod) => acc + mod.file_size, 0) : 0
    results.self = librariesMods.self.length > 0 ? librariesMods.self.reduce((acc, mod) => acc + mod.file_size, 0) : 0
    results.local = librariesMods.local.length > 0 ? librariesMods.local.reduce((acc, mod) => acc + mod.file_size, 0) : 0
    results.total = results.workshop + results.self + results.local
    return results
  })
  // 2. 缓存工坊数据库搜索状态
  const nexusSearch = reactive({
    query: '',
    page: 1,
    results: [],
    total: 0,
    isLoading: false,
    selectedId: null,
    detailData: null,
    isDetailLoading: false
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
    await fetchLibrariesMods()
    await fetchGithubRepos()
    await fetchSavedCollections()
    setupListeners()
  }
  // 监听后端推送
  const setupListeners = () => {
    // 监听 Mod 在线状态更新
    window.addEventListener('workspace-online-update', (e) => {
      const onlineMap = e.detail // { "123": { title, time_updated, ... } }
      console.log("收到批量在线状态更新", onlineMap)
      // 在 workshop 和 self 列表中寻找匹配的 Mod 并更新
      const updateList = (list) => {
        list.forEach(mod => {
          const wid = String(mod.workshop_id)
          if (onlineMap[wid]) {
            const info = onlineMap[wid]
            mod.online_info = info
            
            // 实时计算更新标记
            const localTime = mod.steam_status?.time_downloaded || 
                              mod.steam_status?.installed_version_time || 0
            mod.has_update = info.time_updated > (localTime + 3600 * 1000)
          }
        })
      }
      updateList(librariesMods.workshop)
      updateList(librariesMods.self)
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
    // 同时更新右侧名录列表中的统计数字
    const target = collections.savedList.find(c => c.id === updated.id)
    if (target) {
      Object.assign(target, {
        total: updated.data.total,
        need_download: updated.data.need_download,
        preview_url: updated.data.collection.preview_url,
        title: updated.data.collection.title
      })
    }
  })
  }

  // 拉取无遮蔽的三个库全量数据
  const fetchLibrariesMods = async () => {
    if (!window.pywebview) return
    isFetching.value = true
    try {
      const res = await window.pywebview.api.workspace_get_all_domains()
      if (checkResult(res, '获取三个库全量数据')) {
        librariesMods.local = res.data.local
        librariesMods.workshop = res.data.workshop
        librariesMods.self = res.data.self
        
        const needRefresh = res.data.need_refresh || []
        if (needRefresh && needRefresh.length > 0) {
          window.pywebview.api.workspace_trigger_online_refresh(needRefresh)
          // 立即启动异步在线更新检查
          // const allWids = [
          //   ...librariesMods.workshop.map(m => m.workshop_id),
          //   ...librariesMods.self.map(m => m.workshop_id)
          // ].filter(id => id && id !== 'None')
          // if (allWids.length > 0) {
          //   window.pywebview.api.workspace_trigger_online_refresh(allWids)
          // }
        }
      }
    } finally {
      isFetching.value = false
    }
  }
  // 搜索缓存工坊数据库
  const doNexusSearch = async (queryStr = nexusSearch.query, page = 1) => {
    if (!window.pywebview || queryStr.length < 2) return
    nexusSearch.isLoading = true
    try {
      nexusSearch.query = queryStr
      nexusSearch.page = page
      const res = await window.pywebview.api.nexus_search(queryStr, page)
      if (checkResult(res, '搜索缓存工坊数据库')) {
        nexusSearch.results = res.data.items
        nexusSearch.total = res.data.total
      }
    } finally {
      nexusSearch.isLoading = false
    }
  }
  // 获取云端详情
  const fetchNexusDetails = async (workshop_id) => {
    if (!window.pywebview) return
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

  // 打开并加载模组变更时间线
  const openTimeline = async (workshopId, modName, is_steamcmd=false) => {
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
      const res = await window.pywebview.api.github_get_subscribed()
      if (checkResult(res, '获取Github订阅列表')) {
        github.subscribedRepos = res.data
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

  // 获取并展开选中合集的内部阵列 (动态计算缺失状态)
  const selectCollection = async (coll) => {
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


  return {
    librariesMods, isFetching, librariesSize,
    nexusSearch, timeline,
    fetchLibrariesMods, doNexusSearch, fetchNexusDetails, openTimeline, openTimelineGithub, setupListeners,
    github, fetchGithubRepos, fetchGithubTimeline, initData,
    collections, fetchSavedCollections, addCollection, removeCollection, selectCollection
  }
})