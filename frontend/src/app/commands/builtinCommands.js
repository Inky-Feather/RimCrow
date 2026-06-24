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
      title: 'commands.mods.undoListHistory.title',
      category: 'commands.mods.undoListHistory.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Z'],
      description: 'commands.mods.undoListHistory.description',
      enabled: ({ modStore }) => !!modStore?.canUndoListHistory,
      run: ({ modStore }) => modStore.undoListHistory(),
    },
    {
      id: 'mods.redoListHistory',
      title: 'commands.mods.redoListHistory.title',
      category: 'commands.mods.redoListHistory.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Y', 'Ctrl+Shift+Z'],
      description: 'commands.mods.redoListHistory.description',
      enabled: ({ modStore }) => !!modStore?.canRedoListHistory,
      run: ({ modStore }) => modStore.redoListHistory(),
    },
    {
      id: 'mods.refresh',
      title: 'commands.mods.refresh.title',
      category: 'commands.mods.refresh.category',
      scope: 'global',
      defaultKeys: ['Ctrl+R'],
      captureWhenDisabled: true,
      description: 'commands.mods.refresh.description',
      enabled: ({ appStore }) => !appStore?.isScanRunning,
      run: ({ modStore }) => modStore.scanMods(),
    },
    {
      id: 'mods.forceRefresh',
      title: 'commands.mods.forceRefresh.title',
      category: 'commands.mods.forceRefresh.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Shift+R'],
      captureWhenDisabled: true,
      description: 'commands.mods.forceRefresh.description',
      enabled: ({ appStore }) => !appStore?.isScanRunning,
      run: ({ modStore }) => modStore.scanMods(null, true),
    },
    {
      id: 'loadOrder.save',
      title: 'commands.loadOrder.save.title',
      category: 'commands.loadOrder.save.category',
      scope: 'global',
      defaultKeys: ['Ctrl+S'],
      captureWhenDisabled: true,
      description: 'commands.loadOrder.save.description',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.saveLoadOrder(),
    },
    {
      id: 'loadOrder.importFile',
      title: 'commands.loadOrder.importFile.title',
      category: 'commands.loadOrder.importFile.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+I'],
      description: 'commands.loadOrder.importFile.description',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.importExternalOrder('0'),
    },
    {
      id: 'loadOrder.exportFile',
      title: 'commands.loadOrder.exportFile.title',
      category: 'commands.loadOrder.exportFile.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+E'],
      description: 'commands.loadOrder.exportFile.description',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.exportLoadOrder(null, true, 'modlist'),
    },
    {
      id: 'loadOrder.importShareCode',
      title: 'commands.loadOrder.importShareCode.title',
      category: 'commands.loadOrder.importShareCode.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.loadOrder.importShareCode.description',
      enabled: ({ orderStore }) => !!orderStore,
      run: async ({ appStore, orderStore }) => {
        const data = await orderStore.promptImportShareCode()
        if (data) appStore.uiState.showDiffDrawer = true
      },
    },
    {
      id: 'loadOrder.exportShareCode',
      title: 'commands.loadOrder.exportShareCode.title',
      category: 'commands.loadOrder.exportShareCode.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.loadOrder.exportShareCode.description',
      enabled: ({ orderStore }) => !!orderStore,
      run: ({ orderStore }) => orderStore.exportLoadOrderShareCode(),
    },
    {
      id: 'app.openSettings',
      title: 'commands.app.openSettings.title',
      category: 'commands.app.openSettings.category',
      scope: 'global',
      defaultKeys: ['Ctrl+,'],
      description: 'commands.app.openSettings.description',
      enabled: ({ appStore }) => !appStore?.uiState?.showSettingsPanel,
      run: ({ appStore }) => appStore.openSettingsPanel(),
    },
    {
      id: 'app.openFileSearch',
      title: 'commands.app.openFileSearch.title',
      category: 'commands.app.openFileSearch.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Shift+F'],
      allowInInput: true,
      description: 'commands.app.openFileSearch.description',
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
      title: 'commands.app.openWorkspace.title',
      category: 'commands.app.openWorkspace.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.app.openWorkspace.description',
      enabled: ({ appStore }) => !appStore?.uiState?.showWorkspace,
      run: ({ appStore }) => { appStore.uiState.showWorkspace = true },
    },
    {
      id: 'app.openLogs',
      title: 'commands.app.openLogs.title',
      category: 'commands.app.openLogs.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.app.openLogs.description',
      run: ({ appStore }) => appStore.toggleUiState('showLogDrawer'),
    },
    {
      id: 'app.openRules',
      title: 'commands.app.openRules.title',
      category: 'commands.app.openRules.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.app.openRules.description',
      run: ({ appStore }) => appStore.toggleUiState('showRuleDrawer'),
    },
    {
      id: 'app.openTextureOpt',
      title: 'commands.app.openTextureOpt.title',
      category: 'commands.app.openTextureOpt.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.app.openTextureOpt.description',
      run: ({ appStore }) => appStore.toggleUiState('showTextureOptModal'),
    },
    {
      id: 'app.openModSettingsManager',
      title: 'commands.app.openModSettingsManager.title',
      category: 'commands.app.openModSettingsManager.category',
      scope: 'global',
      defaultKeys: [],
      description: 'commands.app.openModSettingsManager.description',
      run: ({ appStore }) => appStore.toggleUiState('showModSettingsManager'),
    },
    {
      id: 'app.launchGame',
      title: 'commands.app.launchGame.title',
      category: 'commands.app.launchGame.category',
      scope: 'global',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: 'commands.app.launchGame.description',
      run: ({ appStore }) => appStore.launchGame(),
    },
    {
      id: 'mods.autoSortActive',
      title: 'commands.mods.autoSortActive.title',
      category: 'commands.mods.autoSortActive.category',
      scope: 'global',
      defaultKeys: ['Ctrl+Alt+A'],
      description: 'commands.mods.autoSortActive.description',
      enabled: ({ modStore }) => Array.isArray(modStore?.activeIds) && modStore.activeIds.length > 0,
      run: ({ modStore }) => modStore.autoSortMods(),
    },
    {
      id: 'mods.toggleSelectedActive',
      title: 'commands.mods.toggleSelectedActive.title',
      category: 'commands.mods.toggleSelectedActive.category',
      scope: 'mod-list',
      defaultKeys: [],
      description: 'commands.mods.toggleSelectedActive.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: ({ modStore }, args) => modStore.changeModsActive(
        resolveSelectedModIds(modStore, args),
        resolveNextSelectedActiveState(modStore, args),
      ),
    },
    {
      id: 'mods.toggleSelectedCoexistenceSource',
      title: 'commands.mods.toggleSelectedCoexistenceSource.title',
      category: 'commands.mods.toggleSelectedCoexistenceSource.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+Alt+V'],
      description: 'commands.mods.toggleSelectedCoexistenceSource.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.canSwitchCoexistenceSource?.(id)),
      run: ({ modStore }, args) => modStore.toggleSelectedCoexistenceSource(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.revealFirstSelected',
      title: 'commands.mods.revealFirstSelected.title',
      category: 'commands.mods.revealFirstSelected.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+H'],
      description: 'commands.mods.revealFirstSelected.description',
      enabled: ({ modStore }, args) => !!resolveFirstSelectedModId(modStore, args),
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        if (actions?.revealFirstSelected) return await actions.revealFirstSelected()
        return await modStore.revealSelectedMod(resolveFirstSelectedModId(modStore, args))
      },
    },
    {
      id: 'mods.moveSelectedToTop',
      title: 'commands.mods.moveSelectedToTop.title',
      category: 'commands.mods.moveSelectedToTop.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+T'],
      description: 'commands.mods.moveSelectedToTop.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        return await actions?.moveSelectedToListBoundary?.('top') || false
      },
    },
    {
      id: 'mods.moveSelectedToBottom',
      title: 'commands.mods.moveSelectedToBottom.title',
      category: 'commands.mods.moveSelectedToBottom.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+B'],
      description: 'commands.mods.moveSelectedToBottom.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).length > 0,
      run: async ({ modStore }, args) => {
        const actions = getModListActions(args?.scope)
        return await actions?.moveSelectedToListBoundary?.('bottom') || false
      },
    },
    {
      id: 'mods.unsubscribeSelectedWorkshop',
      title: 'commands.mods.unsubscribeSelectedWorkshop.title',
      category: 'commands.mods.unsubscribeSelectedWorkshop.category',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: 'commands.mods.unsubscribeSelectedWorkshop.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.workshop_id),
      run: ({ modStore }, args) => modStore.unsubscribeSelectedWorkshopMods(false, resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.unsubscribeAndDeleteSelectedWorkshop',
      title: 'commands.mods.unsubscribeAndDeleteSelectedWorkshop.title',
      category: 'commands.mods.unsubscribeAndDeleteSelectedWorkshop.category',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: 'commands.mods.unsubscribeAndDeleteSelectedWorkshop.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.workshop_id),
      run: ({ modStore }, args) => modStore.unsubscribeSelectedWorkshopMods(true, resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.deleteSelectedFiles',
      title: 'commands.mods.deleteSelectedFiles.title',
      category: 'commands.mods.deleteSelectedFiles.category',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: 'commands.mods.deleteSelectedFiles.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.path_hash),
      run: ({ modStore }, args) => modStore.deleteSelectedModFiles(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.disableSelectedFiles',
      title: 'commands.mods.disableSelectedFiles.title',
      category: 'commands.mods.disableSelectedFiles.category',
      scope: 'mod-list',
      defaultKeys: [],
      dangerLevel: 'warning',
      description: 'commands.mods.disableSelectedFiles.description',
      enabled: ({ modStore }, args) => resolveSelectedModIds(modStore, args).some(id => modStore?.takeModById?.(id)?.path_hash),
      run: ({ modStore }, args) => modStore.disableSelectedMods(resolveSelectedModIds(modStore, args)),
    },
    {
      id: 'mods.editSelectedRule',
      title: 'commands.mods.editSelectedRule.title',
      category: 'commands.mods.editSelectedRule.category',
      scope: 'mod-list',
      defaultKeys: [],
      displayKeys: ['Alt+MouseLeft'],
      description: 'commands.mods.editSelectedRule.description',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.package_id,
      run: ({ modStore, ruleStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        ruleStore.currentId = target?.active_package_token || target?.package_id
      },
    },
    {
      id: 'mods.openSelectedFolder',
      title: 'commands.mods.openSelectedFolder.title',
      category: 'commands.mods.openSelectedFolder.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+O'],
      description: 'commands.mods.openSelectedFolder.description',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.path,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openPath(target?.path)
      },
    },
    {
      id: 'mods.openSelectedUrl',
      title: 'commands.mods.openSelectedUrl.title',
      category: 'commands.mods.openSelectedUrl.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+I'],
      description: 'commands.mods.openSelectedUrl.description',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.url,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openUrl(target?.url)
      },
    },
    {
      id: 'mods.openSelectedWorkshopPage',
      title: 'commands.mods.openSelectedWorkshopPage.title',
      category: 'commands.mods.openSelectedWorkshopPage.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+W'],
      description: 'commands.mods.openSelectedWorkshopPage.description',
      enabled: ({ modStore }, args) => !!resolvePrimarySelectedMod(modStore, args)?.workshop_id,
      run: ({ appStore, modStore }, args) => {
        const target = resolvePrimarySelectedMod(modStore, args)
        return appStore.openSteamWorkshopById(target?.workshop_id)
      },
    },
    {
      id: 'mods.openSelectedWebPage',
      title: 'commands.mods.openSelectedWebPage.title',
      category: 'commands.mods.openSelectedWebPage.category',
      scope: 'mod-list',
      defaultKeys: ['Ctrl+Shift+I'],
      description: 'commands.mods.openSelectedWebPage.description',
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
      title: 'commands.selection.selectAllInList.title',
      category: 'commands.selection.selectAllInList.category',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+A'],
      displayOnly: true,
      description: 'commands.selection.selectAllInList.description',
    },
    {
      id: 'selection.toggleItem',
      title: 'commands.selection.toggleItem.title',
      category: 'commands.selection.toggleItem.category',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+MouseLeft'],
      displayOnly: true,
      description: 'commands.selection.toggleItem.description',
    },
    {
      id: 'selection.rangeSelect',
      title: 'commands.selection.rangeSelect.title',
      category: 'commands.selection.rangeSelect.category',
      scope: 'mod-list',
      lockedKeys: ['Shift+MouseLeft'],
      displayOnly: true,
      description: 'commands.selection.rangeSelect.description',
    },
    {
      id: 'selection.addRangeSelect',
      title: 'commands.selection.addRangeSelect.title',
      category: 'commands.selection.addRangeSelect.category',
      scope: 'mod-list',
      lockedKeys: ['Ctrl+Shift+MouseLeft'],
      displayOnly: true,
      description: 'commands.selection.addRangeSelect.description',
    },
    {
      id: 'selection.moveFocus',
      title: 'commands.selection.moveFocus.title',
      category: 'commands.selection.moveFocus.category',
      scope: 'mod-list',
      lockedKeys: ['ArrowUp', 'ArrowDown'],
      displayOnly: true,
      description: 'commands.selection.moveFocus.description',
    },
    {
      id: 'selection.extendFocus',
      title: 'commands.selection.extendFocus.title',
      category: 'commands.selection.extendFocus.category',
      scope: 'mod-list',
      lockedKeys: ['Shift+ArrowUp', 'Shift+ArrowDown'],
      displayOnly: true,
      description: 'commands.selection.extendFocus.description',
    },
  ])
}
