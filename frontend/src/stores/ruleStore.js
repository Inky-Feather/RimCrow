import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useModStore } from './modStore'
import { useAppStore } from './appStore'
import { createToastInterface } from 'vue-toastification'

// 动态规则支持属性映射
const DYNAMIC_RULE_PROPS = {
  'package_id': '包名',
  'name': '名称',
  'author': '作者',
  'tags': '标签',
  'groups': '分组', 
  'user_mod_type': '类型'
}
// 动态规则动作映射
const DYNAMIC_RULE_ACTIONS = {
  'weight_shift': '权重偏移 (Shift)',
  'weight_set': '强制权重 (Set)',
  'load_after': '必须在某ID后',
  'load_before': '必须在某ID前',
  'top': '强制置顶',
  'bottom': '强制置底',
}
// 动态规则支持运算符映射
const DYNAMIC_RULE_OPERATORS = {
  'equals': '等于',
  'not_equals': '不等于',
  'contains': '包含',
  'not_contains': '不包含',
  'starts_with': '以...开头',
  'ends_with': '以...结尾',
  'regex': '正则匹配',
}



export const useRuleStore = defineStore('rules', () => {
  const modStore = useModStore()
  const appStore = useAppStore()

  const toast = createToastInterface()

  // --- State ---
  const communityModRules = ref({}) // { pkg_id: { loadAfter: ... } }
  const communityRulesUpdateTime = ref(0)
  const userModRules = ref({})   // { pkg_id: { loadAfter: ... } }
  const workshopModRules = ref({}) // { pkg_id: [dep_pid1, dep_pid2, ...] }
  const userDynamicRules = ref([])
  const settings = ref({
    community_mod_rules_enabled: true,    // 全局社区规则总开关
    user_mod_rules_enabled: true,         // 全局用户单项规则总开关
    dynamic_rules_enabled: true,          // 全局动态规则总开关
    workshop_mod_rules_enabled: true,     // 工坊外置规则总开关
    workshop_rules_as_dependency: false,  // True: 作为强依赖(触发自动补全) | False: 作为普通前置依赖
    excluded_community_mods: [],          // 被禁用的社区 Mod ID 列表 (黑名单)
    excluded_user_mods: [],               // 被禁用的用户 Mod ID 列表 (黑名单)
    excluded_workshop_mods: [],           // 被禁用的工坊 Mod ID 列表 (黑名单)
    // 规则优先级配置：索引越小，优先级越高 (默认: 用户 > 原生 > 社区 > 动态)
    rule_source_priority: ["user", "native", "community", "dynamic", "workshop"]
  })

  const currentId = ref(null)
  const isLoading = ref(false)
  
  // 当前正在检视的目标 Mod ID
  const targetId = computed(() => modStore.lastSelectedMod?.package_id || null)

  // --- Actions ---
  
  // 初始化加载 (在 App 启动或 refreshModList 时调用)
  const fetchRules = async () => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.rules_get_all()
      if (appStore.checkResult(res, '获取规则')) {
        communityModRules.value = res.data.community_rules
        communityRulesUpdateTime.value = res.data.community_rules_update_time
        userModRules.value = res.data.user_mod_rules
        workshopModRules.value = res.data.workshop_rules
        userDynamicRules.value = res.data.user_dynamic_rules
        settings.value = res.data.settings
      }
    } catch (e) {
      console.error("Rules fetch failed", e)
    }
  }

  // --- 核心：计算当前 Mod 的所有约束视图 ---
  // 将分散的数据聚合为： { loadAfter: [{id, source, note}], loadBefore: [...], incompatible: [...] }
  const currentConstraints = computed(() => {
    const pid = targetId.value?.toLowerCase()
    const result = { loadAfter: [], loadBefore: [], incompatible: [] }
    if (!pid) return result

    // 1. Native (About.xml) - 从 modStore 获取
    const mod = modStore.takeModById(pid)
    if (mod) {
      mod.load_after_mods?.forEach(d => result.loadAfter.push({ id: d.package_id, source: 'native' }))
    //   mod.dependencies_mods?.forEach(d => result.loadAfter.push({ id: d.package_id, source: 'native' }))
      mod.load_before_mods?.forEach(d => result.loadBefore.push({ id: d.package_id, source: 'native' }))
      mod.incompatible_mods?.forEach(d => result.incompatible.push({ id: d.package_id, source: 'native' }))
    }

    // 2. Community Rules
    const comm = communityModRules.value[pid]
    if (comm) {
      Object.entries(comm.loadAfter || {}).forEach(([id, info]) => 
        result.loadAfter.push({ id, source: 'community', note: formatNote(info) }))
      Object.entries(comm.loadBefore || {}).forEach(([id, info]) => 
        result.loadBefore.push({ id, source: 'community', note: formatNote(info) }))
      Object.entries(comm.incompatibleWith || {}).forEach(([id, info]) => 
        result.incompatible.push({ id, source: 'community', note: formatNote(info) }))
    }

    // 3. User Single Rules
    const user = userModRules.value[pid]
    if (user) {
      Object.keys(user.loadAfter || {}).forEach(id => 
        result.loadAfter.push({ id, source: 'user' }))
      Object.keys(user.loadBefore || {}).forEach(id => 
        result.loadBefore.push({ id, source: 'user' }))
      Object.keys(user.incompatibleWith || {}).forEach(id => 
        result.incompatible.push({ id, source: 'user' }))
    }

    // 4. Workshop Rules
    const workshop = workshopModRules.value[pid]
    if (workshop) {
      Object.keys(user.loadAfter || {}).forEach(id => 
        result.loadAfter.push({ id, source: 'workshop' }))
    }

    // (动态规则比较复杂，暂不在此展示，以免混淆“手动编辑”的概念)
    
    return result
  })

  // 辅助：格式化社区备注
  const formatNote = (info) => {
    if (!info) return ''
    const lines = Array.isArray(info.comment) ? info.comment : [info.comment]
    return lines.filter(Boolean).join('\n')
  }

  // --- 单项规则操作 ---
  // 添加单项规则 (Drag & Drop 调用)
  const addUserModRule = async (targetModId, type, otherModId) => {
    if (!window.pywebview) return
    // type: 'loadAfter' | 'loadBefore' | 'incompatibleWith'
    if (!targetModId || !otherModId) return
    const pid = targetModId.toLowerCase()
    const other = otherModId.toLowerCase()
    // 获取或初始化当前规则对象
    // 注意：需要深拷贝，不能直接改 ref
    const rule = JSON.parse(JSON.stringify(userModRules.value[pid] || {}))
    // 初始化子对象
    if (!rule[type]) rule[type] = {}
    // 如果已存在，跳过
    if (rule[type][other]) return
    // 写入
    const otherMod = modStore.takeModById(other)
    rule[type][other] = {name: [otherMod.name||''], comment:[] }
    // 乐观更新本地 State
    if (!userModRules.value[pid]) userModRules.value[pid] = {}
    if (!userModRules.value[pid][type]) userModRules.value[pid][type] = {}
    userModRules.value[pid][type][other] = rule[type][other]

    // 发送后端
    const res = await window.pywebview.api.rule_update_user_mod(pid, rule)
    if (!appStore.checkResult(res, '添加用户规则')) {
      toast.error(res.message)
      fetchRules() // 回滚
    } else {
      modStore.scanMods()
    }
  }
  // 移除单项规则中的mod
  const removeUserModRuleItem = async (targetModId, type, otherModId) => {
    const pid = targetModId.toLowerCase()
    const other = otherModId.toLowerCase()
    if (!userModRules.value[pid]?.[type]?.[other] === undefined) return
    const rule = JSON.parse(JSON.stringify(userModRules.value[pid]))
    delete rule[type][other]
    // 乐观更新
    delete userModRules.value[pid][type][other]
    // 清理空对象
    if (Object.keys(rule[type]).length === 0) {
        delete rule[type]
        delete userModRules.value[pid][type]
    }
    // console.log(rule)
    if (Object.keys(rule).length === 0) {
        deleteUserModRule(pid) // 清理空对象
        return
    }
    const res = await window.pywebview.api.rule_update_user_mod(pid, rule)
    if (!appStore.checkResult(res, '移除用户规则')) fetchRules()
    modStore.scanMods()
  }
  // 修改单项规则说明
  const updateComment = async (targetModId, type, otherModId, comment) => {
    if (!window.pywebview) return
    const pid = targetModId.toLowerCase()
    const other = otherModId.toLowerCase()
    if (!userModRules.value[pid]?.[type]?.[other] === undefined) return
    const rule = JSON.parse(JSON.stringify(userModRules.value[pid]))
    rule[type][other].comment = comment
    // 乐观更新
    userModRules.value[pid][type][other] = rule[type][other]
    const res = await window.pywebview.api.rule_update_user_mod(pid, rule)
    if (!appStore.checkResult(res, '更新用户规则说明')) fetchRules()
    modStore.scanMods()
  }
  // 删除用户单项规则
  const deleteUserModRule = async (id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.rule_delete_user_mod(id)
    if (appStore.checkResult(res, '删除用户规则', true)) {
      fetchRules()
      modStore.scanMods()
    }
  }
  // 获取某个 Mod 当前的绝对位置状态
  const getAbsolutePosition = (modId) => {
    const pid = modId?.toLowerCase()
    if (!pid) return 'none'
    // 优先看用户规则
    const user = userModRules.value[pid]
    if (user) {
      if (user.loadTop?.value) return { pos: 'top', source: 'user', comment: user.loadTop.comment }
      if (user.loadBottom?.value) return { pos: 'bottom', source: 'user', comment: user.loadBottom.comment }
    }
    // 次优先看社区规则
    const comm = communityModRules.value[pid]
    if (comm) {
      if (comm.loadTop?.value) return { pos: 'top', source: 'community', comment: comm.loadTop.comment }
      if (comm.loadBottom?.value) return { pos: 'bottom', source: 'community', comment: comm.loadBottom.comment }
    }
    return { pos: 'none', source: null }
  }

  // 设置绝对位置
  const setAbsolutePosition = async (modId, position, comment = '') => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.rule_set_user_mod_absolute_position(modId, position, comment)
    if (appStore.checkResult(res, '设置绝对排序位置')) {
      fetchRules() // 刷新本地数据
      modStore.scanMods() // 触发重新计算
    }
  }

  // 改变规则来源的优先级
  const changeRuleSourcePriority = async (rules_sources) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.change_rule_source_priority(rules_sources)
    if (appStore.checkResult(res, '改变规则优先级', true)) {
      fetchRules()
      modStore.scanMods()
      return true
    }
    return false
  }
  // 设置全局规则开关
  const setGlobalEnable = async (key, enabled) => {
    // key: 'community_mod_rules_enabled' | 'user_mod_rules_enabled' | 'dynamic_rules_enabled'
    const type = {
      'community':'community_mod_rules_enabled',
      'user':'user_mod_rules_enabled',
      'dynamic':'dynamic_rules_enabled',
      'workshop':'workshop_mod_rules_enabled',
      'workshop_dependencies':'workshop_rules_as_dependency',
    }
    if (!window.pywebview) return
    settings.value[type[key]] = enabled
    const res = await window.pywebview.api.rule_global_enable(type[key], enabled)
    if (!appStore.checkResult(res, '全局规则开关')) fetchRules()
    if (key === 'workshop_dependencies') {
      fetchRules()
    }
  }
  // 切换规则开关
  const toggleModRule = async (rule_type, package_id) => {
    if (!window.pywebview) return
    const pid = package_id.toLowerCase()
    let excludedMods = []
    if (rule_type === 'user') {
      excludedMods = settings.value.excluded_user_mods
    } else if (rule_type === 'community') {
      excludedMods = settings.value.excluded_community_mods
    } else if (rule_type === 'workshop') {
      excludedMods = settings.value.excluded_workshop_mods
    } else {
      return
    }
    // 乐观更新
    const excludedSet = new Set(excludedMods);
    excludedSet.has(pid) ? excludedSet.delete(pid) : excludedSet.add(pid);
    // 转回数组赋值（保持数据结构一致）
    if (rule_type === 'user') {
      settings.value.excluded_user_mods = Array.from(excludedSet);
    } else if (rule_type === 'community') {
      settings.value.excluded_community_mods = Array.from(excludedSet);
    } else if (rule_type === 'workshop') {
      settings.value.excluded_workshop_mods = Array.from(excludedSet);
    }
    const res = await window.pywebview.api.rule_toggle_mod(rule_type, pid, excludedSet.has(pid))
    if (!appStore.checkResult(res, '用户规则开关')) fetchRules()
  }

  // --- 动态规则操作 ---
  // 切换动态规则状态
  const toggleDynamicRule = async (rule) => {
    if (!window.pywebview) return
    // 乐观更新 UI
    rule.enabled = !rule.enabled
    const res = await window.pywebview.api.rule_toggle_dynamic(rule.rule_id, rule.enabled)
    if(!appStore.checkResult(res, '切换规则')) {
      fetchRules()
    }
  }
  // 保存动态规则
  const saveDynamicRules = async (rule) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.rule_update_dynamic(rule)
    if (appStore.checkResult(res, '保存规则',true)) {
      fetchRules()
      return true
    }
  }
  // 删除动态规则
  const deleteDynamicRule = async (rule) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.rule_delete_dynamic(rule.rule_id)
    if(appStore.checkResult(res, '删除规则', true)) {
      fetchRules()
    }
  }
  // --- 导入导出 ---
  // 更新社区库
  const updateCommunity = async () => {
    isLoading.value = true
    try {
        // 调用 API
        const res = await window.pywebview.api.update_community_rule()
        if (appStore.checkResult(res, '更新社区库')) {
          const task_id = res.data.task_id
          const filePath = await appStore.waitForDownload(task_id)
          // 重新获取规则数据 (此时后端内存已是最新)
          await fetchRules() 
        }
    } catch (error) {
        toast.error("更新社区库失败: " + error.message)
    } finally {
      isLoading.value = false
    }
  }
  // 更新创意工坊库
  const updateWorkshop = async () => {
    isLoading.value = true
    const res = await appStore.updateExternalDB('workshop_db')
    isLoading.value = false
  }
  // 导出规则
  const handleExport = async () => {
    const ids = userDynamicRules.value.map(r => r.rule_id)
    const res = await window.pywebview.api.rule_export_bundle(ids)
    if(!appStore.checkResult(res, '导出规则', true)) {
      return
    }
  }
  // 导入规则
  const handleImport = async () => {
    const res = await window.pywebview.api.rule_import_bundle()
    if(appStore.checkResult(res, '导入规则', true)) {
      fetchRules()
      modStore.scanMods()
    }
  }
  
  return {
    communityModRules, communityRulesUpdateTime, workshopModRules, userModRules, userDynamicRules, currentId, isLoading,
    targetId, currentConstraints, settings, DYNAMIC_RULE_PROPS, DYNAMIC_RULE_ACTIONS, DYNAMIC_RULE_OPERATORS,
    fetchRules, addUserModRule, removeUserModRuleItem, deleteUserModRule, updateComment,
    getAbsolutePosition, setAbsolutePosition,
    toggleDynamicRule, deleteDynamicRule, updateCommunity, handleExport, handleImport,
    saveDynamicRules, changeRuleSourcePriority,
    setGlobalEnable, toggleModRule,
  }
})