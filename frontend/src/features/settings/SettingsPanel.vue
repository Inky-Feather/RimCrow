<template>
  <CommonModalShell :show="appStore.uiState.showSettingsPanel" persistent
    :show-header="false" :close-on-backdrop="false" size="default" :z-index="100"
    accent="primary"
    panel-class="border-border-base/18" content-class="h-full flex"
    @backdrop="shakeComponent('#btn-cancel')"
    @close="shakeComponent('#btn-cancel')"
  >
        
        <!-- A. 装饰光效 -->
        <div class="absolute -top-24 -left-24 w-64 h-64 bg-accent-primary/10 blur-3xl rounded-full pointer-events-none"></div>
        <div class="absolute -bottom-24 -right-24 w-64 h-64 bg-accent-special/10 blur-3xl rounded-full pointer-events-none"></div>

        <!-- B. 左侧导航栏 -->
        <aside class="w-52 shrink-0 border-r bg-bg-muted border-border-base/5 flex flex-col p-6 relative z-10">
          <div class="mb-10 px-2">
            <h2 class="text-xl font-black text-text-main tracking-tighter italic">{{ t('ui.settings.panel.system', '系统') }} <span class="text-accent-primary">{{ t('ui.settings.panel.settings', '设置') }}</span></h2>
          </div>

          <!-- 动态 Glider 导航 -->
          <nav class="flex flex-col relative gap-1" :style="{ '--total-tabs': tabs.length }">
            <button v-for="(tab, index) in tabs" :key="tab.id" :data-tour="`settings-tab-${tab.id}`"
              class="settings-nav-item relative z-10 flex h-11 min-w-0 items-center gap-3 px-2 text-left font-bold transition-all duration-300 group"
              :class="currentTab === tab.id ? 'text-accent-primary' : 'text-text-dim hover:text-text-dim'"
              @click="changeTab(tab.id)" >
              <component :is="tab.icon" class="size-4 shrink-0" />
              <span class="settings-nav-label min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{{ tab.label }}</span>
            </button>

            <!-- 物理 Glider 滑块 -->
            <div class="glider-container absolute left-0 top-0 w-full h-full pointer-events-none">
              <div class="glider absolute -left-6 w-1 h-11 bg-accent-primary brightness-120 shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.75)] transition-transform duration-500 cubic-bezier"
                :style="{ transform: `translateY(${currentTabIndex * 3}rem)` }">
                <!-- 侧边发光层 -->
                <div class="absolute left-0 top-0 w-40 h-full bg-linear-to-r from-accent-primary/10 to-transparent"></div>
              </div>
            </div>
          </nav>

          <!-- 底部版本号 -->
          <div class="mt-auto px-4 py-2 border-t border-border-base/5 opacity-30">
            <p class="text-xs font-mono text-text-dim">V{{ appStore.appVersion || t('common.status.unknown_version', '版本未知') }}</p>
          </div>
        </aside>

        <!-- C. 右侧主内容区 -->
        <main class="flex-1 flex flex-col min-w-0 bg-bg-deep relative z-10">
          <!-- 顶部状态条 -->
          <header class="h-14 flex items-center justify-between px-8 border-b border-border-base/5">
            <span class="text-xs font-mono text-text-disabled uppercase tracking-[0.3em]">
              / root / {{ currentTabLabel }}
            </span>
            <div class="flex gap-1.5 text-text-disabled relative">
              <Settings class="absolute size-23 -top-16 -right-13" />
            </div>
          </header>

          <!-- 内容滚动容器 -->
          <div class="flex-1 overflow-y-auto p-8 custom-scrollbar">
            <div class=" mx-auto space-y-10">

              <SettingsPathsTab
                v-if="currentTab === 'paths'"
                :form-data="formData"
                :validate-steam-launch-enable="validateSteamLaunchEnable"
                :validate-workshop-mods-enable="validateWorkshopModsEnable"
                :auto-detect="autoDetect"
                :handle-browse="handleBrowse"
                :check-path="checkPath"
              />
              <SettingsGeneralTab v-if="currentTab === 'general'" :form-data="formData" />
              <SettingsFeaturesTab v-if="currentTab === 'features'" :form-data="formData" />
              <SettingsExternalTab
                v-if="currentTab === 'community'"
                :form-data="formData"
                :handle-browse="handleBrowse"
                :check-path="checkPath"
              />
              <SettingsNetworkTab
                v-if="currentTab === 'network'"
                :form-data="formData"
                :reveal-secret="appStore.revealSecret"
                :is-secret-preserved="isSecretPreserved"
                @preserve-secret="preserveFormSecret"
                @clear-secret="clearFormSecret"
              />
              <SettingsAiTab
                v-if="currentTab === 'ai'"
                :form-data="formData"
                :reveal-secret="appStore.revealSecret"
                :is-secret-preserved="isSecretPreserved"
                @preserve-secret="preserveFormSecret"
                @clear-secret="clearFormSecret"
              />
              <SettingsKeybindingsTab v-if="currentTab === 'keybindings'" :form-data="formData" />
              <SettingsDevTab v-if="currentTab === 'dev'" :form-data="formData" />
              <SettingsAboutTab v-if="currentTab === 'about'" :form-data="formData" />

            </div>
          </div>

          <!-- D. 底部操作栏 -->
          <footer class="modal-footer flex items-center justify-end gap-4 px-10 py-3">
            <button id="btn-cancel" :disabled="saving" :class="saving ? 'app-action-disabled' : ''" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">{{ t('ui.settings.panel.discard_changes', '放弃修改') }}</button>
            <button data-tour="settings-save-button" :disabled="saving" :class="saving ? 'app-action-disabled' : ''" @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-on-accent-primary font-black text-sm shadow-[0_0_20px_rgba(var(--rgb-accent-primary),0.3)] hover:scale-105 active:scale-95 transition-all group">
              <div class="absolute inset-0 bg-bg-overlay/10 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              {{ t('ui.settings.panel.apply_and_save', '应用并保存配置') }}
            </button>
          </footer>
        </main>

  </CommonModalShell>
</template>

<script setup>
import { ref, watch, h, computed } from 'vue'
import { FolderTree, AppWindow, Globe, Cpu, Terminal, Component, Settings, Keyboard, Info } from 'lucide-vue-next'
import { shakeComponent } from '../../shared/lib/domEffects'
import { deepClone, toast } from '../../shared/lib/common'
import { createDefaultKeybindingConfig } from '../../shared/commands/keybindingConflicts'

// 导入 Common UI
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import SettingsPathsTab from './panel/SettingsPathsTab.vue'
import SettingsGeneralTab from './panel/SettingsGeneralTab.vue'
import SettingsFeaturesTab from './panel/SettingsFeaturesTab.vue'
import SettingsKeybindingsTab from './panel/SettingsKeybindingsTab.vue'
import SettingsExternalTab from './panel/SettingsExternalTab.vue'
import SettingsNetworkTab from './panel/SettingsNetworkTab.vue'
import SettingsAiTab from './panel/SettingsAiTab.vue'
import SettingsDevTab from './panel/SettingsDevTab.vue'
import SettingsAboutTab from './panel/SettingsAboutTab.vue'
import { DEFAULT_THEME_ID, applyTheme } from './theme/themeManager'
import { useAppStore } from '../../app/stores/appStore'
import { useProfileStore } from '../profiles/profileStore'
import { setLocale, t, translateMessagePayload } from '../../shared/i18n.js'

const appStore = useAppStore()
const profileStore = useProfileStore()

// 设置面板只编辑本地副本，保存时再交给 store 统一提交。
const currentTab = ref('paths')
const formData = ref({})
const saving = ref(false)

// lucide 没有 Steam 图标，这里保留内联图标给“外部依赖”页签使用。
const Steam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)

// 用 computed 生成页签，语言预览切换时标签能立即刷新。
const tabs = computed(() => [
  { id: 'paths', label: t('ui.settings.panel.tab.paths', '路径配置'), icon: FolderTree },
  { id: 'general', label: t('ui.settings.panel.tab.general', '界面设置'), icon: AppWindow },
  { id: 'features', label: t('ui.settings.features.title', '功能设置'), icon: Component },
  { id: 'keybindings', label: t('ui.settings.panel.tab.keybindings', '快捷键'), icon: Keyboard },
  { id: 'community', label: t('ui.settings.external.title', '外部依赖'), icon: Steam },
  { id: 'network', label: t('ui.settings.panel.tab.network', '网络连接'), icon: Globe },
  { id: 'ai', label: t('ui.settings.panel.tab.ai', 'AI 集成'), icon: Cpu },
  { id: 'dev', label: t('ui.settings.panel.tab.dev', '开发调试'), icon: Terminal },
  { id: 'about', label: t('ui.settings.about.title', '关于项目'), icon: Info },
])
// 密钥字段统一登记；未修改的已保存密钥不提交，显式清除通过空值提交。
const SECRET_FIELD_PATHS = {
  'ai.api_key': 'ai.api_key',
  'steam.web_api_key': 'steam_web_api_key',
  'network.proxy.username': 'network.proxy.username',
  'network.proxy.password': 'network.proxy.password',
}
const PROFILE_SETTING_KEYS = new Set([
  'name', 'description', 'game_install_path', 'user_data_path', 'prefer_steam_launch',
  'use_workshop_mods', 'use_self_mods', 'run_commands', 'inactive_mods_order',
  'temp_mods_order', 'last_played_time',
])
// 打开版本用于丢弃过期异步结果；保存快照用于跳过无改动提交。
let settingsPanelOpenVersion = 0
let settingsPanelLanguageSnapshot = ''
let settingsPanelSaveBaseline = {}
let settingsPathCheckCache = { key: '', result: null, checkedAt: 0 }
let isApplyingSettings = false
const PATH_CHECK_CACHE_MS = 30000
// 这些字段只影响当前面板展示，不参与“表单是否已修改”的判断。
const transientFormKeys = new Set([
  'check_info',
  '_secret_status',
  '_secret_storage_warning',
  '_secret_storage_warning_key',
  '_secret_storage_warning_params',
])

const currentTabLabel = computed(() => (
  tabs.value.find(item => item.id === currentTab.value)?.label || currentTab.value
))
const currentTabIndex = computed(() => Math.max(0, tabs.value.findIndex(item => item.id === currentTab.value)))

const normalizeLayoutList = (list, maps) => {
  const source = Array.isArray(list) ? list : []
  const normalized = []
  const usedIds = new Set()
  for (const item of source) {
    const id = String(item?.id || '').trim()
    if (!id || !maps?.[id] || usedIds.has(id)) continue
    normalized.push({ id, visible: item.visible !== false })
    usedIds.add(id)
  }
  Object.keys(maps || {}).forEach((id) => {
    if (!usedIds.has(id)) normalized.push({ id, visible: true })
  })
  return normalized
}

const mergeObject = (base, patch) => ({
  ...(base && typeof base === 'object' ? base : {}),
  ...(patch && typeof patch === 'object' ? patch : {}),
})

// 后端全局设置与当前环境共同组成表单；环境字段优先展示当前 Profile 的运行值。
const buildSettingsFormData = () => {
  const settings = deepClone(appStore.settings || {})
  const context = deepClone(profileStore.activeContext || {})
  const target = { ...settings, ...context }

  target.ui = mergeObject(settings.ui, target.ui)
  target.ui.main_layout = normalizeLayoutList(target.ui.main_layout, appStore.MAIN_LAYOUT_MAPS)
  target.ui.mod_details_layout = normalizeLayoutList(target.ui.mod_details_layout, appStore.DETAILS_LAYOUT_MAPS)
  if (!Array.isArray(target.ui.hidden_dependency_graph_source_ids)) target.ui.hidden_dependency_graph_source_ids = []
  if (!target.ui.keybindings || typeof target.ui.keybindings !== 'object') {
    target.ui.keybindings = createDefaultKeybindingConfig()
  }
  target.network = mergeObject(settings.network, target.network)
  target.network.proxy = mergeObject(settings.network?.proxy, target.network.proxy)
  if (!Array.isArray(target.network.proxy.bypass_list)) target.network.proxy.bypass_list = []
  if (!target.network.hosts || typeof target.network.hosts !== 'object') target.network.hosts = {}
  target.ai = mergeObject(settings.ai, target.ai)
  target.texture_opt = mergeObject(settings.texture_opt, target.texture_opt)
  if (target.skip_language_pack_alias_generation === undefined) target.skip_language_pack_alias_generation = true
  target.translation = appStore.normalizeTranslationSettings(target.translation)
  return target
}

// 保存快照要稳定排序并剔除瞬态字段，避免未改动时误触发保存。
const toComparableSettingsValue = (value) => {
  if (Array.isArray(value)) return value.map(toComparableSettingsValue)
  if (value && typeof value === 'object') {
    const result = {}
    Object.keys(value).sort().forEach((key) => {
      if (transientFormKeys.has(key)) return
      result[key] = toComparableSettingsValue(value[key])
    })
    return result
  }
  return value
}

const buildSettingsSaveSnapshot = (target) => JSON.stringify(toComparableSettingsValue(target || {}))

const hasSettingsFormChanged = () => (
  buildSettingsSaveSnapshot(comparableSettingsForSave(formData.value))
  !== buildSettingsSaveSnapshot(comparableSettingsForSave(settingsPanelSaveBaseline))
)

const getTopLevelKeyFromPath = (pathKey) => String(pathKey || '').split('.').filter(Boolean)[0] || ''

const getNestedField = (target, pathKey) => {
  return String(pathKey || '').split('.').filter(Boolean)
    .reduce((current, key) => current?.[key], target)
}

const deleteNestedField = (target, pathKey) => {
  const segments = String(pathKey || '').split('.').filter(Boolean)
  if (!segments.length) return
  let current = target
  for (let index = 0; index < segments.length - 1; index += 1) {
    if (!current || typeof current !== 'object') return
    current = current[segments[index]]
  }
  if (current && typeof current === 'object') delete current[segments[segments.length - 1]]
}

const comparableSettingsForSave = (target) => {
  const result = toComparableSettingsValue(target || {})
  const preservedKeys = new Set(Array.isArray(target?._preserve_secret_keys) ? target._preserve_secret_keys : [])
  Object.entries(SECRET_FIELD_PATHS).forEach(([secretKey, pathKey]) => {
    if (!preservedKeys.has(secretKey)) return
    const topLevelKey = getTopLevelKeyFromPath(pathKey)
    if (topLevelKey && Object.prototype.hasOwnProperty.call(result, topLevelKey)) {
      deleteNestedField(result, pathKey)
    }
  })
  return result
}

const buildSettingsSavePayload = () => {
  const before = comparableSettingsForSave(settingsPanelSaveBaseline)
  const after = comparableSettingsForSave(formData.value)
  const payload = {}
  const allKeys = new Set([...Object.keys(before), ...Object.keys(after)])
  allKeys.forEach((key) => {
    if (transientFormKeys.has(key)) return
    const beforeValue = before[key]
    const afterValue = after[key]
    if (JSON.stringify(beforeValue) === JSON.stringify(afterValue)) return
    if (key === '_preserve_secret_keys') return
    if (Object.prototype.hasOwnProperty.call(formData.value || {}, key)) {
      payload[key] = deepClone(formData.value[key])
    }
  })

  const beforePreserved = new Set(settingsPanelSaveBaseline?._preserve_secret_keys || [])
  const afterPreserved = new Set(formData.value?._preserve_secret_keys || [])
  const clearedKeys = new Set(Array.isArray(formData.value?._clear_secret_keys) ? formData.value._clear_secret_keys : [])
  Object.entries(SECRET_FIELD_PATHS).forEach(([secretKey, pathKey]) => {
    const preserveChanged = beforePreserved.has(secretKey) !== afterPreserved.has(secretKey)
    if (!preserveChanged) return
    const topLevelKey = getTopLevelKeyFromPath(pathKey)
    if (topLevelKey && Object.prototype.hasOwnProperty.call(formData.value || {}, topLevelKey)) {
      payload[topLevelKey] = deepClone(formData.value[topLevelKey])
    }
  })

  // 已保存密钥仍处于保留状态时，从提交内容中移除字段；明确清除或重新输入则保留字段。
  Object.entries(SECRET_FIELD_PATHS).forEach(([secretKey, pathKey]) => {
    const currentValue = String(getNestedField(formData.value, pathKey) || '')
    const shouldOmit = !clearedKeys.has(secretKey) && (
      afterPreserved.has(secretKey)
      || (!beforePreserved.has(secretKey) && !currentValue.trim())
    )
    if (!shouldOmit) return
    const topLevelKey = getTopLevelKeyFromPath(pathKey)
    if (topLevelKey && Object.prototype.hasOwnProperty.call(payload, topLevelKey)) {
      deleteNestedField(payload, pathKey)
    }
  })
  const changedKeys = Object.keys(payload).filter(key => !key.startsWith('_'))
  if (changedKeys.length) {
    payload._changed_keys = changedKeys
    if (changedKeys.some(key => PROFILE_SETTING_KEYS.has(key))) {
      const profileId = String(profileStore.activeContext?.profile_id || '').trim()
      if (profileId) payload._profile_id = profileId
    }
  }
  return payload
}

// Steam 启动和创意工坊加载互斥，避免同一环境同时走两套 Mod 来源。
watch(() => !!formData.value?.prefer_steam_launch, (enabled) => {
  if (enabled && formData.value) {
    formData.value.use_workshop_mods = false
  }
})

// 监听当前页面切换
const changeTab = (tab) => {
  currentTab.value = tab
}

const getSteamLaunchProblem = (installCheck, steamCheck) => {
  if (!installCheck?.pass) return t('toast.settings.panel.steam_launch_game_path_problem', '游戏安装目录可能无法用于 Steam 启动：{message}', { message: installCheck?.msg || t('toast.settings.panel.select_game_install_path', '请重新选择游戏安装目录') })
  if (!steamCheck?.pass) return t('toast.settings.panel.steam_launch_steam_path_problem', 'Steam 程序路径可能无法使用：{message}', { message: steamCheck?.msg || t('toast.settings.panel.select_steam_path', '请重新选择 Steam.exe 所在目录') })
  return ''
}

// 只提示 Steam 启动风险，不强行回滚开关，最终保存仍尊重用户选择。
const validateSteamLaunchEnable = async () => {
  const installPath = String(formData.value?.game_install_path || '').trim()
  const steamPath = String(formData.value?.steam_path || '').trim()
  if (!installPath) {
    toast.warning(t('toast.settings.panel.game_install_path_missing', '未填写游戏安装目录，Steam 启动可能无法使用'))
    return false
  }
  if (!steamPath) {
    toast.warning(t('toast.settings.panel.steam_path_missing', '未填写 Steam 程序路径，Steam 启动可能无法使用'))
    return false
  }
  const installCheck = await checkPath('game_install_path', installPath, { force: true })
  const steamCheck = await checkPath('steam_path', steamPath)
  const problem = getSteamLaunchProblem(installCheck, steamCheck)
  if (problem) {
    toast.warning(t('toast.settings.panel.path_problem_switch_kept', '{problem}\n此开关会按你的选择保留，启动失败时请回到这里修正路径。', { problem }))
    return false
  }
  if (!installCheck?.data?.is_steam) {
    toast.warning(t('toast.settings.panel.steam_version_unknown', '未能确认当前游戏本体是否为 Steam 版，仍会优先尝试通过 Steam 启动；如果启动失败，可改为直接启动。'))
  }
  return true
}

// 工坊目录允许“不完整但可继续”的警告；真正不可用才返回失败。
const validateWorkshopModsEnable = async () => {
  const workshopPath = String(formData.value?.workshop_mods_path || '').trim()
  if (!workshopPath) {
    toast.warning(t('toast.settings.panel.workshop_path_missing', '未填写创意工坊目录，工坊 Mod 可能无法加载'))
    return false
  }
  const workshopCheck = await checkPath('workshop_mods_path', workshopPath)
  if (workshopCheck?.pass && workshopCheck?.type === 'warn') {
    toast.warning(workshopCheck.msg || t('toast.settings.panel.workshop_path_incomplete', '创意工坊目录当前还不完整，保存后可能需要等 Steam 下载完成。'))
  }
  if (!workshopCheck?.pass) {
    toast.warning(t('toast.settings.panel.workshop_path_problem', '创意工坊目录可能无法使用：{message}\n此开关会按你的选择保留，加载失败时请回到这里修正路径。', { message: workshopCheck?.msg || t('toast.settings.panel.select_workshop_path', '请重新选择创意工坊目录') }))
    return false
  }
  return true
}

// 保存前只检查已启用的启动相关选项，避免未使用路径拖慢普通保存。
const validateEnabledLaunchOptions = async () => {
  let valid = true
  if (formData.value?.prefer_steam_launch) {
    valid = (await validateSteamLaunchEnable()) && valid
  }
  if (formData.value?.use_workshop_mods) {
    valid = (await validateWorkshopModsEnable()) && valid
  }
  return valid
}

// 自动检测路径；后台补全只填空字段，避免覆盖当前环境已保存的隔离目录。
const autoDetect = async (checkAfterDetect = true, overwrite = true) => {
  const paths = await appStore.autoDetectPaths(false)
  if (!paths) return false
  const currentProfileId = String(profileStore.activeContext?.profile_id || appStore.settings.current_profile_id || 'default')
  const isDefaultProfile = currentProfileId === 'default'
  Object.entries(paths).forEach(([key, value]) => {
    const currentValue = String(formData.value?.[key] || '').trim()
    if (!isDefaultProfile && key === 'user_data_path') return
    if (!isDefaultProfile && key === 'game_install_path' && currentValue) return
    if (!overwrite && currentValue) return
    formData.value[key] = value
  })
  if (checkAfterDetect) await checkPaths()
  return true
}

// 检查单个路径，并把结果写回 check_info 供对应页签展示。
const checkPath = async (type, path, options = {}) => {
  console.debug('检查单项路径:', type, path)
  if (!formData.value['check_info']) {
    formData.value['check_info'] = {};
  }
  if (!String(path || '').trim()) {
    const result = {
      pass: false,
      type: 'warn',
      msg: t('ui.settings.panel.path_empty', '未填写路径'),
    }
    formData.value['check_info'][type] = result
    return result
  }
  const res = await appStore.checkPath(type, path, options)
  formData.value['check_info'][type] = res
  if (res?.pass && res?.data && type === 'ripgrep_path') {
    formData.value.ripgrep_path = res.data
  }
  return res
}
// 检查全部路径；只收集后端认识的路径字段，避免把整份表单发给路径检查接口。
const checkPaths = async () => {
  const paths_data = {}
  for (const key in formData.value) {
    if (key.endsWith('_path')) {
      paths_data[key] = formData.value[key]
    }
  }
  const textureToolsPath = formData.value?.texture_opt?.texture_tools_path
  if (textureToolsPath !== undefined) {
    paths_data.texture_tools_path = textureToolsPath
  }
  const cacheKey = buildSettingsSaveSnapshot(paths_data)
  const now = Date.now()
  // 同一批路径短时间内复用结果，避免打开设置页时重复请求后端检测。
  if (settingsPathCheckCache.result && settingsPathCheckCache.key === cacheKey && now - settingsPathCheckCache.checkedAt < PATH_CHECK_CACHE_MS) {
    formData.value['check_info'] = deepClone(settingsPathCheckCache.result)
    return
  }
  // console.log('检查路径', paths_data)
  const res = await appStore.checkPaths(paths_data)
  if (res) {
    formData.value['check_info'] = res
    settingsPathCheckCache = { key: cacheKey, result: deepClone(res), checkedAt: Date.now() }
  }
}

// 点号路径用于统一处理嵌套设置项，例如 network.proxy.password。
const setNestedField = (target, pathKey, value) => {
  const segments = String(pathKey || '').split('.').filter(Boolean)
  if (!segments.length) return
  let current = target
  for (let index = 0; index < segments.length - 1; index += 1) {
    const key = segments[index]
    if (!current[key] || typeof current[key] !== 'object') {
      current[key] = {}
    }
    current = current[key]
  }
  current[segments[segments.length - 1]] = value
}

// 关闭面板时清掉运行时密钥值，避免下次打开看到旧输入。
const clearFormSecrets = (target) => {
  if (!target || typeof target !== 'object') return
  Object.values(SECRET_FIELD_PATHS).forEach(pathKey => setNestedField(target, pathKey, ''))
  delete target._preserve_secret_keys
  delete target._clear_secret_keys
}

const getPreserveSecretKeys = () => (
  Array.isArray(formData.value?._preserve_secret_keys) ? formData.value._preserve_secret_keys : []
)

// 保留列表只接受已登记的密钥，避免无关字段进入表单状态。
const setPreserveSecretKeys = (keys) => {
  const nextKeys = [...new Set(keys.filter(key => SECRET_FIELD_PATHS[key]))]
  if (nextKeys.length) {
    formData.value._preserve_secret_keys = nextKeys
  } else {
    delete formData.value._preserve_secret_keys
  }
}

const getClearSecretKeys = () => (
  Array.isArray(formData.value?._clear_secret_keys) ? formData.value._clear_secret_keys : []
)

const setClearSecretKeys = (keys) => {
  const nextKeys = [...new Set(keys.filter(key => SECRET_FIELD_PATHS[key]))]
  if (nextKeys.length) {
    formData.value._clear_secret_keys = nextKeys
  } else {
    delete formData.value._clear_secret_keys
  }
}

// 已有密钥默认保留；用户不重新输入时不会被空字符串清掉。
const markSavedSecretsPreserved = (target) => {
  const savedKeys = Object.keys(SECRET_FIELD_PATHS).filter(key => target?._secret_status?.[key]?.has_value)
  if (savedKeys.length) target._preserve_secret_keys = [...new Set([...(target._preserve_secret_keys || []), ...savedKeys])]
}

const isSecretPreserved = (secretKey) => getPreserveSecretKeys().includes(secretKey)

const preserveFormSecret = (secretKey) => {
  setClearSecretKeys(getClearSecretKeys().filter(key => key !== secretKey))
  setPreserveSecretKeys([...getPreserveSecretKeys(), secretKey])
}

const clearFormSecret = (secretKey) => {
  const pathKey = SECRET_FIELD_PATHS[secretKey]
  if (!pathKey) return
  setNestedField(formData.value, pathKey, '')
  setPreserveSecretKeys(getPreserveSecretKeys().filter(key => key !== secretKey))
  setClearSecretKeys([...getClearSecretKeys(), secretKey])
}

// 清除后重新输入新值时，自动取消待清除状态；读取已保存密钥仍由 preserve 事件维持保留状态。
Object.entries(SECRET_FIELD_PATHS).forEach(([secretKey, pathKey]) => {
  watch(() => getNestedField(formData.value, pathKey), (value) => {
    if (!String(value || '').trim()) return
    if (getClearSecretKeys().includes(secretKey)) {
      setClearSecretKeys(getClearSecretKeys().filter(key => key !== secretKey))
    }
  })
})

// 后端无法写入系统凭据库时，用较长 toast 提醒用户密钥已临时保留。
const showSecretStorageWarning = (target) => {
  if (!target?._secret_storage_warning) return
  toast.warning(translateMessagePayload({
    message: target._secret_storage_warning,
    message_key: target._secret_storage_warning_key,
    message_params: target._secret_storage_warning_params,
  }, t('toast.settings.secret_storage_warning', '部分密钥暂时无法写入本机安全存储，已临时保留在配置文件中。请检查系统凭据服务后重新保存密钥。')), { timeout: 9000 })
}

// 语言选择立即预览；取消设置时会恢复打开面板前的语言。
const previewLocale = (language) => setLocale(language).catch(error => {
  toast.error(error?.message || t('errors.i18n.user_locale_load_failed', '读取用户语言文件失败。请检查 data/locales 下的语言文件格式。'))
})

// 数据同步：打开时立即生成表单副本；路径检测只在后台补充 check_info，不阻塞设置页渲染。
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    const openVersion = ++settingsPanelOpenVersion
    formData.value = buildSettingsFormData()
    settingsPanelLanguageSnapshot = appStore.settings.language || 'zh-CN'
    markSavedSecretsPreserved(formData.value)
    showSecretStorageWarning(formData.value)
    settingsPanelSaveBaseline = deepClone(formData.value)
    void (async () => {
      if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      const autoDetected = !profileStore.activeContext || profileStore.activeContext.is_healthy === false
      if (autoDetected) {
        await autoDetect(false, false)
        if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      }
      // 路径检查可能较慢，放在表单渲染之后补齐状态，避免打开设置页卡顿。
      await checkPaths()
    })()
  } else {
    settingsPanelOpenVersion += 1
    if (!appStore.themeEditor.isOpen) applyTheme(appStore.currentTheme)
    if (!isApplyingSettings && settingsPanelLanguageSnapshot) void previewLocale(settingsPanelLanguageSnapshot)
    clearFormSecrets(formData.value)
    settingsPanelSaveBaseline = {}
    settingsPanelLanguageSnapshot = ''
  }
}, { immediate: true })

watch(() => formData.value?.language, (language) => {
  if (!appStore.uiState.showSettingsPanel || !language) return
  void previewLocale(language)
})

// 手动选择路径后只检查对应字段，避免一次浏览触发全量路径检测。
const handleBrowse = async (pathKey, fileTypes, checkTarget = undefined) => {
  console.debug('打开路径选择器:', pathKey, fileTypes)
  const currentValue = getNestedField(formData.value, pathKey) || ''
  let res
  if (fileTypes) {
    res = await appStore.getFilePath(currentValue, fileTypes)
  } else {
    res = await appStore.getFolderPath(currentValue)
  }
  if (res) {
    setNestedField(formData.value, pathKey, res)
    // 自动检查路径是否有效
    const finalCheckTarget = checkTarget === undefined ? pathKey : checkTarget
    if (typeof finalCheckTarget === 'string' && finalCheckTarget) {
      await checkPath(finalCheckTarget, res)
    }
  }
}

// 未改动时直接关闭；有改动时交给 store 做统一保存和运行态刷新。
const save = async () => {
  if (saving.value) return
  saving.value = true
  isApplyingSettings = true
  try {
    if (formData.value?.ui) {
      formData.value.ui.theme_id = appStore.settings.ui?.theme_id || DEFAULT_THEME_ID
    }
    if (!hasSettingsFormChanged()) {
      appStore.closeSettingsPanel()
      return
    }
    await validateEnabledLaunchOptions()
    // 校验拦截
    // const hasError = Object.values(formData.value.check_info || {}).some(info => info && !info.pass)
    // if (hasError) {
    //   toast.error("存在无效路径，请修正后再保存！")
    //   return
    // }
    await appStore.applySettings(buildSettingsSavePayload())
  } finally {
    isApplyingSettings = false
    saving.value = false
  }
}
</script>

<style scoped>
.cubic-bezier {
  transition-timing-function: cubic-bezier(0.37, 1.95, 0.66, 0.56);
}

.settings-nav-label {
  font-size: 0.82rem;
  line-height: 1;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border-subtle);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-accent-primary);
}

/* 简单的类名修复，如果 Tailwind 不支持 */
.direction-rtl { direction: rtl; }
</style>
