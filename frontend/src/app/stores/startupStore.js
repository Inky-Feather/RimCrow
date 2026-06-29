import { defineStore } from 'pinia'
import { ref } from 'vue'
import { toast } from '../../shared/lib/common'
import { useAiStore } from '../../features/ai/aiStore'
import { useProfileStore } from '../../features/profiles/profileStore'
import { useWorkspaceStore } from '../../features/workspace/workspaceStore'

// 启动编排只负责“先后顺序”和“阻塞/后台”的取舍，具体业务仍由各自 store/API 执行。
export const useStartupStore = defineStore('startup', () => {
  const phase = ref('idle')
  const lastError = ref('')

  const setPhase = (nextPhase) => {
    phase.value = String(nextPhase || 'idle')
  }

  // 自动更新只需要每天探测一次；系统时间回拨时也允许重新检查，避免长期卡在未来时间戳。
  const shouldRunDailyCheck = (lastCheckTime) => {
    const last = Number(lastCheckTime || 0)
    const duration = Date.now() - last
    return !last || duration > 24 * 60 * 60 * 1000 || duration < 0
  }

  const buildDailyCheckDecision = (enabled, lastCheckTime) => {
    const last = Number(lastCheckTime || 0)
    const elapsed = Date.now() - last
    const due = !!enabled && (!last || elapsed > 24 * 60 * 60 * 1000 || elapsed < 0)
    const reason = !enabled ? 'disabled' : (!last ? 'never_checked' : (elapsed < 0 ? 'clock_rollback' : (due ? 'interval_due' : 'interval_not_due')))
    return { due, reason, enabled: !!enabled, lastCheckTime: last, intervalDays: 1, elapsedMs: elapsed }
  }

  const logStartupCheck = (event, payload = {}, level = 'info') => {
    // 与维护检查保持同一日志前缀，方便在控制台按 [RMM][maintenance-check] 过滤启动期检测。
    const method = level === 'warn' ? 'warn' : level === 'error' ? 'error' : 'info'
    console[method]('[RMM][maintenance-check]', { event, ...payload })
  }

  // 升级上下文由后端在启动时生成；这里把它转成前端动作，例如提示用户和强制扫描。
  const handleUpgradeContext = (upgradeContext) => {
    let scanForce = false
    const context = upgradeContext?.value || {}
    if (context.version_changed) {
      console.info('检测到版本升级:', context.old_version, '->', context.new_version)
      if (context.pending_actions?.includes('recommend_scan')) {
        scanForce = true
      }
      if (context.actions_taken?.length > 0) {
        toast.info(`升级完成: ${context.actions_taken.join(', ')}`)
      }
    }
    if (context.messages?.length > 0) {
      toast.info(context.messages.join('\n'), { timeout: 5000 })
    }
    return scanForce
  }

  // 主启动流程：阻塞项只保留“后端可用、事件注册、AI 配置、缓存数据装载”。
  // 扫描、更新探测、维护检查都放到后段或定时器，保证用户尽快进入主界面。
  const run = async ({
    waitForBackend,
    setupEventListeners,
    refreshData,
    settings,
    upgradeContext,
    uiState,
    checkUpdate,
    confirmStore,
    requestModScan,
    runScheduledMaintenanceChecks,
  }) => {
    lastError.value = ''
    try {
      // 等待后端可用
      setPhase('wait_backend')
      await waitForBackend()
      // 注册事件监听
      setPhase('register_events')
      setupEventListeners()
      // 配置 AI 模型
      setPhase('ai_config')
      await useAiStore().initialize()
      // 加载缓存数据
      setPhase('hydrate_cached_data')
      const refreshed = await refreshData(true)
      if (!refreshed) return false
      // 处理升级上下文
      setPhase('post_hydration')
      const scanForce = handleUpgradeContext(upgradeContext)
      const profileStore = useProfileStore()
      const workspaceStore = useWorkspaceStore()
      if (settings.value.current_profile_id) {
        profileStore.currentProfileId = settings.value.current_profile_id
      }
      await workspaceStore.fetchLibrariesMods()
      const startupWorkshopChanges = workspaceStore.detectStartupWorkshopChanges()
      const startupWorkshopPaths = workspaceStore.takeStartupWorkshopChangesForScan().map(item => item.path)
      // 自动更新探测
      setPhase('startup_update_probe')
      const updateDecision = buildDailyCheckDecision(settings.value.enable_auto_update_check, settings.value.last_update_check_time)
      logStartupCheck('schedule_decision', { id: 'app-update', name: '软件更新', ...updateDecision })
      if (settings.value.enable_auto_update_check && shouldRunDailyCheck(settings.value.last_update_check_time)) {
        logStartupCheck('schedule_run', { id: 'app-update', name: '软件更新' })
        void checkUpdate(false)
      }
      // 自动扫描
      setPhase('startup_scan')
      if (settings.value.enable_auto_scan !== false) {
        await requestModScan({
          forcedUpdate: scanForce,
          preserveListState: true,
          sizeCheckPaths: startupWorkshopPaths,
          startupWorkshopChanges,
        })
      } else if (startupWorkshopChanges.length) {
        window.setTimeout(async () => {
          await workspaceStore.showStartupWorkshopChangesPrompt(startupWorkshopChanges, {
            beforeScan: true,
            scanAction: async () => {
              await requestModScan({
                preserveListState: true,
                sizeCheckPaths: startupWorkshopPaths,
                startupWorkshopChanges,
              })
            },
          })
        }, 800)
      }

      // 给主界面一次渲染和用户操作机会，再排队启动维护检查，避免首屏刚出现就被弹窗抢占。
      setPhase('maintenance_probe_scheduled')
      window.setTimeout(() => {
        if (uiState.showSettingsPanel) {
          logStartupCheck('schedule_skip', { id: 'maintenance', name: '启动维护检查', reason: 'settings_panel_open' })
          return
        }
        runScheduledMaintenanceChecks().catch((error) => {
          logStartupCheck('schedule_error', { id: 'maintenance', name: '启动维护检查', message: error?.message || String(error || '') }, 'error')
        })
      }, 3000)

      setPhase('ready')
      return true
    } catch (error) {
      lastError.value = error?.message || String(error || '')
      throw error
    }
  }

  return {
    // 启动状态
    phase, lastError,
    // 启动入口
    run,
  }
})
