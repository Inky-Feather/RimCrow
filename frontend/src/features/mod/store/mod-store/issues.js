import { computed } from 'vue'
import { toast, checkResult } from '../../../../shared/lib/common'
import { ISSUE_LEVEL, ISSUE_TYPE, ISSUE_TITLE_MAP } from '../../../../shared/lib/constants'
import { useProfileStore } from '../../../profiles/profileStore'

export const useModIssues = ({
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
} = {}) => {
  // --- 实时问题分析 ---
  // 排序问题检测器
  const modIssues = computed(() => {
    const issuesMap = new Map() // Key: modId, Value: Array<Issue>
    dataVersion.value // 依赖触发器
    const profileStore = useProfileStore()

    // 辅助函数：添加问题
    const _add = (id, type, level, message, targetId = null) => {
      const mod = takeModById(id)
      if (!mod) return
      // 忽略检查
      if (mod.ignored_issues && mod.ignored_issues.includes(type)) return
      if (!issuesMap.has(id)) issuesMap.set(id, [])
      issuesMap.get(id).push({ type, level, message, targetId })
    }

    // -------------------------------------------------
    // 1. 全局检查 (Global Checks) - 针对每个个体
    // 范围：所有已加载的 Mod (无论是否启用)
    // -------------------------------------------------
    for (const mod of allModsMap.value.values()) {
      const id = normalizeCanonicalId(mod.package_id)

      // A. 文件缺失
      if (!mod.path || mod.isMissing) {
        _add(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析', id)
        continue // 文件都没了，没必要查别的
      }

      // B. 版本支持检查
      if (profileStore.activeContext.game_version) {
        const gameVerMajor = profileStore.activeContext.game_version.substring(0, 3)
        if (mod.supported_versions && mod.supported_versions.length > 0 && !mod.supported_versions.includes(gameVerMajor)) {
          _add(id, ISSUE_TYPE.WARN_VERSION_MISMATCH, ISSUE_LEVEL.WARN,
            `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_VERSION_MISMATCH]}^^：不支持当前游戏版本··[[${gameVerMajor}]]·· \n __(支持: ··${(mod.supported_versions || []).join('··, ··')}··)__`)
        }
      }
    }

    // 1.5 预处理语言包映射 (Language Packs Mapping)
    // 优先复用后端统一计算的 language_pack_owner_result，避免前端再次发散判断。
    const checkLangEnabled = appStore.settings.check_language_support
    const targetLang = appStore.settings.language // 当前软件语言，后端统一输出规范语言码
    const langPackMap = new Map() // 严格命中：语言包明确声明支持当前语言
    const langPackFallbackMap = new Map() // 兜底命中：归属可信，但语言作者可能漏标 supported_languages
    if (checkLangEnabled && targetLang) {
      for (const mod of allModsMap.value.values()) {
        const isLangPack = (mod.user_mod_type || mod.mod_type) === 'LanguagePack'
        if (!isLangPack) continue
        if (!canUseLanguagePackForIssueDetection(mod)) continue

        const targetIds = getLanguagePackOwnerIds(mod)
        targetIds.forEach(tId => {
          if (!langPackFallbackMap.has(tId)) langPackFallbackMap.set(tId, [])
          langPackFallbackMap.get(tId).push(mod)
        })

        const supportsLang = !!targetLang && (mod.supported_languages || []).includes(targetLang)
        if (supportsLang) {
          targetIds.forEach(tId => {
            if (!langPackMap.has(tId)) langPackMap.set(tId, [])
            langPackMap.get(tId).push(mod)
          })
        }
      }
    }

    // -------------------------------------------------
    // 2. 启用列表检查 (Active List Checks)
    // 范围：activeIds 列表
    // -------------------------------------------------
    // 构建 Map 以实现 O(1) 查找 active 列表中的索引
    const activeIndexMap = new Map()
    const activeTokenMap = new Map()
    const len = activeIds.value.length
    for (let i = 0; i < len; i++) {
        const canonicalId = normalizeCanonicalId(activeIds.value[i])
        const tokenId = normalizeListToken(activeIds.value[i])
        if (!canonicalId) continue
        activeIndexMap.set(canonicalId, i)
        activeTokenMap.set(canonicalId, tokenId)
    }
    // 快速判定任意两个 Mod 之间的合法顺序
    // isMustBefore.get(A)?.has(B) 为 true，表示规则要求 A 必须在 B 之前
    const isMustBefore = new Map()
    const addMustBeforeRule = (beforeId, afterId) => {
        if (!isMustBefore.has(beforeId)) isMustBefore.set(beforeId, new Set())
        isMustBefore.get(beforeId).add(afterId)
    }
    for (let i = 0; i < len; i++) {
        const currentId = normalizeCanonicalId(activeIds.value[i])
        const mod = takeModById(activeIds.value[i])
        if (!mod || mod.isMissing || !mod.rules) continue
        const rules = mod.rules || {}
        // 我必须在别人之后 -> 别人必须在我之前
        const afterTargets = [...(rules.load_after || []), ...(rules.dependencies || [])]
        afterTargets.forEach(r => {
            const tid = normalizeCanonicalId(r.target_id)
            addMustBeforeRule(tid, currentId) // tid 必须在 currentId 之前
        })
        // 我必须在别人之前 -> 我必须在别人之前
        const beforeTargets = rules.load_before || []
        beforeTargets.forEach(r => {
            const tid = normalizeCanonicalId(r.target_id)
            addMustBeforeRule(currentId, tid) // currentId 必须在 tid 之前
        })
    }

    for (let i = 0; i < len; i++) {
      const currentToken = normalizeListToken(activeIds.value[i])
      const currentId = normalizeCanonicalId(activeIds.value[i])
      const mod = takeModById(activeIds.value[i])
      if (!mod || mod.isMissing) continue // X. 文件缺失已在全局检查中处理，这里简单跳过
      if(!mod.rules) continue // 如果没有 rules 数据（可能未初始化），跳过

      // const rules = mod.rules ，这是后端计算好的 { dependencies, load_after, incompatible ... }
      // 兼容性处理：如果后端还没刷新，rules可能为空
      const rules = mod.rules || { dependencies: [], load_after: [], load_before: [], incompatible: [] }

      const wInfo = rules.weight_info || {}
      // 直接使用后端统一提供的 final_weight，兜底为 500
      const finalWeight = wInfo.final_weight !== undefined ? wInfo.final_weight : 500
      const sourceName = wInfo.absolute_source || '未知规则'

      // 1. 置顶检查 (<= 0)
      if (finalWeight <= 0 && i > 0) { // 只检查非首位元素
        const prevId = normalizeCanonicalId(activeIds.value[i - 1])
        const prevToken = activeTokenMap.get(prevId) || prevId
        const prevMod = takeModById(activeIds.value[i - 1])
        const prevW = prevMod?.rules?.weight_info?.final_weight ?? 500
        // 如果紧邻的前一个模组不是置顶的
        if (prevW > 0) {
          // 【关键豁免】：检查是否存在规则要求 prevId 必须在 currentId 之前
          const isAllowedByRule = isMustBefore.get(prevId)?.has(currentId)
          if (!isAllowedByRule) {
            _add(currentToken, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN,
              `^^排序警告^^：根据 ${sourceName} 要求置顶，但被排在了非前置依赖的常规模组 [[${displayModName(prevId)}]] 之后`, prevToken)
          }
        }
      }
      // 2. 置底检查 (>= 10000)
      if (finalWeight >= 10000 && i < len - 1) { // 只检查非末位元素
        const nextId = normalizeCanonicalId(activeIds.value[i + 1])
        const nextToken = activeTokenMap.get(nextId) || nextId
        const nextMod = takeModById(activeIds.value[i + 1])
        const nextW = nextMod?.rules?.weight_info?.final_weight ?? 500
        // 如果紧邻的后一个模组不是置底的
        if (nextW < 10000) {
          // 【关键豁免】：检查是否存在规则要求 currentId 必须在 nextId 之前
          const isAllowedByRule = isMustBefore.get(currentId)?.has(nextId)
          if (!isAllowedByRule) {
            _add(currentToken, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN,
              `^^排序警告^^：根据 ${sourceName} 要求置底，但前方拦截了非后置依赖的常规模组 [[${displayModName(nextId)}]]`, nextToken)
          }
        }
      }

      // 记录已经作为“硬依赖”处理过的目标
      const processedDependencies = new Set()

      // A. 依赖检查 (Dependencies) - 必须存在且启用
      // 这里的 rules.dependencies 来源于 Native (About.xml)
      for (const dep of rules.dependencies || []) {
        const baseTargetId = normalizeCanonicalId(dep.target_id)
        let activeTargetId = baseTargetId
        let usedAlternative = null

        // 1. 检查基础目标是否激活
        if (!activeIndexMap.has(baseTargetId)) {
          // 寻找是否有被激活的备选项 (Alternatives)
          const alts = dep.alternatives || []
          usedAlternative = alts.find(alt => activeIndexMap.has(normalizeCanonicalId(alt)))

          if (usedAlternative) {
            activeTargetId = normalizeCanonicalId(usedAlternative)
            const activeTargetToken = activeTokenMap.get(activeTargetId) || activeTargetId
            // 提示备选项生效 (仅作 INFO 级提示，不报红错)
            const baseName = displayModName(baseTargetId)
            const altName = displayModName(activeTargetId)
            _add(currentToken, ISSUE_TYPE.INFO_ALTERNATIVE_USED, ISSUE_LEVEL.INFO,
              `__${ISSUE_TITLE_MAP[ISSUE_TYPE.INFO_ALTERNATIVE_USED]}__：前置依赖 [[${baseName}]] 已由备选模组 [[${altName}]] 替代`, activeTargetToken)
          } else {
            // 缺失或未启用
            const baseMod = allModsMap.value.get(baseTargetId)
            const baseName = baseMod ? displayModName(baseMod) : baseTargetId
            const hasInstalledBaseMod = hasRealModById(baseTargetId)

            if (!hasInstalledBaseMod) {
              // 主包不在本地，找找备选包在不在本地！
              const localAlt = alts.find(alt => hasRealModById(alt))
              if (localAlt) {
                _add(currentToken, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR,
                  `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]}!!：未启用备选前置模组 [[${displayModName(localAlt)}]]`, activeTokenMap.get(normalizeCanonicalId(localAlt)) || normalizeCanonicalId(localAlt))
              } else {
                // 全都不在本地，彻底缺失
                _add(currentToken, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY, ISSUE_LEVEL.ERROR,
                  `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_MISSING_DEPENDENCY]}!!：缺少前置模组 [[${baseName}]]`, baseTargetId)
              }
            } else {
              _add(currentToken, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR,
                `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]}!!：未启用前置模组 [[${baseName}]]`, baseTargetId)
            }
            continue // 基础依赖和备选依赖都没满足，不用查排序了
          }
        }

        // 2. 标记已处理，防止被下方的 load_after 重复检查
        processedDependencies.add(activeTargetId)

        // 3. 排序检查：依赖项必须在当前 Mod 之前
        if (activeIndexMap.get(activeTargetId) > i) {
          _add(currentToken, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.ERROR,
            `!!依赖后置!!：必须在依赖 [[${displayModName(activeTargetId)}]] 之后加载`, activeTokenMap.get(activeTargetId) || activeTargetId)
        }
      }

      // B. 排序规则 (Load After) - 仅当目标存在且激活时检查
      for (const rule of rules.load_after || []) {
        const targetId = normalizeCanonicalId(rule.target_id)
        if (processedDependencies.has(targetId)) continue
        if (!activeIndexMap.has(targetId)) continue

        const targetName = displayModName(targetId)
        const sourceName = rule.source?.name || '未知规则'
        const level = (rule.is_force || rule.source?.type==="native") ? ISSUE_LEVEL.ERROR : ISSUE_LEVEL.WARN
        const prefix = rule.is_force ? '!!排序错误!!' : '^^排序警告^^'

        if (activeIndexMap.get(targetId) > i) {
          _add(currentToken, ISSUE_TYPE.WARN_WRONG_ORDER, level,
            `${prefix}：根据 __${sourceName}__，应在 [[${targetName}]] 之后加载`, activeTokenMap.get(targetId) || targetId)
        }
      }

      // C. 排序规则 (Load Before) - 仅当目标存在且激活时检查
      for (const rule of rules.load_before || []) {
        const targetId = normalizeCanonicalId(rule.target_id)
        if (processedDependencies.has(targetId)) continue
        if (!activeIndexMap.has(targetId)) continue

        const targetName = displayModName(targetId)
        const sourceName = rule.source?.name || '未知规则'
        const level = rule.is_force ? ISSUE_LEVEL.ERROR : ISSUE_LEVEL.WARN
        const prefix = rule.is_force ? '!!排序错误!!' : '^^排序警告^^'

        if (activeIndexMap.get(targetId) < i) {
          _add(currentToken, ISSUE_TYPE.WARN_WRONG_ORDER, level,
            `${prefix}：根据 __${sourceName}__，应在 [[${targetName}]] 之前加载`, activeTokenMap.get(targetId) || targetId)
        }
      }

      // D. 冲突检查 (Incompatible) - 目标存在且激活即报错
      for (const rule of rules.incompatible || []) {
        const targetId = normalizeCanonicalId(rule.target_id)
        if (activeIndexMap.has(targetId)) {
          const targetName = displayModName(targetId)
          const sourceName = rule.source?.name || '未知规则'
          const extra = rule.source?.detail?.comment ? ` (${rule.source.detail.comment})` : ''
          _add(currentToken, ISSUE_TYPE.ERROR_INCOMPATIBLE, ISSUE_LEVEL.ERROR,
            `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INCOMPATIBLE]}!!：__${sourceName}__ 指出与 [[${targetName}]] 不兼容${extra}`, activeTokenMap.get(targetId) || targetId)
        }
      }

      // E. 联锁检查 (Chain Check - Active)
      // 检查当前列表的前后是否符合 lock 要求
      // if (mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
      //   const chain = interlocksMap.value[mod.interlock_id]
      //   // 查找自己在这个联锁链条中的位置
      //   const myChainIndex = chain.findIndex(id => id.toLowerCase() === currentId)
      //   if (myChainIndex !== -1) {
      //     // 检查前一个
      //     if (myChainIndex > 0) {
      //       const prevExpected = chain[myChainIndex - 1].toLowerCase()
      //       if (i === 0 || activeIds.value[i - 1].toLowerCase() !== prevExpected) {
      //         _add(currentId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN,
      //           `^^联锁断裂^^：必须紧跟在 [[${displayModName(prevExpected)}]] 之后`, prevExpected)
      //       }
      //     }
      //     // 检查后一个
      //     if (myChainIndex < chain.length - 1) {
      //       const nextExpected = chain[myChainIndex + 1].toLowerCase()
      //       if (i === len - 1 || activeIds.value[i + 1].toLowerCase() !== nextExpected) {
      //         _add(currentId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN,
      //           `^^联锁断裂^^：必须紧接 [[${displayModName(nextExpected)}]] 之前`, nextExpected)
      //       }
      //     }
      //   }
      // }

      // F. 语言支持检查 (Language Support) - 仅当开关开启时
      if (checkLangEnabled && targetLang) {
        const isSelfLangPack = (mod.user_mod_type || mod.mod_type) === 'LanguagePack'
        // 如果 Mod 本身就没有声明支持的语言列表（通常意味着没有文本或是框架），直接跳过检查
        if (!mod.supported_languages || mod.supported_languages.length === 0) {
          // pass
        } else {
          // 检查自身是否直接支持当前语言
          const modSupportsLang = !!targetLang && (mod.supported_languages || []).includes(targetLang)
          // 如果自身不支持，且自身不是语言包本体
          if (!modSupportsLang && !isSelfLangPack) {
            const availablePacks = langPackMap.get(currentId) || []
            const fallbackPacks = langPackFallbackMap.get(currentId) || []
            // 检查是否有被激活的适配语言包
            const activePack = availablePacks.find(p => activeIndexMap.has(normalizeCanonicalId(p.package_id)))
            const activeFallbackPack = fallbackPacks.find(p => activeIndexMap.has(normalizeCanonicalId(p.package_id)))
            if (activePack || activeFallbackPack) {
              // pass: 严格语言包或可信兜底语言包已经启用，不再误报缺语言
            }
            else if (!activePack) {
              // 没有被激活的语言包！检查本地是否有未激活的
              if (availablePacks.length > 0) {
                const localPack = availablePacks[0] // 取第一个本地找到的语言包
                const packName = displayModName(localPack.package_id)
                _add(currentToken, ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK]}^^：不支持当前语言，但本地存在语言包 [[${packName}]]`, activeTokenMap.get(normalizeCanonicalId(localPack.package_id)) || normalizeCanonicalId(localPack.package_id))
              } else if (fallbackPacks.length > 0) {
                const fallbackPack = fallbackPacks[0]
                const packName = displayModName(fallbackPack.package_id)
                _add(currentToken, ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK]}^^：不支持当前语言，但本地存在可能相关的语言包 [[${packName}]]（该语言包未声明支持当前语言）`, activeTokenMap.get(normalizeCanonicalId(fallbackPack.package_id)) || normalizeCanonicalId(fallbackPack.package_id))
              } else {
                // 本地彻底没有相关语言包
                _add(currentToken, ISSUE_TYPE.WARN_MISSING_LANGUAGE, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_MISSING_LANGUAGE]}^^：不支持当前语言，且未在本地发现相关语言包`)
              }
            }
          } // 自身是语言包，检查是否存在前置或依赖，且目标Mod是否启用
          else if(isSelfLangPack) {
            const allRelatedModIds = getLanguagePackOwnerIds(mod)
            if(allRelatedModIds.length === 0) {
              _add(currentToken, ISSUE_TYPE.WARN_UNKNOWN_TARGET, ISSUE_LEVEL.WARN,
                `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_UNKNOWN_TARGET]}^^：语言包指向对象未知，请检查该语言包是否多余，或者可在规则编辑器手动指定前置对象`)
            }
            // 如果存在依赖或前置，检测是否有任意一个启用(部分语言包支持多个Mod，只要有一个启用即可)，
            // 如果未启用则提示用户存在多余的语言包，或者提示指向对象未启用
            else {
              const anyActive = allRelatedModIds.some(id => activeIndexMap.has(id))
              if(!anyActive) {
                _add(currentToken, ISSUE_TYPE.WARN_INACTIVE_TARGET, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_INACTIVE_TARGET]}^^：语言包指向对象未启用，请检查该语言包是否多余，或者可在规则编辑器手动指定前置对象`)
              }
            }

          }
        }
      }

    }



    // 辅助：检查整个列表的联锁
    const _checkListChain = (list) => {
      const len = list.length
      for (let i = 0; i < len; i++) {
        const tokenId = normalizeListToken(list[i])
        const id = normalizeCanonicalId(list[i])
        const mod = allModsMap.value.get(id)
        if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
          const chain = interlocksMap.value[mod.interlock_id]
          const myIdx = chain.findIndex(cid => normalizeCanonicalId(cid) === id)
          if (myIdx !== -1) {
            // A. 检查向上断裂 (期待的前一个元素不在我紧挨着的上方)
            if (myIdx > 0) {
              const prevExpected = normalizeCanonicalId(chain[myIdx - 1])
              const prevExpectedToken = activeTokenMap.get(prevExpected) || prevExpected
              if (i === 0 || normalizeCanonicalId(list[i-1]) !== prevExpected) {
                // targetId 传入 prevExpected，方便组件识别这是 "前驱断裂"
                _add(tokenId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN,
                  `^^联锁断裂^^：必须紧跟在 [[${displayModName(prevExpected)}]] 之后`, prevExpectedToken)
              }
            }
            // B. 检查向下断裂 (期待的后一个元素不在我紧挨着的下方)
            if (myIdx < chain.length - 1) {
              const nextExpected = normalizeCanonicalId(chain[myIdx + 1])
              const nextExpectedToken = activeTokenMap.get(nextExpected) || nextExpected
              if (i === len - 1 || normalizeCanonicalId(list[i+1]) !== nextExpected) {
                // targetId 传入 nextExpected，方便组件识别这是 "后继断裂"
                _add(tokenId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN,
                  `^^联锁断裂^^：必须紧接 [[${displayModName(nextExpected)}]] 之前`, nextExpectedToken)
              }
            }
          }
        }
      }
    }
    // -------------------------------------------------
    // 3. 停用列表/临时列表 (Inactive/Temp Checks)
    // 范围：仅检查联锁完整性
    // -------------------------------------------------
    _checkListChain(activeIds.value)
    _checkListChain(inactiveIds.value)
    _checkListChain(tempIds.value)
    return issuesMap
  })


  // 获取问题项目目标ID
  const getIssusTargetIds = (targetIds, issueType) => {
    const toActivate = new Set()
    targetIds.forEach(id => {
      const issues = modIssues.value.get(normalizeListToken(id))
      if (issues) {
        issues.forEach(issue => {
          if (issue.type === issueType && issue.targetId) {
            toActivate.add(issue.targetId)
          }
        })
      }
    })
    return Array.from(toActivate)
  }
  // 获取某个 Mod 问题的最高级别
  const getModIssueState = (id) => {
    const issues = modIssues.value.get(normalizeListToken(id))
    if (!issues || issues.length === 0) return null
    // 优先级: ERROR > WARN > INFO
    if (issues.some(i => i.level === 'error')) return 'error'
    if (issues.some(i => i.level === 'warn')) return 'warn'
    if (issues.some(i => i.level === 'info')) return 'info'
    return 'info'
  }
  // 忽略/取消忽略问题
  // type: 传入错误类型字符串为忽略该问题；不传(null/undefined)为清空所有忽略(重置)
  const ignoreIssue = async (modId, type) => {
      const mod = takeModById(modId)
      // console.log('ignoreIssue', mod)
      if (!mod) return // 幽灵对象无法保存设置
      // 1. 安全获取当前列表 (创建副本，防止直接修改原引用)
      // 如果 mod.ignored_issues 不存在，默认为空数组
      let currentIgnored = Array.isArray(mod.ignored_issues) ? [...mod.ignored_issues] : []
      // console.log('ignoreIssue', modId, type, currentIgnored)
      if (!type) {
          // === 模式 A: 恢复所有警告 (清空忽略列表) ===
          if (currentIgnored.length === 0) return // 本来就是空的，无需操作
          currentIgnored = []
      } else {
          // === 模式 B: 忽略特定问题 ===
          if (currentIgnored.includes(type)) return // 已经忽略了，无需操作
          currentIgnored.push(type)
      }
      // 2. 调用后端保存
      mod.ignored_issues = currentIgnored
      const res = await updateModUserData(modId, { ignored_issues: currentIgnored })
      if (res.status !== 'success') {
        toast.error(`忽略问题失败：${res.message}`)
      } else{
        dataVersion.value++ // 数据版本+1，确保问题判断刷新
      }
  }
  // 批量忽略/取消忽略问题
  const batchIgnoreIssues = async (modIds, type = null) => {
    if (!window.pywebview) return
    appStore.isLoading = true;
    const updates = []; // 准备发送给后端的批量数据
    try {
      modIds.forEach((id) => {
        const mod = takeModById(id);
        if (!mod || !mod.path) return;
        let currentIgnored = Array.isArray(mod.ignored_issues) ? [...mod.ignored_issues] : [];
        let needsUpdate = false;
        if (!type) {
          // - 模式 A: 恢复所有警告
          if (currentIgnored.length > 0) {
            currentIgnored = [];
            needsUpdate = true;
          }
        } else {
          // - 模式 B: 忽略特定问题
          const currentModIssues = modIssues.value.get(normalizeListToken(id)) || [];
          const hasThisIssue = currentModIssues.some(i => i.type === type);
          if (hasThisIssue && !currentIgnored.includes(type)) {
            currentIgnored.push(type);
            needsUpdate = true;
          }
        }
        if (needsUpdate) {
          // 1. 先更新本地 UI 状态 (响应式)
          mod.ignored_issues = currentIgnored;
          // 2. 加入批量更新队列
          updates.push({
            mod_id: id,
            ignored_issues: currentIgnored
          });
        }
      });
      // 如果没有实质性变化，直接返回
      if (updates.length === 0) return;
      // 3. 一次性调用后端 API
      const res = await window.pywebview.api.mods_ignore_issues_update(updates);
      if (checkResult(res, "批量忽略/取消忽略问题")) {
        toast.success(type ? `已忽略 ${updates.length} 项问题` : `已恢复 ${updates.length} 项警告`);
      } else {
        await appStore.refreshData();
      }
    } catch (e) {
      console.error("批量忽略操作失败:", e);
      toast.error(`操作失败: ${e.message}`);
      // 如果失败了，重新刷新列表以保证数据一致性
      await appStore.refreshData();
    } finally {
      appStore.isLoading = false;
      dataVersion.value++ // 数据版本+1，确保问题判断刷新
    }
  }
  // 获取指定列表的错误统计
  const getListIssues = (listType) => {
    // 1. 确定目标 ID 集合
    let targetIds = []
    if (listType === 'active') targetIds = activeIds.value
    else if (listType === 'inactive') targetIds = inactiveIds.value
    else if (listType === 'temp') targetIds = tempIds.value
    // 2. 初始化结果结构
    const result = {
      count: 0,      // 总问题 Mod 数
      errorCount: 0, // 严重错误数
      warnCount: 0,  // 警告数
      infoCount: 0,  // 提示数
      stats: {}      // 动态存放 { [type]: [modId1, modId2...] }
    }
    // 3. 遍历统计
    targetIds.forEach(id => {
      const issues = modIssues.value.get(normalizeListToken(id))
      if (!issues || issues.length === 0) return
      // result.count += issues.length // 累加总问题数
      result.count++  // 累加出问题的Mod数
      // 统计严重程度 (只要有一个 error 就算 error 级)
      if (issues.some(i => i.level === 'error')) result.errorCount++
      else result.warnCount++
      // 按类型聚合 Mod 名称，统计所有出现的错误类型
      issues.forEach(issue => {
        const typeKey = issue.type
        if (!result.stats[typeKey]) {
          result.stats[typeKey] = []
        }
        // 避免同一个 Mod 在同一个类型下重复 (虽然一般不会)
        if (!result.stats[typeKey].includes(normalizeListToken(id))) {
          result.stats[typeKey].push(normalizeListToken(id))
        }
      })
    })
    return result
  }

  return {
    modIssues,
    getIssusTargetIds,
    getModIssueState,
    ignoreIssue,
    batchIgnoreIssues,
    getListIssues,
  }
}
