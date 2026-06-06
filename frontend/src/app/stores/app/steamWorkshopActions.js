import { toast, checkResult } from '../../../shared/lib/common'
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
    if (!window.pywebview) return
    const res = await window.pywebview.api.steamcmd_download(workshop_ids)
    if (checkResult(res, "下载创意工坊项目")) {
      toast.success(`开始下载 ${workshop_ids.length} 个创意工坊项目`)
    }
  }

  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (url) => {
    if(url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      window.open(steamUrl, '_blank')
    }
  }

  const openSteamWorkshopById = (id) => {
    if(id) {
      const steamUrl = `steam://url/CommunityFilePage/${id}`
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
    if (workshopIds.length > 0) {
      await downloadWorkshopItems(workshopIds)
    }
    if (urlSources.length > 0) {
      urlSources.forEach(source => openUrl(source.url))
      toast.info(`已打开 ${urlSources.length} 个外部来源，后续可接入专门下载流程。`)
    }
    return true
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
    await downloadWorkshopItems(workshopIds)
    return true
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
      return true
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    toast.error(`订阅失败: ${res?.message || '未知错误'}`)
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
    // 纯取消订阅必须等 Steam 完成处理；主动删除文件的流程由本函数后续删除步骤负责。
    const shouldWaitForSteamTask = options.waitForTask !== false && normalizedDeleteHashes.length === 0
    if (!options.skipConfirm) {
      const confirmStore = useConfirmStore()
      const message = normalizedDeleteHashes.length > 0
        ? `确定要取消订阅 ${workshop_ids.length} 个创意工坊项目，并删除对应的本地文件吗？\n删除的文件会移入回收站。`
        : `确定要取消订阅 ${workshop_ids.length} 个创意工坊项目吗？\nSteam 完成处理后，列表会自动更新。`
      const ok = await confirmStore.confirmAction('取消订阅', message, {
        type: normalizedDeleteHashes.length > 0 ? 'error' : 'warning',
        confirmText: '确认取消订阅',
      })
      if (!ok) return false
    }
    toast.info('正在连接 Steam...', { timeout: 2500 })
    const res = await window.pywebview.api.steam_unsubscribe(workshop_ids)
    if (res?.status === 'success') {
      const taskId = String(res?.data?.task_id || '')
      let task = null
      toast.info(
        normalizedDeleteHashes.length > 0
          ? '已向 Steam 提交取消订阅，正在删除本地文件...'
          : '已向 Steam 提交取消订阅，正在等待 Steam 完成处理...',
        { timeout: 3500 }
      )
      if (shouldWaitForSteamTask && taskId) {
        try {
          task = await useTaskStore().waitForTaskCompletion(taskId)
        } catch (e) {
          toast.error(`取消订阅未完成：${e.message}`)
          return false
        }
        toast.success('取消订阅成功，正在更新列表...', { timeout: 2500 })
      }
      if (normalizedDeleteHashes.length > 0) {
        const deleteRes = await window.pywebview.api.mods_delete(normalizedDeleteHashes, !!options.force)
        if (deleteRes?.status !== 'success') {
          toast.error(`已向 Steam 提交取消订阅，但本地文件删除失败：${deleteRes?.message || '未知错误'}`)
          return false
        }
        toast.info(`已发送取消订阅请求，并删除 ${deleteRes.data?.success_count || normalizedDeleteHashes.length} 个本地文件`, { timeout: 2500 })
        return { success: true, taskId, task }
      }
      return { success: true, taskId, task }
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    toast.error(`取消订阅失败：${res?.message || '未知错误'}`)
    return false
  }

  // 获取订阅合集列表
  const getCollectionItems = async (collection_id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.steam_collection_items_get(collection_id)
    if (checkResult(res, `获取订阅合集列表 ${collection_id}`)) {
      return res.data
    }
  }

  return {
    // 工坊打开
    openSteamWorkshopUrl, openSteamWorkshopById, openInstallSource,
    // 订阅与下载
    downloadWorkshopItems, subscribeInstallSources, downloadInstallSources,
    downloadPackageIds, subscribePackageIds, subscribeWorkshopIds, unsubscribeWorkshopIds,
    // 合集
    getCollectionItems,
  }
}
