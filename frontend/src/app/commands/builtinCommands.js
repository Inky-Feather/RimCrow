import { registerCommands } from '../../shared/commands/commandRegistry'
import { getCurrentSelectedText } from '../../shared/lib/text'
import { getModListActions } from './modListActions'

let registered = false

const resolvePrimarySelectedMod = (modStore, args = {}) => {
  // 右键菜单会显式传入目标 Mod；键盘快捷键则退回到当前列表最后选中的项目。
  const explicitId = String(args?.modId || '').trim()
  if (explicitId) {
    const explicit = modStore?.takeModById?.(explicitId)
    if (explicit) return explicit
  }
  const last = modStore?.lastSelectedMod
  if (last) return last
  const selectedIds = Array.isArray(modStore?.selectedIds) ? modStore.selectedIds : []
  if (!selectedIds.length) return null
  return modStore.takeModById(selectedIds[selectedIds.length - 1]) || null
}

const resolveSelectedModIds = (modStore, args = {}) => {
  const explicitIds = Array.isArray(args?.modIds) ? args.modIds.filter(Boolean) : []
  if (explicitIds.length) return explicitIds
  return Array.isArray(modStore?.selectedIds) ? modStore.selectedIds.filter(Boolean) : []
}

const resolveFirstSelectedModId = (modStore, args = {}) => {
  const explicitId = String(args?.modId || '').trim()
  if (explicitId) return explicitId
  const selectedIds = resolveSelectedModIds(modStore, args)
  return selectedIds[0] || ''
}

const resolveNextSelectedActiveState = (modStore, args = {}) => {
  const selectedIds = resolveSelectedModIds(modStore, args)
  if (!selectedIds.length) return true
  const activeSet = new Set((Array.isArray(modStore?.activeIds) ? modStore.activeIds : []).map(id => String(id || '').toLowerCase()))
  return !selectedIds.every(id => activeSet.has(String(id || '').toLowerCase()))
}

export const registerBuiltinCommands = () => {
  if (registered) return
  registered = true

  // 内置命令是快捷键、右键菜单和后续插件入口共享的动作清单；用户可改的只是键位，不改命令语义。
  registerCommands([
    {
      id: 'mods.undoListHistory',
      title: '撤销列表操作',
      category: 'Mod 管理',
      scope: 'global',
      defaultKeys: ['Ctrl+Z'],
      description: '撤销当前会话内最近一次 Mod 列表变更。',
      enabled: ({ modStore }) => !!modStore?.canUndoListHistory,
      run: ({ modStore }) => modStore.undoListHistory(),
    },
    {
      id: 'mods.redoListHistory',
      title: '重做列表操作',
      category: 'Mod 管理',
      scope: 'global',
      defaultKeys: ['Ctrl+Y', 'Ctrl+Shift+Z'],
      description: '重做当前会话内刚撤销的 Mod 列表变更。',
      enabled: ({ modStore }) => !!modStore?.canRedoListHistory,
      run: ({ modStore }) => modStore.redoListHistory(),
    },
    {
      id: 'mods.refresh',
      title: '扫描 Mod',
      category: 'Mod 管理',
      scope: 'global',
      defaultKeys: ['Ctrl+R'],
      captureWhenDisabled: true,
      description: '增量扫描 Mod 目录，并阻止浏览器默认刷新页面。',
      enabled: ({ appStore }) => !appStore?.isScanRunning,
      run: ({ modStore }) => modStore.scanMods(),
    },
    {
      id: 'mods.forceRefresh',
      title: '强制扫描 Mod',
      category: 'Mod 管理',
      scope: 'global',
      defaultKeys: ['Ctrl+Shift+R'],
      captureWhenDisabled: true,
      description: '重新检查所有文件，适合文件状态不确定时使用。',
      enabled: ({ appStore }) => !appStore?.isScanRunning,
      run: ({ modStore }) => modStore.scanMods(null, true),
    },
    {
      id: 'loadOrder.save',
      title: '保存加载顺序',
      category: '加载顺序',
      scope: 'global',
      defaultKeys: ['Ctrl+S'],
      captureWhenDisabled: true,
      description: '保存当前启用列表到游戏配置。',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.saveLoadOrder(),
    },
    {
      id: 'loadOrder.importFile',
      title: '导入排序文件',
      category: '加载顺序',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+I'],
      description: '选择并导入一个加载序列文件。',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.importExternalOrder('0'),
    },
    {
      id: 'loadOrder.exportFile',
      title: '导出分享列表',
      category: '加载顺序',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+E'],
      description: '导出为 ModList.xml，包含包名和工坊 ID。',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.exportLoadOrder(null, true, 'modlist'),
    },
    {
      id: 'loadOrder.importShareCode',
      title: '导入排序分享码',
      category: '加载顺序',
      scope: 'global',
      defaultKeys: [],
      description: '粘贴排序分享码，导入后打开差异对比。',
      enabled: ({ orderStore }) => !!orderStore,
      run: async ({ appStore, orderStore }) => {
        const data = await orderStore.promptImportShareCode()
        if (data) appStore.uiState.showDiffDrawer = true
      },
    },
    {
      id: 'loadOrder.exportShareCode',
      title: '导出排序分享码',
      category: '加载顺序',
      scope: 'global',
      defaultKeys: [],
      description: '生成当前启用列表的排序分享码。',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.exportLoadOrderShareCode(),
    },
    {
      id: 'app.openSettings',
      title: '打开设置',
      category: '应用',
      scope: 'global',
      defaultKeys: ['Ctrl+,'],
      description: '打开系统设置面板。',
      enabled: ({ appStore }) => !appStore?.uiState?.showSettingsPanel,
      run: ({ appStore }) => appStore.openSettingsPanel(),
    },
    {
      id: 'app.openFileSearch',
      title: '打开文件内容搜索',
      category: '应用',
      scope: 'global',
      defaultKeys: ['Ctrl+Shift+F'],
      allowInInput: true,
      description: '打开文件内容搜索；如果当前选中了文本，会带入搜索词并直接搜索。',
      run: async ({ appStore, fileSearchStore }) => {
        const selectedText = getCurrentSelectedText()
        if (fileSearchStore) {
          if (selectedText) fileSearchStore.form.query = selectedText
          fileSearchStore.openWorkbench()
          if (selectedText) await fileSearchStore.startSearch()
          return
        }
        appStore.uiState.showFileSearchWorkbench = true
      },
    },
    {
      id: 'app.openWorkspace',
      title: '打开库存枢纽',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      description: '打开库存管理中枢。',
      enabled: ({ appStore }) => !appStore?.uiState?.showWorkspace,
      run: ({ appStore }) => { appStore.uiState.showWorkspace = true },
    },
    {
      id: 'app.openLogs',
      title: '打开日志页面',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      description: '打开运行日志页面。',
      run: ({ appStore }) => appStore.toggleUiState('showLogDrawer'),
    },
    {
      id: 'app.openRules',
      title: '打开规则页面',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      description: '打开规则管理页面。',
      run: ({ appStore }) => appStore.toggleUiState('showRuleDrawer'),
    },
    {
      id: 'app.openTextureOpt',
      title: '打开贴图优化',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      description: '打开贴图优化面板。',
      run: ({ appStore }) => appStore.toggleUiState('showTextureOptModal'),
    },
    {
      id: 'app.openModSettingsManager',
      title: '打开模组配置',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      description: '打开模组配置查看器。',
      run: ({ appStore }) => appStore.toggleUiState('showModSettingsManager'),
    },
    {
      id: 'app.launchGame',
      title: '启动游戏',
      category: '应用',
      scope: 'global',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: '启动当前环境对应的 RimWorld。',
      run: ({ appStore }) => appStore.launchGame(),
    },
    {
      id: 'mods.autoSortActive',
      title: '自动排序启用列表',
      category: 'Mod 管理',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+A'],
      description: '根据当前规则自动排序启用列表。',
      enabled: ({ modStore }) => Array.isArray(modStore?.activeIds) && modStore.activeIds.length > 0,
      run: ({ modStore }) => modStore.autoSortMods(),
    },
    {
      id: 'mods.toggleSelectedActive',
      title: '启用或停用选中 Mod',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      description: '根据当前选中项状态，在启用和停用之间切换。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: ({ modStore }, args) => modStore.changeModsActive(
        resolveSelectedModIds(modStore, args),
        resolveNextSelectedActiveState(modStore, args),
      ),
    },
    {
      id: 'mods.toggleSelectedCoexistenceSource',
      title: '切换选中 Mod 工坊/本地版本',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+Alt+V'],
      description: '以第一个可切换的选中项为准，将所有可共存的选中 Mod 统一切到另一版本。只处理存在共存版本的 Mod。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.canSwitchCoexistenceSource?.(id)),
      run: ({ modStore }, args) => modStore.toggleSelectedCoexistenceSource(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.revealFirstSelected',
      title: '返回选中 Mod 位置',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+H'],
      description: '定位到当前选中的第一个 Mod，多选时只处理第一项。',
      enabled: ({ modStore }, args) => !!resolveFirstSelectedModId(modStore, args),
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        if (actions?.revealFirstSelected) return await actions.revealFirstSelected()
        return await modStore.revealSelectedMod(resolveFirstSelectedModId(modStore, args))
      },
    },
    {
      id: 'mods.moveSelectedToTop',
      title: '移动选中项到列表顶部',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+T'],
      description: '把当前选中的 Mod 移到所在列表顶部。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        return await actions?.moveSelectedToListBoundary?.('top') || false
      },
    },
    {
      id: 'mods.moveSelectedToBottom',
      title: '移动选中项到列表底部',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+B'],
      description: '把当前选中的 Mod 移到所在列表底部。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        return await actions?.moveSelectedToListBoundary?.('bottom') || false
      },
    },
    {
      id: 'mods.unsubscribeSelectedWorkshop',
      title: '取消订阅选中 Mod',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: '取消订阅选中的创意工坊 Mod；完成后从列表移除已处理项目。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.workshop_id),
      run: ({ modStore }, args) => modStore.unsubscribeSelectedWorkshopMods(false, resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.unsubscribeAndDeleteSelectedWorkshop',
      title: '取消订阅并删除选中 Mod',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: '取消订阅选中的创意工坊 Mod，并删除对应本地文件。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.workshop_id),
      run: ({ modStore }, args) => modStore.unsubscribeSelectedWorkshopMods(true, resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.deleteSelectedFiles',
      title: '删除选中 Mod 文件',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: '删除选中 Mod 的本地文件；完成后从列表移除已处理项目。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.path_hash),
      run: ({ modStore }, args) => modStore.deleteSelectedModFiles(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.disableSelectedFiles',
      title: '禁用选中 Mod',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: '禁用选中 Mod 的 About 文件，避免游戏识别与加载；可在已禁用列表重新启用。',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.path_hash),
      run: ({ modStore }, args) => modStore.disableSelectedMods(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.editSelectedRule',
      title: '编辑选中 Mod 规则',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: [],
      displayKeys: ['Alt+MouseLeft'],
      description: '打开最后选中 Mod 的规则编辑页。',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.package_id,
      run: ({ modStore, ruleStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        ruleStore.currentId = target?.active_package_token || target?.package_id
      },
    },
    {
      id: 'mods.openSelectedFolder',
      title: '打开选中 Mod 文件夹',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+O'],
      description: '打开最后选中 Mod 的本地文件夹。',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.path,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openPath(target?.path)
      },
    },
    {
      id: 'mods.openSelectedUrl',
      title: '访问 Mod 网页',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+I'],
      description: '打开目标 Mod 配置的网页链接。',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.url,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openUrl(target?.url)
      },
    },
    {
      id: 'mods.openSelectedWorkshopPage',
      title: '访问创意工坊',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+W'],
      description: '打开目标 Mod 对应的 Steam 创意工坊页面。',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.workshop_id,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openSteamWorkshopById(target?.workshop_id)
      },
    },
    {
      id: 'mods.openSelectedWebPage',
      title: '打开选中 Mod 页面',
      category: 'Mod 列表',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+Shift+I'],
      description: '优先打开 Mod 链接，没有链接时打开创意工坊页面。',
      enabled: ({ modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return !!(target?.url || target?.workshop_id)
      },
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        if (target?.url) return appStore.openUrl(target.url)
        return appStore.openSteamWorkshopById(target?.workshop_id)
      },
    },
    {
      id: 'selection.selectAllInList',
      title: '全选当前列表',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+A'],
      displayOnly: true,
      description: '选中当前列表或当前分组内的全部项目。',
    },
    {
      id: 'selection.toggleItem',
      title: '切换单项选择',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+MouseLeft'],
      displayOnly: true,
      description: '在不清空已有选择的情况下，加入或移除点击的项目。',
    },
    {
      id: 'selection.rangeSelect',
      title: '连续选择',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['Shift+MouseLeft'],
      displayOnly: true,
      description: '从上一次选择锚点连续选到当前点击项目。',
    },
    {
      id: 'selection.addRangeSelect',
      title: '追加连续选择',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+Shift+MouseLeft'],
      displayOnly: true,
      description: '保留已有选择，并追加一段连续范围。',
    },
    {
      id: 'selection.moveFocus',
      title: '移动列表选择',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['ArrowUp', 'ArrowDown'],
      displayOnly: true,
      description: '在列表获得焦点时，上下移动当前选择。',
    },
    {
      id: 'selection.extendFocus',
      title: '键盘连续选择',
      category: '列表选择',
      scope: 'mod-list',
      lockedKeys: ['Shift+ArrowUp', 'Shift+ArrowDown'],
      displayOnly: true,
      description: '在列表获得焦点时，用方向键扩展连续选择范围。',
    },
  ])
}
