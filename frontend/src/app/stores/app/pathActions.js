import { toast, checkResult } from '../../../shared/lib/common'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { isBrowserRuntime, openManagedSubBrowserUrl } from '../../bridge/runtimeBridge'

export const usePathActions = ({ settings, requestModScan } = {}) => {
  // 自动检测路径
  const autoDetectPaths = async (updateStore = false) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths(false)
    if (checkResult(res, "自动检测路径", true) && res.data.paths) {
       // 更新本地 setting store
      if(updateStore) {
        Object.assign(settings.value, res.data.paths)
        toast.success("路径已更新")
      }
      return res.data.paths
    }
  }

  const getDefaultExternalPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_default_external_paths()
    if (checkResult(res, "获取默认外部路径",true) && res.data.paths) {
      return res.data.paths
    }
  }

  // 检测路径信息
  const checkPath = async (path_type, path, options = {}) => {
    if(!path_type || !path) return
    if(!window.pywebview) return
    const res = await window.pywebview.api.path_check(path_type, path, !!options.force)
    if (checkResult(res, "检测路径信息")) {
      return res.data
    }
  }

  // 检测路径信息
  const checkPaths = async (path_data) => {
    if(!path_data) return
    if(!window.pywebview) return
    if (typeof window.pywebview.api.paths_check === 'function') {
      const res = await window.pywebview.api.paths_check(path_data)
      if (checkResult(res, "批量检测路径信息")) {
        return res.data
      }
      return
    }

    // 兼容旧运行态：桌面端已注入的 API 对象可能没有批量检测方法。
    const results = {}
    for (const [pathType, path] of Object.entries(path_data)) {
      if (!String(path || '').trim()) {
        results[pathType] = { pass: false, data: null, type: 'error', msg: '未填写路径' }
        continue
      }
      const res = await window.pywebview.api.path_check(pathType, path, false)
      if (checkResult(res, "检测路径信息", true)) {
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
    checkResult(res, "打开路径")
  }

  const openFile = async (path) => {
    if (!window.pywebview) return
    if (!path) return
    const res = await window.pywebview.api.path_open_file(path)
    checkResult(res, '打开文件')
  }

  const readTextFile = async (path, maxBytes = 2 * 1024 * 1024) => {
    if (!window.pywebview) return null
    if (!path) return null
    const res = await window.pywebview.api.path_read_text_file(path, maxBytes)
    if (checkResult(res, '读取文本文件', false)) {
      return res.data
    }
    return null
  }

  // 获取文件路径
  const getFilePath = async (home_path, file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.file_select_dialog(home_path, file_types)
    if (checkResult(res, "获取文件路径")) {
      return res.data
    } else return
  }

  // 获取文件夹路径
  const getFolderPath = async (home_path) => {
    if(!window.pywebview) return
    if(!home_path) home_path=''
    // 调用后端 API
    const res = await window.pywebview.api.folder_select_dialog(home_path)
    if (checkResult(res, "获取文件夹路径")) {
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
      '删除确认', `确定要删除 ${path} 吗？`,
      {
        trashOptionText: '移入回收站',
        forceOptionText: '强制删除',
      }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.path_delete(path, !!decision.force)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`${decision.force ? '已彻底删除' : '已移入回收站'}: \n${path}`)
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
      title = '删除确认',
      message = `确定要删除这 ${targetPaths.length} 个文件/文件夹吗？`,
      trashOptionText = '移入回收站',
      forceOptionText = '强制删除',
      checkLabel = '批量删除文件/文件夹',
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
      toast.warning(res?.message || `${checkLabel}完成，但有部分项目需要确认`)
    } else {
      const messageText = typeof successMessage === 'function'
        ? successMessage({ paths: targetPaths, force: !!decision.force, res })
        : successMessage
      toast.success(messageText || `${decision.force ? '已彻底删除' : '已移入回收站'} ${targetPaths.length} 个文件/文件夹`)
    }
    if (reScan) {
      // 刷新Mod列表
      await requestModScan?.({ forceCoreRefresh: true })
    }
    return true
  }

  // 打开Url
  const openUrl = (url) => {
    if(!url) { toast.warning("没有可打开的网址。请确认当前条目包含有效链接。"); return}
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
