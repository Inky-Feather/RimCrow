import { toast, checkResult, toUserMessage } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { usePromptQueueStore } from '../../../features/ai/promptQueueStore'
import { t } from '../../../shared/i18n.js'

const getUpdateSources = (info = {}) => {
  const sources = Array.isArray(info.sources) && info.sources.length ? info.sources : [info]
  return sources.filter(source => String(source?.version || info.version || '') === String(info.version || ''))
}

const getUpdateSourceOptions = (info = {}) => {
  const seen = new Set()
  const options = [{ label: t('ui.update.source_auto', '自动选择（推荐）'), value: '' }]
  for (const source of getUpdateSources(info)) {
    const value = String(source?.download_url || '')
    if (!value || seen.has(value)) continue
    seen.add(value)
    options.push({ label: source.source_name || t('common.source.unknown', '未知来源'), value })
  }
  return options
}

export const getUpdateSourceDetails = (info = {}) => {
  if (!info.source_results?.length && !info.has_update) return []
  const results = info.source_results?.length ? info.source_results : getUpdateSources(info).map(source => ({ ...source, status: 'update' }))
  return results.map(result => {
    let value
    if (result.status === 'failed') value = result.error || t('ui.update.source_failed', '暂时无法检查')
    else if (result.status === 'no_package') value = t('ui.update.source_no_package', '没有适用的安装包')
    else if (result.status === 'no_release') value = t('ui.update.source_no_release', '尚未发布版本')
    else if (result.version && info.has_update && result.version !== info.version) value = t('ui.update.source_older', '尚未同步目标版本（v{version}）', { version: result.version })
    else if (result.status === 'update') value = t('ui.update.source_available', '发现新版本 v{version}', { version: result.version || info.version })
    else value = t('ui.update.source_no_update', '未发现新版本')
    if (result.access_path === 'builtin_mirror') value += t('ui.update.via_builtin_mirror', ' · 通过内置镜像读取')
    return { label: result.source_name || t('common.source.unknown', '未知来源'), value }
  })
}

export const getUpdateStatusText = (state = {}) => {
  if (state.isChecking) return t('ui.update.checking_sources', '正在检查更新来源…')
  if (state.checkError) return state.checkError
  if (!state.lastCheckedAt) return t('ui.update.not_checked', '尚未检查更新')
  if (state.info?.local_status === 'downloading') return t('ui.update.downloading', '正在下载更新，进度可在任务栏查看')
  if (state.info?.local_status === 'ready') return t('ui.update.ready', '安装包已就绪，可稍后安装')
  if (state.hasUpdate) return t('ui.update.version_available', '发现新版本 v{version}', { version: state.info?.version })
  if (state.info?.check_status === 'partial') return t('toast.update.partial_no_update', '部分更新源暂时不可用，当前可用来源未发现新版本。')
  return t('ui.update.no_compatible_update', '未发现适用于当前系统的新版本')
}

const buildUpdatePromptItems = (info = {}) => {
  const sources = getUpdateSources(info)
  const changelogSource = sources.find(source => source.source_name === 'GitHub' && source.changelog) || sources.find(source => source.changelog) || info
  return [{
    id: `app-update:${info.version}`,
    title: `RimCrow v${info.version}`,
    description: changelogSource.changelog || t('ui.update.available_desc', '发现可用更新。'),
    descriptionFormat: 'markdown',
    meta: [t('ui.update.file_size_meta', '文件大小: {size}', { size: info.file_size || t('common.status.unknown', '未知') }),
      info.local_status === 'ready' ? t('ui.update.downloaded', '已下载') : ''].filter(Boolean),
    detailsTitle: t('ui.update.source_details', '来源详情'),
    details: getUpdateSourceDetails(info),
    raw: info,
    actions: [],
  }]
}

export const useUpdateActions = ({
  updateState,
  upgradeContext,
  isLoading,
  uiState,
  logMaintenanceCheck,
} = {}) => {
  let isPromptPending = false

  const showAvailableUpdate = async (manual = true) => {
    const info = updateState.info
    if (!info?.has_update || isPromptPending) return
    isPromptPending = true
    try {
      await usePromptQueueStore().enqueue({
        category: 'startup-app-update',
        title: t('ui.update.new_version_title', '发现新版本 v{version}', { version: info.version }),
        message: [info.local_status === 'ready' ? t('ui.update.ready', '安装包已就绪，可稍后安装') : t('ui.update.auto_source_message', '下载失败时会自动尝试备用地址。若仍无法下载，可前往“设置 → 关于项目”的下载地址手动获取适用于当前系统的安装包，退出软件后解压并覆盖安装目录。'),
          info.check_status === 'partial' ? t('ui.update.partial_available', '部分来源暂时无法检查，不影响使用已发现的更新。') : ''].filter(Boolean).join('\n'),
        type: 'success',
        priority: manual ? 20 : 50,
        items: buildUpdatePromptItems(info),
        actionSelector: info.local_status === 'ready' ? null : {
          label: t('ui.update.source_selector', '下载来源'),
          value: '',
          options: getUpdateSourceOptions(info),
        },
        bulkActions: [
          ...(info.local_status === 'ready'
            ? [{ id: 'update', label: t('ui.update.install_now', '立即安装'), kind: 'primary' }]
            : [{ id: 'download', label: t('ui.update.download_update', '下载更新'), kind: 'primary' }]),
          { id: 'skip', label: t('ui.update.later', '以后再说'), kind: 'secondary' },
          ...(!manual ? [{ id: 'ignore', label: t('ui.update.ignore_version', '忽略此版本'), kind: 'secondary' }] : []),
        ],
        onBulkAction: async (actionId, _items, _prompt, selection = '') => {
          if (actionId === 'update') {
            if (info.local_status === 'ready') await _showInstallPrompt({ path: info.local_file_path, version: info.version })
          }
          else if (actionId === 'download') {
            const selectedSource = getUpdateSources(info).find(source => source.download_url === selection) || null
            await _performUpdateAction(info.version, selectedSource)
          }
          else if (actionId === 'ignore') await window.pywebview.api.update_ignore_version(info.version)
        },
      })
    } finally {
      isPromptPending = false
    }
  }

  // 检查更新
  const checkUpdate = async (manual = true) => {
    if (updateState.isChecking || isPromptPending) return
    updateState.isChecking = true
    updateState.checkError = ''
    logMaintenanceCheck('api_start', { id: 'app-update', name: '软件更新', manual })
    try {
      const res = await window.pywebview.api.update_check(manual)
      if (checkResult(res, t('check.update.check', '检查更新'))) {
        const info = res.data
        updateState.lastCheckedAt = Date.now()
        updateState.hasUpdate = !!info.has_update
        updateState.info = info
        updateState.isChecking = false
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res.status, hasUpdate: !!info?.has_update, version: info?.version || '', localStatus: info?.local_status || '' })
        if (info.has_update && (manual || !info.is_ignored) && info.local_status !== 'downloading') {
          await showAvailableUpdate(manual)
        } else if (manual && !info.has_update) {
          if (info.check_status === 'partial') {
            toast.warning(t('toast.update.partial_no_update', '部分更新源暂时不可用，当前可用来源未发现新版本。'))
          } else {
            toast.success(t('ui.update.no_compatible_update', '未发现适用于当前系统的新版本'))
          }
        }
      } else {
        updateState.checkError = toUserMessage(res, t('ui.update.check_failed', '无法检查更新，请稍后重试。'))
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res?.status || 'error', message: res?.message || '' }, 'warn')
      }
    } catch (error) {
      updateState.checkError = toUserMessage(error, t('ui.update.check_failed', '无法检查更新，请稍后重试。'))
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
    const expectedVersion = data.version || updateState.info?.version
    const confirmStore = useConfirmStore()
    const ok = await confirmStore.confirmAction(
      t('dialog.update.confirm_install_title', '确认安装更新？'),
      t('dialog.update.confirm_install_message', '压缩包已经下载到：{path}\n是否继续安装更新？安装后将重启应用程序。', { path: data.path }),
      { confirmText: t('dialog.update.confirm_install', '确认安装'), cancelText: t('common.action.cancel', '取消'), type: 'warning' }
    )
    if (!ok) return toast.info(t('toast.update.install_cancelled', '已取消安装更新。'))
    await _performUpdateAction(expectedVersion)
  }

  // 触发操作 (下载 OR 安装)
  const _performUpdateAction = async (expectedVersion = updateState.info?.version, selectedSource = null) => {
    const info = updateState.info
    if (!info) return
    if (expectedVersion !== info.version) return toast.warning(t('ui.update.result_changed', '更新信息已变化，请重新查看更新。'))
    let isInstallConfirmed = false
    // 如果是 Ready 状态，弹出最后确认框 (因为会重启)
    if (info.local_status === 'ready') {
      const confirmStore = useConfirmStore()
      const ok = await confirmStore.confirmAction(
        t('dialog.update.ready_restart_title', '准备重启'),
        t('dialog.update.ready_restart_message', '安装包已准备就绪。点击确认将关闭当前程序并自动安装更新。'),
        { confirmText: t('dialog.update.restart_install', '立即重启安装'), type: 'warning' }
      )
      if (!ok) return
      isInstallConfirmed = true
    }

    // 调用统一接口
    const res = await window.pywebview.api.update_trigger_action(expectedVersion, isInstallConfirmed, selectedSource?.download_url || '')
    if (checkResult(res, t('check.update.start_download', '开始下载更新包'))) {
      if (res.data?.status === 'ready') {
        info.local_status = 'ready'
        info.local_file_path = res.data.path
        await _showInstallPrompt(res.data)
      }
      // 如果后端开始下载，这里不需要做什么，因为 EventListener 会接管进度条
      if (res.data && res.data.status === 'downloading' && info.local_status !== 'ready') {
        info.local_status = 'downloading'
        toast.info(t('toast.update.download_started', '已开始下载更新包，请留意底部状态栏。'))
      }
    }
  }

  return {
    // 更新检查与展示
    checkUpdate, showChangelog, showAvailableUpdate,
    // 下载完成安装提示
    _showInstallPrompt,
  }
}
