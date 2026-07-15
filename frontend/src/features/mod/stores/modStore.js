import { defineStore } from 'pinia'
import { ref, computed, nextTick } from 'vue'
import { deepClone, toast, checkResult, toUserMessage } from '../../../shared/lib/common'
import { useAppStore } from '../../../app/stores/appStore'
import { useGroupStore } from './groupStore'
import { useTaskStore } from '../../../app/stores/taskStore'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useMissingInstallStore } from '../../supplement/missingInstallStore'
import { useProfileStore } from '../../profiles/profileStore'
import { useSupplementStore } from '../../supplement/supplementStore'
import {
  buildSteamPackageToken,
  normalizePackageId,
  normalizePackageToken,
  normalizeWorkshopId,
  parsePackageToken,
  stripPackageTokenSuffix,
} from '../lib/modIdentity'
import { DEFAULT_TOOL_PACKAGE_IDS, isCorePackageId, isOfficialMod } from '../lib/packageScope.js'
import { useInstallSourceHints } from './mod-store/installSourceHints'
import { useModListHistory } from './mod-store/listHistory'
import { useModSelection } from './mod-store/selection'
import { useModExportPlan } from './mod-store/exportPlan'
import { useModIssues } from './mod-store/issues'
import { t } from '../../../shared/i18n.js'

export const useModStore = defineStore('mods', () => {
  const appStore = useAppStore()
  const taskStore = useTaskStore()
  const confirmStore = useConfirmStore()
  const profileStore = useProfileStore()
  const normalizeListToken = (id = '') => normalizePackageToken(id)
  const normalizeCanonicalId = (id = '') => stripPackageTokenSuffix(id)
  const buildCanonicalIdSet = (ids = []) => new Set(
    (ids || []).map(normalizeCanonicalId).filter(Boolean)
  )
  const resolveStoredMod = (id = '') => {
    const canonicalId = normalizeCanonicalId(id)
    return canonicalId ? allModsMap.value.get(canonicalId) : null
  }
  const normalizeRuntimeRoot = (path = '') => {
    const normalized = String(path || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
    return normalized ? `${normalized}/` : ''
  }
  const isExportableRuntimeMod = (mod) => {
    if (!mod || mod.isMissing || !mod.path) return false
    const localRoot = normalizeRuntimeRoot(profileStore.activeContext?.local_mods_path)
    const selfRoot = normalizeRuntimeRoot(appStore.settings?.self_mods_path)
    const workshopRoot = normalizeRuntimeRoot(appStore.settings?.workshop_mods_path)
    const modPath = normalizeRuntimeRoot(mod.path)
    if (!modPath) return false
    return (
      (localRoot && modPath.startsWith(localRoot))
      || (selfRoot && modPath.startsWith(selfRoot))
      || (workshopRoot && modPath.startsWith(workshopRoot))
    )
  }
  // 检查两个值是否相等
  const arePlainValuesEqual = (left, right) => {
    if (left === right) return true
    if (Array.isArray(left) || Array.isArray(right)) {
      if (!Array.isArray(left) || !Array.isArray(right)) return false
      if (left.length !== right.length) return false
      return left.every((value, index) => arePlainValuesEqual(value, right[index]))
    }
    if (!left || !right || typeof left !== 'object' || typeof right !== 'object') {
      return false
    }
    const leftKeys = Object.keys(left)
    const rightKeys = Object.keys(right)
    if (leftKeys.length !== rightKeys.length) return false
    return leftKeys.every(key => (
      Object.prototype.hasOwnProperty.call(right, key) && arePlainValuesEqual(left[key], right[key])
    ))
  }
  const snapshotModFields = (modIds = [], fields = []) => (
    [...new Set(modIds)].map(id => {
      const mod = resolveStoredMod(id)
      if (!mod) return null
      return {
        id,
        values: Object.fromEntries(fields.map(field => [field, deepClone(mod[field])])),
      }
    }).filter(Boolean)
  )
  const restoreModSnapshots = (snapshots = []) => {
    snapshots.forEach(snapshot => {
      const mod = resolveStoredMod(snapshot.id)
      if (mod) Object.assign(mod, snapshot.values)
    })
    dataVersion.value++
  }
  // 获取语言包所有者ID
  const getLanguagePackOwnerIds = (mod) => {
    const resolvedOwners = mod?.language_pack_owner_result?.owners || []
    return [...new Set(
      resolvedOwners
        .map(owner => normalizePackageId(owner?.package_id))
        .filter(Boolean)
    )]
  }
  const canUseLanguagePackForIssueDetection = (mod) => {
    const confidence = String(mod?.language_pack_owner_result?.summary_confidence || '').trim().toLowerCase()
    return confidence === 'high' || confidence === 'medium'
  }
  const isLanguagePackMod = (mod) => (mod?.user_mod_type || mod?.mod_type) === 'LanguagePack'
  const currentLanguage = computed(() => String(appStore.settings?.language || '').trim())
  const isDeclaredForCurrentLanguage = (mod) => (
    !!currentLanguage.value && (mod?.supported_languages || []).includes(currentLanguage.value)
  )

  // === State ===
  const allModsMap = ref(new Map())   // 核心数据，使用 Map 加速查找
  const dataVersion = ref(0)          // 数据版本，用于响应式刷新触发器
  const {
    installSourceHints,
    getInstallSourceHints,
    applyInstallSourceHintToMod,
    mergeInstallSourceHintsFromMods,
    clearInstallSourceHints,
    clearInstallSourceHintsByOrigin,
  } = useInstallSourceHints({ dataVersion, arePlainValuesEqual })

  const inactiveIds = ref([])         // 未激活Mod列表
  const tempIds = ref([])             // 临时Mod列表
  const activeIds = ref([])           // 已激活Mod列表
  const disabledMods = ref([])        // 当前环境路径范围内的物理禁用 Mod 资产
  const strictDisableRestoreFailures = ref({}) // 本次扫描中严格禁用恢复失败的提示

  const interlocksMap = ref(new Map()) // 联锁字典: Map<String(interlock_id), Array<String(package_ids)>>
  const savedInactiveIds = ref([])   // 从后端拉取的历史停用顺序
  const savedTempIds = ref([])       // 从后端拉取的临时列表顺序
  const savedActiveIds = ref([])      // 原始已激活列表快照（用于判断 列表变化）
  const activeLoadModifyTime = ref(0) // 已激活列表最后修改时间戳
  const activeLoadVersionToken = ref({})
  const pendingGhostFetches = new Map()
  const dismissedUnavailableIds = new Set()
  // 仅用于删除/取订后的保留列表状态同步，防止残留目录把刚清掉的数据立刻写回界面。
  const locallyRemovedPathHashes = new Set()

  const conflictList = ref([])        // 重复包名冲突列表
  const coexistenceList = ref([])     // 共存Mod列表

  const {
    selectedIds,
    lastSelectedMod,
    currentTargetId,
    isDraggingMod,
    selectedMods,
    selectedStats,
    clearSelection,
    selectMods,
  } = useModSelection({
    interlocksMap,
    normalizeListToken,
    takeModById: (...args) => takeModById(...args),
  })

  // === Getters ===
  // 检查列表变化
  const isDirty = computed(() => {
    // 简单数组比较：长度不同，或内容/顺序不同
    if (activeIds.value.length !== savedActiveIds.value.length) return true
    // 逐个比较
    return activeIds.value.some((id, i) => id !== savedActiveIds.value[i])
  })
  // 获取所有模组的所有标签（去重）
  const allModTags = computed(() => {
    return [...new Set(Array.from(allModsMap.value.values()).flatMap(mod => mod.tags || []))]
  })
  const installedWorkshopIds = computed(() => {
    return new Set(
      Array.from(allModsMap.value.values())
        .filter(mod => !mod?.isMissing && !!mod?.path)
        .map(mod => normalizeWorkshopId(mod?.workshop_id))
        .filter(Boolean)
    )
  })
  const {
    exportableVisibleCount,
    exportableActiveCount,
    resolveCurrentExportBaseIds,
    resolveCurrentExportPlan,
  } = useModExportPlan({
    activeIds,
    inactiveIds,
    tempIds,
    interlocksMap,
    appSettings: computed(() => appStore.settings || {}),
    currentLanguage,
    normalizeCanonicalId,
    takeModById: (...args) => takeModById(...args),
    isExportableRuntimeMod,
    isLanguagePackMod,
    canUseLanguagePackForIssueDetection,
    getLanguagePackOwnerIds,
    isDeclaredForCurrentLanguage,
  })
  // === Actions ===
  const normalizeHistoryModIds = (ids = []) => {
    const source = Array.isArray(ids) ? ids : [ids]
    return [...new Set(
      source
        .map(id => normalizeListToken(id))
        .filter(Boolean)
    )]
  }
  const confirmUndoListHistory = async (entry = {}) => {
    const notice = entry?.undoNotice
    if (!notice?.message) return true
    const ok = await confirmStore.confirmAction(
      notice.title || t('dialog.mod_store.undo.title', '撤销列表变更'),
      notice.message,
      {
        type: notice.type || 'warning',
        confirmText: notice.confirmText || t('common.action.restore_list', '恢复列表'),
        cancelText: notice.cancelText || t('common.action.cancel', '取消'),
      }
    )
    return !!ok
  }
  const {
    listHistoryUndoStack,
    listHistoryRedoStack,
    isApplyingListHistory,
    listHistoryTotal,
    listHistoryPosition,
    canUndoListHistory,
    canRedoListHistory,
    captureListHistorySnapshot,
    clearListHistory,
    runListHistoryTransaction,
    recordListHistory,
    undoListHistory,
    redoListHistory,
  } = useModListHistory({
    activeIds,
    inactiveIds,
    tempIds,
    savedActiveIds,
    activeLoadModifyTime,
    activeLoadVersionToken,
    dataVersion,
    normalizeHistoryModIds,
    resolveStoredMod,
    beforeUndoListHistory: confirmUndoListHistory,
  })
  const disabledPathHashes = computed(() => disabledMods.value.map(mod => mod.path_hash).filter(Boolean))
  const setListIds = (listId, ids = []) => {
    const nextIds = normalizeHistoryModIds(ids)
    nextIds.forEach(id => dismissedUnavailableIds.delete(id))
    if (listId === 'active') activeIds.value = nextIds
    else if (listId === 'inactive') inactiveIds.value = nextIds
    else if (listId === 'temp') tempIds.value = nextIds
  }
  // 设置活动加载基线
  const setActiveLoadBaseline = (ids = [], modifyTime = 0, versionToken = {}) => {
    savedActiveIds.value = [...(ids || [])]
    activeLoadModifyTime.value = modifyTime || 0
    activeLoadVersionToken.value = { ...(versionToken || {}) }
  }
  // 获取 Mod 对象
  const takeModById = (id, defaultName = t('common.entity.unknown_mod', '未知模组')) => {
    if (!id) return null
    const tokenInfo = parsePackageToken(id)
    const canonicalId = tokenInfo.canonicalPackageId || normalizeCanonicalId(id)
    if (canonicalId && allModsMap.value.has(canonicalId)) {
      const mod = allModsMap.value.get(canonicalId)
      applyInstallSourceHintToMod(mod, canonicalId)
      if (tokenInfo.sourcePreference === 'steam' && mod?.coexist_workshop_variant) {
        const variant = {
          ...mod,
          ...mod.coexist_workshop_variant,
          package_id: canonicalId,
          canonical_package_id: canonicalId,
          active_package_token: buildSteamPackageToken(canonicalId),
          source_preference: 'steam',
          is_coexistence: true,
        }
        applyInstallSourceHintToMod(variant, canonicalId)
        return variant
      }
      mod.canonical_package_id = canonicalId
      mod.active_package_token = canonicalId
      mod.source_preference = 'local'
      return mod
    }
    // 构造缺失模组的“幽灵对象”
    const ghostMod = {
      package_id: canonicalId || id,
      canonical_package_id: canonicalId || id,
      active_package_token: tokenInfo.sourcePreference === 'steam' ? buildSteamPackageToken(canonicalId || id) : (canonicalId || id),
      name: `⚠ ${defaultName} (${canonicalId || id})`,
      path: null,
      description: t('ui.mod.missing.description', '该模组在本地未找到，可能未下载，或已被手动删除。'),
      isMissing: true,
    }
    applyInstallSourceHintToMod(ghostMod, canonicalId || id)
    return ghostMod
  }
  const getAvailableModInstances = () => {
    const tokens = new Set()
    for (const mod of allModsMap.value.values()) {
      const canonicalId = normalizeCanonicalId(mod?.package_id)
      if (!canonicalId) continue
      tokens.add(canonicalId)
      if (mod?.coexist_workshop_variant) tokens.add(buildSteamPackageToken(canonicalId))
    }
    return [...tokens].map(token => takeModById(token)).filter(Boolean)
  }
  const hasRealModById = (id) => {
    if (!id) return false
    const mod = resolveStoredMod(id)
    if (!mod) return false
    // ghost 项虽然会被塞进 allModsMap，但它们不应该被当成“真实已安装模组”。
    return !!mod && !mod.isMissing && !!mod.path
  }
  // 检查是否已安装指定 workshop ID
  const hasInstalledWorkshopId = (workshopId = '') => {
    const normalizedWorkshopId = normalizeWorkshopId(workshopId)
    if (!normalizedWorkshopId) return false
    return installedWorkshopIds.value.has(normalizedWorkshopId)
  }
  // 获取 Mod 对象列表
  const takeModListByIds = (ids) => {
    return (ids || []).map(id => takeModById(id)).filter(Boolean)
  }
  // 显示 Mod 名称（优先 alias_name -> display_name -> name -> package_id）
  const displayModName = (modOrId, defaultName = t('common.entity.unknown_mod', '未知模组')) => {
    // 处理输入：Mod 对象或 ID 字符串统统转为Mod对象
    let mod = null
    if(typeof modOrId === 'string') mod = takeModById(modOrId, defaultName)
    else if(modOrId?.package_id) mod = modOrId
    // 构造显示名称
    const res = mod?.alias_name || mod?.display_name || mod?.name || mod?.package_id
    return res || `⚠ ${defaultName} (${modOrId})`
  }
  // 显示 Mod 类型（优先 user_mod_type -> mod_type -> Unknown）
  const displayModType = (modOrId) => {
    // 处理输入：Mod 对象或 ID 字符串统统转为Mod对象
    let mod = null
    if(typeof modOrId === 'string') mod = takeModById(modOrId)
    else if(modOrId?.package_id) mod = modOrId
    // 构造显示类型
    const res = mod?.user_mod_type || mod?.mod_type || 'Unknown'
    return res
  }
  // 显示 Mod 图标，只使用 About 中声明或默认发现的图标。
  const displayModIcon = (id) => {
    const mod = takeModById(id)
    if (mod && mod.icon_path) return appStore.getLocalUrl(mod.icon_path)
    return '' // 返回空或默认图路径
  }

  // --- 列表数据处理 ---
  // 刷新未激活Mod列表 (实现“新Mod置顶，旧Mod持久，联锁聚拢”)
  const updateInactiveIds = () => {
    // 清理临时列表 (Temp - Active) （Temp列表 是前端的临时列表，防止与刷新后的 Active列表 出现重复项）
    const activeSet = buildCanonicalIdSet(activeIds.value)
    tempIds.value = tempIds.value.filter(id => !activeSet.has(normalizeCanonicalId(id)))
    inactiveIds.value = takeInactiveIds()
  }
  // 获取未激活Mod ID 列表 (全集 - 活跃 - 临时)
  const takeInactiveIds = () => {
    const activeSet = buildCanonicalIdSet(activeIds.value)
    const tempSet = buildCanonicalIdSet(tempIds.value)
    // 1. 获取所有没在 active 和 temp 里的 Mod
    const newMods = [] // 收集"新" Mod（未在保存的 inactive 列表中出现过）
    // 建立旧顺序的查找索引 O(1)
    const savedIndexMap = new Map()
    savedInactiveIds.value.forEach((id, idx) => savedIndexMap.set(normalizeCanonicalId(id), idx))
    for (const mod of allModsMap.value.values()) {
      const pid = normalizeCanonicalId(mod.package_id)
      if (!activeSet.has(pid) && !tempSet.has(pid)) {
        if (!savedIndexMap.has(pid)) {
          newMods.push(mod)
        }
      }
    }
    // 2. 将 "新 Mod" 按照文件创建时间/修改时间降序排列 (最新的在最前面)
    newMods.sort((a, b) => {
      const timeA = Math.max(a.file_create_time || 0, a.file_modify_time || 0)
      const timeB = Math.max(b.file_create_time || 0, b.file_modify_time || 0)
      return timeB - timeA
    })
    const newModIds = newMods.map(m => m.package_id)
    // 3. 将 "旧 Mod" 按照 savedInactiveIds 中的原始顺序排列
    const oldModIds = savedInactiveIds.value.filter(id => {
      const pid = normalizeCanonicalId(id)
      return !activeSet.has(pid) && !tempSet.has(pid) && hasRealModById(pid)
    })
    // 4. 基础合并
    const baseInactive = [...newModIds, ...oldModIds]
    const finalInactive = []
    const processed = new Set()
    const tokenByCanonicalId = new Map(baseInactive.map(id => [normalizeCanonicalId(id), id]))
    // 建立查找表提升性能
    const baseInactiveSet = buildCanonicalIdSet(baseInactive)
    for (const id of baseInactive) {
      const pid = normalizeCanonicalId(id)
      if (processed.has(pid)) continue

      const mod = allModsMap.value.get(pid)
      // 如果属于某个联锁序列
      if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
        const chain = interlocksMap.value[mod.interlock_id]
        // 遍历该链条，把所有属于 inactive 列表的兄弟姐妹都拉过来，按链条固有顺序排列
        for (const chainId of chain) {
          const cid = normalizeCanonicalId(chainId)
          if (baseInactiveSet.has(cid) && !processed.has(cid)) {
            // 找到原始大小写格式的 ID 并存入
            finalInactive.push(tokenByCanonicalId.get(cid) || chainId)
            processed.add(cid)
          }
        }
      } else {
        // 独立 Mod，直接推入
        finalInactive.push(id)
        processed.add(pid)
      }
    }

    return finalInactive
  }
  // 批量查询未知 PackageID 并将其作为幽灵项存入 Map
  const fetchAndCacheGhostMods = async (ids = []) => {
    if (!ids || ids.length === 0 || !window.pywebview) return

    const normalizedIds = [...new Set(
      ids
        .map(id => normalizeCanonicalId(id))
        .filter(Boolean)
    )]

    // 筛选出本地缺失(完全未知或本身就是 isMissing )的 ID
    const unknownIds = normalizedIds.filter(id => {
      const existing = allModsMap.value.get(id)
      return !existing || existing.isMissing
    })
    if (unknownIds.length === 0) return

    const pendingTasks = []
    const idsToFetch = []
    unknownIds.forEach(id => {
      const pendingTask = pendingGhostFetches.get(id)
      if (pendingTask) pendingTasks.push(pendingTask)
      else idsToFetch.push(id)
    })

    const buildGhostMod = (id, currentMod = null, meta = null) => {
      const baseMod = currentMod ? { ...currentMod } : { package_id: id }
      if (meta) {
        Object.assign(baseMod, meta)
        baseMod.name = `⚠ ${meta.name || id} (${id})`
        baseMod.display_name = meta.name
      } else if (!currentMod) {
        baseMod.name = t('ui.mod.missing.name_with_id', '⚠ 未知模组 ({id})', { id })
      }
      baseMod.path = null
      baseMod.isMissing = true
      baseMod.description = t('ui.mod.missing.description', '该模组在本地未找到，可能未下载，或已被手动删除。')
      baseMod.package_id = id
      applyInstallSourceHintToMod(baseMod, id)
      return baseMod
    }

    let batchTask = null
    if (idsToFetch.length > 0) {
      batchTask = (async () => {
        try {
          const res = await window.pywebview.api.get_workshop_details_by_package_ids(idsToFetch)
          if (res?.status === 'success' && res.data) {
            let changed = false
            const metaMap = Object.fromEntries(
              Object.entries(res.data || {}).map(([packageId, payload]) => [
                packageId,
                payload?.display?.selected || payload || null,
              ])
            )
            idsToFetch.forEach(id => {
              const currentGhost = allModsMap.value.get(id) || null
              if (
                dismissedUnavailableIds.has(id)
                && (!currentGhost || currentGhost.isMissing || !currentGhost.path)
              ) return
              const nextGhost = buildGhostMod(id, currentGhost, metaMap[id] || null)
              if (arePlainValuesEqual(currentGhost, nextGhost)) return
              allModsMap.value.set(id, nextGhost)
              changed = true
            })
            if (changed) {
              dataVersion.value++
            }
          }
        } catch (e) {
          console.error("加载幽灵模组缓存信息失败:", e)
        } finally {
          idsToFetch.forEach(id => {
            if (pendingGhostFetches.get(id) === batchTask) {
              pendingGhostFetches.delete(id)
            }
          })
        }
      })()
      idsToFetch.forEach(id => pendingGhostFetches.set(id, batchTask))
      pendingTasks.push(batchTask)
    }

    if (pendingTasks.length > 0) {
      await Promise.allSettled(pendingTasks)
    }
  }
  const takeDisabledModByPathHash = (pathHash) => {
    const targetHash = String(pathHash || '').trim()
    if (!targetHash) return null
    return disabledMods.value.find(mod => mod?.path_hash === targetHash) || null
  }
  // 设置 Mod 数据
  const setMods = (data, options = {}) => {
    const { resetHistory = false, preserveListState = false } = options || {}
    if (resetHistory) clearListHistory()
    clearInstallSourceHintsByOrigin('import')
    if (!preserveListState) {
      dismissedUnavailableIds.clear()
      locallyRemovedPathHashes.clear()
    }
    const nextActiveIds = normalizeHistoryModIds(data.active_load_order || [])
    if (!preserveListState) {
      activeIds.value = nextActiveIds
      setActiveLoadBaseline(
        nextActiveIds,
        data.active_load_modify_time || 0,
        data.active_load_version_token || {}
      )
    }
    const persistTempList = !!appStore.settings.ui?.persist_temp_mod_list
    if (!preserveListState) {
      savedInactiveIds.value = normalizeHistoryModIds(data.inactive_load_order || []) // 接收持久化停用顺序
      savedTempIds.value = normalizeHistoryModIds(data.temp_load_order || [])
      if (!persistTempList && savedTempIds.value.length > 0) {
        savedInactiveIds.value = normalizeHistoryModIds([...savedTempIds.value, ...savedInactiveIds.value])
      }
    }
    interlocksMap.value = data.interlocks || {}             // 接收联锁字典
    // 创建一个 Set 用于 O(1) 快速查找
    const activeSet = buildCanonicalIdSet(preserveListState ? activeIds.value : nextActiveIds)
    // 直接重建 Map，确保删除的 Mod 能被移除，新增的能被加入
    const tempMap = new Map()
    data.all_mods.forEach(mod => {
      const canonicalId = normalizeCanonicalId(mod.package_id)
      const pathHash = String(mod.path_hash || '').trim()
      // 删除/取订后的自动扫描会保留三列表状态；只屏蔽刚处理的具体副本，避免误挡同包名共存副本。
      if (preserveListState && pathHash && locallyRemovedPathHashes.has(pathHash)) return
      // 初始化启用时间（如果 Mod 是 Active 但没有启用时间，则记录为排序文件更新时间，若仍有问题则记录为当前时间）
      if (canonicalId && activeSet.has(canonicalId) && !mod.last_active_time) {
        mod.last_active_time = data.active_load_modify_time || Date.now()
      }
      // 强制保证列表字段存在且格式正确
      if (!Array.isArray(mod.author) && !mod.author) mod.author = ['Unknown']
      if (!Array.isArray(mod.supported_versions)) mod.supported_versions = []
      if (!Array.isArray(mod.supported_languages)) mod.supported_languages = []
      if (!Array.isArray(mod.gallery_paths)) mod.gallery_paths = []
      if (!Array.isArray(mod.load_after_mods)) mod.load_after_mods = []
      if (!Array.isArray(mod.load_before_mods)) mod.load_before_mods = []
      if (!Array.isArray(mod.incompatible_mods)) mod.incompatible_mods = []
      if (!Array.isArray(mod.tags)) mod.tags = []
      if (!Array.isArray(mod.ignored_issues)) mod.ignored_issues = []
      applyInstallSourceHintToMod(mod, mod.package_id)
      tempMap.set(canonicalId, mod)
    })
    allModsMap.value = tempMap
    if (preserveListState) locallyRemovedPathHashes.clear()
    disabledMods.value = Array.isArray(data.disabled_mods) ? data.disabled_mods.filter(mod => mod?.path_hash) : []
    if (lastSelectedMod.value) {
      const lastToken = lastSelectedMod.value.active_package_token || lastSelectedMod.value.package_id
      lastSelectedMod.value = takeModById(lastToken) || (selectedIds.value.length > 0
        ? takeModById(selectedIds.value[selectedIds.value.length - 1])
        : null)
    }
    if (!preserveListState) {
      tempIds.value = persistTempList
        ? savedTempIds.value.filter(id => !activeSet.has(normalizeCanonicalId(id)) && hasRealModById(id))
        : []
      // 重新计算 Inactive列表 (排除 Active 和 Temp)（本质上 Temp列表 与 Inactive列表 一样，但在前端分出差异方便整理）
      updateInactiveIds()
    }
    dataVersion.value++    // 更新数据版本号（刷新标记）
    // 初始化获取完所有模组后，如果 activeIds 中存在未知项，批量缓存它们！
    if (!preserveListState) fetchAndCacheGhostMods(activeIds.value)
  }
  const mergeModEnrichment = (payload = {}) => {
    // enrichment 只补列表展示标记，不改变三列表和主数据集合。
    const patches = payload?.mods && typeof payload.mods === 'object' ? payload.mods : {}
    Object.entries(patches).forEach(([packageId, patch]) => {
      const mod = allModsMap.value.get(normalizeCanonicalId(packageId))
      if (!mod || !patch || typeof patch !== 'object') return
      const { coexist_workshop_variant: workshopPatch, ...basePatch } = patch
      Object.assign(mod, basePatch)
      // enrichment 返回的是增量；共存实例必须合并到嵌套对象，不能覆盖整个实例导致原生规则等字段丢失。
      if (workshopPatch && typeof workshopPatch === 'object' && mod.coexist_workshop_variant) {
        Object.assign(mod.coexist_workshop_variant, workshopPatch)
      }
    })
    const disabledPatches = payload?.disabled_mods && typeof payload.disabled_mods === 'object' ? payload.disabled_mods : {}
    disabledMods.value.forEach(mod => {
      const patch = disabledPatches[String(mod?.path_hash || '').trim()]
      if (patch && typeof patch === 'object') Object.assign(mod, patch)
    })
    if (payload?.interlocks && typeof payload.interlocks === 'object') {
      interlocksMap.value = payload.interlocks
    }
    dataVersion.value++
  }
  // 重置 Mod 数据
  const reset = () => {
    clearListHistory()
    allModsMap.value.clear()
    activeIds.value = []
    inactiveIds.value = []
    tempIds.value = []
    disabledMods.value = []
    strictDisableRestoreFailures.value = {}
    savedActiveIds.value = []
    savedInactiveIds.value = []
    savedTempIds.value = []
    activeLoadModifyTime.value = 0
    activeLoadVersionToken.value = {}
    clearInstallSourceHints()
    dismissedUnavailableIds.clear()
    dataVersion.value++
  }
  // 从所有列表中移除指定 IDs
  const removeIdsOnAllList = (ids) => {
    const normalizedIds = buildCanonicalIdSet(normalizeHistoryModIds(ids))
    activeIds.value = activeIds.value.filter(i => !normalizedIds.has(normalizeCanonicalId(i)))
    inactiveIds.value = inactiveIds.value.filter(i => !normalizedIds.has(normalizeCanonicalId(i)))
    tempIds.value = tempIds.value.filter(i => !normalizedIds.has(normalizeCanonicalId(i)))
  }
  // 删除或取订删除成功后只清理前端真实模组数据；是否移除列表项由调用方按具体流程决定。
  const removeDeletedModsFromLocalData = (items) => {
    const list = Array.isArray(items) ? items : [items].filter(Boolean)
    const normalizedIdSet = buildCanonicalIdSet(normalizeHistoryModIds(list.map(item => (
      item && typeof item === 'object'
        ? (item.package_id || item.id)
        : item
    ))))
    const removedPathHashes = new Set(list
      .map(item => item && typeof item === 'object' ? String(item.path_hash || '').trim() : '')
      .filter(Boolean))
    if (normalizedIdSet.size === 0 && removedPathHashes.size === 0) return 0

    let changed = false
    removedPathHashes.forEach(pathHash => locallyRemovedPathHashes.add(pathHash))
    normalizedIdSet.forEach(id => {
      const mod = allModsMap.value.get(id)
      if ((!removedPathHashes.size || removedPathHashes.has(String(mod?.path_hash || '').trim())) && allModsMap.value.delete(id)) changed = true
      dismissedUnavailableIds.delete(id)
    })

    const selectedBefore = selectedIds.value.length
    selectedIds.value = selectedIds.value.filter(id => !normalizedIdSet.has(normalizeCanonicalId(id)))
    if (selectedIds.value.length !== selectedBefore) {
      changed = true
    }
    if (normalizedIdSet.has(normalizeCanonicalId(currentTargetId.value))) {
      currentTargetId.value = ''
      changed = true
    }
    if (normalizedIdSet.has(normalizeCanonicalId(lastSelectedMod.value?.active_package_token || lastSelectedMod.value?.package_id))) {
      lastSelectedMod.value = selectedIds.value.length > 0
        ? takeModById(selectedIds.value[selectedIds.value.length - 1])
        : null
      changed = true
    }

    if (changed) dataVersion.value++
    return normalizedIdSet.size || removedPathHashes.size
  }
  const removeUnavailableIdsCompletely = (ids) => {
    const normalizedIds = normalizeHistoryModIds(ids)
    const normalizedIdSet = buildCanonicalIdSet(normalizedIds)
    if (normalizedIdSet.size === 0) return 0

    removeIdsOnAllList(normalizedIds)

    let changed = false
    normalizedIdSet.forEach(id => {
      dismissedUnavailableIds.add(id)
      const mod = allModsMap.value.get(id)
      if (mod && (mod.isMissing || !mod.path)) {
        allModsMap.value.delete(id)
        changed = true
      }
    })

    const selectedBefore = selectedIds.value.length
    selectedIds.value = selectedIds.value.filter(id => !normalizedIdSet.has(normalizeCanonicalId(id)))
    if (selectedIds.value.length !== selectedBefore) {
      changed = true
    }
    if (normalizedIdSet.has(normalizeCanonicalId(currentTargetId.value))) {
      currentTargetId.value = ''
      changed = true
    }
    if (normalizedIdSet.has(normalizeCanonicalId(lastSelectedMod.value?.active_package_token || lastSelectedMod.value?.package_id))) {
      lastSelectedMod.value = selectedIds.value.length > 0
        ? takeModById(selectedIds.value[selectedIds.value.length - 1])
        : null
      changed = true
    }

    if (changed) {
      dataVersion.value++
    }
    return normalizedIdSet.size
  }
  // 批量启用/停用Mod
  const changeModsActive = async (ids, active) => {
    if(typeof ids === 'string') ids = [ids]
    const nextIds = Array.isArray(ids) ? [...ids] : []
    if (nextIds.length === 0) return false
    return await runListHistoryTransaction({
      type: active ? 'change-active-enable' : 'change-active-disable',
      label: active
        ? t('history.mod.activate_count', '启用 {count} 个 Mod', { count: nextIds.length })
        : t('history.mod.deactivate_count', '停用 {count} 个 Mod', { count: nextIds.length }),
      trackedModIds: nextIds
    }, async () => {
      removeIdsOnAllList(nextIds)
      if(active) {
        await smartInsertMods(nextIds)
      } else {
        inactiveIds.value.unshift(...nextIds)
      }
      takeModListByIds(nextIds).forEach(mod => {
        mod.last_moved_time = Date.now()
        mod.last_active_time = Date.now()
      })
    })
  }
  const canSwitchCoexistenceSource = (id) => {
    const mod = resolveStoredMod(id)
    return !!mod?.coexist_workshop_variant
  }
  const buildCoexistenceListToken = (id, targetSource = 'local') => {
    const canonicalId = normalizeCanonicalId(id)
    if (!canonicalId) return ''
    if (targetSource === 'steam' && canSwitchCoexistenceSource(canonicalId)) {
      return buildSteamPackageToken(canonicalId)
    }
    return canonicalId
  }
  const replaceCoexistenceTokensInList = (list = [], canonicalIds = new Set(), targetSource = 'local') => {
    return (list || []).map(id => {
      const canonicalId = normalizeCanonicalId(id)
      if (!canonicalIds.has(canonicalId) || !canSwitchCoexistenceSource(canonicalId)) {
        return normalizeListToken(id)
      }
      return buildCoexistenceListToken(canonicalId, targetSource)
    })
  }
  const switchCoexistenceSource = async (ids, targetSource = 'local') => {
    const canonicalIds = buildCanonicalIdSet(Array.isArray(ids) ? ids : [ids])
    const switchableIds = new Set([...canonicalIds].filter(id => canSwitchCoexistenceSource(id)))
    if (switchableIds.size === 0) return false
    return await runListHistoryTransaction({
      type: `coexist-source-${targetSource}`,
      label: targetSource === 'steam'
        ? t('history.mod.switch_to_workshop_count', '切换 {count} 个 Mod 到工坊版', { count: switchableIds.size })
        : t('history.mod.switch_to_local_count', '切换 {count} 个 Mod 到本地版', { count: switchableIds.size }),
      trackedModIds: [...switchableIds],
    }, async () => {
      activeIds.value = replaceCoexistenceTokensInList(activeIds.value, switchableIds, targetSource)
      inactiveIds.value = replaceCoexistenceTokensInList(inactiveIds.value, switchableIds, targetSource)
      tempIds.value = replaceCoexistenceTokensInList(tempIds.value, switchableIds, targetSource)
      savedInactiveIds.value = replaceCoexistenceTokensInList(savedInactiveIds.value, switchableIds, targetSource)
      savedTempIds.value = replaceCoexistenceTokensInList(savedTempIds.value, switchableIds, targetSource)
      selectedIds.value = replaceCoexistenceTokensInList(selectedIds.value, switchableIds, targetSource)
      if (currentTargetId.value && switchableIds.has(normalizeCanonicalId(currentTargetId.value))) {
        currentTargetId.value = buildCoexistenceListToken(currentTargetId.value, targetSource)
      }
      if (lastSelectedMod.value) {
        const activeToken = lastSelectedMod.value.active_package_token || lastSelectedMod.value.package_id
        if (switchableIds.has(normalizeCanonicalId(activeToken))) {
          lastSelectedMod.value = takeModById(buildCoexistenceListToken(activeToken, targetSource))
        }
      }
    })
  }
  const toggleCoexistenceSource = async (id) => {
    const currentInfo = parsePackageToken(id)
    const targetSource = currentInfo.sourcePreference === 'steam' ? 'local' : 'steam'
    return await switchCoexistenceSource([id], targetSource)
  }
  const toggleSelectedCoexistenceSource = async (ids = selectedIds.value) => {
    const targetIds = Array.isArray(ids) && ids.length ? ids : selectedIds.value
    const firstSwitchableId = targetIds.find(id => canSwitchCoexistenceSource(id))
    if (!firstSwitchableId) return false
    const currentInfo = parsePackageToken(firstSwitchableId)
    const currentMod = resolveStoredMod(firstSwitchableId)
    const currentSource = currentInfo.sourcePreference || currentMod?.source_preference || currentMod?.store
    const targetSource = currentSource === 'steam' || currentSource === 'workshop' ? 'local' : 'steam'
    return await switchCoexistenceSource(targetIds, targetSource)
  }
  const revealSelectedMod = async (id = selectedIds.value[0]) => {
    const targetId = normalizeListToken(id)
    if (!targetId) return false
    // 连续定位同一个 Mod 时需要先清空目标，否则 Vue watch 不会再次触发滚动。
    currentTargetId.value = ''
    await nextTick()
    currentTargetId.value = targetId
    return true
  }
  // 智能插入 Mod 到 Active 列表
  const smartInsertMods = async (ids) => {
    if (!ids || ids.length === 0) return
    if (!window.pywebview) return
    if(typeof ids === 'string') ids = [ids]
    console.debug('准备智能插入 Mod:', ids)

    const res = await window.pywebview.api.smart_insert_mod_in_actives(ids, activeIds.value)
    if(checkResult(res, t('check.mod.smart_insert_active', '智能插入 Mod 到 Active 列表')) && res.data){
      activeIds.value = [...res.data]
    }
  }
  // --- 扫描处理 ---
  // 扫描 Mod 文件
  const scanMods = async (path_list=null, forced_update=false, size_check_override=null, size_check_paths=null) => {
    if (appStore.isScanRunning || !window.pywebview) return false
    strictDisableRestoreFailures.value = {}
    try {
      // 调用 API，会立即返回 { status: 'started' }
      const res = await window.pywebview.api.scan_mods(path_list, forced_update, size_check_override, size_check_paths)
      if (res.status === 'warning') {
        toast.info(res.message || t('toast.mod.scan_already_running', '扫描任务已在进行中，请等待当前扫描完成。'))
        return false
      }
      if (res.status !== 'success' && res.status !== 'started') {
        console.error("启动扫描失败:", res)
        toast.error(toUserMessage(res.message, t('toast.mod.scan_start_failed', '扫描启动失败。可能是当前环境路径无效、扫描器未初始化或后台任务暂时不可用，详细原因已写入系统日志。')))
        return false
      }
      const taskDetail = res?.data?.details || {}
      const taskId = String(taskDetail?.task_id || '')
      if (taskId && taskDetail?.status === 'started') {
        taskStore.createPlaceholderTask({
          id: taskId,
          type: 'scan',
          status: 'pending',
          progress: 0,
          message: t('tasks.message.queued', '任务已加入后台队列'),
          metrics: {
            title: t('tasks.scan.title', '模组扫描'),
            forced_update: !!forced_update,
            specific_paths: Array.isArray(path_list) ? path_list : [],
          },
        })
      }
      return true
    } catch (e) {
      console.error("扫描请求异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.scan_request_failed', '扫描请求异常。可能是软件后端暂时不可用或当前环境路径配置异常，详细原因已写入系统日志。')))
      return false
    }
  }
  // 扫描完成事件处理
  const scanComplete = async (detail = {}, options = {}) => {
    coexistenceList.value = Array.isArray(detail?.coexistences) ? detail.coexistences : []
    conflictList.value = Array.isArray(detail?.conflicts) ? detail.conflicts : []
    const restoreFailures = Array.isArray(detail?.strict_disable_restore_failures) ? detail.strict_disable_restore_failures : []
    strictDisableRestoreFailures.value = Object.fromEntries(
      restoreFailures.filter(item => item?.path_hash).map(item => [item.path_hash, item])
    )

    if (detail?.status === 'cancelled') {
      toast.info(detail.message || t('toast.mod.scan_cancelled', '扫描已取消'))
      console.info("扫描已取消:", detail)
      return
    }

    if (detail?.status && detail.status !== 'success') {
      toast.error(toUserMessage(detail.message, t('toast.mod.scan_failed', '扫描异常。可能是路径权限、文件占用或扫描器内部状态暂时不可用，详细原因已写入系统日志。')))
      console.error("扫描完成事件异常:", detail)
      return
    }

    const stats = detail?.stats || {}
    const added = Number(stats.added || 0)
    const updated = Number(stats.updated || 0)
    const removed = Number(stats.removed || 0)
    const skipped = Number(stats.skipped || 0)
    const externalEnabled = Number(stats.external_enabled || 0)
    const strictRestored = Number(stats.strict_restored_disabled || 0)
    const strictRestoreFailed = Number(stats.strict_restore_failed || 0)
    const total = Number(detail?.total ?? (added + updated + skipped))
    const silentSuccess = !!options?.silentSuccess
    const disabledStateText = [
      externalEnabled ? t('toast.mod.scan_external_enabled_count', '外部解除禁用 {count} 个', { count: externalEnabled }) : '',
      strictRestored ? t('toast.mod.scan_strict_restored_count', '已重新禁用 {count} 个', { count: strictRestored }) : '',
      strictRestoreFailed ? t('toast.mod.scan_strict_restore_failed_count', '恢复失败 {count} 个', { count: strictRestoreFailed }) : '',
    ].filter(Boolean).join('，')

    let totalCount = 0
    if (coexistenceList.value.length > 0) {
      if (appStore.settings.show_coexistence_message){
        console.warn("发现共存:", coexistenceList.value)
        totalCount += coexistenceList.value.length
      }
    }
    // 处理扫描结果，检测冲突提示 (包含可共存Mod)
    if (conflictList.value.length > 0) {
      console.warn("发现冲突:", conflictList.value)
      totalCount += conflictList.value.length
    }
    if (totalCount > 0) {
      // 注意：有冲突时暂不提示 "扫描完成" 的 Toast，以免遮挡，或者提示 Warning
      toast.warning(t('toast.mod.scan_conflicts_found', '扫描已完成，发现 {count} 个包名重复冲突需要处理。{extra}', { count: totalCount, extra: disabledStateText ? `\n${disabledStateText}` : '' }), {timeout: 10000})
    } else if (strictRestoreFailed > 0) {
      toast.warning(t('toast.mod.scan_done_with_restore_warning', '扫描已完成，共扫描 {total} 个模组，新增 {added} 个，更新 {updated} 个，删除 {removed} 个，已知 {skipped} 个。\n{extra}', { total, added, updated, removed, skipped, extra: disabledStateText }), {position: "top-center", timeout: 8000})
    } else if (!silentSuccess) {
      toast.success(t('toast.mod.scan_done', '扫描已完成，共扫描 {total} 个模组，新增 {added} 个，更新 {updated} 个，删除 {removed} 个，已知 {skipped} 个。{extra}', { total, added, updated, removed, skipped, extra: disabledStateText ? `\n${disabledStateText}` : '' }),{position: "top-center",timeout: 5000})
    }
    // 扫描结束后只回填模组主数据，避免把工作区、GitHub、合集等页面也一起重刷。
    console.debug("扫描统计:", {
      status: detail?.status,
      total,
      stats,
      conflict_count: conflictList.value.length,
      coexistence_count: coexistenceList.value.length,
      should_check_mod_residue: !!detail?.should_check_mod_residue,
      core_refresh_required: !!options?.forceCoreRefresh || detail?.core_refresh_required !== false,
    })
    if (!options?.forceCoreRefresh && detail?.core_refresh_required === false) {
      console.info('扫描未发现列表核心数据变化，跳过核心列表同步。')
      void appStore.refreshModEnrichment({ silent: true })
    } else {
      await appStore.refreshModCoreData('扫描后同步模组数据', {
        preserveListState: !!options?.preserveListState,
        refreshRules: options?.refreshRules !== false,
        refreshBackups: options?.refreshBackups !== false,
        refreshWorkspaceLibraries: options?.refreshWorkspaceLibraries !== false,
      })
    }
  }
  // 自动排序 Mod
  const autoSortMods = async (mod_ids) => {
    if (!window.pywebview) return
    // 处理空输入，默认使用当前活动项
    if (!mod_ids || mod_ids.length === 0) mod_ids = activeIds.value
    try {
      const missingInstallStore = useMissingInstallStore()
      const supplementStore = useSupplementStore()
      const canResolveMissing = await missingInstallStore.ensureResolvedBeforeAction({
        activeIds: activeIds.value,
        actionLabel: t('common.action.sort', '排序'),
      })
      if (!canResolveMissing) return
      const canContinue = await supplementStore.ensureRequiredBeforeAutosort({ activeIds: activeIds.value })
      if (!canContinue) return
      mod_ids = activeIds.value
      const res = await window.pywebview.api.auto_sort_mods(mod_ids)
      if (checkResult(res, t('check.mod.auto_sort', '自动排序Mod'))) {
        await runListHistoryTransaction({
          type: 'auto-sort',
          label: t('history.mod.auto_sort_count', '自动排序 {count} 个 Mod', { count: mod_ids.length })
        }, async () => {
          activeIds.value = res.data.sorted_ids || []
          updateInactiveIds()
        })
        toast.success(t('toast.mod.auto_sort_done', '自动排序已完成'))
        // 处理警告信息
        if(res.data.warnings?.length > 0) {
          let warningMessages = ''
          let warnModRule= []
          res.data.warnings.forEach(warning => {
            warningMessages += warning.message + '\n'
            if(warning.source_id) {
              warnModRule.push({mod_id: warning.source_id, target_id: warning.target_id||null ,type: warning.rule_type})
            }
          })
          toast.warning(warningMessages,{position: "top-center",timeout: 5000})
          if (warnModRule.length > 0) {
            console.debug("自动排序警告:",warnModRule)
            let msg = t('toast.mod.auto_sort_rule_warning_intro', '请检查以下Mod规则是否正确：\n')
            warnModRule.forEach(item => {
              msg += t('toast.mod.auto_sort_rule_warning_item', '{mod} 的 {type} 规则 可能存在问题：（{target}）\n', {
                mod: displayModName(item.mod_id),
                type: item.type.name,
                target: displayModName(item.target_id),
              })
            })
            toast.warning(msg,{position: "top-center",timeout: 10000})
          }
        }
        return true
      }
    } catch (e) {
      console.error("自动排序Mod异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.auto_sort_failed', '自动排序失败。可能是规则数据、缺失项处理或后端排序器暂时不可用，详细原因已写入系统日志。')))
    }
    return false
  }
  const normalizeResetActiveListConfig = (config = {}) => {
    return {
      excludedBuiltinIds: config.excluded_builtin_ids || [],
      userIds: config.user_ids || [],
      excludedDerivedIds: config.excluded_derived_ids || [],
    }
  }
  const resolveResetActiveListConfig = () => {
    const config = appStore.settings?.reset_active_list || {}
    return normalizeResetActiveListConfig(config)
  }
  const buildResetActiveListBasePreset = ({ config: configOverride = null, enableToolMods = appStore.settings?.enable_tool_mods } = {}) => {
    const config = configOverride || resolveResetActiveListConfig()
    const excludedBuiltinIds = new Set((config.excludedBuiltinIds || []).map(normalizePackageId).filter(Boolean))
    const officialIds = Array.from(allModsMap.value.values())
      .filter(mod => isOfficialMod(mod))
      .map(mod => normalizePackageToken(mod?.active_package_token || mod?.package_id))
      .filter(Boolean)
    const coreIds = officialIds.filter(isCorePackageId)
    const toolIds = enableToolMods
      ? Array.from(DEFAULT_TOOL_PACKAGE_IDS).filter(id => hasRealModById(id))
      : []
    const requiredIds = normalizeHistoryModIds([...coreIds, ...toolIds])
    const builtinIds = normalizeHistoryModIds(officialIds.filter(id => !isCorePackageId(id) && !excludedBuiltinIds.has(normalizePackageId(id))))
    const userIds = normalizeHistoryModIds(config.userIds)
    return {
      requiredIds,
      builtinIds,
      userIds,
      baseIds: normalizeHistoryModIds([...requiredIds, ...builtinIds, ...userIds]),
    }
  }
  const buildResetActiveListPreset = async (options = {}) => {
    const supplementStore = useSupplementStore()
    const config = options.config ? normalizeResetActiveListConfig(options.config) : resolveResetActiveListConfig()
    const basePreset = buildResetActiveListBasePreset({ config, enableToolMods: options.enableToolMods ?? appStore.settings?.enable_tool_mods })
    const baseIds = basePreset.baseIds
    const payload = await supplementStore.resolveSupplementPayloadForList(baseIds, { selectionMode: 'danger' })
    const removeSet = buildCanonicalIdSet(payload.removeIds || [])
    const excludedDerivedSet = buildCanonicalIdSet([...(config.excludedDerivedIds || []), ...(config.excludedBuiltinIds || [])])
    const baseSet = buildCanonicalIdSet(baseIds)
    const disabledToolSet = options.enableToolMods === false || (options.enableToolMods == null && !appStore.settings?.enable_tool_mods)
      ? buildCanonicalIdSet(Array.from(DEFAULT_TOOL_PACKAGE_IDS))
      : new Set()
    const derivedIds = normalizeHistoryModIds(payload.addIds || [])
      .filter(id => {
        const canonicalId = normalizeCanonicalId(id)
        return !baseSet.has(canonicalId) && !excludedDerivedSet.has(canonicalId) && !disabledToolSet.has(canonicalId)
      })
    const finalIds = normalizeHistoryModIds([
      ...baseIds.filter(id => !removeSet.has(normalizeCanonicalId(id))),
      ...derivedIds,
    ])
    return { ...basePreset, derivedIds, finalIds }
  }
  const resolveResetActiveListPreview = async (options = {}) => buildResetActiveListPreset(options)
  const sortActiveIdsForReset = async (ids = []) => {
    const targetIds = normalizeHistoryModIds(ids)
    if (!window.pywebview || targetIds.length === 0) return targetIds
    const res = await window.pywebview.api.auto_sort_mods(targetIds)
    if (!checkResult(res, t('check.mod.reset_active_sort', '重置启用列表排序'))) return null
    if (res.data?.warnings?.length > 0) {
      toast.warning(res.data.warnings.map(warning => warning.message).filter(Boolean).join('\n'), { position: 'top-center', timeout: 5000 })
    }
    return normalizeHistoryModIds(res.data?.sorted_ids || targetIds)
  }
  const applyResetActiveListPreset = async ({ silent = false } = {}) => {
    const preset = await buildResetActiveListPreset()
    const presetIds = normalizeHistoryModIds(preset.finalIds)
    if (presetIds.length === 0) {
      if (!silent) toast.warning(t('toast.mod.reset_active_list_no_base', '未找到可用于重置的官方模组或必要项，请先确认当前环境的游戏目录和模组扫描结果。'))
      return false
    }
    const sortedIds = await sortActiveIdsForReset(presetIds)
    if (!sortedIds) return false
    const success = await runListHistoryTransaction({
      type: 'reset-active-list',
      label: t('history.mod.reset_active_list', '重置启用列表'),
      trackedModIds: sortedIds,
    }, async () => {
      setListIds('active', sortedIds)
      updateInactiveIds()
      takeModListByIds(sortedIds).forEach(mod => {
        mod.last_moved_time = Date.now()
        mod.last_active_time = Date.now()
      })
    })
    if (success && !silent) toast.success(t('toast.mod.reset_active_list_done', '启用列表已重置'))
    return success
  }
  const resetActiveList = async ({ silent = false } = {}) => {
    if (!silent) {
      const ok = await confirmStore.confirmAction(
        t('dialog.mod.reset_active_list.title', '重置启用列表'),
        t('dialog.mod.reset_active_list.message', '此操作会清空当前启用列表，并按重置预设重新加入官方模组、必要项和补齐项。当前未保存的启用顺序会被替换。是否继续？'),
        { type: 'warning', confirmText: t('dialog.mod.reset_active_list.confirm', '清空并重置'), cancelText: t('common.action.cancel', '取消') },
      )
      if (!ok) return false
    }
    return await applyResetActiveListPreset({ silent })
  }
  const getLocalizeActionTitle = (totalCount = 0, existingCount = 0) => {
    const createCount = Math.max(Number(totalCount || 0) - Number(existingCount || 0), 0)
    if (existingCount > 0) return createCount > 0 ? t('dialog.mod.localize.sync_and_create_title', '本地化/同步本地共存模组') : t('dialog.mod.localize.sync_title', '同步本地共存模组')
    return t('dialog.mod.localize.create_title', '本地化共存模组')
  }
  const resolveLocalizeCandidates = (mods = [], store='workshop') => {
    const candidateMap = new Map()
    for (const mod of (Array.isArray(mods) ? mods : [])) {
      if (mod?.store === store && mod.path_hash) {
        candidateMap.set(mod.path_hash, { pathHash: mod.path_hash, isExisting: !!mod.is_coexistence })
      } else if (store === 'workshop' && mod?.coexist_workshop_variant?.path_hash) {
        candidateMap.set(mod.coexist_workshop_variant.path_hash, { pathHash: mod.coexist_workshop_variant.path_hash, isExisting: true })
      }
    }
    const candidates = [...candidateMap.values()]
    const existingCount = candidates.filter(m => m.isExisting).length
    return {
      candidates,
      pathHashes: candidates.map(m => m.pathHash),
      existingCount,
      createCount: Math.max(candidates.length - existingCount, 0),
      actionTitle: getLocalizeActionTitle(candidates.length, existingCount),
    }
  }
  const formatLocalizeConflictMessage = (conflicts = []) => {
    const rows = conflicts.slice(0, 6).map(item => {
      const packageText = item.package_id || t('common.status.unknown', '未知')
      const existingText = item.existing_package_id || t('common.status.unknown', '未知')
      return t('dialog.mod.localize.conflict_item', '目录 {folder} 已存在：当前 {current}，目标 {target}', {
        folder: item.target_folder,
        current: existingText,
        target: packageText,
      })
    })
    if (conflicts.length > rows.length) {
      rows.push(t('dialog.mod.localize.conflict_more', '还有 {count} 个同名目录需要按相同方式处理。', { count: conflicts.length - rows.length }))
    }
    return [
      t('dialog.mod.localize.conflict_message', '以下目标目录已经被其它 Mod 使用。请选择这些冲突项的处理方式，未冲突的 Mod 会正常处理。'),
      '',
      ...rows,
    ].join('\n')
  }
  const chooseLocalizeConflictAction = async (conflicts = []) => confirmStore.confirmAction(
    t('dialog.mod.localize.conflict_title', '同名目录需要确认'),
    formatLocalizeConflictMessage(conflicts),
    {
      type: 'warning',
      actionButtons: [
        { label: t('common.action.overwrite', '覆盖'), value: 'overwrite', kind: 'danger' },
        { label: t('common.action.save_as', '另存'), value: 'save_as', kind: 'primary' },
        { label: t('common.action.skip', '跳过'), value: 'skip' },
      ],
      defaultActionValue: 'save_as',
    }
  )
  // 本地化或同步本地共存
  const localizeSelectedMods = async (store='workshop') => {
    if (selectedIds.value.length === 0) return;
    // 使用 path_hash 精确定位当前副本，避免共存场景误选到另一份同包名模组。
    const { pathHashes, existingCount } = resolveLocalizeCandidates(selectedMods.value, store)
    if (pathHashes.length === 0) {
      toast.info(t('toast.mod.localize_no_workshop_items', '选中的模组中没有来自工坊的项'));
      return;
    }
    await localizeMods(pathHashes, store, { existingCount })
  }
  const localizeMods = async (pathHashes, store='workshop', options = {}) => {
    const storeText = store === 'workshop' ? t('common.source.workshop', 'Steam 创意工坊') : store
    const existingCount = Number(options?.existingCount || 0)
    const createCount = Math.max(pathHashes.length - existingCount, 0)
    const actionTitle = getLocalizeActionTitle(pathHashes.length, existingCount)
    const syncMessage = existingCount > 0
      ? (
          createCount > 0
            ? t('dialog.mod.localize.sync_and_create_message', '选中的 {total} 个{store}模组中，{createCount} 个会本地化为共存模组，{existingCount} 个会同步已有本地共存副本。', { total: pathHashes.length, store: storeText, createCount, existingCount })
            : t('dialog.mod.localize.sync_message', '选中的 {total} 个{store}模组已经存在本地共存模组。\n继续后会用当前{store}文件同步已有本地副本。', { total: pathHashes.length, store: storeText })
        )
      : t('dialog.mod.localize.create_message', '确定要将选中的 {total} 个{store}模组本地化为共存模组吗？\n本地化后会独立占用磁盘空间，后续{store}更新不会自动改动这些本地副本。', { total: pathHashes.length, store: storeText })
    const confirm = await confirmStore.confirmAction(
      actionTitle,
      syncMessage,
      { type: existingCount > 0 ? 'warning' : 'info', confirmText: existingCount > 0 ? t('common.action.start_processing', '开始处理') : t('common.action.start_localize', '开始本地化') }
    );
    if (!confirm) return false

    let conflictAction = ''
    while (true) {
      appStore.isLoading = true
      let res
      try {
        res = await window.pywebview.api.localize_workshop_mods(pathHashes, store, conflictAction)
      } finally {
        appStore.isLoading = false
      }
      if (res?.status === 'success' && res.data?.requires_conflict_action) {
        conflictAction = await chooseLocalizeConflictAction(res.data.conflicts || [])
        if (!conflictAction) return false
        continue
      }
      return checkResult(res, actionTitle)
    }
  }
  // 批量禁用选中项Mod
  const disableMods = async (pathHashes, disabled = true, options = {}) => {
    const hashes = [...new Set((Array.isArray(pathHashes) ? pathHashes : [pathHashes]).map(hash => String(hash || '').trim()).filter(Boolean))]
    if (hashes.length === 0) return false
    if (disabled) {
      const countText = hashes.length > 1
        ? t('dialog.mod.disable.selected_count', '选中的 {count} 个 Mod', { count: hashes.length })
        : t('dialog.mod.disable.this_mod', '该 Mod')
      const confirm = await confirmStore.confirmAction(
        t('dialog.mod.disable.title', '禁用确认'),
        t('dialog.mod.disable.message', '确定要禁用{target}吗？\n\n禁用会把该 Mod 的 About.xml 改名为 About.xml.disabled，让游戏扫描不到它。文件仍保留在原位置，可以在“已禁用”列表中重新启用。\n这里的“禁用”不是游戏内的“停用”。停用只是从当前加载顺序中移除；禁用会让游戏暂时看不到整个 Mod。\n请确保你完全明确后果再确认操作。', { target: countText }),
        { type: 'warning' }
      );
      if (!confirm) return false
    }
    appStore.isLoading = true;
    try {
      const res = await window.pywebview.api.mods_disable(hashes, disabled);
      const actionText = disabled ? t('check.mod.disable_selected', '禁用选中的模组') : t('check.mod.enable_selected', '启用选中的模组')
      if (checkResult(res, actionText)) {
        const successCount = Number(res.data?.success_count || hashes.length)
        const errorCount = Number(res.data?.error_count || 0)
        toast.success(t(disabled ? 'toast.mod.disabled_count' : 'toast.mod.enabled_count', disabled ? '已禁用 {count} 个 Mod{errorText}' : '已启用 {count} 个 Mod{errorText}', {
          count: successCount,
          errorText: errorCount ? t('toast.mod.failed_suffix', '，{count} 个失败', { count: errorCount }) : '',
        }))
        if (options.finishScan !== false) {
          await appStore.requestModScan({ preserveListState: !!options.preserveListState })
        }
        return res.data || { success_count: successCount, error_count: errorCount }
      }
      return false
    } finally {
      appStore.isLoading = false;
    }
  }
  const disableSelectedMods = async (ids = selectedIds.value) => {
    const items = resolveSelectedActionItems(ids).filter(item => item.mod?.path_hash)
    const pathHashes = [...new Set(items.map(item => item.mod.path_hash).filter(Boolean))]
    if (pathHashes.length === 0) return false
    const result = await disableMods(pathHashes, true, { finishScan: false })
    if (!result) return false
    const successPathHashes = new Set((result.success_items || []).map(item => item.path_hash).filter(Boolean))
    const changedItems = successPathHashes.size > 0
      ? items.filter(item => successPathHashes.has(item.mod.path_hash))
      : items
    if (changedItems.length === 0) return false
    await runListHistoryTransaction({
      type: 'disable-mod-files',
      label: t('history.mod.disable_count', '禁用 {count} 个 Mod', { count: changedItems.length }),
      trackedModIds: changedItems.map(item => item.id).filter(Boolean),
    }, async () => {
      removeIdsOnAllList(changedItems.map(item => item.id))
      selectMods([])
      return true
    })
    await appStore.requestModScan({ preserveListState: true })
    return true
  }
  // 批量删除Mod文件及数据记录
  const deleteMods = async (path_hashes, finish_scan = true) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const decision = await confirmStore.confirmDeleteAction(
      t('dialog.mod.delete.title', '删除确认'),
      t('dialog.mod.delete.message', '确定要删除这 {count} 个Mod吗？', { count: path_hashes.length }),
      {
        trashOptionText: t('common.action.move_to_trash', '移入回收站'),
        forceOptionText: t('common.action.force_delete', '强制删除'),
      }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.mods_delete(path_hashes, !!decision.force)
    if (checkResult(res, t('check.mod.delete_batch', '批量删除Mod'))) {
      toast.success(decision.force
        ? t('toast.mod.batch_force_deleted', '已彻底删除 {count} 个Mod', { count: res.data.success_count })
        : t('toast.mod.batch_moved_to_trash', '已移入回收站 {count} 个Mod', { count: res.data.success_count }))
      if(finish_scan) await appStore.requestModScan({ forceCoreRefresh: true })
      return true
    }
  }
  const resolveSelectedActionItems = (ids = selectedIds.value) => {
    const targetIds = Array.isArray(ids) && ids.length ? ids : selectedIds.value
    return targetIds.map(id => ({
      id: normalizeListToken(id),
      mod: takeModById(id),
    })).filter(item => item.id)
  }
  const removeDeletedItemsFromLists = async ({ items = [], type, label }) => {
    const listIds = items.map(item => item.id).filter(Boolean)
    const dataItems = items.map(item => ({
      id: item.mod?.package_id || item.id,
      path_hash: item.mod?.path_hash || '',
    })).filter(item => item.id || item.path_hash)
    if (listIds.length === 0) return false

    // 删除类动作会移除真实数据；撤销列表历史时只恢复列表 ID，缺失状态由扫描结果继续接管。
    return await runListHistoryTransaction({
      type,
      label,
      trackedModIds: listIds,
    }, async () => {
      removeDeletedModsFromLocalData(dataItems)
      selectMods([])
      removeIdsOnAllList(listIds)
      return true
    })
  }
  const deleteSelectedModFiles = async (ids = selectedIds.value) => {
    const deleteItems = resolveSelectedActionItems(ids).filter(item => item.mod?.path_hash)
    const pathHashes = [...new Set(deleteItems.map(item => item.mod.path_hash).filter(Boolean))]
    if (pathHashes.length === 0) return false
    const res = await deleteMods(pathHashes, false)
    if (!res) return false
    const removed = await removeDeletedItemsFromLists({
      items: deleteItems,
      type: 'delete-mod-files',
      label: t('history.mod.delete_local_files_count', '删除 {count} 个本地文件', { count: deleteItems.length }),
    })
    if (removed) await appStore.requestModScan({ preserveListState: true, forceCoreRefresh: true })
    return removed
  }
  const unsubscribeSelectedWorkshopMods = async (deleteFiles = false, ids = selectedIds.value) => {
    const workshopItems = resolveSelectedActionItems(ids).filter(item => item.mod?.workshop_id)
    const pathHashes = workshopItems.map(item => item.mod.path_hash).filter(Boolean)
    const workshopIds = [...new Set(workshopItems.map(item => item.mod.workshop_id).filter(Boolean))]
    if (workshopIds.length === 0) return false
    const res = await appStore.unsubscribeWorkshopIds(
      workshopIds,
      pathHashes,
      { deleteFiles: !!deleteFiles }
    )
    if (!res) return false

    const targetDetails = res?.task?.metrics?.target_details || {}
    const unsubscribeCompleteReasons = new Set([
      'folder_and_record_removed',
      'folder_removed',
      'unsubscribed_but_folder_exists',
      'timeout',
    ])
    const removedWorkshopItems = deleteFiles
      ? workshopItems
      // 取消订阅完成可能仍有残留文件夹，不能只用 folder_removed 判断是否清理列表项。
      : workshopItems.filter(item => unsubscribeCompleteReasons.has(targetDetails[String(item.mod.workshop_id)]?.complete_reason))
    if (removedWorkshopItems.length === 0) return false
    const removed = await removeDeletedItemsFromLists({
      items: removedWorkshopItems,
      type: deleteFiles ? 'unsubscribe-delete-mod-files' : 'unsubscribe-mods',
      label: deleteFiles
        ? t('history.mod.unsubscribe_and_delete_count', '取消订阅并删除 {count} 个文件', { count: removedWorkshopItems.length })
        : t('history.mod.unsubscribe_workshop_count', '取消订阅 {count} 个创意工坊项目', { count: removedWorkshopItems.length }),
    })
    if (removed) await appStore.requestModScan({ preserveListState: true, forceCoreRefresh: true })
    return removed
  }

  // --- Mod数据操作 ---
  // 更新Mod用户数据
  const updateModUserData = async (modId, userData) => {
    if (!window.pywebview) return
    const rollback = snapshotModFields([modId], Object.keys(userData || {}))
    try {
      // 更新本地 Map
      const mod = resolveStoredMod(modId)
      if (mod) Object.assign(mod, userData)
      const res = await window.pywebview.api.mod_user_data_update(modId, userData)
      if (!checkResult(res, t('check.mod.update_user_data', '更新Mod用户数据'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      console.error("更新Mod用户数据异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.update_user_data_failed', '更新 Mod 用户数据失败，已还原本地状态。请稍后重试，详细原因已写入系统日志。')))
      restoreModSnapshots(rollback)
      return false
    }
  }
  // 更新Mod最后操作时间
  const updateModTime = async () => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      // 提取所有对象的时间属性 {package_id:xxxx, last_active_time:xxxx, last_moved_time:xxxx}
      const all_mods = Array.from(allModsMap.value.values(), mod => ({
        path_hash: mod.path_hash,
        package_id: mod.package_id,
        last_active_time: mod.last_active_time,
        last_moved_time: mod.last_moved_time
      }));
      console.debug("准备更新 Mod 最后操作时间:", {all_mods_time:all_mods})
      const res = await window.pywebview.api.mod_time_update(all_mods)
      if (!checkResult(res, t('check.mod.update_time', '更新Mod最后操作时间'))) {
        await appStore.refreshModCoreData('Mod 时间更新失败后同步模组数据', {
          preserveListState: true,
          refreshRules: false,
          refreshBackups: false,
          refreshWorkspaceLibraries: false,
        })
        return false
      }
      return true
    } catch (e) {
      console.error("更新Mod最后操作时间异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.update_time_failed', '更新 Mod 操作时间失败。正在重新同步模组数据，详细原因已写入系统日志。')))
      await appStore.refreshModCoreData('Mod 时间更新异常后同步模组数据', {
        preserveListState: true,
        refreshRules: false,
        refreshBackups: false,
        refreshWorkspaceLibraries: false,
      })
      return false
    }
  }

  // --- 批量数据操作 ---
  // 批量设置颜色
  const setModsColor = async (modIds, color) => {
    if (!window.pywebview) return
    const rollback = snapshotModFields(modIds, ['sign_color'])
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.sign_color = color
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_sign_color_update(modIds, color)
      if (!checkResult(res, t('check.mod.batch_set_color', '批量设置 Mod 颜色'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, t('toast.mod.batch_set_color_failed', '批量设置颜色失败，已还原本地状态。请稍后重试。')))
      restoreModSnapshots(rollback)
      return false
    }
  }
  // 批量设置类型
  const setModsType = async (modIds, type) => {
    if (!window.pywebview) return
    const rollback = snapshotModFields(modIds, ['user_mod_type'])
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.user_mod_type = type
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_user_mod_type_update(modIds, type)
      if (!checkResult(res, t('check.mod.batch_set_type', '批量设置 Mod 类型'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, t('toast.mod.batch_set_type_failed', '批量设置类型失败，已还原本地状态。请稍后重试。')))
      restoreModSnapshots(rollback)
      return false
    }
  }
  // 批量添加标签
  const addModsTags = async (modIds, tags) => {
    if (!window.pywebview) return
    const rollback = snapshotModFields(modIds, ['tags'])
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.tags = [...new Set([...(mod.tags || []), ...tags])]  // 自动去重
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_add_tags(modIds, tags)
      if (!checkResult(res, t('check.mod.batch_add_tags', '批量添加 Mod 标签'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, t('toast.mod.batch_add_tags_failed', '批量添加标签失败，已还原本地状态。请稍后重试。')))
      restoreModSnapshots(rollback)
      return false
    }
  }
  // 批量移除标签
  const removeModsTags = async (modIds, tags) => {
    if (!window.pywebview) return
    const rollback = snapshotModFields(modIds, ['tags'])
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.tags = (mod.tags || []).filter(t => !tags.includes(t))
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_remove_tags(modIds, tags)
      if (!checkResult(res, t('check.mod.batch_remove_tags', '批量移除 Mod 标签'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, t('toast.mod.batch_remove_tags_failed', '批量移除标签失败，已还原本地状态。请稍后重试。')))
      restoreModSnapshots(rollback)
      return false
    }
  }
  // 智能切换标签
  // 如果所有选中项都有该 Tag -> 移除，如果部分有或都没有 -> 添加 (补全)
  const selectModsTag = async (tag) => {
    // 检查当前状态
    const stats = selectedStats.value.tags[tag] // 'all', 'some', undefined
    if (stats === 'all') {  // 全都有 -> 移除
      await removeModsTags(selectedIds.value, [tag]) // 需实现 removeModsTags
    } else {  // 部分有或全无 -> 添加
      await addModsTags(selectedIds.value, [tag])
    }
  }
  // 智能切换分组 (Toggle Group)
  const selectModsGroup = async (groupId) => {
    const stats = selectedStats.value.groups[groupId]
    const groupStore = useGroupStore()
    if (stats === 'all') {
      await groupStore.groupRemoveMods(groupId, selectedIds.value)
    } else {
      await groupStore.groupAddMods(groupId, selectedIds.value)
    }
  }
  // 获取 Mod 联锁链
  const getModInterlockChain = (modId) => {
    const mod = takeModById(modId);
    if (!mod || !mod.interlock_id) return null;
    const source = interlocksMap.value
    if (source instanceof Map) return source.get(mod.interlock_id) || null
    return source?.[mod.interlock_id] || null
  }
  const refreshAfterInterlockChange = async (historyLabel) => {
    const refreshed = await appStore.refreshModCoreData(historyLabel, {
      preserveListState: true,
      refreshRules: false,
      refreshBackups: false,
      refreshWorkspaceLibraries: false,
      refreshEnrichment: false,
    })
    await appStore.refreshModEnrichment({ silent: true })
    dataVersion.value++
    return refreshed
  }
  // 批量设置 Mod 联锁
  const linkMods = async (modIds) => {
    if (!window.pywebview) return
    try {
      // 发送请求给后端
      const res = await window.pywebview.api.mods_link(modIds)
      if (checkResult(res, t('check.mod.link', '设置 Mod 联锁'), true)) {
        await refreshAfterInterlockChange('联锁变更后同步模组数据')
        return true
      }
    } catch (e) {
      console.error("设置 Mod 联锁异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.link_failed', '设置 Mod 联锁失败。请稍后重试，详细原因已写入系统日志。')))
      return false
    }
  }
  // 批量解除 Mod 联锁
  const unlinkMods = async (modIds) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.mods_unlink(modIds)
      if (checkResult(res, t('check.mod.unlink', '解除 Mod 联锁'), true)) {
        await refreshAfterInterlockChange('联锁变更后同步模组数据')
        return true
      }
    } catch (e) {
      return false
    }
  }
  // 修复断裂联锁
  const healInterlock = async (interlock_id) => {
    if (!window.pywebview || !interlock_id) return
    appStore.isLoading = true
    try {
      const res = await window.pywebview.api.mods_interlock_heal(interlock_id)
      if (checkResult(res, t('check.mod.heal_interlock', '修复断裂联锁'), true)) {
        await refreshAfterInterlockChange('联锁修复后同步模组数据')
        return true
      }
    } finally {
      appStore.isLoading = false
    }
  }
  // 获取断裂联锁的缺失成员
  const getInterlockMissingDetails = async (interlock_id) => {
    if (!window.pywebview || !interlock_id) return []
    try {
      const res = await window.pywebview.api.mods_interlock_missing_get(interlock_id)
      if (checkResult(res, t('check.mod.get_interlock_missing', '获取联锁缺失项'))) return res.data
    } catch (e) {
      console.error("获取联锁缺失项失败:", e)
    }
    return []
  }
  // 批量更新Mod用户数据
  const batchUpdateModsUserData = async (updatesList) => {
    if (!window.pywebview) return
    appStore.isLoading = true
    const updateFields = [...new Set(
      updatesList.flatMap(update => Object.keys(update).filter(key => key !== 'mod_id'))
    )]
    const rollback = snapshotModFields(updatesList.map(update => update.mod_id), updateFields)
    try {
      // 1. 乐观更新：立即更新本地 Map 状态
      updatesList.forEach(({ mod_id, ...userData }) => {
        const mod = resolveStoredMod(mod_id)
        if (mod) {
          Object.assign(mod, userData)
        }
      })
      // 2. 发送请求给后端
      const res = await window.pywebview.api.mods_user_data_update(updatesList)
      if (!checkResult(res, t('check.mod.batch_update_data', '批量更新Mod数据'), true)) {
        restoreModSnapshots(rollback)
        return false
      }
      return true
    } catch (e) {
      console.error("批量更新Mod数据异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.mod.batch_update_data_failed', '批量更新 Mod 数据失败，已还原本地状态。请稍后重试，详细原因已写入系统日志。')))
      restoreModSnapshots(rollback)
      return false
    } finally {
      appStore.isLoading = false
      dataVersion.value++ // 触发响应式重新计算
    }
  }

  const interlockDetailsMap = ref({}) // { "interlock_id": [ {package_id, workshop_id, reason} ] }
  const loadingInterlocks = new Set() // 记录当前正在请求中的 ID，防止并发风暴
  const loadInterlockDetails = async (interlockId) => {
    if (!interlockId || !window.pywebview) return
    // 1. 如果已经缓存过，直接返回
    if (interlockDetailsMap.value[interlockId]) return
    // 2. 如果当前正在请求中，直接屏蔽
    if (loadingInterlocks.has(interlockId)) return

    loadingInterlocks.add(interlockId)
    try {
      const res = await window.pywebview.api.mods_interlock_missing_get(interlockId)
      if (res.status === 'success') {
        interlockDetailsMap.value[interlockId] = res.data
        dataVersion.value++ // 驱动视图层重绘
      }
    } catch (e) {
      console.error("加载联锁详情失败:", e)
    } finally {
      loadingInterlocks.delete(interlockId) // 请求结束，释放锁
    }
  }
  const {
    modIssues,
    getIssusTargetIds,
    getModIssueState,
    ignoreIssue,
    batchIgnoreIssues,
    getListIssues,
  } = useModIssues({
    appStore,
    allModsMap,
    activeIds,
    inactiveIds,
    tempIds,
    interlocksMap,
    dataVersion,
    normalizeListToken,
    normalizeCanonicalId,
    takeModById,
    hasRealModById,
    displayModName,
    getLanguagePackOwnerIds,
    canUseLanguagePackForIssueDetection,
    updateModUserData,
  })

  return {
    // 状态
    allModsMap, dataVersion, inactiveIds, tempIds, activeIds, disabledMods, disabledPathHashes, strictDisableRestoreFailures, interlocksMap, savedInactiveIds, savedTempIds, interlockDetailsMap,
    savedActiveIds, activeLoadModifyTime, activeLoadVersionToken, conflictList, coexistenceList,
    selectedIds, lastSelectedMod, currentTargetId, isDraggingMod,
    listHistoryUndoStack, listHistoryRedoStack, isApplyingListHistory,

    // 派生状态
    isDirty, selectedMods, selectedStats, allModTags, modIssues, exportableVisibleCount, exportableActiveCount,
    listHistoryTotal, listHistoryPosition,
    canUndoListHistory, canRedoListHistory,

    // 列表读取与基础写入
    setMods, mergeModEnrichment, reset, setActiveLoadBaseline, captureListHistorySnapshot, takeModById, getAvailableModInstances, takeDisabledModByPathHash, hasRealModById, hasInstalledWorkshopId, takeModListByIds, displayModName, displayModType, displayModIcon, fetchAndCacheGhostMods,
    isLanguagePackMod, getLanguagePackOwnerIds, canUseLanguagePackForIssueDetection, isDeclaredForCurrentLanguage,
    // 来源提示与列表选择
    getInstallSourceHints, mergeInstallSourceHintsFromMods, clearInstallSourceHints, clearInstallSourceHintsByOrigin,
    updateInactiveIds, takeInactiveIds, setListIds, removeIdsOnAllList, removeDeletedModsFromLocalData, removeUnavailableIdsCompletely, selectMods, clearSelection, changeModsActive, getModInterlockChain, loadInterlockDetails,
    // 扫描、排序与模组操作
    scanMods, scanComplete, autoSortMods, resetActiveList, applyResetActiveListPreset, resolveResetActiveListPreview, resolveLocalizeCandidates, localizeSelectedMods, localizeMods, disableMods, disableSelectedMods, deleteMods, deleteSelectedModFiles, unsubscribeSelectedWorkshopMods, smartInsertMods,
    canSwitchCoexistenceSource, switchCoexistenceSource, toggleCoexistenceSource, toggleSelectedCoexistenceSource, revealSelectedMod,
    // 用户数据与联锁
    updateModUserData, updateModTime, linkMods, unlinkMods, healInterlock, getInterlockMissingDetails, batchUpdateModsUserData,
    setModsColor, setModsType, addModsTags, removeModsTags, selectModsTag, selectModsGroup,
    // 问题检测
    getModIssueState, ignoreIssue, batchIgnoreIssues, getListIssues, getIssusTargetIds,
    // 历史与导出
    clearListHistory, runListHistoryTransaction, recordListHistory, undoListHistory, redoListHistory,
    resolveCurrentExportBaseIds, resolveCurrentExportPlan,
  }
})
