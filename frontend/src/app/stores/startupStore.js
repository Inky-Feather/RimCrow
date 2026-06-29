import { defineStore } from 'pinia'
import { ref } from 'vue'
import { toast } from '../../shared/lib/common'
import { startupPerfMark, startupPerfMeasure } from '../../shared/lib/startupPerf'
import { useAiStore } from '../../features/ai/aiStore'
import { useProfileStore } from '../../features/profiles/profileStore'
import { useWorkspaceStore } from '../../features/workspace/workspaceStore'

// 启动编排只负责“先后顺序”和“阻塞/后台”的取舍，具体业务仍由各自 store/API 执行。
export const useStartupStore = defineStore('startup', () => {
  const phase = ref('idle')
  const lastError = ref('')

  const setPhase = (nextPhase) => {
    phase.value = String(nextPhase || 'idle')
    startupPerfMark('startup_phase', { phase: phase.value })
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
    // 与维护检查保持同一日志前缀，方便在控制台按 [RimCrow][maintenance-check] 过滤启动期检测。
    const method = level === 'warn' ? 'warn' : level === 'error' ? 'error' : 'info'
    console[method]('[RimCrow][maintenance-check]', { event, ...payload })
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

  const runStartupBackground = async ({
    scanForce,
    settings,
    uiState,
    checkUpdate,
    requestModScan,
    runScheduledMaintenanceChecks,
    refreshModEnrichment,
    refreshBackupData,
    loadStartupInventorySummary,
    isScanRunning,
  }) => {
    try {
      setPhase('background_direct_data')
      const autoScanEnabled = settings.value.enable_auto_scan !== false
      const workspaceStore = useWorkspaceStore()
      const summarizeStartupInventory = async () => {
        try {
          const startupWorkshopChanges = await startupPerfMeasure('startup.background.inventory_summary', () => loadStartupInventorySummary({ silent: true }))
          const startupWorkshopEvents = Array.isArray(startupWorkshopChanges) ? startupWorkshopChanges : []
          const startupWorkshopPaths = startupWorkshopEvents
            .filter(item => item.status === 'changed' && item.path)
            .map(item => item.path)
          startupPerfMark('startup.inventory_detected', {
            changes: startupWorkshopEvents.length,
            scan_paths: startupWorkshopPaths.length,
          })
          return { events: startupWorkshopEvents, paths: startupWorkshopPaths }
        } catch (error) {
          console.warn('启动库存检测失败:', error)
          startupPerfMark('startup.inventory_failed', { message: error?.message || String(error || '') })
          return { events: [], paths: [] }
        }
      }
      const startDirectJobs = () => {
        const directJobs = [
          ['backups', () => refreshBackupData({ silent: true })],
          ['ai_config', () => useAiStore().initialize({ silent: true })],
        ]
        if (!autoScanEnabled) {
          directJobs.unshift(['mod_enrichment', () => refreshModEnrichment({ silent: true })])
        }
        // 这些数据只补充界面标记或辅助面板，自动扫描启动后再进入队列。
        void Promise.allSettled(directJobs.map(async ([id, runner]) => ({
          id,
          value: await startupPerfMeasure(`startup.background.${id}`, runner),
        }))).then((results) => {
          let failedCount = 0
          results.forEach((result) => {
            if (result.status === 'rejected') {
              failedCount += 1
              console.warn('启动后台数据补齐失败:', result.reason)
              return
            }
            if (result.value.value === false || result.value.value == null) {
              failedCount += 1
              console.warn('启动后台数据补齐未完成:', result.value.id)
            }
          })
          if (failedCount > 0) {
            toast.warning('部分启动数据暂时未能补齐，列表标记可能稍后才会出现。', { timeout: 3000 })
          }
          return results
        })
      }
      const scheduleAuxiliaryWarmup = (delayMs = 5000) => {
        window.setTimeout(() => {
          if (isScanRunning?.value) {
            scheduleAuxiliaryWarmup(3000)
            return
          }
          void startupPerfMeasure('startup.background.auxiliary_warmup', async () => {
            if (!window.pywebview?.api?.startup_warm_auxiliary_data) return false
            const res = await window.pywebview.api.startup_warm_auxiliary_data()
            if (res?.status && res.status !== 'success') {
              console.warn('启动辅助缓存预热失败:', res)
              toast.warning('部分后台数据暂时未能预热，相关提示可能稍后才会出现。', { timeout: 3000 })
              return false
            }
            return true
          }).catch((error) => {
            console.warn('启动辅助缓存预热失败:', error)
            toast.warning('部分后台数据暂时未能预热，相关提示可能稍后才会出现。', { timeout: 3000 })
          })
        }, delayMs)
      }

      // 自动扫描
      setPhase('startup_scan')
      const inventoryPromise = summarizeStartupInventory()
      if (autoScanEnabled) {
        const { events, paths } = await inventoryPromise
        await startupPerfMeasure('startup.request_mod_scan', () => requestModScan({
          forcedUpdate: scanForce,
          preserveListState: true,
          sizeCheckPaths: paths,
          startupWorkshopChanges: events,
          refreshRules: false,
          refreshBackups: false,
          refreshWorkspaceLibraries: false,
          silentSuccess: true,
        }))
        startDirectJobs()
      } else {
        startDirectJobs()
        const { events } = await inventoryPromise
        if (events.length) {
          window.setTimeout(async () => {
            await workspaceStore.showStartupWorkshopChangesPrompt(events, {
              beforeScan: true,
            })
          }, 800)
        }
      }
      scheduleAuxiliaryWarmup()

      // 给主界面和自动扫描一次启动机会，再排队更新与维护检查，避免首屏刚出现就被弹窗抢占。
      setPhase('deferred_checks_scheduled')
      window.setTimeout(() => {
        const updateDecision = buildDailyCheckDecision(settings.value.enable_auto_update_check, settings.value.last_update_check_time)
        logStartupCheck('schedule_decision', { id: 'app-update', name: '软件更新', ...updateDecision })
        if (settings.value.enable_auto_update_check && shouldRunDailyCheck(settings.value.last_update_check_time)) {
          logStartupCheck('schedule_run', { id: 'app-update', name: '软件更新' })
          void checkUpdate(false)
        }
      }, 1500)
      window.setTimeout(() => {
        if (uiState.showSettingsPanel) {
          logStartupCheck('schedule_skip', { id: 'maintenance', name: '启动维护检查', reason: 'settings_panel_open' })
          return
        }
        runScheduledMaintenanceChecks().catch((error) => {
          logStartupCheck('schedule_error', { id: 'maintenance', name: '启动维护检查', message: error?.message || String(error || '') }, 'error')
        })
      }, 3000)
    } catch (error) {
      console.error('启动后台流程失败:', error)
      toast.warning('启动后的后台检查未完成。部分列表标记或自动扫描可能需要稍后手动刷新。', { timeout: 4000 })
    }
  }

  // 主启动流程：阻塞项只保留“后端可用、事件注册、首屏核心数据”。
  // 展示标记、库存检测、扫描和维护检查都在首屏之后后台排队。
  const run = async ({
    waitForBackend,
    setupEventListeners,
    notifyFrontendReady,
    loadStartupCoreData,
    refreshModEnrichment,
    refreshBackupData,
    loadStartupInventorySummary,
    isScanRunning,
    settings,
    upgradeContext,
    uiState,
    checkUpdate,
    requestModScan,
    runScheduledMaintenanceChecks,
  }) => {
    lastError.value = ''
    try {
      // 等待后端可用
      setPhase('wait_backend')
      await startupPerfMeasure('startup.wait_backend', waitForBackend)
      // 注册事件监听
      setPhase('register_events')
      setupEventListeners()
      // 加载首屏核心数据
      setPhase('hydrate_core_data')
      const refreshed = await startupPerfMeasure('startup.load_core_data', () => loadStartupCoreData())
      if (!refreshed) return false
      // 处理升级上下文
      setPhase('post_hydration')
      const scanForce = handleUpgradeContext(upgradeContext)
      const profileStore = useProfileStore()
      if (settings.value.current_profile_id) {
        profileStore.currentProfileId = settings.value.current_profile_id
      }

      setPhase('ready')
      window.setTimeout(() => {
        void (async () => {
          try {
            await startupPerfMeasure('startup.frontend_ready', async () => {
              if (typeof notifyFrontendReady === 'function') await notifyFrontendReady()
            })
          } catch (error) {
            console.warn('启动事件通道启用失败，后台流程继续执行:', error)
          }
          if (!profileStore.activeContext?.is_healthy) {
            setPhase('waiting_for_settings')
            return
          }
          await runStartupBackground({
            scanForce,
            settings,
            uiState,
            checkUpdate,
            requestModScan,
            runScheduledMaintenanceChecks,
            refreshModEnrichment,
            refreshBackupData,
            loadStartupInventorySummary,
            isScanRunning,
          })
        })()
      }, 0)
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
