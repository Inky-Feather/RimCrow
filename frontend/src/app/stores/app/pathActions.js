import { toast, checkResult } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { isBrowserRuntime, openManagedSubBrowserUrl } from '../../bridge/runtimeBridge'
import { showUserErrorToast } from '../../../shared/lib/common'
import { t } from '../../../shared/i18n.js'

export const usePathActions = ({ settings, requestModScan } = {}) => {
  // 自动检测路径
  const autoDetectPaths = async (updateStore = false) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths(false)
    if (checkResult(res, t('check.path.auto_detect', '自动检测路径'), true) && res.data.paths) {
       // 更新本地 setting store
      if(updateStore) {
        Object.assign(settings.value, res.data.paths)
        toast.success(t('toast.path.updated', '路径已更新'))
      }
      return res.data.paths
    }
  }

  const getDefaultExternalPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_default_external_paths()
    if (checkResult(res, t('check.path.default_external', '获取默认外部路径'), true) && res.data.paths) {
      return res.data.paths
    }
  }

  // 检测路径信息
  const checkPath = async (path_type, path, options = {}) => {
    if(!path_type || !path) return
    if(!window.pywebview) return
    const res = await window.pywebview.api.path_check(path_type, path, !!options.force)
    if (checkResult(res, t('check.path.check', '检测路径信息'))) {
      return res.data
    }
  }

  // 检测路径信息
  const checkPaths = async (path_data) => {
    if(!path_data) return
    if(!window.pywebview) return
    if (typeof window.pywebview.api.paths_check === 'function') {
      const res = await window.pywebview.api.paths_check(path_data)
      if (checkResult(res, t('check.path.check_batch', '批量检测路径信息'))) {
        return res.data
      }
      return
    }

    // 兼容旧运行态：桌面端已注入的 API 对象可能没有批量检测方法。
    const results = {}
    for (const [pathType, path] of Object.entries(path_data)) {
      if (!String(path || '').trim()) {
        results[pathType] = { pass: false, data: null, type: 'error', msg: t('check.path.empty', '未填写路径') }
        continue
      }
      const res = await window.pywebview.api.path_check(pathType, path, false)
      if (checkResult(res, t('check.path.check', '检测路径信息'), true)) {
        results[pathType] = res.data
      }
    }
    return results
  }

  // 打开路径
  const openPath = async (path) => {
    if(!window.pywebview) return
    if(!path) return
    console.debug("准备打开路径:", path)
    const res = await window.pywebview.api.path_open(path)
    checkResult(res, t('common.action.open_path', '打开路径'))
  }

  const openFile = async (path) => {
    if (!window.pywebview) return
    if (!path) return
    const res = await window.pywebview.api.path_open_file(path)
    checkResult(res, t('common.action.open_file', '打开文件'))
  }

  const readTextFile = async (path, maxBytes = 2 * 1024 * 1024) => {
    if (!window.pywebview) return null
    if (!path) return null
    const res = await window.pywebview.api.path_read_text_file(path, maxBytes)
    if (checkResult(res, t('check.path.read_text_file', '读取文本文件'), false)) {
      return res.data
    }
    return null
  }

  // 获取文件路径
  const getFilePath = async (home_path, file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.file_select_dialog(home_path, file_types)
    if (checkResult(res, t('check.path.select_file', '获取文件路径'))) {
      return res.data
    } else return
  }

  // 获取文件夹路径
  const getFolderPath = async (home_path) => {
    if(!window.pywebview) return
    if(!home_path) home_path=''
    // 调用后端 API
    const res = await window.pywebview.api.folder_select_dialog(home_path)
    if (checkResult(res, t('check.path.select_folder', '获取文件夹路径'))) {
        return res.data
    } else if (res.status === 'error') {
        console.error("获取文件夹路径异常:", res.message)
    }
  }

  // 删除文件/文件夹
  const deletePath = async (path, reScan=true) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const decision = await confirmStore.confirmDeleteAction(
      t('dialog.path.delete.title', '删除确认'),
      t('dialog.path.delete.message', '确定要删除 {path} 吗？', { path }),
      {
        trashOptionText: t('common.action.move_to_trash', '移入回收站'),
        forceOptionText: t('common.action.force_delete', '强制删除'),
      }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.path_delete(path, !!decision.force)
    if (checkResult(res, t('check.path.delete', '删除文件/文件夹'))) {
      toast.success(decision.force
        ? t('toast.path.force_deleted', '已彻底删除: \n{path}', { path })
        : t('toast.path.moved_to_trash', '已移入回收站: \n{path}', { path }))
      if(reScan){
        // 刷新Mod列表
        await requestModScan?.({ forceCoreRefresh: true })
      }
      return true
    }
  }

  // 批量删除文件/文件夹
  const deletePaths = async (paths, options = {}) => {
    if(!window.pywebview) return
    const targetPaths = Array.isArray(paths) ? paths.filter(Boolean) : []
    if (!targetPaths.length) return false
    const {
      title = t('dialog.path.delete.title', '删除确认'),
      message = t('dialog.path.delete.batch_message', '确定要删除这 {count} 个文件/文件夹吗？', { count: targetPaths.length }),
      trashOptionText = t('common.action.move_to_trash', '移入回收站'),
      forceOptionText = t('common.action.force_delete', '强制删除'),
      checkLabel = t('check.path.delete_batch', '批量删除文件/文件夹'),
      successMessage,
      reScan = true,
      allowWarning = false,
    } = options || {}
    const confirmStore = useConfirmStore()
    const decision = await confirmStore.confirmDeleteAction(
      title,
      message,
      { trashOptionText, forceOptionText }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.paths_delete(targetPaths, !!decision.force)
    if (res?.status !== 'success' && !(allowWarning && res?.status === 'warning')) {
      checkResult(res, checkLabel)
      return false
    }
    if (res?.status === 'warning') {
      showUserErrorToast(res, t('toast.path.batch_delete_warning', '{label}完成，但有部分项目需要确认', { label: checkLabel }), { variant: 'warning' })
    } else {
      const messageText = typeof successMessage === 'function'
        ? successMessage({ paths: targetPaths, force: !!decision.force, res })
        : successMessage
      toast.success(messageText || (decision.force
        ? t('toast.path.batch_force_deleted', '已彻底删除 {count} 个文件/文件夹', { count: targetPaths.length })
        : t('toast.path.batch_moved_to_trash', '已移入回收站 {count} 个文件/文件夹', { count: targetPaths.length })))
    }
    if (reScan) {
      // 刷新Mod列表
      await requestModScan?.({ forceCoreRefresh: true })
    }
    return true
  }

  // 打开Url
  const openUrl = (url) => {
    if(!url) { toast.warning(t('toast.path.no_openable_url', '没有可打开的网址。请确认当前条目包含有效链接。')); return}
    if (isBrowserRuntime()) {
      openManagedSubBrowserUrl(url, 'RimCrow')
      return
    }
    if(settings.value.open_url_on_system){
      window.open(url, '_blank')
    }else{
      if (!window.pywebview) return
      window.pywebview.api.open_sub_browser(url)
    }
  }

  return {
    // 路径检测
    autoDetectPaths, getDefaultExternalPaths, checkPath, checkPaths,
    // 打开与选择
    openPath, openFile, readTextFile, getFilePath, getFolderPath, openUrl,
    // 删除
    deletePath, deletePaths,
  }
}
