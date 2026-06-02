import { toast, checkResult } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useProfileStore } from '../../../features/profiles/profileStore'
import { useWorkspaceStore } from '../../../features/workspace/workspaceStore'

export const usePackageTransferActions = ({
  uiState,
  packageTransferDialog,
  isLoading,
  settings,
  taskStore,
  openPath,
  refreshData,
  requestModScan,
} = {}) => {
  const applyModPackageImportPostActions = async (task) => {
    const profileStore = useProfileStore()
    const workspaceStore = useWorkspaceStore()
    const postActions = task?.metrics?.post_actions || {}
    const shouldScanCurrentView = !!postActions.scan_current_view
    const shouldRefreshCurrentProfile = !!postActions.refresh_current_profile
    const shouldRefreshProfileList = !!postActions.refresh_profile_list

    const followUpTasks = []
    if (shouldRefreshProfileList) {
      followUpTasks.push(profileStore.fetchProfiles())
    }
    if (shouldRefreshCurrentProfile) {
      followUpTasks.push(refreshData())
    }
    if (shouldRefreshProfileList) {
      followUpTasks.push(workspaceStore.fetchGithubRepos())
      followUpTasks.push(workspaceStore.fetchSavedCollections())
    }
    if (followUpTasks.length > 0) {
      await Promise.all(followUpTasks)
    }
    if (shouldScanCurrentView) {
      await requestModScan()
    }
  }

  const showExportCompleteDialog = async (title, targetPath) => {
    const normalizedPath = String(targetPath || '').trim()
    if (!normalizedPath) {
      toast.success(`${title}完成`)
      return
    }
    const confirmStore = useConfirmStore()
    const action = await confirmStore.confirmAction(
      `${title}完成`,
      `导出路径：${normalizedPath}`,
      {
        type: 'success',
        actionButtons: [
          { label: '打开导出目录', value: 'open', kind: 'primary' },
          { label: '关闭', value: 'close', kind: 'secondary' },
        ],
      }
    )
    if (action === 'open') {
      // 后端会在传入文件路径时打开其所在目录，这里保留完整导出路径方便日志和异常提示定位。
      await openPath(normalizedPath)
    }
  }

  const openPackageTransferDialog = (mode = 'mod-import', preset = {}) => {
    packageTransferDialog.mode = String(mode || 'mod-import')
    packageTransferDialog.preset = { ...(preset || {}) }
    uiState.showPackageTransferDialog = true
  }

  const openCustomModExportDialog = ({
    title = '导出模组',
    description = '可按需附带依赖、联锁项和语言包。',
    modIds = [],
    summary = '',
  } = {}) => {
    const normalizedModIds = [...new Set(
      (modIds || [])
        .map(id => String(id || '').trim())
        .filter(Boolean)
    )]
    openPackageTransferDialog('mod-export', {
      title,
      description,
      mod_ids: normalizedModIds,
      allowExtraOptions: true,
      export_scope: 'custom',
      summary: summary || `已选 ${normalizedModIds.length} 个模组。`,
    })
  }

  const updatePackageTransferDialogPreset = (patch = {}) => {
    Object.assign(packageTransferDialog.preset, patch || {})
  }

  const closePackageTransferDialog = () => {
    uiState.showPackageTransferDialog = false
    packageTransferDialog.mode = 'mod-import'
    packageTransferDialog.preset = {}
  }

  // --- 统一软件数据导入导出 ---
  const getDataBundleSchema = async () => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.data_bundle_get_schema()
    return checkResult(res, '获取数据导入导出配置') ? res.data : null
  }

  const inspectDataBundle = async (bundlePath) => {
    if (!window.pywebview || !bundlePath) return null
    const res = await window.pywebview.api.data_bundle_inspect(bundlePath)
    return checkResult(res, '读取数据包摘要') ? res.data : null
  }

  const exportDataBundle = async (payload = {}) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.data_bundle_export(payload)
    if (!checkResult(res, '导出软件数据', true)) return false
    window.setTimeout(() => {
      void showExportCompleteDialog('软件数据导出', res.data?.path)
    }, 0)
    return res.data
  }

  const importDataBundle = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return false
    isLoading.value = true
    try {
      const res = await window.pywebview.api.data_bundle_import(bundlePath, payload)
      if (!checkResult(res, '导入软件数据', true)) return false

      const profileStore = useProfileStore()
      const workspaceStore = useWorkspaceStore()
      Object.assign(settings.value, res.data?.settings || {})
      profileStore.activeContext = res.data?.active_context || profileStore.activeContext

      await refreshData()
      await Promise.all([
        profileStore.fetchProfiles(),
        workspaceStore.fetchGithubRepos(),
        workspaceStore.fetchSavedCollections(),
      ])

      const warnings = res.data?.result?.warnings || []
      if (warnings.length > 0) {
        toast.warning(warnings.join('\n'), { timeout: 8000 })
      }
      return res.data
    } finally {
      isLoading.value = false
    }
  }

  const getModPackageSchema = async () => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.mod_package_get_schema()
    return checkResult(res, '获取模组打包配置') ? res.data : null
  }

  const prepareModPackageImport = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return null
    const res = await window.pywebview.api.mod_package_prepare_import(bundlePath, payload)
    return checkResult(res, '预检模组包导入') ? res.data : null
  }

  const getModPackageProfileSummary = async (profileId = '') => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.mod_package_get_profile_summary(profileId)
    return checkResult(res, '读取环境导出统计') ? res.data : null
  }

  const exportModPackage = async (payload = {}) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.mod_package_export(payload)
    if (!checkResult(res, '启动导出任务')) return false
    const taskId = String(res.data?.task_id || '').trim()
    if (taskId) {
      taskStore.createPlaceholderTask({
        id: taskId,
        type: 'mod-export',
        status: 'pending',
        progress: 0,
        message: '准备导出模组包...',
        metrics: {
          title: '导出模组包',
          target_path: res.data?.target_path || '',
        },
      })
    }
    return res.data
  }

  const importModPackage = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return false
    if (taskStore.hasActiveTaskOfType('mod-import')) {
      toast.info('已有模组包导入任务正在进行')
      return false
    }
    const normalizedPayload = { ...(payload || {}) }
    const res = await window.pywebview.api.mod_package_import(bundlePath, normalizedPayload)
    if (!checkResult(res, '启动模组包导入')) return false
    const taskId = String(res.data?.task_id || '').trim()
    if (taskId) {
      taskStore.createPlaceholderTask({
        id: taskId,
        type: 'mod-import',
        status: 'pending',
        progress: 0,
        message: '准备导入模组包...',
        metrics: {
          title: '导入模组包',
          bundle_path: bundlePath,
        },
      })
    }
    return res.data
  }

  return {
    applyModPackageImportPostActions,
    showExportCompleteDialog,
    openPackageTransferDialog,
    openCustomModExportDialog,
    updatePackageTransferDialogPreset,
    closePackageTransferDialog,
    getDataBundleSchema,
    inspectDataBundle,
    exportDataBundle,
    importDataBundle,
    getModPackageSchema,
    prepareModPackageImport,
    getModPackageProfileSummary,
    exportModPackage,
    importModPackage,
  }
}
