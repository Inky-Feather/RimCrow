import { toast, checkResult } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { usePromptQueueStore } from '../../../features/ai/promptQueueStore'

export const useUpdateActions = ({
  updateState,
  upgradeContext,
  isLoading,
  uiState,
  logMaintenanceCheck,
} = {}) => {
  // 检查更新
  const checkUpdate = async (manual = true) => {
    updateState.isChecking = true
    logMaintenanceCheck('api_start', { id: 'app-update', name: '软件更新', manual })
    try {
      const res = await window.pywebview.api.update_check(manual)
      if (checkResult(res, "检查更新")) {
        const info = res.data
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res.status, hasUpdate: !!info?.has_update, version: info?.version || '', localStatus: info?.local_status || '' })
        if (info.has_update) {
          updateState.hasUpdate = true
          updateState.info = info
          const promptQueue = usePromptQueueStore()
          await promptQueue.enqueue({
            category: 'startup-app-update',
            title: `发现新版本 v${info.version}`,
            message: `来源: ${info.source_name || '未知'}。文件大小: ${info.file_size || '未知'}。`,
            type: 'success',
            priority: manual ? 20 : 50,
            items: [{
              id: info.version || 'app-update',
              title: `RimModManager v${info.version}`,
              description: info.changelog || '发现可用更新。',
              raw: info,
              actions: [
                { id: 'update', label: '立即更新', kind: 'primary' },
                { id: manual ? 'skip' : 'ignore', label: manual ? '以后再说' : '忽略此版本', kind: 'secondary' },
              ],
            }],
            bulkActions: [
              { id: 'update_all', label: '立即更新', kind: 'primary' },
              { id: manual ? 'skip_all' : 'ignore_all', label: manual ? '以后再说' : '忽略此版本', kind: 'secondary' },
            ],
            onItemAction: async (_item, actionId) => {
              if (actionId === 'update') {
                await _performUpdateAction()
              } else if (actionId === 'ignore' && !manual) {
                await window.pywebview.api.update_ignore_version(info.version)
              }
            },
            onBulkAction: async (actionId) => {
              if (actionId === 'update_all') {
                await _performUpdateAction()
              } else if (actionId === 'ignore_all' && !manual) {
                await window.pywebview.api.update_ignore_version(info.version)
              }
            },
          })
        } else if (manual) {
          toast.success("当前已是最新版本")
        }
      } else {
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res?.status || 'error', message: res?.message || '' }, 'warn')
      }
    } catch (error) {
      logMaintenanceCheck('api_error', { id: 'app-update', name: '软件更新', manual, message: error?.message || String(error || '') }, 'error')
      throw error
    } finally {
      updateState.isChecking = false
    }
  }

  const showChangelog = async () => {
    // 1. 如果当前没有日志数据（比如是从设置面板点进来的），主动从后端拉取
    if (!upgradeContext.value.changelog || upgradeContext.value.changelog.length === 0) {
      isLoading.value = true // 开启加载动画
      try {
        const res = await window.pywebview.api.get_changelog()
        if (res.status === 'success') {
          upgradeContext.value.changelog = res.data
        }
      } catch (e) {
          console.error("无法获取更新日志:", e)
      } finally {
          isLoading.value = false
      }
    }
    // 2. 显示弹窗
    uiState.showUpdateModal = true
  }

  const _showInstallPrompt = async (data) => {
    const confirmStore = useConfirmStore()
    const ok = await confirmStore.confirmAction(
      `确认安装更新？`,
      `压缩包已经下载到：${data.path}\n是否继续安装更新？安装后将重启应用程序。`,
      { confirmText: '确认安装', cancelText: '取消', type: 'warning' }
    )
    if (!ok) return toast.info("用户取消安装")
    await _performUpdateAction()
  }

  // 触发操作 (下载 OR 安装)
  const _performUpdateAction = async () => {
    const info = updateState.info
    if (!info) return
    // 如果是 Ready 状态，弹出最后确认框 (因为会重启)
    if (info.local_status === 'ready') {
      const confirmStore = useConfirmStore()
      const ok = await confirmStore.confirmAction(
        "准备重启",
        "安装包已准备就绪。点击确认将关闭当前程序并自动安装更新。",
        { confirmText: '立即重启安装', type: 'warning' }
      )
      if (!ok) return
    }

    // 调用统一接口
    const res = await window.pywebview.api.update_trigger_action()
    if (checkResult(res,'开始下载更新包')) {
      // 如果后端开始下载，这里不需要做什么，因为 EventListener 会接管进度条
      if (res.data && res.data.status === 'downloading') {
        toast.info("开始下载更新包...")
      }
    } else {
      toast.error(res.message)
    }
  }

  return {
    // 更新检查与展示
    checkUpdate, showChangelog,
    // 下载完成安装提示
    _showInstallPrompt,
  }
}
