import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useModStore } from './modStore'
import { useAppStore } from './appStore'
import { createToastInterface } from 'vue-toastification'

// 动态规则支持属性映射
const DYNAMIC_RULE_PROPS = {
  'package_id': '包 ID',
  'name': '名称',
  'author': '作者',
  'tags': '标签',
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
  const userModRules = ref({})   // { pkg_id: { loadAfter: ... } }
  const userDynamicRules = ref([])
  const settings = ref({})

  const currentId = ref(null)
  
  // 当前正在检视的目标 Mod ID
  const targetId = computed(() => modStore.lastSelectedMod?.package_id || null)

  // --- Actions ---
  
  // 初始化加载 (在 App 启动或 refreshModList 时调用)
  const fetchRules = async () => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.get_all_rules()
      if (appStore.checkResult(res, '获取规则')) {
        communityModRules.value = res.data.community_rules
        userModRules.value = res.data.user_mod_rules
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
      mod.load_after_mods?.forEach(id => result.loadAfter.push({ id, source: 'native' }))
    //   mod.dependencies_mods?.forEach(d => result.loadAfter.push({ id: d.package_id, source: 'native' }))
      mod.load_before_mods?.forEach(id => result.loadBefore.push({ id, source: 'native' }))
      mod.incompatible_mods?.forEach(id => result.incompatible.push({ id, source: 'native' }))
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
    // 注意：我们需要深拷贝，不能直接改 ref
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
    if (res.status !== 'success') {
      toast.error(res.message)
      fetchRules() // 回滚
    } else {
      // 成功后触发健康检查 (因为规则变了)
      // modStore.checkHealth() // 需在组件侧或这里调用
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
    if (res.status !== 'success') fetchRules()
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
    if (res.status !== 'success') fetchRules()
  }
  // 删除用户单项规则
  const deleteUserModRule = async (id) => {
    if (!window.pywebview) return
    await window.pywebview.api.rule_delete_user_mod(id)
    fetchRules()
  }
  // 设置全局规则开关
  const setGlobalEnable = async (key, enabled) => {
    // key: 'community_mod_rules_enabled' | 'user_mod_rules_enabled' | 'dynamic_rules_enabled'
    const type = {
      'community':'community_mod_rules_enabled',
      'user':'user_mod_rules_enabled',
      'dynamic':'dynamic_rules_enabled',
    }
    if (!window.pywebview) return
    settings.value[type[key]] = enabled
    const res = await window.pywebview.api.rule_global_enable(type[key], enabled)
    if (res.status !== 'success') fetchRules()
  }
  // 切换社区规则排除开关
  const toggleCommunityModRule = async (package_id) => {
    if (!window.pywebview) return
    const pid = package_id.toLowerCase()
    // 乐观更新
    const { excluded_community_mods: excludedMods } = settings.value;
    const excludedSet = new Set(excludedMods);
    excludedSet.has(pid) ? excludedSet.delete(pid) : excludedSet.add(pid);
    // 转回数组赋值（保持数据结构一致）
    settings.value.excluded_community_mods = Array.from(excludedSet);
    const res = await window.pywebview.api.rule_toggle_community_mod(pid, excludedSet.has(pid))
    if (res.status !== 'success') fetchRules()
  }
  // 切换用户规则开关
  const toggleUserModRule = async (package_id) => {
    if (!window.pywebview) return
    const pid = package_id.toLowerCase()
    // 乐观更新
    const { excluded_user_mods: excludedMods } = settings.value;
    const excludedSet = new Set(excludedMods);
    excludedSet.has(pid) ? excludedSet.delete(pid) : excludedSet.add(pid);
    // 转回数组赋值（保持数据结构一致）
    settings.value.excluded_user_mods = Array.from(excludedSet);
    const res = await window.pywebview.api.rule_toggle_user_mod(pid, excludedSet.has(pid))
    if (res.status !== 'success') fetchRules()
  }

  // --- 动态规则操作 ---
  // 切换动态规则状态
  const toggleDynamicRule = async (rule) => {
    if (!window.pywebview) return
    // 乐观更新 UI
    rule.enabled = !rule.enabled
    await window.pywebview.api.rule_toggle_dynamic(rule.rule_id, rule.enabled)
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
    await window.pywebview.api.rule_delete_dynamic(rule.rule_id)
    fetchRules()
  }
  // --- 导入导出 ---
  // 更新社区库
  const updateCommunity = async () => {
    try {
        // 调用 API
        const res = await window.pywebview.api.rule_update_community()
        if (appStore.checkResult(res, '更新社区库', true)) {
            // 重新获取规则数据 (此时后端内存已是最新)
            await fetchRules() 
        }
    } catch (error) {
        toast.error("更新社区库失败: " + error.message)
    }
  }
  // 导出规则
  const handleExport = async () => {
    const ids = userDynamicRules.value.map(r => r.rule_id)
    await window.pywebview.api.rule_export_bundle(ids)
  }
  // 导入规则
  const handleImport = async () => {
    await window.pywebview.api.rule_import_bundle()
    fetchRules()
  }
  
  return {
    communityModRules, userModRules, userDynamicRules, currentId,
    targetId, currentConstraints, settings, DYNAMIC_RULE_PROPS, DYNAMIC_RULE_ACTIONS, DYNAMIC_RULE_OPERATORS,
    fetchRules, addUserModRule, removeUserModRuleItem, deleteUserModRule, updateComment,
    toggleDynamicRule, deleteDynamicRule, updateCommunity, handleExport, handleImport,
    saveDynamicRules, 
    setGlobalEnable, toggleCommunityModRule, toggleUserModRule,
  }
})