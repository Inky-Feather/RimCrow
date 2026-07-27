import { toast, checkResult, showUserErrorToast } from '../../../shared/lib/common'
import { useWorkspaceStore } from '../../../features/workspace/workspaceStore'
import { usePromptQueueStore } from '../../../features/ai/promptQueueStore'
import { getCurrentLocale, t } from '../../../shared/i18n.js'

export const useMaintenanceActions = ({
  settings,
  waitForDownload,
  refreshData,
  refreshModsData,
  refreshModCoreData,
  downloadWorkshopItems,
} = {}) => {
  const isTimedCheckDue = (enabled, lastCheckTime, intervalDays, fallbackDays = 1) => {
    if (!enabled) return false
    const last = Number(lastCheckTime || 0)
    const interval = Math.max(1, Number(intervalDays || fallbackDays)) * 24 * 60 * 60 * 1000
    const duration = Date.now() - last
    return !last || duration > interval || duration < 0
  }

  const buildTimedCheckDecision = ({ enabled, lastCheckTime, intervalDays, fallbackDays = 1 } = {}) => {
    const last = Number(lastCheckTime || 0)
    const interval = Math.max(1, Number(intervalDays || fallbackDays)) * 24 * 60 * 60 * 1000
    const elapsed = Date.now() - last
    const due = !!enabled && (!last || elapsed > interval || elapsed < 0)
    const reason = !enabled ? 'disabled' : (!last ? 'never_checked' : (elapsed < 0 ? 'clock_rollback' : (due ? 'interval_due' : 'interval_not_due')))
    return { due, reason, enabled: !!enabled, lastCheckTime: last, intervalDays: Math.round(interval / 24 / 60 / 60 / 1000), elapsedMs: elapsed }
  }

  const logMaintenanceCheck = (event, payload = {}, level = 'info') => {
    // 统一启动/维护检测日志格式，排查“为什么没自动检查”时只需要搜索这个前缀。
    const method = level === 'warn' ? 'warn' : level === 'error' ? 'error' : 'info'
    console[method]('[RimCrow][maintenance-check]', { event, ...payload })
  }

  const formatDateTime = (timestamp) => {
    const value = Number(timestamp || 0)
    if (!value) return t('common.status.unknown', '未知')
    try {
      return new Date(value).toLocaleString(getCurrentLocale())
    } catch {
      return t('common.status.unknown', '未知')
    }
  }

  const formatFileSize = (value) => {
    const size = Number(value || 0)
    if (!size) return t('common.status.unknown', '未知')
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / 1024 / 1024).toFixed(1)} MB`
  }

  const shortSignature = (value) => String(value || '').trim().slice(0, 12)

  const buildExternalDataMeta = (item = {}) => {
    const mode = String(item?.comparison_mode || '').trim()
    if (mode === 'missing') {
      if (item.data_type === 'git_provider_catalog') {
        return [
          t('maintenance.external_data.meta.local_cache_missing', '本地缓存缺失'),
          Array.isArray(item.source_labels) && item.source_labels.length > 0 ? t('maintenance.external_data.meta.sources', '来源 {sources}', { sources: item.source_labels.join('、') }) : '',
          item.remote_size ? t('maintenance.external_data.meta.remote_items', '远端项目 {count} 个', { count: item.remote_size }) : '',
        ].filter(Boolean)
      }
      return [
        t('maintenance.external_data.meta.local_file_missing', '本地文件缺失'),
        item.remote_signature ? t('maintenance.external_data.meta.remote_signature', '远端签名 {signature}', { signature: shortSignature(item.remote_signature) }) : '',
        item.remote_size ? t('maintenance.external_data.meta.remote_size', '远端大小 {size}', { size: formatFileSize(item.remote_size) }) : '',
      ].filter(Boolean)
    }
    if (mode === 'signature') {
      return [
        Array.isArray(item.source_labels) && item.source_labels.length > 0 ? t('maintenance.external_data.meta.sources', '来源 {sources}', { sources: item.source_labels.join('、') }) : '',
        item.local_signature ? t('maintenance.external_data.meta.local_signature', '本地签名 {signature}', { signature: shortSignature(item.local_signature) }) : '',
        item.remote_signature ? t('maintenance.external_data.meta.remote_signature', '远端签名 {signature}', { signature: shortSignature(item.remote_signature) }) : '',
      ].filter(Boolean)
    }
    if (mode === 'size') {
      return [
        t('maintenance.external_data.meta.local_size', '本地大小 {size}', { size: formatFileSize(item.local_size) }),
        t('maintenance.external_data.meta.remote_size', '远端大小 {size}', { size: formatFileSize(item.remote_size) }),
      ].filter(Boolean)
    }
    return [
      item.local_version ? t('maintenance.external_data.meta.local_version', '本地版本 {version}', { version: item.local_version }) : t('maintenance.external_data.meta.local_time', '本地时间 {time}', { time: formatDateTime(item.local_mtime) }),
      item.remote_version ? t('maintenance.external_data.meta.remote_version', '远端版本 {version}', { version: item.remote_version }) : t('maintenance.external_data.meta.remote_time', '远端时间 {time}', { time: formatDateTime(item.remote_updated_at) }),
    ].filter(Boolean)
  }

  const installToolIssues = async (issues = []) => {
    if (!window.pywebview || !Array.isArray(issues) || issues.length === 0) return false
    let started = false
    const hasSteamCmdIssue = issues.some(item => item?.tool_id === 'steamcmd')
    const hasToddsIssue = issues.some(item => item?.tool_id === 'todds')
    const hasRipgrepIssue = issues.some(item => item?.tool_id === 'ripgrep')

    if (hasSteamCmdIssue) {
      const res = await window.pywebview.api.steam_tools_install()
      if (checkResult(res, t('check.maintenance.handle_steamcmd', '处理 SteamCMD 环境'))) {
        started = true
        if (Array.isArray(res.data?.pending_tasks) && res.data.pending_tasks.length > 0) {
          toast.info(t('toast.maintenance.steamcmd_tasks_started', 'SteamCMD 相关任务已启动，请留意底部状态栏。'))
        }
      }
    }

    if (hasToddsIssue) {
      const res = await window.pywebview.api.texture_prepare_download(settings.value.texture_opt)
      if (checkResult(res, t('check.maintenance.handle_todds', '处理 todds 环境'))) {
        started = true
        if (!res.data?.already_ready) {
          toast.info(t('toast.maintenance.todds_download_started', 'todds 下载任务已启动，请留意底部状态栏。'))
        }
      }
    }

    if (hasRipgrepIssue) {
      const ripgrepIssue = issues.find(item => item?.tool_id === 'ripgrep') || {}
      const res = await window.pywebview.api.ripgrep_prepare_download(ripgrepIssue?.maintenance_action === 'upgrade')
      if (checkResult(res, t('check.maintenance.handle_ripgrep', '处理 ripgrep 环境'))) {
        started = true
        if (!res.data?.already_ready) {
          toast.info(t('toast.maintenance.ripgrep_download_started', 'ripgrep 下载任务已启动，请留意底部状态栏。'))
        }
      }
    }
    return started
  }

  const refreshGitProviderCatalog = async ({ silent = false } = {}) => {
    if (!window.pywebview) return false
    if (silent) {
      const res = await window.pywebview.api.github_get_provider_catalog('', true)
      return checkResult(res, t('check.maintenance.refresh_git_catalog', '刷新 Git 推荐清单'), false, { silent: true })
    }
    const workspaceStore = useWorkspaceStore()
    const refreshed = await workspaceStore.fetchGithubProviderCatalog({ force: true })
    if (refreshed) toast.success(t('toast.maintenance.git_catalog_refreshed', 'Git 推荐清单已刷新。'))
    return refreshed
  }

  const MOD_DATA_EXTERNAL_DB_TYPES = new Set(['community_rules', 'workshop_db', 'instead_db', 'multiplayer_compatibility', 'mp_compat_package_ids'])
  const refreshAfterExternalDataUpdate = async (historyLabel = t('history.maintenance.external_data_refresh_after_update', '外部库更新后同步模组数据')) => {
    if (refreshModCoreData) return await refreshModCoreData(historyLabel, { preserveListState: true })
    if (refreshModsData) return await refreshModsData(historyLabel, { preserveListState: true })
    return await refreshData(false, historyLabel)
  }

  const updateExternalDataItems = async (items = [], { silent = false } = {}) => {
    let updated = 0
    let shouldRefreshModData = false
    for (const item of Array.isArray(items) ? items : []) {
      if (!item?.data_type) continue
      if (await updateExternalDB(item.data_type, { silent, refreshAfter: false })) {
        updated += 1
        shouldRefreshModData = shouldRefreshModData || MOD_DATA_EXTERNAL_DB_TYPES.has(item.data_type)
      }
    }
    if (shouldRefreshModData) await refreshAfterExternalDataUpdate()
    return updated
  }

  const getToolIssueActionLabel = (item = {}) => {
    // 后端会把存在性、初始化、升级判断统一成 maintenance_action，前端只负责显示用户能理解的动作。
    const action = String(item?.maintenance_action || '').trim()
    if (action === 'upgrade') return t('maintenance.tool.action.upgrade', '升级')
    if (action === 'initialize') return t('maintenance.tool.action.initialize', '初始化')
    if (action === 'install') return t('maintenance.tool.action.install', '安装')
    return t('maintenance.tool.action.handle', '处理')
  }

  const triggerGithubManagedModUpdate = async (item = {}) => {
    if (!window.pywebview || !item?.repo_url) return false
    const targetVersion = String(item.target_version || item.latest_version || '').trim()
    const res = await window.pywebview.api.github_trigger_download(item.repo_url, item.install_type || 'source', targetVersion)
    if (!checkResult(res, t('check.maintenance.update_git_mod', '更新 Git 仓库模组 {title}', { title: item.title || '' }).trim())) return false
    toast.info(t('toast.maintenance.git_deploy_started', 'Git 仓库部署任务已启动，请留意底部状态栏。'), { timeout: 4000 })
    const workspaceStore = useWorkspaceStore()
    workspaceStore.startGithubTimelinePolling(item.repo_url, { intervalMs: 4000, maxPolls: 15 })
    return true
  }

  const updateManagedModItems = async (items = []) => {
    // 批量动作按来源拆分：SteamCMD 支持合并下载，Git 仓库订阅逐项启动部署任务。
    const normalizedItems = Array.isArray(items) ? items : []
    const workshopIds = [...new Set(
      normalizedItems
        .filter(item => String(item?.source || '').toLowerCase() === 'steamcmd')
        .map(item => String(item?.workshop_id || '').trim())
        .filter(Boolean)
    )]
    if (workshopIds.length > 0) await downloadWorkshopItems(workshopIds)

    for (const item of normalizedItems.filter(item => String(item?.source || '').toLowerCase() === 'github')) {
      await triggerGithubManagedModUpdate(item)
    }
    return workshopIds.length > 0 || normalizedItems.some(item => String(item?.source || '').toLowerCase() === 'github')
  }

  // 维护检查的时间戳统一在前端落到 settings，避免每个检查函数重复处理“何时算检查成功”。
  const persistMaintenanceCheckedAt = (settingKey, data, shouldPersist = null) => {
    const checkedAt = Number(data?.checked_at || 0)
    if (!settingKey || !checkedAt) return
    if (typeof shouldPersist === 'function' && !shouldPersist(data)) return
    settings.value[settingKey] = checkedAt
  }

  // 维护类接口都遵循同一返回格式：手动触发走 checkResult 给用户反馈，启动期静默触发只接受 success。
  const fetchMaintenanceData = async ({
    apiName,
    workName,
    manual = true,
    lastCheckKey = '',
    shouldPersistCheckedAt = null,
    overrides = null,
  } = {}) => {
    if (!window.pywebview) return null
    const caller = window.pywebview.api?.[apiName]
    if (typeof caller !== 'function') return null

    const res = overrides ? await caller(overrides) : await caller()
    if (manual ? !checkResult(res, workName) : res?.status !== 'success') {
      logMaintenanceCheck('api_result', { apiName, workName, manual, status: res?.status || 'missing', message: res?.message || '' }, manual ? 'warn' : 'error')
      return null
    }

    const data = res.data || {}
    persistMaintenanceCheckedAt(lastCheckKey, data, shouldPersistCheckedAt)
    logMaintenanceCheck('api_result', { apiName, workName, manual, status: res.status, checkedAt: data.checked_at || 0, count: data.count ?? data.issues?.length ?? data.updates?.length ?? 0 })
    return data
  }

  // 工具环境可能涉及外部下载，因此只做检查本身静默；发现问题后统一进入提示队列交给用户决定。
  const checkToolMaintenance = async ({ manual = true, prompt = true, overrides = null } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_tools',
      workName: t('check.maintenance.tools', '检查工具环境'),
      manual,
      lastCheckKey: 'last_tool_check_time',
      overrides,
    })
    if (!data) return null

    const issues = Array.isArray(data.issues) ? data.issues : []
    if (!prompt) return data
    if (issues.length === 0) {
      if (manual) toast.success(t('toast.maintenance.tools_ready', '工具环境检查完成，当前均已就绪。'))
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-tools',
      title: t('maintenance.tool.prompt.title', '工具环境需要处理'),
      message: t('maintenance.tool.prompt.message', '以下工具当前未就绪，可单独处理，也可以批量处理。'),
      type: 'warning',
      priority: manual ? 30 : 60,
      items: issues.map(item => ({
        id: item.tool_id || item.name,
        title: item.name || item.tool_id || t('maintenance.tool.fallback_title', '工具'),
        description: item.message || t('maintenance.tool.need_handle', '需要处理'),
        meta: [
          item.resolved_path,
          item.current_version ? t('maintenance.common.current_version', '当前版本 {version}', { version: item.current_version }) : '',
          item.latest_version ? t('maintenance.common.latest_version', '最新版本 {version}', { version: item.latest_version }) : '',
        ].filter(Boolean),
        raw: item,
        actions: [
          { id: 'install', label: getToolIssueActionLabel(item), kind: 'primary' },
          { id: 'skip', label: t('common.action.later_short', '稍后'), kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'install_all', label: t('maintenance.action.handle_all', '全部处理'), kind: 'primary' },
        { id: 'skip_all', label: t('maintenance.action.skip_all', '全部稍后'), kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'install') await installToolIssues([item])
      },
      onBulkAction: async (actionId, items) => {
        if (actionId === 'install_all') await installToolIssues(items)
      },
    })
    return data
  }

  // 外部库更新属于网络下载动作：启动期可以静默检查，但实际更新必须经由队列弹窗确认。
  const checkExternalDataUpdates = async ({ manual = true, prompt = true, overrides = null } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_external_data',
      workName: t('check.maintenance.external_data', '检查外部库更新'),
      manual,
      lastCheckKey: 'last_external_data_update_check_time',
      overrides,
      // 整轮远端状态都没拿到时，不要把失败记录成一次成功检查。
      shouldPersistCheckedAt: (payload) => {
        const items = Array.isArray(payload?.items) ? payload.items : []
        const failed = Array.isArray(payload?.failed) ? payload.failed : []
        return items.length === 0 || failed.length < items.length
      },
    })
    if (!data) return null

    const updates = Array.isArray(data.updates) ? data.updates : []
    const failed = Array.isArray(data.failed) ? data.failed : []
    if (!prompt) return data
    if (!manual && settings.value.enable_silent_external_data_update && updates.length > 0) {
      const updated = await updateExternalDataItems(updates, { silent: true })
      logMaintenanceCheck('external_data_silent_update', { total: updates.length, updated, failed: failed.length })
      return data
    }
    if (failed.length > 0 && updates.length === 0) {
      const summary = failed.slice(0, 3).map(item => item.name || item.data_type || t('maintenance.external_data.fallback_title', '外部库')).join('、')
      const remain = failed.length > 3 ? t('maintenance.common.more_count_suffix', ' 等 {count} 项', { count: failed.length }) : ''
      toast.warning(t('toast.maintenance.external_data_failed_summary', '外部库检查未完成：{summary}{remain} 检查失败，请稍后重试或检查网络环境。', { summary, remain }), { timeout: 4500 })
      return data
    }
    if (updates.length === 0) {
      if (manual) toast.success(t('toast.maintenance.external_data_up_to_date', '外部库检查完成，当前均已是最新。'))
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-external-data',
      title: t('maintenance.external_data.prompt.title', '发现外部库更新'),
      message: failed.length > 0
        ? t('maintenance.external_data.prompt.partial_failed', '另有 {count} 项外部库暂时检查失败，本次只展示已成功获取到远端状态的更新项。', { count: failed.length })
        : t('maintenance.external_data.prompt.message', '以下外部库文件检测到更新，可单独更新，也可以批量更新。'),
      type: 'warning',
      priority: manual ? 35 : 65,
      items: updates.map(item => ({
        id: item.data_type || item.name,
        title: item.name || item.data_type || t('maintenance.external_data.fallback_title', '外部库'),
        description: item.message || t('maintenance.external_data.default_description', '检测到远端文件与本地不一致。'),
        meta: buildExternalDataMeta(item),
        raw: item,
        actions: [
          { id: 'update', label: t('common.action.update', '更新'), kind: 'primary' },
          { id: 'skip', label: t('common.action.later_short', '稍后'), kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'update_all', label: t('maintenance.action.update_all', '全部更新'), kind: 'primary' },
        { id: 'skip_all', label: t('maintenance.action.skip_all', '全部稍后'), kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'update') await updateExternalDB(item.data_type)
      },
      onBulkAction: async (actionId, items) => {
        if (actionId !== 'update_all') return
        // 顺序执行，避免同时刷新同一批缓存时互相打断。
        await updateExternalDataItems(items)
      },
    })
    return data
  }

  // 管理器负责的模组更新包含 SteamCMD 工坊模组和 Git 仓库订阅模组，统一弹窗避免多来源重复打扰。
  const checkManagedModUpdates = async ({ manual = true, prompt = true } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_managed_mod_updates',
      workName: t('check.maintenance.managed_mod_updates', '检查管理器模组更新'),
      manual,
      lastCheckKey: 'last_steamcmd_mod_update_check_time',
    })
    if (!data) return null

    const updates = Array.isArray(data.updates) ? data.updates : []
    if (!prompt) return data
    if (updates.length === 0) {
      if (manual) toast.success(t('toast.maintenance.managed_mods_up_to_date', '管理器模组检查完成，当前均已是最新。'))
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-managed-mods',
      title: t('maintenance.managed_mods.prompt.title', '发现管理器模组更新'),
      message: t('maintenance.managed_mods.prompt.message', '检测到 {count} 个由管理器维护的模组有新版本。', { count: updates.length }),
      type: 'warning',
      priority: manual ? 40 : 70,
      items: updates.map(item => ({
        id: `${item.source || 'mod'}:${item.workshop_id || item.repo_url || item.title}`,
        title: item.title || item.workshop_id || t('common.entity.unknown_mod', '未知模组'),
        description: item.message || (item.workshop_id ? t('common.field.workshop_id_prefix', '工坊 ID：{value}', { value: item.workshop_id }) : item.repo_url || ''),
        meta: [
          item.source_label || item.source,
          item.installed_version ? t('maintenance.common.current_version', '当前版本 {version}', { version: item.installed_version }) : '',
          item.latest_version ? t('maintenance.common.latest_version', '最新版本 {version}', { version: item.latest_version }) : '',
        ].filter(Boolean),
        raw: item,
        actions: [
          { id: 'update', label: t('common.action.update', '更新'), kind: 'primary' },
          { id: 'skip', label: t('common.action.later_short', '稍后'), kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'update_all', label: t('maintenance.action.update_all', '全部更新'), kind: 'primary' },
        { id: 'skip_all', label: t('maintenance.action.skip_all', '全部稍后'), kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'update') await updateManagedModItems([item])
      },
      onBulkAction: async (actionId, items) => {
        if (actionId === 'update_all') await updateManagedModItems(items)
      },
    })
    return data
  }
  const checkSteamcmdModUpdates = checkManagedModUpdates

  // 启动后的维护检查只做轻量描述表，不引入任务引擎；以后新增检查时只追加一项配置。
  const getScheduledMaintenanceChecks = () => [
    {
      id: 'tools',
      name: t('maintenance.schedule.tools', '外部工具'),
      enabled: settings.value.enable_auto_tool_check,
      lastCheckTime: settings.value.last_tool_check_time,
      intervalDays: settings.value.tool_check_interval_days,
      fallbackDays: 3,
      run: () => checkToolMaintenance({ manual: false, prompt: true }),
    },
    {
      id: 'external-data',
      name: t('maintenance.schedule.external_data', '外部库'),
      enabled: settings.value.enable_auto_external_data_update_check,
      lastCheckTime: settings.value.last_external_data_update_check_time,
      intervalDays: settings.value.external_data_update_check_interval_days,
      fallbackDays: 1,
      run: () => checkExternalDataUpdates({ manual: false, prompt: true }),
    },
    {
      id: 'managed-mods',
      name: t('maintenance.schedule.managed_mods', '管理器模组更新'),
      enabled: settings.value.enable_auto_steamcmd_mod_update_check,
      lastCheckTime: settings.value.last_steamcmd_mod_update_check_time,
      intervalDays: settings.value.steamcmd_mod_update_check_interval_days,
      fallbackDays: 1,
      run: () => checkManagedModUpdates({ manual: false, prompt: true }),
    },
  ]

  const runScheduledMaintenanceChecks = async () => {
    for (const check of getScheduledMaintenanceChecks()) {
      const decision = buildTimedCheckDecision(check)
      logMaintenanceCheck('schedule_decision', { id: check.id, name: check.name, ...decision })
      if (!decision.due) continue
      try {
        logMaintenanceCheck('schedule_run', { id: check.id, name: check.name })
        await check.run()
        logMaintenanceCheck('schedule_done', { id: check.id, name: check.name })
      } catch (error) {
        logMaintenanceCheck('schedule_error', { id: check.id, name: check.name, message: error?.message || String(error || '') }, 'error')
        throw error
      }
    }
  }

  // 兼容旧调用名：手动检查工具环境并按需弹窗。
  const checkSteamTools = async () => checkToolMaintenance({ manual: true, prompt: true })

  // 更新外置数据库
  const updateExternalDB = async (type, { silent = false, refreshAfter = true } = {}) => {
    try {
      const workNameMap = {
        community_rules: t('check.maintenance.update_community_rules', '更新社区规则库'),
        workshop_db: t('check.maintenance.update_workshop_db', '更新社区工坊数据库'),
        instead_db: t('check.maintenance.update_instead_db', '更新替代 Mod 数据库'),
        multiplayer_compatibility: t('check.maintenance.update_multiplayer_compatibility', '更新 Multiplayer 兼容表'),
        mp_compat_package_ids: t('check.maintenance.update_mp_compat_package_ids', '生成 Multiplayer Compatibility 适配缓存'),
        git_provider_catalog: t('check.maintenance.refresh_git_catalog', '刷新 Git 推荐清单'),
      }
      if (type === 'git_provider_catalog') {
        return refreshGitProviderCatalog({ silent })
      }
      // 调用 API
      const res = await window.pywebview.api.update_external_db(type)
      const workName = workNameMap[type] || t('check.maintenance.update_external_db_type', '更新外置数据库 {type}', { type })
      if (checkResult(res, workName, false, { silent })) {
        const task_id = res.data.task_id
        if (task_id) await waitForDownload(task_id)
        // 重新获取数据
        const historyLabel = t('history.maintenance.external_data_refresh_after_named_update', '{name}后同步模组数据', { name: workNameMap[type] || t('maintenance.external_data.update_fallback', '外置数据库更新') })
        if (refreshAfter && MOD_DATA_EXTERNAL_DB_TYPES.has(type)) await refreshAfterExternalDataUpdate(historyLabel)
        return true
      }
      return false
    } catch (error) {
      if (!silent && !error?.from_task) showUserErrorToast(error, t('toast.maintenance.external_data_update_failed', '更新外部库失败。请检查网络连接、代理设置和本地文件写入权限。'))
      return false
    }
  }

  return {
    // 日志与调度
    isTimedCheckDue, logMaintenanceCheck, runScheduledMaintenanceChecks,
    // 检查入口
    checkSteamTools, checkToolMaintenance, checkExternalDataUpdates, checkManagedModUpdates, checkSteamcmdModUpdates,
    // 更新动作
    updateExternalDB,
  }
}
