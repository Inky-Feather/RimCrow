import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useModStore } from './modStore'
import { useAppStore } from './appStore'
import { useConfirmStore } from './confirmStore'

export const useOrderStore = defineStore('order', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const modStore = useModStore()
  const confirmStore = useConfirmStore()
  const checkResult = appStore.checkResult
  
  // === State ===
  const backups = ref(null)           // 备份文件列表
  const backupProfileId = ref('')     // 当前查看的备份所属环境
  const backupProfileDir = ref('')    // 当前查看环境的备份目录
  const backupIds = ref([])           // 当前备份的排序列表
  const backupMods = ref([])          // 当前备份/导入文件的模组明细
  const currentBackupFile = ref('')   // 当前备份文件
  const backupLoadModifyTime = ref(0) // 备份加载顺序修改时间
  const currentBackupFormat = ref('') // 当前备份文件格式
  const currentBackupName = ref('')   // 当前备份/导入列表名称
  const currentBackupSourceProfileId = ref('') // 当前对比文件来源于哪个环境；空串表示外部导入
  const currentBackupWorkshopIds = ref([]) // 文件中直接给出的 workshop id 列表
  const currentBackupWarnings = ref([]) // 解析时的非致命提示
  const currentBackupErrors = ref([])   // 解析时的错误信息
  const currentImportCheck = ref({ summary: {}, items: [] }) // 后端返回的导入检查分类报告

  const backupNameMap = computed(() => {
    // 记录“包名 -> 导入文件中的显示名称”，供差异视图在本地缺失时兜底显示。
    return Object.fromEntries(
      backupMods.value
        .map(mod => [String(mod.package_id || '').toLowerCase(), mod.name || mod.package_id])
        .filter(([packageId]) => packageId)
    )
  })
  const importCheckItems = computed(() => currentImportCheck.value?.items || [])
  const importCheckSummary = computed(() => ({
    exact_match: currentImportCheck.value?.summary?.exact_match || 0,
    package_match: currentImportCheck.value?.summary?.package_match || 0,
    replacement: currentImportCheck.value?.summary?.replacement || 0,
    other_version: currentImportCheck.value?.summary?.other_version || 0,
    missing: currentImportCheck.value?.summary?.missing || 0,
    unknown: currentImportCheck.value?.summary?.unknown || 0,
  }))
  const importCheckMap = computed(() => {
    return new Map(
      importCheckItems.value.map(item => [String(item.row_key || item.package_id || '').trim().toLowerCase(), item])
    )
  })
  const problemImportItems = computed(() =>
    importCheckItems.value.filter(item => ['missing', 'replacement', 'other_version', 'unknown'].includes(item.status))
  )
  const missingImportItems = computed(() =>
    importCheckItems.value.filter(item => item.status === 'missing')
  )
  const replacementImportItems = computed(() =>
    importCheckItems.value.filter(item => item.status === 'replacement')
  )
  const actionableReplacementImportItems = computed(() =>
    replacementImportItems.value.filter(item => !item.installed_via_replacement)
  )
  const otherVersionImportItems = computed(() =>
    importCheckItems.value.filter(item => item.status === 'other_version')
  )
  const unknownImportItems = computed(() =>
    importCheckItems.value.filter(item => item.status === 'unknown')
  )
  const nonImportableImportItems = computed(() =>
    importCheckItems.value.filter(item => item.origin_kind === 'workshop_only')
  )
  const backupDisplayIds = computed(() => {
    if (importCheckItems.value.length > 0) {
      return importCheckItems.value.map(item => String(item.row_key || item.package_id || '').trim()).filter(Boolean)
    }
    return backupIds.value
  })

  const setBackupOrder = (order = {}, fallbackPath = '') => {
    // 把导入文件的排序、格式和模组明细一次性落到 store，避免多个组件重复解析。
    backupIds.value = order.active_ids || []
    backupMods.value = order.mods || []
    currentBackupFile.value = order.file || fallbackPath || ''
    backupLoadModifyTime.value = order.modify_time || 0
    currentBackupFormat.value = order.format || ''
    currentBackupName.value = order.list_name || ''
    currentBackupSourceProfileId.value = order.source_profile_id || ''
    currentBackupWorkshopIds.value = order.workshop_ids || []
    currentBackupWarnings.value = order.warnings || []
    currentBackupErrors.value = order.errors || []
    currentImportCheck.value = order.import_check || { summary: {}, items: [] }
  }
  const clearBackupOrder = () => {
    setBackupOrder({}, '')
  }
  const setBackupProfile = (profileId = '', meta = null) => {
    backupProfileId.value = profileId || ''
    if (meta && Object.prototype.hasOwnProperty.call(meta, 'backup_dir')) {
      backupProfileDir.value = meta.backup_dir || ''
    }
  }

  // === Actions ===
  // 获取加载顺序
  const getLoadOrder = async (mods_config_file_path=null, source_profile_id='') => {
    const order = await getFileOrder(mods_config_file_path, source_profile_id)
    if (order) {
      const shouldContinue = await confirmImportStripping(order.import_check)
      if (!shouldContinue) return false
      // 后端现在统一返回 modify_time。
      // active_load_modify_time 保留兼容旧数据结构，优先兼容旧接口，缺失时回退到新字段。
      await modStore.runListHistoryTransaction({
        type: 'load-order',
        label: '加载文件序列'
      }, async () => {
        modStore.setListIds('active', order.active_ids || [])
        modStore.savedActiveIds = [...(order.active_ids || [])]
        modStore.activeLoadModifyTime = order.active_load_modify_time || order.modify_time || 0
        modStore.updateInactiveIds()
        // 加载外部存档文件时解析未知项
        modStore.fetchAndCacheGhostMods(modStore.activeIds)
      })
      toast.success("Mod序列已加载")
      return true
    }
    return false
  }
  // 获取备份加载顺序
  const getBackupOrder = async (mods_config_file_path=null, source_profile_id='') => {
    const order = await getFileOrder(mods_config_file_path, source_profile_id)
    if (order) {
      // 除了 active_ids 之外，还要把格式、列表名和结构化明细一起缓存下来，
      // 后面 diff 抽屉显示标题、名称和一键订阅都依赖这些字段。
      setBackupOrder(order, mods_config_file_path)

      // 解析器已经把“可读但不致命”的问题放在 warnings 里，这里直接提示用户。
      if ((order.warnings || []).length > 0) {
        toast.info(`导入完成，但有 ${order.warnings.length} 条提示`, { timeout: 1800 })
      }

      return {
        path: currentBackupFile.value,
        modify_time: backupLoadModifyTime.value,
        format: currentBackupFormat.value,
        list_name: currentBackupName.value,
        source_profile_id: currentBackupSourceProfileId.value,
        workshop_ids: [...currentBackupWorkshopIds.value],
        warnings: [...currentBackupWarnings.value],
        errors: [...currentBackupErrors.value],
        import_check: currentImportCheck.value,
      }
      // toast.success("备份Mod序列已加载")
    }
  }
  // 应用备份列表
  const applyBackup = async () => {
    const shouldContinue = await confirmImportStripping(currentImportCheck.value, backupIds.value)
    if (!shouldContinue) return false
    if (!backupIds.value) return false
    await modStore.runListHistoryTransaction({
      type: 'apply-backup',
      label: '应用文件序列'
    }, async () => {
      modStore.setListIds('active', backupIds.value)
      modStore.updateInactiveIds()
      // 加载外部存档文件时解析未知项
      modStore.fetchAndCacheGhostMods(modStore.activeIds)
    })
    toast.success("已应用Mod序列")
    return true
  }
  // 保存停用列表顺序
  const saveInactiveOrder = async () => {
    const modStore = useModStore()
    if (!window.pywebview) return false
    appStore.isLoading = true
    try {
      // Temp 列表如果有关闭软件前未处理的，归入 Inactive 末尾保存
      const finalInactive = [...modStore.inactiveIds, ...modStore.tempIds]
      // 过滤掉已经在 Active 里的防止出错
      const activeSet = new Set(modStore.activeIds.map(id=>id.toLowerCase()))
      const cleanInactive = finalInactive.filter(id => !activeSet.has(id.toLowerCase()))
      const res = await window.pywebview.api.load_order_inactive_save(cleanInactive)
      if (checkResult(res, "保存停用列表顺序")) {
        modStore.savedInactiveIds = [...cleanInactive] || []
        modStore.updateInactiveIds()
        return true
      }
    } finally {
      appStore.isLoading = false
    }
    return false
  }
  // 保存Mod加载顺序
  const saveLoadOrder = async () => {
    const modStore = useModStore()
    // if (!modStore.isDirty) {
    //   setTimeout(() => {
    //     toast.info("Mod序列未修改无须保存",{timeout: 1000})
    //   }, 100);
    //   // return true
    // }
    if (!window.pywebview) return false
    appStore.isLoading = true
    try {
      // 使用默认路径
      const res = await window.pywebview.api.load_order_save(modStore.activeIds, modStore.isDirty)
      if (checkResult(res, "保存Mod加载顺序", true)) {
        modStore.savedActiveIds = [...modStore.activeIds] || []
        await saveInactiveOrder()
        modStore.updateInactiveIds()
        // 保存始终写当前环境；这里仅刷新当前正在查看的备份列表，不强行切换筛选环境。
        getBackups(backupProfileId.value || appStore.settings.current_profile_id || null)
        modStore.updateModTime() // 更新Mod最后操作时间
        return true
      }
    } finally {
      appStore.isLoading = false
    }
    return false
  }
  // 导出Mod加载顺序
  const exportLoadOrder = async (target_path=null, trigger_dialog=true, export_format='modsconfig', list_name=null) => {
    if (!window.pywebview) return false
    try {
      // 导出格式和列表名都直接传给后端，让后端决定写出 ModsConfig.xml 还是 ModList.xml。
      const res = await window.pywebview.api.load_order_export(modStore.activeIds, target_path, trigger_dialog, export_format, list_name)
      if (checkResult(res, "导出Mod加载顺序")) {
        // console.log("导出加载顺序成功:", res)
        toast.success("Mod序列已导出")
        return true
      } 
    } catch (e) {
      console.error("导出Mod序列异常:", e)
      toast.error(`导出Mod序列异常: \n${e.message}`)
    } 
    return false
  }
  const copyTextToClipboard = async (text) => {
    const value = String(text || '')
    if (!value) return false
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value)
        return true
      }
    } catch (error) {
      console.warn('Clipboard API copy failed:', error)
    }

    try {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.setAttribute('readonly', 'readonly')
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(textarea)
      return copied
    } catch (error) {
      console.warn('Fallback copy failed:', error)
      return false
    }
  }
  const exportLoadOrderShareCode = async (list_name = null) => {
    if (!window.pywebview) return ''
    if (!modStore.activeIds || modStore.activeIds.length === 0) {
      toast.warning('当前没有可分享的启用序列')
      return ''
    }
    try {
      const res = await window.pywebview.api.load_order_share_export(modStore.activeIds, list_name)
      if (!checkResult(res, '生成分享码')) return ''

      const shareCode = res.data?.share_code || ''
      if (!shareCode) {
        toast.error('后端没有返回有效的分享码')
        return ''
      }

      const copied = await copyTextToClipboard(shareCode)
      await confirmStore.open({
        title: copied ? '分享码已复制' : '分享码已生成',
        message: copied
          ? `已生成 ${res.data?.count || modStore.activeIds.length} 个模组的分享码，并已复制到剪贴板。`
          : '自动复制失败，请手动复制下面的分享码。',
        mode: 'prompt',
        type: copied ? 'success' : 'warning',
        inputValue: shareCode,
        placeholder: 'RMM1-...',
        confirmText: '关闭',
        cancelText: '取消',
      })
      return shareCode
    } catch (e) {
      console.error('生成分享码异常:', e)
      toast.error(`生成分享码异常: \n${e.message}`)
    }
    return ''
  }
  // 从文件获取加载顺序
  const getFileOrder = async (mods_config_file_path=null, source_profile_id='') => {
    if (!window.pywebview) return
    const res = (mods_config_file_path || source_profile_id) ? 
      await window.pywebview.api.load_order_file_open(mods_config_file_path, source_profile_id || null) : 
      await window.pywebview.api.load_order_get()
    
    if (checkResult(res, "打开加载顺序")) {
      console.log("打开加载顺序:", res)
      return res.data
    }
  }
  const importShareCode = async (shareCode, source_profile_id='') => {
    const normalizedCode = String(shareCode || '').trim()
    if (!normalizedCode) {
      toast.warning('分享码不能为空')
      return null
    }
    if (!window.pywebview) return null

    const res = await window.pywebview.api.load_order_share_import(normalizedCode, source_profile_id || null)
    if (checkResult(res, '导入分享码')) {
      const order = res.data || {}
      setBackupOrder(order, order.file || order.share_code_ref || '')
      if ((order.warnings || []).length > 0) {
        toast.info(`导入完成，但有 ${order.warnings.length} 条提示`, { timeout: 1800 })
      }
      return order
    }
    return null
  }
  const promptImportShareCode = async (source_profile_id='') => {
    const shareCode = await confirmStore.open({
      title: '导入分享码',
      message: '请粘贴 RMM1 开头的分享码，解析后会进入差异对比视图。',
      mode: 'prompt',
      type: 'info',
      placeholder: 'RMM1-...',
      confirmText: '导入',
      cancelText: '取消',
    })
    if (!shareCode) return null

    const order = await importShareCode(shareCode, source_profile_id)
    if (order) {
      toast.success('分享码已导入')
    }
    return order
  }
  const getImportCheckItem = (rowKeyOrPackageId) => {
    const key = String(rowKeyOrPackageId || '').trim().toLowerCase()
    if (!key) return null
    return importCheckMap.value.get(key) || importCheckMap.value.get(`wid:${key}`) || null
  }
  const confirmImportStripping = async (importCheck = currentImportCheck.value, importableIds = backupIds.value) => {
    const items = importCheck?.items || []
    const workshopOnlyItems = items.filter(item => item.origin_kind === 'workshop_only')
    if (workshopOnlyItems.length === 0) return true

    if ((items || []).length > 0 && (importableIds || []).length === 0) {
      await confirmStore.open({
        title: '无法直接导入',
        message: `该文件包含 ${workshopOnlyItems.length} 个纯 WorkshopID 条目。\n游戏加载序列只识别包名，这些条目会被自动剔除。\n剔除后当前没有可导入的包名项，请先在对比列表里处理订阅/下载。`,
        mode: 'alert',
        type: 'warning',
        confirmText: '知道了',
      })
      return false
    }

    return await confirmStore.open({
      title: '导入提示',
      message: `该文件包含 ${workshopOnlyItems.length} 个纯 WorkshopID 条目。\n这些条目只会用于对比和订阅/下载提示，不会写入游戏加载序列。\n继续时将自动剔除它们，是否继续？`,
      mode: 'confirm',
      type: 'warning',
    })
  }
  const takeImportCheckItems = (statuses = [], rowKeys = []) => {
    const statusSet = new Set((statuses || []).map(status => String(status || '').trim()))
    const rowKeySet = new Set((rowKeys || []).map(key => String(key || '').trim().toLowerCase()))
    return importCheckItems.value.filter(item => {
      const rowKey = String(item.row_key || '').trim().toLowerCase()
      if (rowKeySet.size > 0 && !rowKeySet.has(rowKey)) return false
      if (statusSet.size > 0 && !statusSet.has(item.status)) return false
      return true
    })
  }
  const collectImportCheckWorkshopIds = (items = []) => {
    return [...new Set(
      items
        .map(item => String(item.target_workshop_id || '').trim())
        .filter(Boolean)
    )]
  }
  const openImportCheckWorkshop = (rowKeyOrPackageId) => {
    const item = getImportCheckItem(rowKeyOrPackageId)
    if (item?.target_workshop_id) {
      appStore.openSteamWorkshopById(item.target_workshop_id)
    }
  }
  const subscribeImportCheckItems = async (statuses = [], rowKeys = []) => {
    const items = takeImportCheckItems(statuses, rowKeys).filter(item => !item.installed_via_replacement)
    const workshopIds = collectImportCheckWorkshopIds(items)
    if (workshopIds.length === 0) {
      toast.info("当前筛选结果中没有可订阅的工坊项目")
      return false
    }
    return await appStore.subscribeWorkshopIds(workshopIds)
  }
  const downloadImportCheckItems = async (statuses = [], rowKeys = []) => {
    const items = takeImportCheckItems(statuses, rowKeys).filter(item => !item.installed_via_replacement)
    const workshopIds = collectImportCheckWorkshopIds(items)
    if (workshopIds.length === 0) {
      toast.info("当前筛选结果中没有可下载的工坊项目")
      return false
    }
    await appStore.downloadWorkshopItems(workshopIds)
    return true
  }
  const _rebuildImportCheckSummary = (items = []) => {
    return items.reduce((summary, item) => {
      const key = item.status
      if (Object.prototype.hasOwnProperty.call(summary, key)) {
        summary[key] += 1
      }
      return summary
    }, {
      exact_match: 0,
      package_match: 0,
      replacement: 0,
      other_version: 0,
      missing: 0,
      unknown: 0,
    })
  }
  const removeImportCheckItems = async (statuses = [], rowKeys = []) => {
    const items = takeImportCheckItems(statuses, rowKeys)
    if (items.length === 0) return false

    const rowKeySet = new Set(items.map(item => String(item.row_key || '').trim().toLowerCase()))
    const packageIdSet = new Set(
      items
        .map(item => String(item.package_id || '').trim().toLowerCase())
        .filter(Boolean)
    )
    const workshopOnlyRowSet = new Set(
      items
        .filter(item => !item.package_id && item.import_workshop_id)
        .map(item => String(item.import_workshop_id || '').trim())
    )

    backupIds.value = backupIds.value.filter(id => !packageIdSet.has(String(id || '').toLowerCase()))
    backupMods.value = backupMods.value.filter(mod => !packageIdSet.has(String(mod.package_id || '').toLowerCase()))
    currentBackupWorkshopIds.value = currentBackupWorkshopIds.value.filter(wid => !workshopOnlyRowSet.has(String(wid || '').trim()))

    const nextItems = importCheckItems.value.filter(item => {
      const rowKey = String(item.row_key || '').trim().toLowerCase()
      return !rowKeySet.has(rowKey)
    })
    currentImportCheck.value = {
      summary: _rebuildImportCheckSummary(nextItems),
      items: nextItems,
    }
    toast.success(`已移除 ${items.length} 个导入项`)
    return true
  }
  // 兼容旧调用入口：缺失项一键订阅现在复用新的 import_check 分类结果。
  const subscribeMissingBackupMods = async () => {
    return await subscribeImportCheckItems(['missing'])
  }
  // 打开备份目录
  const openBackupPath = async () => {
    appStore.openPath(backupProfileDir.value || [appStore.settings.home_path,"backups"].join("/"))
  }
  // 获取所有备份文件路径 {today: [], earlier: [], other: []}
  const getBackups = async (profile_id=null) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.backups_get_all(profile_id)
    if (checkResult(res, "获取备份文件")) {
      const payload = res.data || {}
      const files = {
        today: payload.today || [],
        earlier: payload.earlier || [],
        other: payload.other || [],
        last_backup: payload.last_backup || [],
      }
      // 更新本地 store
      backups.value = files
      if (payload.profile) {
        setBackupProfile(payload.profile.id || profile_id || backupProfileId.value, payload.profile)
      } else if (profile_id) {
        setBackupProfile(profile_id)
      } else if (!backupProfileId.value) {
        setBackupProfile(appStore.settings.current_profile_id || 'default')
      }
      console.log("获取备份文件:", backups.value)
      return payload
    }
  }


  return {
    backups, backupProfileId, backupProfileDir, backupIds, backupMods, currentBackupFile, backupLoadModifyTime, currentBackupFormat, currentBackupName, currentBackupSourceProfileId, currentBackupWorkshopIds, currentBackupWarnings, currentBackupErrors,
    backupNameMap, backupDisplayIds, currentImportCheck, importCheckItems, importCheckSummary, importCheckMap, problemImportItems, missingImportItems, replacementImportItems, actionableReplacementImportItems, otherVersionImportItems, unknownImportItems, nonImportableImportItems,
    getLoadOrder, getBackupOrder, applyBackup, saveInactiveOrder, saveLoadOrder, exportLoadOrder,
    exportLoadOrderShareCode, getFileOrder, importShareCode, promptImportShareCode, subscribeMissingBackupMods, getImportCheckItem, takeImportCheckItems, collectImportCheckWorkshopIds, openImportCheckWorkshop,
    subscribeImportCheckItems, downloadImportCheckItems, removeImportCheckItems, confirmImportStripping,
    setBackupOrder, clearBackupOrder, setBackupProfile, openBackupPath, getBackups,
  }
})
