import { toast, checkResult, toUserMessage } from '../../../shared/lib/common'
import { useWorkspaceStore } from '../../../features/workspace/workspaceStore'
import { normalizeInstallSource, normalizeInstallSources } from '../../../features/mod/lib/modIdentity'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useTaskStore } from '../taskStore'

export const useSteamWorkshopActions = ({
  openUrl,
} = {}) => {
  const showSteamNotReadyHint = (res) => {
    const statusHint = res?.data?.steam_status?.user_hint
    if (res?.data?.action === 'steam_not_ready' && statusHint?.message) {
      toast.warning(`${statusHint.title || 'Steam 未就绪'}\n${statusHint.message}`, { timeout: 6000 })
    }
  }

  // 下载创意工坊项目
  const downloadWorkshopItems = async (workshop_ids) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.steamcmd_download(workshop_ids)
    if (checkResult(res, "下载创意工坊项目")) {
      toast.success(`开始下载 ${workshop_ids.length} 个创意工坊项目`)
      return { success: true, taskId: String(res?.data?.task_id || '') }
    }
    return false
  }

  const downloadWorkshopItemsViaSteam = async (workshop_ids, options = {}) => {
    if (!window.pywebview) return false
    if (!workshop_ids || workshop_ids.length === 0) return false
    toast.info('正在连接 Steam。', { timeout: 2500 })
    const res = await window.pywebview.api.steam_workshop_download(
      workshop_ids,
      options.highPriority !== false,
      Number(options.waitSeconds || 30)
    )
    if (res?.status === 'success') {
      const taskId = String(res?.data?.task_id || '')
      let task = null
      toast.info(`已向 Steam 提交 ${workshop_ids.length} 个创意工坊项目的下载请求，正在等待下载完成。`, { timeout: 3500 })
      if (taskId) {
        try {
          task = await useTaskStore().waitForTaskCompletion(taskId)
        } catch (e) {
        toast.error(toUserMessage(e?.message || e, 'Steam 下载未完成。请确认 Steam 已登录并正常联网，或稍后在 Steam 下载队列中查看进度。'))
          return false
        }
      }
      return { success: true, taskId, task }
    }
    if (res?.status === 'warning') {
      if (res?.data?.action === 'steam_not_ready') {
        showSteamNotReadyHint(res)
      } else {
        toast.warning(toUserMessage(res?.message, 'Steam 暂时无法处理工坊下载请求。请确认 Steam 已登录、网络可用，稍后重试。'))
      }
      return false
    }
    toast.error(toUserMessage(res?.message, 'Steam 工坊下载请求失败。请确认 Steam 已登录、网络可用，且目标工坊项目仍可访问。'))
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
      else toast.warning(toUserMessage(res?.message, 'Steam 暂时无法查询工坊详情。请确认 Steam 已登录、网络可用，稍后重试。'))
    }
    return null
  }

  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (url) => {
    if(url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      window.open(steamUrl, '_blank')
    }
  }

  const openSteamWorkshopById = (id, openInSteam = true) => {
    if(id) {
      const steamUrl = openInSteam ? `steam://url/CommunityFilePage/${id}` : `https://steamcommunity.com/sharedfiles/filedetails/?id=${id}`
      window.open(steamUrl, '_blank')
    }
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
    const skippedUrlCount = normalizedSources.filter(source => source.kind === 'url').length
    if (workshopIds.length === 0) {
      if (skippedUrlCount > 0) {
        toast.info('URL 来源暂不支持订阅，只能打开来源页或后续扩展下载流程。')
      }
      return false
    }
    const success = await subscribeWorkshopIds(workshopIds)
    if (success && skippedUrlCount > 0) {
      toast.info(`已跳过 ${skippedUrlCount} 个 URL 来源订阅项`)
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
    const urlSources = normalizedSources.filter(source => source.kind === 'url' && source.url)
    if (workshopIds.length === 0 && urlSources.length === 0) return false
    let downloadResult = null
    if (workshopIds.length > 0) {
      downloadResult = await downloadWorkshopItems(workshopIds)
    }
    if (urlSources.length > 0) {
      urlSources.forEach(source => openUrl(source.url))
      toast.info(`已打开 ${urlSources.length} 个外部来源，后续可接入专门下载流程。`)
    }
    return downloadResult || urlSources.length > 0
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
      toast.info(`已发送 ${workshop_ids.length} 个创意工坊项目的订阅请求`, { timeout: 2500 })
      return { success: true, taskId: String(res?.data?.task_id || '') }
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    toast.error(toUserMessage(res?.message, '订阅失败。请确认 Steam 已登录、网络可用，且目标工坊项目仍可访问。'))
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
        ? `确定要取消订阅 ${workshop_ids.length} 个创意工坊项目，并删除对应的本地文件吗？\n删除的文件会移入回收站。`
        : `确定要取消订阅 ${workshop_ids.length} 个创意工坊项目吗？\nSteam 完成处理后，列表会自动更新。`
      const ok = await confirmStore.confirmAction('取消订阅', message, {
        type: shouldDeleteFiles ? 'error' : 'warning',
        confirmText: '确认取消订阅',
      })
      if (!ok) return false
    }
    toast.info('正在连接 Steam。', { timeout: 2500 })
    const res = await window.pywebview.api.steam_unsubscribe(workshop_ids)
    if (res?.status === 'success') {
      const taskId = String(res?.data?.task_id || '')
      let task = null
      toast.info(
        shouldDeleteFiles
          ? '已向 Steam 提交取消订阅，正在删除本地文件。'
          : '已向 Steam 提交取消订阅，正在等待 Steam 完成处理。',
        { timeout: 3500 }
      )
      if (shouldWaitForSteamTask && taskId) {
        try {
          task = await useTaskStore().waitForTaskCompletion(taskId)
        } catch (e) {
          toast.error(toUserMessage(e?.message || e, '取消订阅未完成。请确认 Steam 已登录并正常联网，稍后刷新订阅状态。'))
          return false
        }
        toast.success('取消订阅成功，正在更新列表。', { timeout: 2500 })
      }
      if (shouldDeleteFiles || shouldCleanupRecordsOnly) {
        const deleteRes = await window.pywebview.api.mods_delete(normalizedDeleteHashes, !!options.force, shouldDeleteFiles)
        if (deleteRes?.status !== 'success') {
          const actionName = shouldDeleteFiles ? '本地文件删除' : '库存记录清理'
          toast.error(toUserMessage(deleteRes?.message, `已向 Steam 提交取消订阅，但${actionName}失败。请检查本地文件权限、文件占用状态和目标路径是否可访问。`))
          return false
        }
        toast.info(
          shouldDeleteFiles
            ? `已发送取消订阅请求，并删除 ${deleteRes.data?.success_count || normalizedDeleteHashes.length} 个本地文件`
            : `已取消订阅，并清理 ${deleteRes.data?.success_count || normalizedDeleteHashes.length} 条库存记录`,
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
    toast.error(toUserMessage(res?.message, '取消订阅失败。请确认 Steam 已登录、网络可用，稍后重试。'))
    return false
  }

  // 获取订阅合集列表
  const getCollectionItems = async (collection_id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.lifecycle_fetch_collection(collection_id)
    if (checkResult(res, `获取订阅合集列表 ${collection_id}`)) {
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
