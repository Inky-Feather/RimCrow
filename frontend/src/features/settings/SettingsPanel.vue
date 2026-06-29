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
        <aside class="w-45 border-r bg-bg-muted border-border-base/5 flex flex-col p-6 relative z-10">
          <div class="mb-10 px-2">
            <h2 class="text-xl font-black text-text-main tracking-tighter italic">系统 <span class="text-accent-primary">设置</span></h2>
          </div>

          <!-- 动态 Glider 导航 -->
          <nav class="flex flex-col relative space-y-1" :style="{ '--total-tabs': tabs.length }">
            <button v-for="(tab, index) in tabs" :key="tab.id" :data-tour="`settings-tab-${tab.id}`"
              class="relative z-10 flex items-center gap-3 px-4 py-3 text-md font-bold transition-all duration-300 group"
              :class="currentTab === tab.id ? 'text-accent-primary' : 'text-text-dim hover:text-text-dim'"
              @click="changeTab(tab.id)" >
              <component :is="tab.icon" class="size-4" />
              <span>{{ tab.label }}</span>
            </button>

            <!-- 物理 Glider 滑块 -->
            <div class="glider-container absolute left-0 top-0 w-full h-full pointer-events-none">
              <div class="glider absolute -left-6 w-1 h-11 bg-accent-primary brightness-120 shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.75)] transition-transform duration-500 cubic-bezier"
                :style="{ transform: `translateY(${tabs.findIndex(t => t.id === currentTab) * 2.85}rem)` }">
                <!-- 侧边发光层 -->
                <div class="absolute left-0 top-0 w-40 h-full bg-linear-to-r from-accent-primary/10 to-transparent"></div>
              </div>
            </div>
          </nav>

          <!-- 底部版本号 -->
          <div class="mt-auto px-4 py-2 border-t border-border-base/5 opacity-30">
            <p class="text-xs font-mono text-text-dim">V{{ appStore.appVersion }}</p>
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
            <button id="btn-cancel" :disabled="saving" :class="saving ? 'app-action-disabled' : ''" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">放弃修改</button>
            <button data-tour="settings-save-button" :disabled="saving" :class="saving ? 'app-action-disabled' : ''" @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-on-accent-primary font-black text-sm shadow-[0_0_20px_rgba(var(--rgb-accent-primary),0.3)] hover:scale-105 active:scale-95 transition-all group">
              <div class="absolute inset-0 bg-bg-overlay/10 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              应用并保存配置
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

const appStore = useAppStore()
const profileStore = useProfileStore()

const currentTab = ref('paths')
const formData = ref({})
const saving = ref(false)

const Steam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)

const tabs = [
  { id: 'paths', label: '路径配置', icon: FolderTree },
  { id: 'general', label: '界面设置', icon: AppWindow },
  { id: 'features', label: '功能设置', icon: Component },
  { id: 'keybindings', label: '快捷键', icon: Keyboard },
  { id: 'community', label: '外部依赖', icon: Steam },
  { id: 'network', label: '网络连接', icon: Globe },
  { id: 'ai', label: 'AI 集成', icon: Cpu },
  { id: 'dev', label: '开发调试', icon: Terminal },
  { id: 'about', label: '关于项目', icon: Info },
]
const SECRET_FIELD_PATHS = {
  'ai.api_key': 'ai.api_key',
  'steam.web_api_key': 'steam_web_api_key',
  'network.proxy.username': 'network.proxy.username',
  'network.proxy.password': 'network.proxy.password',
}
let settingsPanelOpenVersion = 0

const currentTabLabel = computed(() => (
  tabs.find(item => item.id === currentTab.value)?.label || currentTab.value
))

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
  if (!installCheck?.pass) return `游戏安装目录可能无法用于 Steam 启动：${installCheck?.msg || '请重新选择游戏安装目录'}`
  if (!steamCheck?.pass) return `Steam 程序路径可能无法使用：${steamCheck?.msg || '请重新选择 Steam.exe 所在目录'}`
  return ''
}

const validateSteamLaunchEnable = async () => {
  const installPath = String(formData.value?.game_install_path || '').trim()
  const steamPath = String(formData.value?.steam_path || '').trim()
  if (!installPath) {
    toast.warning('未填写游戏安装目录，Steam 启动可能无法使用')
    return false
  }
  if (!steamPath) {
    toast.warning('未填写 Steam 程序路径，Steam 启动可能无法使用')
    return false
  }
  const installCheck = await checkPath('game_install_path', installPath, { force: true })
  const steamCheck = await checkPath('steam_path', steamPath)
  const problem = getSteamLaunchProblem(installCheck, steamCheck)
  if (problem) {
    toast.warning(`${problem}\n此开关会按你的选择保留，启动失败时请回到这里修正路径。`)
    return false
  }
  if (!installCheck?.data?.is_steam) {
    toast.warning('未能确认当前游戏本体是否为 Steam 版，仍会优先尝试通过 Steam 启动；如果启动失败，可改为直接启动。')
  }
  return true
}

const validateWorkshopModsEnable = async () => {
  const workshopPath = String(formData.value?.workshop_mods_path || '').trim()
  if (!workshopPath) {
    toast.warning('未填写创意工坊目录，工坊 Mod 可能无法加载')
    return false
  }
  const workshopCheck = await checkPath('workshop_mods_path', workshopPath)
  if (workshopCheck?.pass && workshopCheck?.type === 'warn') {
    toast.warning(workshopCheck.msg || '创意工坊目录当前还不完整，保存后可能需要等 Steam 下载完成。')
  }
  if (!workshopCheck?.pass) {
    toast.warning(`创意工坊目录可能无法使用：${workshopCheck?.msg || '请重新选择创意工坊目录'}\n此开关会按你的选择保留，加载失败时请回到这里修正路径。`)
    return false
  }
  return true
}

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

// 自动检测路径
const autoDetect = async (checkAfterDetect = true) => {
  const paths = await appStore.autoDetectPaths(false)
  if (!paths) return false
  Object.assign(formData.value, paths)
  if (checkAfterDetect) await checkPaths()
  return true
}

// 检查游戏路径是否有效
const checkPath = async (type, path, options = {}) => {
  console.debug('检查单项路径:', type, path)
  if (!formData.value['check_info']) {
    formData.value['check_info'] = {};
  }
  if (!String(path || '').trim()) {
    const result = {
      pass: false,
      type: 'warn',
      msg: '未填写路径',
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
// 检查全部路径
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
  // console.log('检查路径', paths_data)
  const res = await appStore.checkPaths(paths_data)
  if (res) {
    formData.value['check_info'] = res
  }
}

const getNestedField = (target, pathKey) => {
  return String(pathKey || '').split('.').filter(Boolean)
    .reduce((current, key) => current?.[key], target)
}

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

const clearFormSecrets = (target) => {
  if (!target || typeof target !== 'object') return
  Object.values(SECRET_FIELD_PATHS).forEach(pathKey => setNestedField(target, pathKey, ''))
  delete target._preserve_secret_keys
}

const getPreserveSecretKeys = () => (
  Array.isArray(formData.value?._preserve_secret_keys) ? formData.value._preserve_secret_keys : []
)

const setPreserveSecretKeys = (keys) => {
  const nextKeys = [...new Set(keys.filter(key => SECRET_FIELD_PATHS[key]))]
  if (nextKeys.length) {
    formData.value._preserve_secret_keys = nextKeys
  } else {
    delete formData.value._preserve_secret_keys
  }
}

const markSavedSecretsPreserved = (target) => {
  const savedKeys = Object.keys(SECRET_FIELD_PATHS).filter(key => target?._secret_status?.[key]?.has_value)
  if (savedKeys.length) target._preserve_secret_keys = [...new Set([...(target._preserve_secret_keys || []), ...savedKeys])]
}

const isSecretPreserved = (secretKey) => getPreserveSecretKeys().includes(secretKey)

const preserveFormSecret = (secretKey) => {
  setPreserveSecretKeys([...getPreserveSecretKeys(), secretKey])
}

const clearFormSecret = (secretKey) => {
  setNestedField(formData.value, SECRET_FIELD_PATHS[secretKey], '')
  setPreserveSecretKeys(getPreserveSecretKeys().filter(key => key !== secretKey))
}

const showSecretStorageWarning = (target) => {
  if (!target?._secret_storage_warning) return
  toast.warning(target._secret_storage_warning, { timeout: 9000 })
}

// 数据同步：打开时立即生成表单副本；路径检测只在后台补充 check_info，不阻塞设置页渲染。
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    const openVersion = ++settingsPanelOpenVersion
    formData.value = buildSettingsFormData()
    markSavedSecretsPreserved(formData.value)
    showSecretStorageWarning(formData.value)
    void (async () => {
      if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      const autoDetected = !profileStore.activeContext || profileStore.activeContext.is_healthy === false
      if (autoDetected) {
        await autoDetect(false)
        if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      }
      await checkPaths()
    })()
  } else {
    settingsPanelOpenVersion += 1
    if (!appStore.themeEditor.isOpen) applyTheme(appStore.currentTheme)
    clearFormSecrets(formData.value)
  }
}, { immediate: true })

// 手动选择其他路径
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

const save = async () => {
  if (saving.value) return
  saving.value = true
  try {
    await validateEnabledLaunchOptions()
    // 校验拦截
    // const hasError = Object.values(formData.value.check_info || {}).some(info => info && !info.pass)
    // if (hasError) {
    //   toast.error("存在无效路径，请修正后再保存！")
    //   return
    // }
    if (formData.value?.ui) {
      formData.value.ui.theme_id = appStore.settings.ui?.theme_id || DEFAULT_THEME_ID
    }
    await appStore.applySettings(formData.value)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.cubic-bezier {
  transition-timing-function: cubic-bezier(0.37, 1.95, 0.66, 0.56);
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
