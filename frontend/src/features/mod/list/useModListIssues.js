import { computed } from 'vue'
import { ISSUE_TITLE_MAP } from '../../../shared/lib/constants'
import { Megaphone, MegaphoneOff, SearchAlert } from 'lucide-vue-next'

export function useModListIssues({
  props,
  appStore,
  modStore,
  menuStore,
  issuesSummary,
  invalidModsToRemove,
  refreshVirtualList,
  isFilterByIssue,
  toggleIssueTypeFilter,
  normalizeTokenId,
}) {
  // 构造问题详情 Tooltip
  const issueTooltip = computed(() => {
    const summary = issuesSummary.value // Store 返回的对象
    // console.log('问题摘要:', summary)
    if (summary.count === 0) return null
    const errorInfo = summary.errorCount > 0 ? `!!${summary.errorCount} 个错误!!` : ''
    const warningInfo = summary.warnCount > 0 ? `^^${summary.warnCount} 个警告^^` : ''
    let text = `**发现 ${summary.count} 个问题Mod**（${errorInfo} ${warningInfo}）`
    // 遍历 stats 对象生成详情
    // 格式:
    // !!缺失前置(10):!!
    // ModA | ModB | ... | __及其他 7 项__
    for (const [type, ids] of Object.entries(summary.stats)) {
      if (ids.length === 0) continue
      const typeName = ISSUE_TITLE_MAP[type] || type
      const isError = ['missing_dependency', 'inactive_dependency', 'missing_file', 'incompatible','wrong_order'].includes(type)
      // 标题颜色: Error 用红(!!), Warn 用黄(^^)
      const titleMark = isError ? '!!' : '^^'
      text += `\n${titleMark}${typeName} (${ids.length}):${titleMark}`
      // 列出前 3 个
      const previewIds = ids.slice(0, 3)
      previewIds.forEach(id => {
        text += `\n  • ${modStore.displayModName(id)}`
      })
      // 剩余数量提示
      if (ids.length > 3) {
        text += `\n  __...及其他 ${ids.length - 3} 项__`
      }
    }
    text += isFilterByIssue.value ? '\n\n__[[(再次点击取消筛选)]]__' : '\n\n__[[(点击筛选查看全部问题项)]]__'
    text += '\n__[[(可从^^右键菜单^^筛选单项问题)]]__'
    text += appStore.settings.check_language_support ? '\n__(可在设置中关闭语言支持检查)__' : ''
    return text
  })

  // 移除无效的mod
  const removeInvalidMod = async () => {
    const invalidMods = invalidModsToRemove.value
    if (invalidMods.length === 0) return
    await modStore.runListHistoryTransaction({
      type: 'batch-remove-list-items',
      label: `移除 ${invalidMods.length} 个无效 Mod`,
      trackedModIds: invalidMods
    }, async () => {
      modStore.removeUnavailableIdsCompletely(invalidMods)
    })
    await refreshVirtualList()
  }

  // 问题提示右键菜单
  const issueContextMenu = async (event) => {
    // console.log(issueState,issueState.value)
    // 通用菜单
    const commnMenuItems = [
      // { label: '修改类型', icon: ChessPawn,
      //   children: [...Object.entries(MOD_TYPE_MAP).map(([key, value]) => ({
      //     icon: MOD_TYPE_ICON_MAP[key],
      //     label: value, action: () => modStore.setModsType(selectedIds, key)
      //   })),{ label: '恢复默认', level: 'warn', action: () => modStore.setModsType(selectedIds, null) }]
      // },
    ]
    // 1. 获取所有选中 Mod 的当前问题并集
    const allSelectedIssues = props.modelValue.flatMap(id => modStore.modIssues.get(normalizeTokenId(id)) || [])
    // 2. 提取唯一的错误类型 (Type Unique Set)
    const uniqueIssueTypes = [...new Set(allSelectedIssues.map(i => i.type))]

    // 3. 检查选中项中是否有人已经设置了忽略 (用于显示“恢复警告”)
    const anyModHasIgnored = props.modelValue.some(id => {
      const m = modStore.takeModById(id)
      return m && m.ignored_issues && m.ignored_issues.length > 0
    })
    // 统一的问题菜单组
    const issueManagementItems = []
    // 如果并集不为空，显示“筛选...”子菜单
    if (uniqueIssueTypes.length > 0) {
      issueManagementItems.push({
        label: props.modelValue.length > 1 ? `筛选单项问题 (${uniqueIssueTypes.length})...` : '筛选单项问题...',
        icon: SearchAlert,
        children: uniqueIssueTypes.map(type => ({
          label: `单独筛选：${ISSUE_TITLE_MAP[type] || type}`,
          // 这里的 level 可以取该类型在所有 Mod 中的最高级别
          level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
          action: () => toggleIssueTypeFilter(type)
        }))
      })
    }
    // A. 如果并集不为空，显示“忽略...”子菜单
    if (uniqueIssueTypes.length > 0) {
      issueManagementItems.push({ divider: true })
      issueManagementItems.push({
        label: props.modelValue.length > 1 ? `忽略所有问题 (${uniqueIssueTypes.length})...` : '忽略问题...',
        icon: MegaphoneOff,
        children: uniqueIssueTypes.map(type => ({
          label: `忽略：${ISSUE_TITLE_MAP[type] || type}`,
          // 这里的 level 可以取该类型在所有 Mod 中的最高级别
          level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
          action: () => modStore.batchIgnoreIssues(props.modelValue, type)
        }))
      })
    }
    // B. 如果有选项被忽略了，显示“恢复警告”
    if (anyModHasIgnored) {
      // 如果之前没加 divider，补一个
      if (issueManagementItems.length === 0) issueManagementItems.push({ divider: true })
      issueManagementItems.push({
        label: props.modelValue.length > 1 ? '恢复所有警告' : '恢复警告',
        icon: Megaphone,
        level: 'warn',
        action: () => modStore.batchIgnoreIssues(props.modelValue, null)
      })
    }

    // 合并菜单
    const menuItems = [
      ...commnMenuItems,
      ...issueManagementItems, // 插入批量忽略逻辑
    ]

    menuStore.open(event, menuItems)
  }

  return {
    issueTooltip,
    removeInvalidMod,
    issueContextMenu,
  }
}
