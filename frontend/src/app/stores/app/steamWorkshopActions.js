import { toast, checkResult, showUserErrorToast, toUserMessage } from '../../../shared/lib/common'
import { useWorkspaceStore } from '../../../features/workspace/workspaceStore'
import { normalizeInstallSource, normalizeInstallSources } from '../../../features/mod/lib/modIdentity'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useTaskStore } from '../taskStore'
import { dispatchSteamUri, openWorkshopPage } from '../../../shared/lib/steamUri'
import { t } from '../../../shared/i18n.js'

export const useSteamWorkshopActions = ({
  openUrl,
} = {}) => {
  const showSteamNotReadyHint = (res) => {
    const statusHint = res?.data?.steam_status?.user_hint
    if (res?.data?.action === 'steam_not_ready' && statusHint?.message) {
      toast.warning(`${statusHint.title || t('steam.status.not_ready', 'Steam 未就绪')}\n${statusHint.message}`, { timeout: 6000 })
    }
  }

  // 下载创意工坊项目
  const downloadWorkshopItems = async (workshop_ids) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.steamcmd_download(workshop_ids)
    if (checkResult(res, t('check.steam.download_workshop_items', '下载创意工坊项目'))) {
      toast.success(t('toast.steam.download_started', '开始下载 {count} 个创意工坊项目', { count: workshop_ids.length }))
      return { success: true, taskId: String(res?.data?.task_id || '') }
    }
    return false
  }

  const downloadWorkshopItemsViaSteam = async (workshop_ids, options = {}) => {
    if (!window.pywebview) return false
    if (!workshop_ids || workshop_ids.length === 0) return false
    toast.info(t('toast.steam.connecting', '正在连接 Steam。'), { timeout: 2500 })
    const res = await window.pywebview.api.steam_workshop_download(
      workshop_ids,
      options.highPriority !== false,
      Number(options.waitSeconds || 30)
    )
    if (res?.status === 'success') {
      const taskId = String(res?.data?.task_id || '')
      let task = null
      toast.info(t('toast.steam.download_submitted_waiting', '已向 Steam 提交 {count} 个创意工坊项目的下载请求，正在等待下载完成。', { count: workshop_ids.length }), { timeout: 3500 })
      if (taskId) {
        try {
          task = await useTaskStore().waitForTaskCompletion(taskId)
        } catch (e) {
          if (!e?.from_task) showUserErrorToast(e, t('toast.steam.download_incomplete', 'Steam 下载未完成。请确认 Steam 已登录并正常联网，或稍后在 Steam 下载队列中查看进度。'))
          return false
        }
      }
      return { success: true, taskId, task }
    }
    if (res?.status === 'warning') {
      if (res?.data?.action === 'steam_not_ready') {
        showSteamNotReadyHint(res)
      } else {
        toast.warning(toUserMessage(res, t('toast.steam.download_temporarily_unavailable', 'Steam 暂时无法处理工坊下载请求。请确认 Steam 已登录、网络可用，稍后重试。')))
      }
      return false
    }
    showUserErrorToast(res, t('toast.steam.download_failed', 'Steam 工坊下载请求失败。请确认 Steam 已登录、网络可用，且目标工坊项目仍可访问。'))
    return false
  }

  const querySteamWorkshopDetails = async (workshop_ids, options = {}) => {
    if (!window.pywebview) return null
    if (!workshop_ids || workshop_ids.length === 0) return null
    const res = await window.pywebview.api.steam_workshop_details(
      workshop_ids,
      Number(options.waitSeconds || 20)
    )
    if (res?.status === 'success') return res.data
    if (res?.status === 'warning') {
      if (res?.data?.action === 'steam_not_ready') showSteamNotReadyHint(res)
      else toast.warning(toUserMessage(res, t('toast.steam.details_temporarily_unavailable', 'Steam 暂时无法查询工坊详情。请确认 Steam 已登录、网络可用，稍后重试。')))
    }
    return null
  }

  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (url) => {
    if (url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      void dispatchSteamUri(steamUrl)
    }
  }

  const openSteamWorkshopById = (id, openInSteam = true) => {
    if (id) {
      void openWorkshopPage(id, openInSteam)
      return true
    }
    return false
  }

  const openInstallSource = (source) => {
    const normalizedSource = normalizeInstallSource(source, source?.packageId || source?.package_id)
    if (!normalizedSource) return false
    if (normalizedSource.kind === 'workshop') {
      openSteamWorkshopById(normalizedSource.workshopId)
      return true
    }
    openUrl(normalizedSource.url)
    return true
  }

  const subscribeInstallSources = async (sources = []) => {
    const normalizedSources = normalizeInstallSources(sources)
    const workshopIds = [...new Set(
      normalizedSources
        .filter(source => source.kind === 'workshop')
        .map(source => source.workshopId)
        .filter(Boolean)
    )]
    const gitSources = normalizedSources.filter(source => source.kind === 'git' && source.url)
    const skippedUrlCount = normalizedSources.filter(source => source.kind === 'url').length
    if (workshopIds.length === 0 && gitSources.length === 0) {
      if (skippedUrlCount > 0) {
        toast.info(t('toast.steam.url_source_subscribe_unsupported', 'URL 来源暂不支持订阅，只能打开来源页或后续扩展下载流程。'))
      }
      return false
    }
    const workshopSuccess = workshopIds.length > 0 ? await subscribeWorkshopIds(workshopIds) : null
    const gitSuccess = gitSources.length > 0 ? await subscribeGitInstallSources(gitSources) : null
    const success = workshopSuccess || gitSuccess
    if (success && skippedUrlCount > 0) {
      toast.info(t('toast.steam.url_source_subscribe_skipped', '已跳过 {count} 个 URL 来源订阅项', { count: skippedUrlCount }))
    }
    return success
  }

  const downloadInstallSources = async (sources = []) => {
    const normalizedSources = normalizeInstallSources(sources)
    const workshopIds = [...new Set(
      normalizedSources
        .filter(source => source.kind === 'workshop')
        .map(source => source.workshopId)
        .filter(Boolean)
    )]
    const gitSources = normalizedSources.filter(source => source.kind === 'git' && source.url)
    const urlSources = normalizedSources.filter(source => source.kind === 'url' && source.url)
    if (workshopIds.length === 0 && gitSources.length === 0 && urlSources.length === 0) return false
    let downloadResult = null
    if (workshopIds.length > 0) {
      downloadResult = await downloadWorkshopItems(workshopIds)
    }
    const gitResult = gitSources.length > 0 ? await subscribeGitInstallSources(gitSources) : null
    if (urlSources.length > 0) {
      urlSources.forEach(source => openUrl(source.url))
      toast.info(t('toast.steam.url_sources_opened', '已打开 {count} 个外部来源，后续可接入专门下载流程。', { count: urlSources.length }))
    }
    return downloadResult || gitResult || urlSources.length > 0
  }

  const safeUrlHost = (url = '') => {
    try {
      return new URL(String(url || '')).hostname
    } catch {
      return ''
    }
  }

  const buildGitSubscribePayload = (source) => {
    const info = source.info && typeof source.info === 'object' ? source.info : {}
    return {
      url: source.url,
      owner: info.owner || info.source_id || 'catalog',
      repo: info.repo || info.name || source.packageId || 'catalog_mod',
      provider: info.provider || '',
      host: info.host || safeUrlHost(source.url),
      default_branch: source.defaultBranch || info.branch || '',
      install_type: source.installType || info.install_type || (info.type === 'zip' ? 'zip' : 'source'),
      installed_version: '',
      info: {
        ...info,
        package_id: info.package_id || source.packageId,
        name: info.name || source.title,
      },
    }
  }

  const subscribeGitInstallSources = async (sources = []) => {
    if (!window.pywebview) return false
    let successCount = 0
    for (const source of sources) {
      const res = await window.pywebview.api.github_subscribe(buildGitSubscribePayload(source))
      if (checkResult(res, t('check.github.subscribe_install_source', '订阅 Git 来源'), false, { silent: sources.length > 1 })) {
        successCount += 1
      }
    }
    if (successCount > 0) {
      toast.info(t('toast.github.install_source_submitted', '已提交 {count} 个 Git 来源订阅，正在开始下载。', { count: successCount }), { timeout: 3000 })
      return { success: true }
    }
    return false
  }

  const resolveWorkshopIdsFromPackageIds = async (packageIds) => {
    if (!packageIds) return []
    const workshopStore = useWorkspaceStore()
    return await workshopStore.resolvePackageIdsToWorkshopIds(packageIds)
  }

  // 根据包名下载Mod
  const downloadPackageIds = async (packageIds) => {
    const workshopIds = await resolveWorkshopIdsFromPackageIds(packageIds)
    if (workshopIds.length === 0) return false
    // 调用下载函数
    return await downloadWorkshopItems(workshopIds)
  }

  // 根据包名订阅Mod
  const subscribePackageIds = async (packageIds) => {
    const workshopIds = await resolveWorkshopIdsFromPackageIds(packageIds)
    if (workshopIds.length === 0) return false
    // 调用订阅函数
    await subscribeWorkshopIds(workshopIds)
    return true
  }

  // 订阅模组
  const subscribeWorkshopIds = async (workshop_ids) => {
    if (!window.pywebview) return
    if (!workshop_ids || workshop_ids.length === 0) return
    const res = await window.pywebview.api.steam_subscribe(workshop_ids)
    if (res?.status === 'success') {
      toast.info(t('toast.steam.subscribe_submitted', '已发送 {count} 个创意工坊项目的订阅请求', { count: workshop_ids.length }), { timeout: 2500 })
      return { success: true, taskId: String(res?.data?.task_id || '') }
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    showUserErrorToast(res, t('toast.steam.subscribe_failed', '订阅失败。请确认 Steam 已登录、网络可用，且目标工坊项目仍可访问。'))
    return false
  }

  // 取消订阅模组
  const unsubscribeWorkshopIds = async (workshop_ids, deletePathHashes = null, deleteOptions = {}) => {
    if (!window.pywebview) return false
    if (!workshop_ids || workshop_ids.length === 0) return
    const options = deleteOptions || {}
    const normalizedDeleteHashes = Array.isArray(deletePathHashes)
      ? deletePathHashes.filter(Boolean)
      : []
    const shouldDeleteFiles = normalizedDeleteHashes.length > 0 && options.deleteFiles !== false
    const shouldCleanupRecordsOnly = normalizedDeleteHashes.length > 0 && options.deleteFiles === false
    // 纯取消订阅必须等 Steam 完成处理；主动删除文件的流程由本函数后续删除步骤负责。
    const shouldWaitForSteamTask = options.waitForTask !== false && !shouldDeleteFiles
    if (!options.skipConfirm) {
      const confirmStore = useConfirmStore()
      const message = shouldDeleteFiles
        ? t('dialog.steam.unsubscribe_delete_message', '确定要取消订阅 {count} 个创意工坊项目，并删除对应的本地文件吗？\n删除的文件会移入回收站。', { count: workshop_ids.length })
        : t('dialog.steam.unsubscribe_message', '确定要取消订阅 {count} 个创意工坊项目吗？\nSteam 完成处理后，列表会自动更新。', { count: workshop_ids.length })
      const ok = await confirmStore.confirmAction(t('dialog.steam.unsubscribe_title', '取消订阅'), message, {
        type: shouldDeleteFiles ? 'error' : 'warning',
        confirmText: t('dialog.steam.unsubscribe_confirm', '确认取消订阅'),
      })
      if (!ok) return false
    }
    toast.info(t('toast.steam.connecting', '正在连接 Steam。'), { timeout: 2500 })
    const res = await window.pywebview.api.steam_unsubscribe(workshop_ids)
    if (res?.status === 'success') {
      const taskId = String(res?.data?.task_id || '')
      let task = null
      toast.info(
        shouldDeleteFiles
          ? t('toast.steam.unsubscribe_submitted_deleting', '已向 Steam 提交取消订阅，正在删除本地文件。')
          : t('toast.steam.unsubscribe_submitted_waiting', '已向 Steam 提交取消订阅，正在等待 Steam 完成处理。'),
        { timeout: 3500 }
      )
      if (shouldWaitForSteamTask && taskId) {
        try {
          task = await useTaskStore().waitForTaskCompletion(taskId)
        } catch (e) {
          if (!e?.from_task) showUserErrorToast(e, t('toast.steam.unsubscribe_incomplete', '取消订阅未完成。请确认 Steam 已登录并正常联网，稍后刷新订阅状态。'))
          return false
        }
        toast.success(t('toast.steam.unsubscribe_success_refreshing', '取消订阅成功，正在更新列表。'), { timeout: 2500 })
      }
      if (shouldDeleteFiles || shouldCleanupRecordsOnly) {
        const deleteRes = await window.pywebview.api.mods_delete(normalizedDeleteHashes, !!options.force, shouldDeleteFiles)
        if (deleteRes?.status !== 'success') {
          const actionName = shouldDeleteFiles ? t('steam.action.local_file_delete', '本地文件删除') : t('steam.action.inventory_cleanup', '库存记录清理')
          showUserErrorToast(deleteRes, t('toast.steam.unsubscribe_followup_failed', '已向 Steam 提交取消订阅，但{action}失败。请检查本地文件权限、文件占用状态和目标路径是否可访问。', { action: actionName }))
          return false
        }
        toast.info(
          shouldDeleteFiles
            ? t('toast.steam.unsubscribe_deleted_files', '已发送取消订阅请求，并删除 {count} 个本地文件', { count: deleteRes.data?.success_count || normalizedDeleteHashes.length })
            : t('toast.steam.unsubscribe_cleaned_records', '已取消订阅，并清理 {count} 条库存记录', { count: deleteRes.data?.success_count || normalizedDeleteHashes.length }),
          { timeout: 2500 }
        )
        return { success: true, taskId, task }
      }
      return { success: true, taskId, task }
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    showUserErrorToast(res, t('toast.steam.unsubscribe_failed', '取消订阅失败。请确认 Steam 已登录、网络可用，稍后重试。'))
    return false
  }

  // 获取订阅合集列表
  const getCollectionItems = async (collection_id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.lifecycle_fetch_collection(collection_id)
    if (checkResult(res, t('check.steam.fetch_collection_items', '获取订阅合集列表 {collectionId}', { collectionId: collection_id }))) {
      return res.data?.children || []
    }
  }

  return {
    // 工坊打开
    openSteamWorkshopUrl, openSteamWorkshopById, openInstallSource,
    // 订阅与下载
    downloadWorkshopItems, subscribeInstallSources, downloadInstallSources,
    downloadPackageIds, subscribePackageIds, subscribeWorkshopIds, unsubscribeWorkshopIds,
    downloadWorkshopItemsViaSteam, querySteamWorkshopDetails,
    // 合集
    getCollectionItems,
  }
}
