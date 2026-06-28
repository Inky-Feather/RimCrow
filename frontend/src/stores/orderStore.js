import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useModStore } from './modStore'
import { useAppStore } from './appStore'

export const useOrderStore = defineStore('order', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const modStore = useModStore()
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

  const backupNameMap = computed(() => {
    // 记录“包名 -> 导入文件中的显示名称”，供差异视图在本地缺失时兜底显示。
    return Object.fromEntries(
      backupMods.value
        .map(mod => [String(mod.package_id || '').toLowerCase(), mod.name || mod.package_id])
        .filter(([packageId]) => packageId)
    )
  })
  const missingBackupMods = computed(() => {
    // 只要本地库里不存在，就视为“导入文件中缺失的模组”。
    return backupMods.value.filter(mod => {
      const packageId = String(mod.package_id || '').toLowerCase()
      return packageId && !modStore.allModsMap.has(packageId)
    })
  })
  const missingBackupWorkshopIds = computed(() => {
    // 优先使用文件里自带的 workshop_id，避免再走一次包名反查。
    return [...new Set(
      missingBackupMods.value
        .map(mod => String(mod.workshop_id || '').trim())
        .filter(Boolean)
    )]
  })
  const missingBackupPackageIds = computed(() => {
    // 没有 workshop_id 的缺失项保留 package_id，后面再向后端静默反查。
    return [...new Set(
      missingBackupMods.value
        .filter(mod => !mod.workshop_id)
        .map(mod => String(mod.package_id || '').toLowerCase())
        .filter(Boolean)
    )]
  })
  const missingBackupSubscribableCount = computed(() => {
    return new Set([
      ...missingBackupWorkshopIds.value.map(id => `w:${id}`),
      ...missingBackupPackageIds.value.map(id => `p:${id}`)
    ]).size
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
      // 后端现在统一返回 modify_time。
      // active_load_modify_time 保留兼容旧数据结构，优先兼容旧接口，缺失时回退到新字段。
      modStore.activeIds = order.active_ids || []
      modStore.savedActiveIds = [...order.active_ids] || []
      modStore.activeLoadModifyTime = order.active_load_modify_time || order.modify_time || 0
      modStore.updateInactiveIds()
      // 加载外部存档文件时解析未知项
      modStore.fetchAndCacheGhostMods(modStore.activeIds)
      toast.success("Mod序列已加载")
    }
  }
  // 获取备份加载顺序
  const getBackupOrder = async (mods_config_file_path=null, source_profile_id='') => {
    const order = await getFileOrder(mods_config_file_path, source_profile_id)
    if (order) {
      // 除了 active_ids 之外，还要把格式、列表名和结构化明细一起缓存下来，
      // 后面 diff 抽屉显示标题、名称和一键订阅都依赖这些字段。
      setBackupOrder(order, mods_config_file_path)
      // 加载外部存档文件时解析未知项
      modStore.fetchAndCacheGhostMods(order.activeIds)
      return {
        path: currentBackupFile.value,
        modify_time: backupLoadModifyTime.value,
        format: currentBackupFormat.value,
        list_name: currentBackupName.value,
        source_profile_id: currentBackupSourceProfileId.value,
      }
      // toast.success("备份Mod序列已加载")
    }
  }
  // 应用备份列表
  const applyBackup = () => {
    if (!backupIds.value) return
    modStore.activeIds = backupIds.value
    modStore.updateInactiveIds()
    // 加载外部存档文件时解析未知项
    modStore.fetchAndCacheGhostMods(modStore.activeIds)
    toast.success("已应用Mod序列")
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
  // 一键订阅导入文件中缺失的工坊模组
  const subscribeMissingBackupMods = async () => {
    // 先收集文件里已经明确给出的 workshop_id。
    const workshopIds = new Set(missingBackupWorkshopIds.value)
    const fallbackPackageIds = missingBackupPackageIds.value

    if (fallbackPackageIds.length > 0 && window.pywebview) {
      // 对没有 workshop_id 的缺失项，再按 package_id 向后端补查一次。
      const res = await window.pywebview.api.get_workshop_ids_by_package_ids_map(fallbackPackageIds)
      if (res?.status === 'success' && res.data) {
        Object.values(res.data).forEach(id => {
          if (id) workshopIds.add(String(id))
        })
      }
    }

    // 最终统一走已有订阅接口，复用 Steam 启动检测和提示逻辑。
    const finalWorkshopIds = [...workshopIds]
    if (finalWorkshopIds.length === 0) {
      toast.info("导入列表中没有可订阅的缺失工坊 Mod")
      return false
    }

    return await appStore.subscribeWorkshopIds(finalWorkshopIds)
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
    backups, backupProfileId, backupProfileDir, backupIds, backupMods, currentBackupFile, backupLoadModifyTime, currentBackupFormat, currentBackupName, currentBackupSourceProfileId,
    backupNameMap, missingBackupMods, missingBackupWorkshopIds, missingBackupPackageIds, missingBackupSubscribableCount,
    getLoadOrder, getBackupOrder, applyBackup, saveInactiveOrder, saveLoadOrder, exportLoadOrder,
    getFileOrder, subscribeMissingBackupMods, setBackupOrder, clearBackupOrder, setBackupProfile, openBackupPath, getBackups,
  }
})
