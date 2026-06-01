import { computed, ref, watch } from 'vue'
import { generateHtmlHelp } from '../search/SearchHelp'
import { ISSUE_TYPE } from '../../../shared/lib/constants'

const SORT_MODE_MAP = {
  'default': '默认',
  'name': '名称',
  'package_id': '包名',
  'author': '作者',
  'last_active_time': '启用时间',
  'last_moved_time': '移动时间',
  'file_create_time': '创建时间',
  'file_modify_time': '修改时间',
  'file_size': '文件大小',
}

export function useModListQuery({
  props,
  appStore,
  modStore,
  searchStore,
  toast,
  normalizeTokenId,
  normalizeCanonicalId,
}) {
  const isSimpleView = ref(true) // 是否简单视图
  const isSortAsc = ref(true)   // 是否升序排序
  const sortMode = ref('default')  // 排序模式

  const searchQuery = ref([]) // 存储搜索数组
  const searchLogic = ref('AND') // 存储逻辑关系
  const searchResults = ref([]) // 搜索结果数组
  const currentSearchIndex = ref(-1) // 当前搜索项在结果数组中的索引
  const currentTargetId = computed(() => modStore.currentTargetId)   // 当前搜索定位项ID
  const highlightTimer = ref() // 定位高亮定时器

  const filterQuery = ref([]) // 存储标签数组
  const filterLogic = ref('AND') // 存储逻辑关系
  const filterByLine = ref([])  // 存储筛选线路数组
  const isFilterByIssue = ref(false)  // 是否筛选问题项
  const filterIssueType = ref('')   // 筛选问题项类型

  const isSortChange = ref(false) // 是否排序切换
  const engine = computed(() => searchStore.engine)
  const searchResultSet = computed(() => new Set(searchResults.value))

  const resolveTargetListId = (targetId, candidates = []) => {
    const normalizedTargetToken = normalizeTokenId(targetId)
    if (!normalizedTargetToken) return ''
    const exactMatch = (candidates || []).find(id => normalizeTokenId(id) === normalizedTargetToken)
    if (exactMatch) return exactMatch
    const canonicalTargetId = normalizeCanonicalId(targetId)
    if (!canonicalTargetId) return ''
    return (candidates || []).find(id => normalizeCanonicalId(id) === canonicalTargetId) || ''
  }
  const resolvedCurrentTargetId = computed(() => resolveTargetListId(currentTargetId.value, props.modelValue))

  const isFiltered = computed(() => filterQuery.value.length > 0 || isFilterByIssue.value || filterByLine.value?.length > 0)
  const allowSort = computed(() => sortMode.value === 'default' && !isFiltered.value && isSortAsc.value)
  const itemHeight = computed(() => isSimpleView.value ? appStore.scalePx(30)+4 : appStore.scalePx(50)+4)

  // 切换问题项筛选
  const toggleIssueFilter = () => {
    isFilterByIssue.value = !isFilterByIssue.value
    filterIssueType.value = ''  // 整体筛选时，清空问题项类型筛选
  }
  const toggleIssueTypeFilter = (type) => {
    console.log('toggleIssueTypeFilter', type)
    // 检查类型是否符合ISSUE_TYPE
    if (!Object.values(ISSUE_TYPE).includes(type)) {
      isFilterByIssue.value = false
      filterIssueType.value = ''
      return
    }
    if (!filterIssueType.value) {
      isFilterByIssue.value = true
    }
    // 切换选中状态
    filterIssueType.value = filterIssueType.value === type ? '' : type
  }
  // 清除筛选
  const clearFilter = () => {
    filterQuery.value = []
    isFilterByIssue.value = false
    filterByLine.value = []
    filterIssueType.value = ''
  }
  // 清除排序
  const clearSort = () => {
    sortMode.value = 'default'
    isSortAsc.value = true
  }

  // 动态计算帮助文本
  const searchHelpText = computed(() => {
    if (!engine.value) return 'Loading...'
    // 这里可以做一层缓存，避免每次 render 都生成字符串
    return generateHtmlHelp(engine.value)
  })

  // 排序提示
  const sortTooltip = computed(() => {
    let text = `按${SORT_MODE_MAP[sortMode.value]}排序`
    text += `${isSortAsc.value ? '（升序）' : '（降序）'}`
    text += "\n__筛选和排序只供视觉检阅，^^不影响实际顺序^^，\n并且此状态下^^禁止拖拽排序或插入^^__"
    text += `\n\n__[[(点击恢复默认排序)]]__`
    return text
  })
  // 筛选提示
  const filterTooltip = computed(() => {
    let text = ''
    if (filterQuery.value.length > 0) { text += `已筛选检索关键词` }
    if (isFilterByIssue.value) { text += '\n已筛选问题项' }
    if (filterByLine.value.length > 0) { text += `\n已筛选依赖组` }
    text = text.trim()
    text += "\n__筛选和排序只供视觉检阅，^^不影响实际顺序^^，\n并且此状态下^^禁止拖拽排序或插入^^__"
    text += `\n\n__[[(点击清除所有筛选)]]__`
    return text
  })
  // 处理点击依赖图线路（筛选依赖组）
  const handleLineClick = (lines) => {
    // 重复点击清空
    if (filterByLine.value.length > 0) {
      filterByLine.value = []
      return
    }
    filterByLine.value = lines
  }
  // 左侧依赖线只跟随当前“可见列表”，这样折叠后视觉和交互才能保持同步。
  const showDependencyGraph = computed(() => allowSort.value || filterByLine.value.length > 0)

  // 显示列表：筛选 -> 排序
  const displayList = computed(() => {
    let list = props.modelValue.slice() // 复制一份 ID 列表
    // 1. 优先处理错误筛选
    if (isFilterByIssue.value) {
      list = list.filter(id => {
        // 从所有问题项中检测是否有该 Mod 的问题
        const issues = modStore.modIssues.get(normalizeTokenId(id))
        // 有问题项且符合筛选类型
        if (filterIssueType.value) {
          return issues && issues.some(issue => issue.type === filterIssueType.value)
        }
        // 有问题项但未指定类型，默认显示
        return issues && issues.length > 0
      })
    }
    // 2. 处理依赖图筛选
    if (filterByLine.value.length > 0) {
      list = list.filter(id => {
        return filterByLine.value.includes(id)
      })
    }
    // 3. 标签筛选
    if (filterQuery.value.length > 0 && engine.value) {
      // A. 全局搜索符合条件的对象
      // engine.search 返回的是 Mod 对象数组
      const matchedObjects = engine.value.search(filterQuery.value, filterLogic.value)
      // B. 提取 ID 并建立 Set 供快速查找
      const matchedSet = new Set(matchedObjects.map(m => normalizeCanonicalId(m.package_id)))
      // C. 取交集 (当前列表 AND 搜索结果)
      list = list.filter(id => matchedSet.has(normalizeCanonicalId(id)))
    }

    // 4. 排序 (仅视觉)
    if (sortMode.value !== 'default') {
      list.sort((a, b) => {
        const mA = modStore.takeModById(a)
        const mB = modStore.takeModById(b)
        if (sortMode.value === 'name') return (mA?.name || a).localeCompare(mB?.name || b)
        if (sortMode.value === 'author') return (mA?.author?.[0] || '').localeCompare(mB?.author?.[0] || '')
        if (sortMode.value === 'package_id') return (mA?.package_id || a).localeCompare(mB?.package_id || b)
        if (sortMode.value === 'last_active_time') return (mA?.last_active_time || 0) - (mB?.last_active_time || 0)
        if (sortMode.value === 'last_moved_time') return (mA?.last_moved_time || 0) - (mB?.last_moved_time || 0)
        if (sortMode.value === 'file_create_time') return (mA?.file_create_time || 0) - (mB?.file_create_time || 0)
        if (sortMode.value === 'file_modify_time') return (mA?.file_modify_time || 0) - (mB?.file_modify_time || 0)
        if (sortMode.value === 'file_size') return (mA?.file_size || 0) - (mB?.file_size || 0)

        return 0
      })
    }
    // 如果需要逆序，反转数组
    if (!isSortAsc.value) list.reverse()

    return list
  })

  const sortIcon = computed(() => {
    return SORT_MODE_MAP[sortMode.value] || '默认'
  })

  // 执行搜索
  const executeSearch = (next = true) => {
    // 清空旧结果
    if (!searchQuery.value.length) {
      searchResults.value = []
      modStore.currentTargetId = ''
      currentSearchIndex.value = -1
      return
    }
    // 检查 Engine 是否存在
    if (!engine.value) return
    // 1. 全局搜索
    const matchedObjects = engine.value.search(searchQuery.value, searchLogic.value)
    const matchedSet = new Set(matchedObjects.map(m => normalizeCanonicalId(m.package_id)))
    // 2. 过滤结果：定位当前筛选/排序后的结果，隐藏分组会在跳转前自动展开
    const results = displayList.value.filter(id => matchedSet.has(normalizeCanonicalId(id)))
    if (JSON.stringify(results) !== JSON.stringify(searchResults.value)) {
      searchResults.value = results
      currentSearchIndex.value = -1
    }
    if (results.length === 0) return
    let index = currentSearchIndex.value
    if (next) {
      index++
      if (index >= results.length) {
        index = 0 // 循环
        toast.info("已到达最后一个搜索结果，循环回到第一个", { timeout: 2000 })
      }
    }
    // 定位
    const targetId = results[index]
    currentSearchIndex.value = index
    // 先确保目标 ID 在可见范围内
    if (results.includes(targetId)) {
      modStore.currentTargetId = targetId
    }
  }

  const bindTargetReveal = ({ vListRef, visibleList, revealCollapsedSectionFor }) => {
    // 监听 currentTargetId 变化
    watch(currentTargetId, async (newVal, oldVal) => {
      if (!newVal || newVal === oldVal) return
      const resolvedTargetId = resolveTargetListId(newVal, props.modelValue)
      if (!resolvedTargetId) {
        console.info(`Item ${newVal} not found in ${props.title} list model.`)
        return
      }
      // 1. 检查目标是否在当前所有的 modelValue 中（不仅是 displayList）
      if (!props.modelValue.includes(resolvedTargetId)) return

      // 2. 检查是否被当前的筛选器过滤掉了
      if (!displayList.value.includes(resolvedTargetId)) {
        console.info(`Item ${resolvedTargetId} is filtered out by current ${props.title} filter.`)
        toast.warning(`搜索项 ${resolvedTargetId} 已被 ${props.title} 列表筛选器过滤，请清除筛选后重试。`)
      }
      await revealCollapsedSectionFor(resolvedTargetId)

      // 3. 执行定位
      const index = visibleList.value.indexOf(resolvedTargetId)
      if (index !== -1) {
        // 稍微延迟一下确保虚拟列表渲染就绪
        setTimeout(() => {
          if (vListRef.value) {
            vListRef.value.scrollToKey(resolvedTargetId)
          }
        }, 50)
        // 延迟一段时间后移除高亮
        if (highlightTimer.value) {
          clearTimeout(highlightTimer.value)
        }
        highlightTimer.value = setTimeout(() => {
          modStore.currentTargetId = ''
        }, 2000)
      }
    })
  }

  return {
    SORT_MODE_MAP,
    isSimpleView,
    isSortAsc,
    sortMode,
    searchQuery,
    searchLogic,
    searchResults,
    currentSearchIndex,
    currentTargetId,
    filterQuery,
    filterLogic,
    filterByLine,
    isFilterByIssue,
    filterIssueType,
    isSortChange,
    engine,
    searchResultSet,
    resolvedCurrentTargetId,
    allowSort,
    isFiltered,
    itemHeight,
    toggleIssueFilter,
    toggleIssueTypeFilter,
    clearFilter,
    clearSort,
    searchHelpText,
    sortTooltip,
    filterTooltip,
    handleLineClick,
    showDependencyGraph,
    displayList,
    sortIcon,
    executeSearch,
    bindTargetReveal,
  }
}
