import { toast, checkResult, toUserMessage } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { usePromptQueueStore } from '../../../features/ai/promptQueueStore'

const getUpdateDescriptionFormat = (sourceName = '') => {
  const normalized = String(sourceName || '').trim().toLowerCase()
  if (normalized.includes('github')) return 'markdown'
  if (normalized.includes('蓝奏') || normalized.includes('lanzou')) return 'html'
  return 'text'
}

const getUpdateSources = (info = {}) => {
  const sources = Array.isArray(info.sources) && info.sources.length ? info.sources : [info]
  return sources.filter(source => String(source?.version || info.version || '') === String(info.version || ''))
}

const buildUpdatePromptItems = (info = {}, manual = true) => {
  const sources = getUpdateSources(info)
  return sources.map((source, index) => {
    const sourceName = source.source_name || '未知来源'
    const meta = [
      `来源: ${sourceName}`,
      `文件大小: ${source.file_size || '未知'}`,
      source.local_status === 'ready' ? '已下载' : '',
    ].filter(Boolean)

    return {
      id: `${info.version || 'app-update'}:${sourceName}:${index}`,
      title: `${sourceName} · RimCrow v${source.version || info.version}`,
      description: source.changelog || info.changelog || '发现可用更新。',
      descriptionFormat: getUpdateDescriptionFormat(sourceName),
      meta,
      raw: { ...info, ...source, sources: info.sources },
      actions: index === 0 ? [
        { id: 'update', label: source.local_status === 'ready' ? '立即安装' : '立即更新', kind: 'primary' },
        { id: manual ? 'skip' : 'ignore', label: manual ? '以后再说' : '忽略此版本', kind: 'secondary' },
      ] : [],
    }
  })
}

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
          const sources = getUpdateSources(info)
          const sourceNames = sources.map(source => source.source_name || '未知来源').join('、')
          const promptQueue = usePromptQueueStore()
          await promptQueue.enqueue({
            category: 'startup-app-update',
            title: `发现新版本 v${info.version}`,
            message: sources.length > 1 ? `检测到多个同版本来源: ${sourceNames}。将优先使用第一个来源，失败后自动尝试候补来源。` : `来源: ${sourceNames || '未知来源'}。文件大小: ${info.file_size || '未知'}。`,
            type: 'success',
            priority: manual ? 20 : 50,
            items: buildUpdatePromptItems(info, manual),
            bulkActions: [
              { id: 'update_all', label: info.local_status === 'ready' ? '立即安装' : '立即更新', kind: 'primary' },
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
          if (info.check_status === 'partial') {
            toast.warning("部分更新源暂时不可用，当前可用来源未发现新版本。")
          } else {
            toast.success("当前已是最新版本")
          }
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
    if (!ok) return toast.info("已取消安装更新。")
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
        toast.info("已开始下载更新包，请留意底部状态栏。")
      }
    } else {
      toast.error(toUserMessage(res?.message, '启动更新失败。请检查网络连接、代理设置和安装目录权限，详细原因已写入系统日志。'))
    }
  }

  return {
    // 更新检查与展示
    checkUpdate, showChangelog,
    // 下载完成安装提示
    _showInstallPrompt,
  }
}
