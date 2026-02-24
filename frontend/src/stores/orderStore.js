import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useModStore } from './modStore'
import { useAppStore } from './appStore'

export const useOrderStore = defineStore('order', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const checkResult = appStore.checkResult
  
  // === State ===
  const backups = ref(null)           // 备份文件列表
  const backupIds = ref([])           // 当前备份的排序列表
  const currentBackupFile = ref('')   // 当前备份文件
  const backupLoadModifyTime = ref(0) // 备份加载顺序修改时间

  // === Actions ===
  // 获取加载顺序
  const getLoadOrder = async (mods_config_file_path=null) => {
    const order = await getFileOrder(mods_config_file_path)
    if (order) {
      const modStore = useModStore()
      modStore.activeIds = order.active_ids || []
      modStore.savedActiveIds = [...order.active_ids] || []
      modStore.activeLoadModifyTime = order.active_load_modify_time || 0
      modStore.updateInactiveIds()
      toast.success("Mod序列已加载")
    }
  }
  // 获取备份加载顺序
  const getBackupOrder = async (mods_config_file_path=null) => {
    const order = await getFileOrder(mods_config_file_path)
    if (order) {
      backupIds.value = order.active_ids || []
      currentBackupFile.value = order.file || mods_config_file_path
      backupLoadModifyTime.value = order.modify_time || 0
      return {path: currentBackupFile.value, modify_time: backupLoadModifyTime.value}
      // toast.success("备份Mod序列已加载")
    }
  }
  // 应用备份列表
  const applyBackup = () => {
    if (!backupIds.value) return
    const modStore = useModStore()
    modStore.activeIds = backupIds.value
    modStore.updateInactiveIds()
    toast.success("已应用Mod序列")
  }
  // 保存Mod加载顺序
  const saveLoadOrder = async () => {
    const modStore = useModStore()
    if (!modStore.isDirty) {
      setTimeout(() => {
        toast.info("Mod序列未修改无须保存",{timeout: 1000})
      }, 100);
      return true
    }
    if (!window.pywebview) return false
    appStore.isLoading = true
    try {
      // 使用默认路径
      const res = await window.pywebview.api.load_order_save(modStore.activeIds)
      if (checkResult(res, "保存Mod加载顺序")) {
        modStore.savedActiveIds = [...modStore.activeIds] || []
        modStore.updateInactiveIds()
        // console.log("保存加载顺序成功:", res)
        toast.success("Mod序列已保存")
        getBackups()
        modStore.updateModTime() // 更新Mod最后操作时间
        return true
      }
    } catch (e) {
      console.error("保存Mod序列异常:", e)
      toast.error(`保存Mod序列异常: \n${e.message}`)
    } finally {
      appStore.isLoading = false
    }
    return false
  }
  // 导出Mod加载顺序
  const exportLoadOrder = async (target_path=null, trigger_dialog=true) => {
    if (!window.pywebview) return false
    try {
      const modStore = useModStore()
      // 使用默认路径
      const res = await window.pywebview.api.load_order_export(modStore.activeIds, target_path, trigger_dialog)
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
  const getFileOrder = async (mods_config_file_path=null) => {
    if (!window.pywebview) return
    const res = mods_config_file_path ? 
      await window.pywebview.api.load_order_file_open(mods_config_file_path) : 
      await window.pywebview.api.load_order_get()
    
    if (checkResult(res, "打开加载顺序")) {
      console.log("打开加载顺序:", res)
      return res.data
    }
  }
  // 打开备份目录
  const openBackupPath = async () => {
    appStore.openPath([appStore.settings.home_path,"backups"].join("/"))
  }
  // 获取所有备份文件路径 {today: [], earlier: [], other: []}
  const getBackups = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.backups_get_all()
    if (checkResult(res, "获取备份文件")) {
      // 更新本地 store
      backups.value = res.data
      console.log("获取备份文件:", backups.value)
    }
  }


  return {
    backups, backupIds, currentBackupFile, backupLoadModifyTime,
    getLoadOrder, getBackupOrder, applyBackup, saveLoadOrder, exportLoadOrder,
    getFileOrder, openBackupPath, getBackups,
  }
})