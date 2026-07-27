import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

import { useSettingsActions } from '../src/app/stores/app/settingsActions.js'
import { useAppStore } from '../src/app/stores/appStore.js'
import { useModStore } from '../src/features/mod/stores/modStore.js'
import { useGroupStore } from '../src/features/mod/stores/groupStore.js'
import { useProfileStore } from '../src/features/profiles/profileStore.js'
import { useTaskStore } from '../src/app/stores/taskStore.js'
import { useRuleStore } from '../src/features/rules/ruleStore.js'

const print = console.log.bind(console)
console.log = () => {}
console.info = () => {}
console.debug = () => {}

const ok = (data = {}) => ({ status: 'success', data })

const installWindow = (api = {}) => {
  const listeners = new Map()
  globalThis.document = {
    documentElement: { style: { setProperty() {} }, dataset: {}, classList: { toggle() {} } },
  }
  globalThis.window = {
    pywebview: {
      api: {
        profiles_get: async () => ok([]),
        locale_get_language_options: async () => ok({ registry_options: [], user_locale_options: [] }),
        ...api,
      },
    },
    setTimeout,
    clearTimeout,
    addEventListener: (type, listener) => {
      const items = listeners.get(type) || []
      items.push(listener)
      listeners.set(type, items)
    },
    removeEventListener: (type, listener) => {
      const items = listeners.get(type) || []
      listeners.set(type, items.filter(item => item !== listener))
    },
    dispatchEvent: async (event) => {
      const items = listeners.get(event?.type) || []
      for (const listener of items) await listener(event)
      return true
    },
  }
}

const resetStores = (api = {}) => {
  setActivePinia(createPinia())
  installWindow(api)
}

const context = (patch = {}) => ({
  profile_id: 'default',
  game_install_path: 'G:/RimWorld',
  user_data_path: 'U:/RimWorld',
  use_workshop_mods: false,
  use_self_mods: false,
  is_healthy: true,
  ...patch,
})

const createSettingsActions = ({ settings = {}, uiState = { showSettingsPanel: true }, overrides = {} } = {}) => useSettingsActions({
  settings: ref({ ui: {}, ...settings }),
  uiState,
  isLoading: ref(false),
  userThemes: ref([]),
  applyCurrentTheme: () => {},
  syncRemoteImageCache: () => {},
  refreshData: async () => {},
  requestModScan: async () => {},
  refreshModCoreData: async () => {},
  refreshModEnrichment: async () => {},
  ...overrides,
})

async function testSettingsSourceChangeForcesCoreRefresh() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        workshop_mods_path: 'W:/Workshop',
        self_mods_path: 'S:/Self',
        steamcmd_mods_path: 'C:/SteamCMD',
      },
      active_context: context({ use_workshop_mods: true }),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context({ use_workshop_mods: false })

  const scans = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      workshop_mods_path: 'W:/Workshop',
      self_mods_path: 'S:/Self',
      steamcmd_mods_path: 'C:/SteamCMD',
    },
    overrides: {
      refreshData: async () => assert.fail('来源变化且自动扫描开启时不应只走 refreshData'),
      requestModScan: async (options) => { scans.push(options || {}) },
      refreshModCoreData: async () => assert.fail('来源变化应交给扫描后的核心刷新'),
    },
  })

  await actions.applySettings({ use_workshop_mods: true })

  assert.equal(scans.length, 1)
  assert.equal(scans[0].forceCoreRefresh, true)
}

async function testIssueSettingsRefreshModData() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        workshop_mods_path: 'W:/Workshop',
        self_mods_path: 'S:/Self',
        steamcmd_mods_path: 'C:/SteamCMD',
        check_language_support: false,
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      workshop_mods_path: 'W:/Workshop',
      self_mods_path: 'S:/Self',
      steamcmd_mods_path: 'C:/SteamCMD',
      check_language_support: true,
    },
    overrides: {
      refreshData: async () => assert.fail('问题判定设置变化不需要整套 refreshData'),
      requestModScan: async () => assert.fail('问题判定设置变化不需要扫描磁盘'),
      refreshModCoreData: async () => assert.fail('语言支持问题开关不需要刷新核心列表'),
      refreshModEnrichment: async () => assert.fail('语言支持问题开关不需要刷新补充信息'),
    },
  })

  await actions.applySettings({ check_language_support: false })
}

async function testWideLanguagePackDetectionRefreshesCore() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        wide_language_pack_detection: true,
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const coreRefreshes = []
  const actions = createSettingsActions({
    settings: {
      wide_language_pack_detection: false,
    },
    overrides: {
      refreshData: async () => assert.fail('宽泛语言包识别不需要整套 refreshData'),
      requestModScan: async () => assert.fail('宽泛语言包识别不需要扫描磁盘'),
      refreshModCoreData: async (...args) => { coreRefreshes.push(args) },
    },
  })

  await actions.applySettings({ wide_language_pack_detection: true })

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
}

async function testMultiplayerCompatibilitySettingRefreshesEnrichmentOnly() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        workshop_mods_path: 'W:/Workshop',
        self_mods_path: 'S:/Self',
        steamcmd_mods_path: 'C:/SteamCMD',
        enable_multiplayer_compatibility_check: true,
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const enrichments = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      workshop_mods_path: 'W:/Workshop',
      self_mods_path: 'S:/Self',
      steamcmd_mods_path: 'C:/SteamCMD',
      enable_multiplayer_compatibility_check: false,
    },
    overrides: {
      refreshData: async () => assert.fail('联机兼容开关变化不需要整套 refreshData'),
      requestModScan: async () => assert.fail('联机兼容开关变化不需要扫描磁盘'),
      refreshModCoreData: async () => assert.fail('联机兼容开关变化不需要重拉核心列表'),
      refreshModEnrichment: async (...args) => { enrichments.push(args) },
    },
  })

  await actions.applySettings({ enable_multiplayer_compatibility_check: true })

  assert.equal(enrichments.length, 1)
  assert.equal(enrichments[0][0].silent, true)
}

async function testToolModsSettingForcesCoreRefreshScan() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        workshop_mods_path: 'W:/Workshop',
        self_mods_path: 'S:/Self',
        steamcmd_mods_path: 'C:/SteamCMD',
        enable_tool_mods: true,
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const scans = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      workshop_mods_path: 'W:/Workshop',
      self_mods_path: 'S:/Self',
      steamcmd_mods_path: 'C:/SteamCMD',
      enable_tool_mods: false,
    },
    overrides: {
      refreshData: async () => assert.fail('辅助工具模组开关变化且自动扫描开启时不应只走 refreshData'),
      requestModScan: async (options) => { scans.push(options || {}) },
      refreshModCoreData: async () => assert.fail('辅助工具模组开关变化应交给扫描后的核心刷新'),
    },
  })

  await actions.applySettings({ enable_tool_mods: true })

  assert.equal(scans.length, 1)
  assert.equal(scans[0].forceCoreRefresh, true)
}

async function testSteamLaunchPreferenceForcesCoreRefreshScan() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        prefer_steam_launch: true,
      },
      active_context: context({ prefer_steam_launch: true }),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context({ prefer_steam_launch: false })

  const scans = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      prefer_steam_launch: false,
    },
    overrides: {
      refreshData: async () => assert.fail('Steam 启动偏好会影响工坊识别，不应只走 refreshData'),
      requestModScan: async (options) => { scans.push(options || {}) },
      refreshModCoreData: async () => assert.fail('来源变化应交给扫描后的核心刷新'),
    },
  })

  await actions.applySettings({ prefer_steam_launch: true })

  assert.equal(scans.length, 1)
  assert.equal(scans[0].forceCoreRefresh, true)
}

async function testRuleSourcePathChangeRefreshesRules() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        user_rules_path: 'R:/NewUserRules.json',
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const coreRefreshes = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      user_rules_path: 'R:/OldUserRules.json',
    },
    overrides: {
      refreshData: async () => assert.fail('规则路径变化不需要整套 refreshData'),
      requestModScan: async () => assert.fail('规则路径变化不需要扫描磁盘'),
      refreshModCoreData: async (...args) => { coreRefreshes.push(args) },
    },
  })

  await actions.applySettings({ user_rules_path: 'R:/NewUserRules.json' })

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
  assert.equal(coreRefreshes[0][1].refreshRules, true)
}

async function testExternalDataPathChangeRefreshesModData() {
  resetStores({
    save_all_settings: async () => ok({
      settings: {
        enable_auto_scan: true,
        current_profile_id: 'default',
        community_workshop_db_path: 'D:/New/workshop.json',
      },
      active_context: context(),
      remote_image_cache: {},
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const coreRefreshes = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      current_profile_id: 'default',
      community_workshop_db_path: 'D:/Old/workshop.json',
    },
    overrides: {
      refreshData: async () => assert.fail('外部库路径变化不需要整套 refreshData'),
      requestModScan: async () => assert.fail('外部库路径变化不需要扫描磁盘'),
      refreshModCoreData: async (...args) => { coreRefreshes.push(args) },
    },
  })

  await actions.applySettings({ community_workshop_db_path: 'D:/New/workshop.json' })

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
  assert.equal(coreRefreshes[0][1].refreshRules, false)
  assert.notEqual(coreRefreshes[0][1].refreshEnrichment, false)
}

async function testSaveSettingToolModsForcesCoreRefreshScan() {
  resetStores({
    save_setting: async () => ok({
      settings: {
        enable_auto_scan: true,
        enable_tool_mods: true,
      },
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const scans = []
  const actions = createSettingsActions({
    settings: {
      enable_auto_scan: true,
      enable_tool_mods: false,
    },
    uiState: { showSettingsPanel: false },
    overrides: {
      refreshData: async () => assert.fail('辅助工具模组开关单项保存且自动扫描开启时不应只走 refreshData'),
      requestModScan: async (options) => { scans.push(options || {}) },
      refreshModCoreData: async () => assert.fail('辅助工具模组开关变化应交给扫描后的核心刷新'),
    },
  })

  await actions.saveSetting('enable_tool_mods', true)

  assert.equal(scans.length, 1)
  assert.equal(scans[0].forceCoreRefresh, true)
}

async function testSaveSettingResetActiveListOnlyUpdatesSetting() {
  const calls = []
  resetStores({
    save_setting: async (key, config) => {
      calls.push([key, config])
      return ok({ settings: { reset_active_list: config } })
    },
  })
  const config = {
    user_ids: ['ludeon.rimworld'],
    excluded_builtin_ids: ['ludeon.rimworld.royalty'],
    excluded_derived_ids: [],
  }
  const actions = createSettingsActions({
    settings: { reset_active_list: {} },
    overrides: {
      refreshData: async () => assert.fail('预设列表保存不应刷新完整数据'),
      requestModScan: async () => assert.fail('预设列表保存不应扫描模组目录'),
      refreshModCoreData: async () => assert.fail('预设列表保存不应刷新核心列表'),
      refreshModEnrichment: async () => assert.fail('预设列表保存不应刷新补充信息'),
    },
  })

  const saved = await actions.saveSetting('reset_active_list', config)

  assert.equal(saved, true)
  assert.deepEqual(calls, [['reset_active_list', config]])
}

async function testSaveSettingLanguageSupportDoesNotRefreshModData() {
  resetStores({
    save_setting: async () => ok({
      settings: {
        check_language_support: false,
      },
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const actions = createSettingsActions({
    settings: {
      check_language_support: true,
    },
    uiState: { showSettingsPanel: false },
    overrides: {
      refreshData: async () => assert.fail('语言包检查单项保存不需要整套 refreshData'),
      requestModScan: async () => assert.fail('语言包检查单项保存不需要扫描磁盘'),
      refreshModCoreData: async () => assert.fail('语言包检查单项保存不需要刷新核心列表'),
      refreshModEnrichment: async () => assert.fail('语言包检查单项保存不需要刷新补充信息'),
    },
  })

  await actions.saveSetting('check_language_support', false)
}

async function testSaveSettingWideLanguagePackDetectionRefreshesCore() {
  resetStores({
    save_setting: async () => ok({
      settings: {
        wide_language_pack_detection: true,
      },
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const coreRefreshes = []
  const actions = createSettingsActions({
    settings: {
      wide_language_pack_detection: false,
    },
    uiState: { showSettingsPanel: false },
    overrides: {
      refreshData: async () => assert.fail('宽泛语言包识别单项保存不需要整套 refreshData'),
      requestModScan: async () => assert.fail('宽泛语言包识别单项保存不需要扫描磁盘'),
      refreshModCoreData: async (...args) => { coreRefreshes.push(args) },
    },
  })

  await actions.saveSetting('wide_language_pack_detection', true)

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
}

async function testSaveSettingIssueEnrichmentSettingRefreshesEnrichment() {
  resetStores({
    save_setting: async () => ok({
      settings: {
        enable_multiplayer_compatibility_check: true,
      },
    }),
  })
  const profileStore = useProfileStore()
  profileStore.activeContext = context()

  const enrichments = []
  const actions = createSettingsActions({
    settings: {
      enable_multiplayer_compatibility_check: false,
    },
    uiState: { showSettingsPanel: false },
    overrides: {
      refreshData: async () => assert.fail('联机兼容单项保存不需要整套 refreshData'),
      requestModScan: async () => assert.fail('联机兼容单项保存不需要扫描磁盘'),
      refreshModCoreData: async () => assert.fail('联机兼容单项保存不需要重拉核心列表'),
      refreshModEnrichment: async (...args) => { enrichments.push(args) },
    },
  })

  await actions.saveSetting('enable_multiplayer_compatibility_check', true)

  assert.equal(enrichments.length, 1)
  assert.equal(enrichments[0][0].silent, true)
}

async function testResetClearsScanResultData() {
  resetStores()
  const modStore = useModStore()
  modStore.conflictList = [{ package_id: 'a' }]
  modStore.coexistenceList = [{ package_id: 'b' }]
  modStore.strictDisableRestoreFailures = { hash: { path_hash: 'hash' } }

  modStore.reset()

  assert.deepEqual(modStore.conflictList, [])
  assert.deepEqual(modStore.coexistenceList, [])
  assert.deepEqual(modStore.strictDisableRestoreFailures, {})
}

async function testRuleLoadingIsSharedBeforeEditorReadsSources() {
  let resolveRules
  let requestCount = 0
  resetStores({
    rules_get_all: () => {
      requestCount += 1
      return new Promise(resolve => { resolveRules = resolve })
    },
  })

  const ruleStore = useRuleStore()
  const firstLoad = ruleStore.ensureRulesLoaded()
  const secondLoad = ruleStore.ensureRulesLoaded()

  await Promise.resolve()
  assert.equal(requestCount, 1)

  resolveRules(ok({
    community_rules: { 'demo.mod': { loadAfter: {} } },
    community_rules_update_time: 1,
    workshop_rules: { 'demo.mod': { dependencies: {} } },
    workshop_rules_update_time: 2,
    user_mod_rules: { 'demo.mod': { loadBefore: {} } },
    user_dynamic_rules: [{ rule_id: 'dynamic-1' }],
    settings: { user_mod_rules_enabled: true },
  }))

  assert.equal(await firstLoad, true)
  assert.equal(await secondLoad, true)
  assert.deepEqual(ruleStore.communityModRules, { 'demo.mod': { loadAfter: {} } })
  assert.deepEqual(ruleStore.workshopModRules, { 'demo.mod': { dependencies: {} } })
  assert.deepEqual(ruleStore.userModRules, { 'demo.mod': { loadBefore: {} } })
  assert.deepEqual(ruleStore.userDynamicRules, [{ rule_id: 'dynamic-1' }])
}

async function testRuleEditorRuleOperationsHandleMissingState() {
  resetStores()
  const ruleStore = useRuleStore()
  ruleStore.userModRules = { 'demo.mod': {} }

  await ruleStore.removeUserModRuleItem('demo.mod', 'loadAfter', 'missing.mod')
  await ruleStore.updateComment('demo.mod', 'loadAfter', 'missing.mod', 'ignored')

  assert.deepEqual(ruleStore.getAbsolutePosition(), { pos: 'none', source: null })
}

async function testWorkshopRuleUpdateResetsBusyStateOnFailure() {
  resetStores()
  const appStore = useAppStore()
  appStore.updateExternalDB = async () => { throw new Error('update failed') }
  const ruleStore = useRuleStore()

  await assert.rejects(() => ruleStore.updateWorkshop(), /update failed/)
  assert.equal(ruleStore.isLoading, false)
}

async function testFailedUserRuleDeleteWaitsForStateRollback() {
  let resolveRefresh
  resetStores({
    rule_update_user_mod: async () => ({ status: 'error', message: 'save failed' }),
    rules_get_all: () => new Promise(resolve => { resolveRefresh = resolve }),
  })
  const ruleStore = useRuleStore()
  ruleStore.userModRules = {
    'demo.mod': {
      loadAfter: { 'other.mod': { comment: [] } },
      loadBefore: { 'keep.mod': { comment: [] } },
    },
  }

  let settled = false
  const removePromise = ruleStore.removeUserModRuleItem('demo.mod', 'loadAfter', 'other.mod').then(() => { settled = true })
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(settled, false)
  assert.equal(typeof resolveRefresh, 'function')
  resolveRefresh(ok({
    user_mod_rules: {
      'demo.mod': {
        loadAfter: { 'other.mod': { comment: [] } },
        loadBefore: { 'keep.mod': { comment: [] } },
      },
    },
  }))
  await removePromise

  assert.deepEqual(ruleStore.userModRules, {
    'demo.mod': {
      loadAfter: { 'other.mod': { comment: [] } },
      loadBefore: { 'keep.mod': { comment: [] } },
    },
  })
}

async function testUpdateUserDataRuleInputsRefreshRuleState() {
  resetStores({
    mod_user_data_update: async () => ok(),
  })
  const appStore = useAppStore()
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const modStore = useModStore()
  modStore.setMods({
    all_mods: [{ package_id: 'demo.mod', name: 'Demo', path: 'D:/Mods/Demo', tags: [] }],
    active_load_order: [],
    inactive_load_order: [],
    temp_load_order: [],
    interlocks: {},
  })

  await modStore.updateModUserData('demo.mod', { tags: ['demo'], alias_name: 'Demo Alias', notes: 'memo' })
  await modStore.updateModUserData('demo.mod', { sign_color: '#ffffff' })

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
  assert.equal(coreRefreshes[0][1].refreshRules, false)
}

async function testBatchUpdateUserDataRuleInputsRefreshRuleState() {
  resetStores({
    mods_user_data_update: async () => ok(),
  })
  const appStore = useAppStore()
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const modStore = useModStore()
  modStore.setMods({
    all_mods: [{ package_id: 'demo.mod', name: 'Demo', path: 'D:/Mods/Demo', tags: [] }],
    active_load_order: [],
    inactive_load_order: [],
    temp_load_order: [],
    interlocks: {},
  })

  await modStore.batchUpdateModsUserData([{ mod_id: 'demo.mod', alias_name: 'Demo Alias', notes: 'memo' }])

  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, true)
}

async function testModMetadataChangesRefreshRuleInputs() {
  resetStores({
    mods_user_mod_type_update: async () => ok(),
    mods_add_tags: async () => ok(),
    mods_remove_tags: async () => ok(),
  })
  const appStore = useAppStore()
  appStore.settings.ui = {}
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const modStore = useModStore()
  modStore.setMods({
    all_mods: [{ package_id: 'demo.mod', name: 'Demo', path: 'D:/Mods/Demo', tags: [] }],
    active_load_order: [],
    inactive_load_order: [],
    temp_load_order: [],
    interlocks: {},
  })

  await modStore.setModsType(['demo.mod'], 'Texture')
  await modStore.addModsTags(['demo.mod'], ['demo'])
  await modStore.removeModsTags(['demo.mod'], ['demo'])

  assert.equal(coreRefreshes.length, 3)
  assert.ok(coreRefreshes.every(([, options]) => options.preserveListState === true))
  assert.ok(coreRefreshes.every(([, options]) => options.refreshBackups === false))
}

async function testGroupChangesRefreshRuleInputs() {
  resetStores({
    group_add_mods: async () => ok(),
    group_remove_mods: async () => ok(),
    group_update: async () => ok(),
    group_delete: async () => ok(),
  })
  const appStore = useAppStore()
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const groupStore = useGroupStore()
  groupStore.groupList = [{ group_id: 'g', name: 'Old', color: '#fff', mod_ids: [] }]

  await groupStore.groupAddMods('g', ['demo.mod'])
  await groupStore.groupRemoveMods('g', ['demo.mod'])
  await groupStore.updateGroup('g', { name: 'New' })
  await groupStore.deleteGroup('g')

  assert.equal(coreRefreshes.length, 4)
  assert.ok(coreRefreshes.every(([, options]) => options.preserveListState === true))
  assert.ok(coreRefreshes.every(([, options]) => options.refreshWorkspaceLibraries === false))
}

async function testCurrentProfilePathUpdateScansAfterRefresh() {
  resetStores({
    profile_update: async () => ok({ refresh_mode: 'rebootstrap' }),
  })
  const appStore = useAppStore()
  appStore.settings.enable_auto_scan = true
  const calls = []
  appStore.refreshData = async () => { calls.push(['refreshData']) }
  appStore.requestModScan = async (options) => { calls.push(['requestModScan', options || {}]) }

  const profileStore = useProfileStore()
  profileStore.currentProfileId = 'default'
  await profileStore.updateProfile('default', { game_install_path: 'G:/NewRimWorld' })

  assert.deepEqual(calls, [
    ['refreshData'],
    ['requestModScan', { forceCoreRefresh: true }],
  ])
}

async function testCurrentProfileSourceUpdateRefreshesCoreOnly() {
  resetStores({
    profile_update: async () => ok({
      refresh_mode: 'light',
      active_context: context({ use_self_mods: true }),
    }),
  })
  const appStore = useAppStore()
  appStore.settings.enable_auto_scan = true
  appStore.refreshData = async () => assert.fail('环境模组来源开关变化不需要整套 refreshData')
  appStore.requestModScan = async () => assert.fail('环境模组来源开关变化不需要扫描磁盘')
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const profileStore = useProfileStore()
  profileStore.currentProfileId = 'default'
  profileStore.activeContext = context({ use_self_mods: false })
  await profileStore.updateProfile('default', { use_self_mods: true })

  assert.equal(profileStore.activeContext.use_self_mods, true)
  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, false)
}

async function testCurrentProfileSteamLaunchPreferenceRefreshesCoreOnly() {
  resetStores({
    profile_update: async () => ok({
      refresh_mode: 'light',
      active_context: context({ prefer_steam_launch: true }),
    }),
  })
  const appStore = useAppStore()
  appStore.settings.enable_auto_scan = true
  appStore.refreshData = async () => assert.fail('Steam 启动偏好变化不需要整套 refreshData')
  appStore.requestModScan = async () => assert.fail('Steam 启动偏好变化不需要扫描磁盘')
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }

  const profileStore = useProfileStore()
  profileStore.currentProfileId = 'default'
  profileStore.activeContext = context({ prefer_steam_launch: false })
  await profileStore.updateProfile('default', { prefer_steam_launch: true })

  assert.equal(profileStore.activeContext.prefer_steam_launch, true)
  assert.equal(coreRefreshes.length, 1)
  assert.equal(coreRefreshes[0][1].preserveListState, false)
}

async function testCurrentProfileUnchangedSourceFieldsDoNotRefreshCore() {
  resetStores({
    profile_update: async () => ok({
      refresh_mode: 'light',
      active_context: context({ use_workshop_mods: true, use_self_mods: false, prefer_steam_launch: true }),
    }),
  })
  const appStore = useAppStore()
  appStore.refreshData = async () => assert.fail('环境来源字段实际未变化不需要整套 refreshData')
  appStore.requestModScan = async () => assert.fail('环境来源字段实际未变化不需要扫描磁盘')
  appStore.refreshModCoreData = async () => assert.fail('环境来源字段实际未变化不需要刷新模组数据')

  const profileStore = useProfileStore()
  profileStore.currentProfileId = 'default'
  profileStore.activeContext = context({ use_workshop_mods: true, use_self_mods: false, prefer_steam_launch: true })
  await profileStore.updateProfile('default', {
    name: 'Default',
    use_workshop_mods: true,
    use_self_mods: false,
    prefer_steam_launch: true,
  })
}

async function testRefreshModCoreDataSyncsActiveContext() {
  resetStores({
    get_mod_list_core: async () => ok({
      groups: [],
      all_mods: [],
      active_load_order: [],
      inactive_load_order: [],
      temp_load_order: [],
      interlocks: {},
      active_context: context({ profile_id: 'profile-b', user_data_path: 'U:/ProfileB' }),
    }),
  })
  const profileStore = useProfileStore()
  profileStore.currentProfileId = 'profile-a'
  profileStore.activeContext = context({ profile_id: 'profile-a', user_data_path: 'U:/ProfileA' })

  const appStore = useAppStore()
  const refreshed = await appStore.refreshModCoreData('测试同步环境上下文', {
    refreshRelated: false,
    refreshEnrichment: false,
  })

  assert.equal(refreshed, true)
  assert.equal(profileStore.currentProfileId, 'profile-b')
  assert.equal(profileStore.activeContext.user_data_path, 'U:/ProfileB')
}

async function testModInventoryTasksScanAndReplaceListState() {
  const scanStarts = []
  resetStores({
    get_startup_bootstrap: async () => ok({
      settings: { enable_auto_scan: false, show_coexistence_message: false, ui: {} },
      active_context: context({ is_healthy: false }),
      user_themes: [],
      remote_image_cache: {},
      upgrade_context: {},
    }),
    get_mod_list_core: async () => ok({
      groups: [],
      all_mods: [],
      active_load_order: [],
      inactive_load_order: [],
      temp_load_order: [],
      interlocks: {},
    }),
    monitor_frontend_ready: async () => ok(),
    scan_mods: async (...args) => {
      scanStarts.push(args)
      return ok({ details: { task_id: `scan-${scanStarts.length}`, status: 'started' } })
    },
  })
  const appStore = useAppStore()
  appStore.settings.show_coexistence_message = false
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }
  await appStore.initialize()

  await window.dispatchEvent({ type: 'global-progress', detail: { id: 'steamcmd-1', type: 'steamcmd-download', status: 'success', progress: 100, metrics: {} } })
  assert.equal(scanStarts.length, 1)
  await window.dispatchEvent({ type: 'scan-complete', detail: { task_id: 'scan-1', status: 'success', stats: { added: 1 }, core_refresh_required: true } })
  assert.equal(coreRefreshes[0][1].preserveListState, false)

  await window.dispatchEvent({ type: 'global-progress', detail: { id: 'steam-download-1', type: 'steam-workshop-download', status: 'success', progress: 100, metrics: {} } })
  assert.equal(scanStarts.length, 2)
  await window.dispatchEvent({ type: 'scan-complete', detail: { task_id: 'scan-2', status: 'success', stats: { added: 1 }, core_refresh_required: true } })
  assert.equal(coreRefreshes[1][1].preserveListState, false)

  await window.dispatchEvent({ type: 'global-progress', detail: { id: 'steam-unsub-1', type: 'steam-unsubscribe', status: 'success', progress: 100, metrics: {} } })
  assert.equal(scanStarts.length, 3)
}

async function testQueuedReplaceScanOverridesPreserveScan() {
  const scanStarts = []
  resetStores({
    get_startup_bootstrap: async () => ok({
      settings: { enable_auto_scan: false, show_coexistence_message: false, ui: {} },
      active_context: context({ is_healthy: false }),
      user_themes: [],
      remote_image_cache: {},
      upgrade_context: {},
    }),
    get_mod_list_core: async () => ok({
      groups: [],
      all_mods: [],
      active_load_order: [],
      inactive_load_order: [],
      temp_load_order: [],
      interlocks: {},
    }),
    monitor_frontend_ready: async () => ok(),
    scan_mods: async (...args) => {
      scanStarts.push(args)
      return ok({ details: { task_id: `queued-scan-${scanStarts.length}`, status: 'started' } })
    },
  })
  const appStore = useAppStore()
  appStore.settings.show_coexistence_message = false
  const coreRefreshes = []
  appStore.refreshModCoreData = async (...args) => { coreRefreshes.push(args) }
  await appStore.initialize()

  const taskStore = useTaskStore()
  taskStore.createPlaceholderTask({ id: 'active-scan', type: 'scan', status: 'running' })
  assert.equal(await appStore.requestModScan({ preserveListState: true }), false)
  await window.dispatchEvent({ type: 'global-progress', detail: { id: 'steamcmd-queued', type: 'steamcmd-download', status: 'success', progress: 100, metrics: {} } })
  assert.equal(scanStarts.length, 0)

  await window.dispatchEvent({ type: 'scan-complete', detail: { task_id: 'active-scan', status: 'success', stats: {}, core_refresh_required: false } })
  await new Promise(resolve => setTimeout(resolve, 5))
  assert.equal(scanStarts.length, 1)
  await window.dispatchEvent({ type: 'scan-complete', detail: { task_id: 'queued-scan-1', status: 'success', stats: { added: 1 }, core_refresh_required: true } })
  assert.equal(coreRefreshes[0][1].preserveListState, false)
}

async function testScanTaskDoesNotGuessFailureFromElapsedTime() {
  resetStores()
  const taskStore = useTaskStore()
  taskStore.upsertTask({
    id: 'scan-timeout',
    type: 'scan',
    status: 'running',
    progress: 1,
    message: 'preparing',
    metrics: { stage: 'prepare_cleanup', active_timeout_ms: 5 },
    timestamp: Date.now(),
  })

  await new Promise(resolve => setTimeout(resolve, 20))

  const task = taskStore.getTask('scan-timeout')
  assert.equal(task.status, 'running')
  assert.equal(task.progress, 1)
}

for (const test of [
  testSettingsSourceChangeForcesCoreRefresh,
  testIssueSettingsRefreshModData,
  testWideLanguagePackDetectionRefreshesCore,
  testRuleLoadingIsSharedBeforeEditorReadsSources,
  testRuleEditorRuleOperationsHandleMissingState,
  testWorkshopRuleUpdateResetsBusyStateOnFailure,
  testFailedUserRuleDeleteWaitsForStateRollback,
  testMultiplayerCompatibilitySettingRefreshesEnrichmentOnly,
  testToolModsSettingForcesCoreRefreshScan,
  testSteamLaunchPreferenceForcesCoreRefreshScan,
  testRuleSourcePathChangeRefreshesRules,
  testExternalDataPathChangeRefreshesModData,
  testSaveSettingToolModsForcesCoreRefreshScan,
  testSaveSettingResetActiveListOnlyUpdatesSetting,
  testSaveSettingLanguageSupportDoesNotRefreshModData,
  testSaveSettingWideLanguagePackDetectionRefreshesCore,
  testSaveSettingIssueEnrichmentSettingRefreshesEnrichment,
  testResetClearsScanResultData,
  testUpdateUserDataRuleInputsRefreshRuleState,
  testBatchUpdateUserDataRuleInputsRefreshRuleState,
  testModMetadataChangesRefreshRuleInputs,
  testGroupChangesRefreshRuleInputs,
  testCurrentProfilePathUpdateScansAfterRefresh,
  testCurrentProfileSourceUpdateRefreshesCoreOnly,
  testCurrentProfileSteamLaunchPreferenceRefreshesCoreOnly,
  testCurrentProfileUnchangedSourceFieldsDoNotRefreshCore,
  testRefreshModCoreDataSyncsActiveContext,
  testModInventoryTasksScanAndReplaceListState,
  testQueuedReplaceScanOverridesPreserveScan,
  testScanTaskDoesNotGuessFailureFromElapsedTime,
]) {
  await test()
}

print('refreshActions.test.mjs passed')
