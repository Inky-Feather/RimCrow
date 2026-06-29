import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { toast, checkResult, toUserMessage } from '../../shared/lib/common'
import { useModStore } from '../mod/stores/modStore'
import { useAppStore } from '../../app/stores/appStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useMissingInstallStore } from '../supplement/missingInstallStore'
import { useSupplementStore } from '../supplement/supplementStore'
import { normalizeInstallSource, normalizePackageId, normalizePackageToken } from '../mod/lib/modIdentity'

export const useOrderStore = defineStore('order', () => {
  const appStore = useAppStore()
  const modStore = useModStore()
  const confirmStore = useConfirmStore()
  const supplementStore = useSupplementStore()

  // === State ===
  const backups = ref(null)           // 备份文件列表
  const backupProfileId = ref('')     // 当前查看的备份所属环境
  const backupProfileDir = ref('')    // 当前查看环境的备份目录
  const tempImports = ref([])         // 所有导入入口统一登记到这里，供备份面板展示“临时导入”
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
        .map(mod => [normalizePackageId(mod.package_id), mod.name || mod.package_id])
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
      importCheckItems.value.map(item => [normalizePackageToken(item.row_key || item.package_id), item])
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
  // 设置当前查看环境的备份目录
  const setBackupProfile = (profileId = '', meta = null) => {
    backupProfileId.value = profileId || ''
    if (meta && Object.prototype.hasOwnProperty.call(meta, 'backup_dir')) {
      backupProfileDir.value = meta.backup_dir || ''
    }
  }
  const buildTempImportKey = (order = {}) => {
    const fileKey = String(order.path || order.file || '').trim()
    if (fileKey) return fileKey
    const fallbackParts = [
      String(order.format || ''),
      String(order.list_name || ''),
      String(order.source_profile_id || ''),
      Array.isArray(order.active_ids) ? order.active_ids.join(',') : '',
      Array.isArray(order.workshop_ids) ? order.workshop_ids.join(',') : '',
    ]
    return fallbackParts.join('|')
  }
  const registerTempImport = (order = {}) => {
    const normalizedOrder = order ? { ...order } : {}
    const tempKey = buildTempImportKey(normalizedOrder)
    if (!tempKey) return null
    const entry = {
      ...normalizedOrder,
      path: String(normalizedOrder.path || normalizedOrder.file || tempKey),
      file: String(normalizedOrder.file || normalizedOrder.path || tempKey),
    }
    tempImports.value = [
      entry,
      ...tempImports.value.filter(item => buildTempImportKey(item) !== tempKey),
    ]
    return entry
  }
  const removeTempImport = (pathOrOrder = '') => {
    const tempKey = typeof pathOrOrder === 'object'
      ? buildTempImportKey(pathOrOrder)
      : buildTempImportKey({ path: pathOrOrder })
    if (!tempKey) return false
    const prevLength = tempImports.value.length
    tempImports.value = tempImports.value.filter(item => buildTempImportKey(item) !== tempKey)
    return tempImports.value.length !== prevLength
  }
  const clearTempImports = () => {
    tempImports.value = []
  }
  const buildEditingMods = (ids = []) => (
    (ids || []).map(id => {
      const normalizedId = normalizePackageToken(id)
      return {
        package_id: normalizedId,
        name: modStore.displayModName(normalizedId),
      }
    })
  )
  const isSameOrder = (left = [], right = []) => {
    if ((left || []).length !== (right || []).length) return false
    return (left || []).every((item, index) => item === right[index])
  }
  const applyDiskOrder = async (order = {}, { toastMessage = '' } = {}) => {
    const nextIds = order.active_ids || []
    modStore.setListIds('active', nextIds)
    modStore.setActiveLoadBaseline(
      nextIds,
      order.modify_time || 0,
      order.version_token || {}
    )
    modStore.updateInactiveIds()
    await modStore.fetchAndCacheGhostMods(nextIds)
    if (toastMessage) {
      toast.info(toastMessage, { timeout: 2200 })
    }
    return true
  }
  const showDiskConflict = async (payload = {}, toastMessage = '检测到磁盘序列已变化，请先处理冲突。') => {
    const diskOrder = payload.disk_order || {}
    const editingIds = payload.editing_order?.active_ids || []
    await applyDiskOrder(diskOrder)
    setBackupOrder({
      active_ids: editingIds,
      mods: buildEditingMods(editingIds),
      file: 'conflict://unsaved',
      modify_time: Date.now(),
      format: 'conflict',
      list_name: '未保存改动',
      source_profile_id: '',
      source_profile_name: '',
      workshop_ids: [],
      warnings: [],
      errors: [],
      import_check: { summary: {}, items: [] },
    }, 'conflict://unsaved')
    appStore.uiState.showDiffDrawer = true
    toast.warning(toastMessage, { timeout: 3200 })
    return false
  }
  const captureRuntimeRefreshSnapshot = () => ({
    active_ids: [...(modStore.activeIds || [])],
    is_dirty: !!modStore.isDirty,
    captured_at: Date.now(),
  })
  const presentRuntimeRefreshDiff = async (snapshot = null) => {
    const editingIds = snapshot?.active_ids || []
    if (!editingIds.length) return false
    if (isSameOrder(editingIds, modStore.activeIds)) return false
    setBackupOrder({
      active_ids: editingIds,
      mods: buildEditingMods(editingIds),
      file: 'runtime://before-refresh',
      modify_time: snapshot?.captured_at || Date.now(),
      format: 'conflict',
      list_name: snapshot?.is_dirty ? '刷新前未保存改动' : '刷新前工作序列',
      source_profile_id: '',
      source_profile_name: '',
      workshop_ids: [],
      warnings: [],
      errors: [],
      import_check: { summary: {}, items: [] },
    }, 'runtime://before-refresh')
    appStore.uiState.showDiffDrawer = true
    toast.warning(
      snapshot?.is_dirty
        ? '游戏退出后磁盘序列已刷新，未保存改动已转入差异对比。'
        : '游戏退出后磁盘序列与管理器工作序列不同，已打开差异对比。',
      { timeout: 3600 }
    )
    return true
  }
  const bytesToBase64 = (buffer) => {
    let binary = ''
    const bytes = new Uint8Array(buffer)
    const chunkSize = 0x8000
    for (let index = 0; index < bytes.length; index += chunkSize) {
      const chunk = bytes.subarray(index, index + chunkSize)
      binary += String.fromCharCode(...chunk)
    }
    return btoa(binary)
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
        modStore.mergeInstallSourceHintsFromMods?.(order.mods || [], 'import')
        if (!mods_config_file_path) {
          modStore.setActiveLoadBaseline(
            order.active_ids || [],
            order.active_load_modify_time || order.modify_time || 0,
            order.version_token || {}
          )
        }
        modStore.updateInactiveIds()
        // 加载外部存档文件时解析未知项
        await modStore.fetchAndCacheGhostMods(modStore.activeIds)
      })
      toast.success("Mod序列已加载")
      return true
    }
    return false
  }
  const buildCurrentBackupMeta = () => ({
    path: currentBackupFile.value,
    file: currentBackupFile.value,
    active_ids: [...backupIds.value],
    mods: [...backupMods.value],
    modify_time: backupLoadModifyTime.value,
    format: currentBackupFormat.value,
    list_name: currentBackupName.value,
    source_profile_id: currentBackupSourceProfileId.value,
    workshop_ids: [...currentBackupWorkshopIds.value],
    warnings: [...currentBackupWarnings.value],
    errors: [...currentBackupErrors.value],
    import_check: currentImportCheck.value,
  })
  const activateTempImportEntry = (entry = null) => {
    if (!entry) return null
    // 临时导入项需要成为当前对比对象，确保选中态和 diff 抽屉都明确落在“临时导入”分组。
    setBackupOrder(entry, entry.file || entry.path || '')
    return entry
  }
  // 切换当前对比项。这里只负责读取并切换，不负责登记“临时导入”。
  const selectBackupOrder = async (mods_config_file_path=null, source_profile_id='') => {
    const order = await getFileOrder(mods_config_file_path, source_profile_id)
    if (order) {
      setBackupOrder(order, mods_config_file_path)
      return buildCurrentBackupMeta()
    }
    return null
  }
  // 外部导入：导入数据，登记为“临时导入”，并切换到该临时导入项。
  const importExternalOrder = async (mods_config_file_path=null, source_profile_id='') => {
    const order = await selectBackupOrder(mods_config_file_path, source_profile_id)
    if (!order) return null

    if ((order.warnings || []).length > 0) {
      toast.info(`导入完成，但有 ${order.warnings.length} 条提示`, { timeout: 1800 })
    }
    const entry = registerTempImport(buildCurrentBackupMeta())
    return activateTempImportEntry(entry)
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
      modStore.mergeInstallSourceHintsFromMods?.(backupMods.value || [], 'import')
      modStore.updateInactiveIds()
      // 加载外部存档文件时解析未知项
      await modStore.fetchAndCacheGhostMods(modStore.activeIds)
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
      // 未开启临时列表保存时，Temp 列表退出前回到 Inactive 队首。
      const persistTempList = !!appStore.settings.ui?.persist_temp_mod_list
      const finalInactive = persistTempList ? [...modStore.inactiveIds] : [...modStore.tempIds, ...modStore.inactiveIds]
      const finalTemp = persistTempList ? [...modStore.tempIds] : []
      // 过滤掉已经在 Active 里的防止出错
      const activeSet = new Set(modStore.activeIds.map(id => normalizePackageId(id)))
      const cleanInactive = finalInactive.filter(id => !activeSet.has(normalizePackageId(id)))
      const cleanTemp = finalTemp.filter(id => !activeSet.has(normalizePackageId(id)))
      const res = await window.pywebview.api.load_order_inactive_save(cleanInactive, cleanTemp)
      if (checkResult(res, "保存停用列表顺序")) {
        modStore.savedInactiveIds = [...cleanInactive] || []
        modStore.savedTempIds = [...cleanTemp] || []
        return true
      }
    } finally {
      appStore.isLoading = false
    }
    return false
  }
  // 保存Mod加载顺序
  const saveLoadOrder = async ({ actionLabel = '保存' } = {}) => {
    const modStore = useModStore()
    // if (!modStore.isDirty) {
    //   setTimeout(() => {
    //     toast.info("Mod序列未修改无须保存",{timeout: 1000})
    //   }, 100);
    //   // return true
    // }
    if (!window.pywebview) return false
    const missingInstallStore = useMissingInstallStore()
    const canResolveMissing = await missingInstallStore.ensureResolvedBeforeAction({
      activeIds: modStore.activeIds,
      actionLabel,
    })
    if (!canResolveMissing) return false
    const canContinue = await supplementStore.ensureRequiredBeforeSave({
      activeIds: modStore.activeIds,
      actionLabel,
    })
    if (!canContinue) return false
    appStore.isLoading = true
    try {
      // 使用默认路径
      const res = await window.pywebview.api.load_order_save_with_token(
        modStore.activeIds,
        modStore.isDirty,
        modStore.activeLoadVersionToken || {}
      )
      if (res?.status === 'warning' && res?.data?.status === 'conflict') {
        return await showDiskConflict(res.data, '磁盘加载顺序已被外部修改，未执行保存。')
      }
      if (checkResult(res, "保存Mod加载顺序", true)) {
        modStore.setActiveLoadBaseline(
          res.data?.active_ids || modStore.activeIds,
          res.data?.modify_time || Date.now(),
          res.data?.version_token || {}
        )
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
      let resolvedPath = target_path
      let rememberDialogDir = false
      if (!resolvedPath && trigger_dialog) {
        const pickRes = await window.pywebview.api.load_order_export_pick_path(export_format)
        if (pickRes?.status === 'warning') return false
        if (!checkResult(pickRes, "选择导出路径")) return false
        resolvedPath = pickRes.data?.path || ''
        rememberDialogDir = !!resolvedPath
        trigger_dialog = false
      }
      // 导出格式和列表名都直接传给后端，让后端决定写出 ModsConfig.xml 还是 ModList.xml。
      const res = await window.pywebview.api.load_order_export(
        modStore.activeIds,
        resolvedPath,
        trigger_dialog,
        export_format,
        list_name,
        rememberDialogDir
      )
      if (checkResult(res, "导出Mod加载顺序")) {
        // console.log("导出加载顺序成功:", res)
        toast.success("Mod序列已导出")
        return true
      }
    } catch (e) {
      console.error("导出Mod序列异常:", e)
      toast.error(toUserMessage(e?.message || e, '导出 Mod 序列失败。请检查目标目录权限、磁盘空间和当前启用列表状态，详细原因已写入系统日志。'))
    }
    return false
  }
  const saveBackupAs = async (path, profile_id='') => {
    if (!window.pywebview || !path) return false
    const pickRes = await window.pywebview.api.backup_file_save_as_pick_dir()
    if (pickRes?.status === 'warning') return false
    if (!checkResult(pickRes, '选择保存目录')) return false
    const targetDir = pickRes.data?.path || ''
    if (!targetDir) return false

    const res = await window.pywebview.api.backup_file_save_as(
      path,
      targetDir,
      profile_id || backupProfileId.value || null
    )
    if (checkResult(res, '另存备份')) {
      toast.success(`备份已另存为: \n${res.data?.path || targetDir}`)
      return true
    }
    return false
  }
  const renameManualBackup = async (path, new_name, profile_id='') => {
    if (!window.pywebview || !path || !new_name) return null
    const res = await window.pywebview.api.backup_manual_rename(
      path,
      new_name,
      profile_id || backupProfileId.value || null
    )
    if (checkResult(res, '重命名备份')) {
      const data = res.data || {}
      if (data.sanitized) {
        toast.warning('文件名中的特殊字符已替换为下划线')
      }
      if (currentBackupFile.value === path && data.path) {
        currentBackupFile.value = data.path
      }
      toast.success('备份已重命名')
      return data
    }
    return null
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
      console.warn('剪贴板 API 复制失败，准备使用兼容复制方式:', error)
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
      console.warn('兼容复制方式失败:', error)
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
        placeholder: 'RC-...',
        confirmText: '关闭',
        cancelText: '取消',
      })
      return shareCode
    } catch (e) {
      console.error('生成分享码异常:', e)
      toast.error(toUserMessage(e?.message || e, '生成分享码失败。请检查当前启用列表是否有效，或稍后重试。详细原因已写入系统日志。'))
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
      console.debug("加载顺序已打开:", res)
      return res.data
    }
  }
  const importPayloadFile = async (file, source_profile_id='') => {
    if (!window.pywebview || !file) return null
    const normalizedName = String(file.name || 'import.txt').trim() || 'import.txt'
    const content = await file.arrayBuffer()
    const res = await window.pywebview.api.load_order_file_import_payload(
      {
        filename: normalizedName,
        mime_type: String(file.type || ''),
        size: Number(file.size || 0),
        content_base64: bytesToBase64(content),
      },
      source_profile_id || null
    )
    if (checkResult(res, '导入加载顺序')) {
      const order = res.data || {}
      setBackupOrder(order, order.file || normalizedName)
      if ((order.warnings || []).length > 0) {
        toast.info(`导入完成，但有 ${order.warnings.length} 条提示`, { timeout: 1800 })
      }
      const entry = registerTempImport(buildCurrentBackupMeta())
      return activateTempImportEntry(entry)
    }
    return null
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
      const entry = registerTempImport(buildCurrentBackupMeta())
      return activateTempImportEntry(entry)
    }
    return null
  }
  const promptImportShareCode = async (source_profile_id='') => {
    const shareCode = await confirmStore.open({
      title: '导入分享码',
      message: '请粘贴 RC- 开头的分享码，解析后会进入差异对比视图。',
      mode: 'prompt',
      type: 'info',
      placeholder: 'RC-...',
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
    const key = normalizePackageToken(rowKeyOrPackageId)
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
    const rowKeySet = new Set((rowKeys || []).map(key => normalizePackageToken(key)))
    return importCheckItems.value.filter(item => {
      const rowKey = normalizePackageToken(item.row_key)
      if (rowKeySet.size > 0 && !rowKeySet.has(rowKey)) return false
      if (statusSet.size > 0 && !statusSet.has(item.status)) return false
      return true
    })
  }
  const getImportCheckTargetSource = (item = null) => (
    normalizeInstallSource(item?.target_source || null, item?.package_id || '')
  )
  const collectImportCheckSources = (items = []) => (
    items
      .map(item => getImportCheckTargetSource(item))
      .filter(Boolean)
  )
  const openImportCheckWorkshop = (rowKeyOrPackageId) => {
    const item = getImportCheckItem(rowKeyOrPackageId)
    const source = getImportCheckTargetSource(item)
    if (source) {
      appStore.openInstallSource(source)
    }
  }
  const subscribeImportCheckItems = async (statuses = [], rowKeys = []) => {
    const items = takeImportCheckItems(statuses, rowKeys).filter(item => !item.installed_via_replacement)
    const sources = collectImportCheckSources(items)
    const hasWorkshopSource = sources.some(source => source.kind === 'workshop')
    if (!hasWorkshopSource) {
      toast.info("当前筛选结果中没有可订阅的工坊项目")
      return false
    }
    return await appStore.subscribeInstallSources(sources)
  }
  const downloadImportCheckItems = async (statuses = [], rowKeys = []) => {
    const items = takeImportCheckItems(statuses, rowKeys).filter(item => !item.installed_via_replacement)
    const sources = collectImportCheckSources(items)
    if (sources.length === 0) {
      toast.info("当前筛选结果中没有可下载的目标来源")
      return false
    }
    return await appStore.downloadInstallSources(sources)
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

    const rowKeySet = new Set(items.map(item => normalizePackageToken(item.row_key)))
    const packageIdSet = new Set(
      items
        .map(item => normalizePackageId(item.package_id))
        .filter(Boolean)
    )
    const workshopOnlyRowSet = new Set(
      items
        .filter(item => !item.package_id && item.import_workshop_id)
        .map(item => String(item.import_workshop_id || '').trim())
    )

    backupIds.value = backupIds.value.filter(id => !packageIdSet.has(normalizePackageId(id)))
    backupMods.value = backupMods.value.filter(mod => !packageIdSet.has(normalizePackageId(mod.package_id)))
    currentBackupWorkshopIds.value = currentBackupWorkshopIds.value.filter(wid => !workshopOnlyRowSet.has(String(wid || '').trim()))

    const nextItems = importCheckItems.value.filter(item => {
      const rowKey = normalizePackageToken(item.row_key)
      return !rowKeySet.has(rowKey)
    })
    currentImportCheck.value = {
      summary: _rebuildImportCheckSummary(nextItems),
      items: nextItems,
    }
    toast.success(`已移除 ${items.length} 个导入项`)
    return true
  }
  // 打开备份目录
  const openBackupPath = async () => {
    appStore.openPath(backupProfileDir.value || [appStore.settings.home_path,"backups"].join("/"))
  }
  // 获取所有备份文件路径 {today: [], earlier: [], other: []}
  const getBackups = async (profile_id=null, { silent = false } = {}) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.backups_get_all(profile_id)
    if (checkResult(res, "获取备份文件", false, { silent })) {
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
      console.debug("获取备份文件:", backups.value)
      return payload
    }
  }
  return {
    // 备份状态
    backups, backupProfileId, backupProfileDir, tempImports, backupIds, backupMods, currentBackupFile, backupLoadModifyTime, currentBackupFormat, currentBackupName, currentBackupSourceProfileId, currentBackupWorkshopIds, currentBackupWarnings, currentBackupErrors,
    // 导入检查状态
    backupNameMap, backupDisplayIds, currentImportCheck, importCheckItems, importCheckSummary, importCheckMap, problemImportItems, missingImportItems, replacementImportItems, actionableReplacementImportItems, otherVersionImportItems, unknownImportItems, nonImportableImportItems,
    // 读取、导入与导出
    getLoadOrder, selectBackupOrder, importExternalOrder, applyBackup, saveInactiveOrder, saveLoadOrder, exportLoadOrder, saveBackupAs, renameManualBackup,
    exportLoadOrderShareCode, getFileOrder, importPayloadFile, importShareCode, promptImportShareCode, getImportCheckItem, takeImportCheckItems, getImportCheckTargetSource, openImportCheckWorkshop,
    // 导入检查处理
    subscribeImportCheckItems, downloadImportCheckItems, removeImportCheckItems, confirmImportStripping,
    // 备份状态维护
    setBackupOrder, clearBackupOrder, setBackupProfile, registerTempImport, removeTempImport, clearTempImports, openBackupPath, getBackups, captureRuntimeRefreshSnapshot, presentRuntimeRefreshDiff,
  }
})
