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
                :steam-launch-disabled="steamLaunchDisabled"
                :workshop-mods-disabled="workshopModsDisabled"
                :mark-steam-launch-touched="markSteamLaunchTouched"
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

            </div>
          </div>

          <!-- D. 底部操作栏 -->
          <footer class="modal-footer flex items-center justify-end gap-4 px-10 py-3">
            <button id="btn-cancel" :disabled="saving" :class="saving ? 'rmm-action-disabled' : ''" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">放弃修改</button>
            <button data-tour="settings-save-button" :disabled="saving" :class="saving ? 'rmm-action-disabled' : ''" @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-on-accent-primary font-black text-sm shadow-[0_0_20px_rgba(var(--rgb-accent-primary),0.3)] hover:scale-105 active:scale-95 transition-all group">
              <div class="absolute inset-0 bg-bg-overlay/10 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              应用并保存配置
            </button>
          </footer>
        </main>

  </CommonModalShell>
</template>

<script setup>
import { ref, watch, h, computed } from 'vue'
import { FolderTree, AppWindow, Globe, Cpu, Terminal, Component, Settings, Keyboard } from 'lucide-vue-next'
import { shakeComponent } from '../../shared/lib/domEffects'
import { toast } from '../../shared/lib/common'
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
import { DEFAULT_THEME_ID, applyTheme } from './theme/themeManager'
import { useAppStore } from '../../app/stores/appStore'
import { useProfileStore } from '../profiles/profileStore'

const appStore = useAppStore()
const profileStore = useProfileStore()

const currentTab = ref('paths')
const formData = ref({})
const steamLaunchTouched = ref(false)
const saving = ref(false)
const detectedIsSteam = computed(() => {
  const checkedInstall = formData.value?.check_info?.game_install_path
  if (checkedInstall && Object.prototype.hasOwnProperty.call(checkedInstall, 'pass')) {
    if (checkedInstall.data && Object.prototype.hasOwnProperty.call(checkedInstall.data, 'is_steam')) {
      return !!checkedInstall.data.is_steam
    }
    return false
  }
  return !!formData.value?.is_steam
})
const steamLaunchDisabled = computed(() => !detectedIsSteam.value)
const hasWorkshopPath = computed(() => !!String(formData.value?.workshop_mods_path || '').trim())
const workshopModsDisabled = computed(() => steamLaunchDisabled.value || !!formData.value?.prefer_steam_launch || !hasWorkshopPath.value)

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

// 数据同步：打开时深度拷贝
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    const openVersion = ++settingsPanelOpenVersion
    steamLaunchTouched.value = false
    // 利用 requestAnimationFrame 或 setTimeout
    // 让浏览器先渲染出弹窗的“背景”和“动画第一帧”，然后再去塞数据
    requestAnimationFrame(async () => {
      if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      // 使用 structuredClone (Node 17+ / 现代浏览器均支持，速度更快)，将全局 Settings 和 当前 Context 捏合成一个对象给表单用
      // 如果环境不支持，保留原来的 JSON 方式，但放在 requestAnimationFrame 里依然能解决卡顿
      try {
      formData.value = {
          ...structuredClone(appStore.settings),
          ...structuredClone(profileStore.activeContext) // 覆盖/合并上下文路径
        }
      } catch (e) {
        formData.value = { 
          ...JSON.parse(JSON.stringify(appStore.settings)),
          ...JSON.parse(JSON.stringify(profileStore.activeContext))
        }
      }
      if (formData.value.ui && formData.value.ui.smooth_list_target_scroll === undefined) {
        formData.value.ui.smooth_list_target_scroll = true
      }
      if (formData.value.ui && !Array.isArray(formData.value.ui.hidden_dependency_graph_source_ids)) {
        formData.value.ui.hidden_dependency_graph_source_ids = []
      }
      if (formData.value.ui && !formData.value.ui.keybindings) {
        // 兼容旧配置文件：默认键位由前端命令注册表决定，设置里只保存用户覆盖项。
        formData.value.ui.keybindings = createDefaultKeybindingConfig()
      }
      if (formData.value.skip_language_pack_alias_generation === undefined) {
        formData.value.skip_language_pack_alias_generation = true
      }
      if (!formData.value.translation || typeof formData.value.translation !== 'object') {
        formData.value.translation = {}
      }
      formData.value.translation = appStore.normalizeTranslationSettings(formData.value.translation)
      markSavedSecretsPreserved(formData.value)
      showSecretStorageWarning(formData.value)
      // 如果当前上下文不健康，自动检测路径
      const autoDetected = !profileStore.activeContext || profileStore.activeContext.is_healthy === false
      if (autoDetected) {
        await autoDetect(false)
        if (openVersion !== settingsPanelOpenVersion || !appStore.uiState.showSettingsPanel) return
      }
      // 检测所有路径是否有效
      await checkPaths()
    })
  } else {
    settingsPanelOpenVersion += 1
    if (!appStore.themeEditor.isOpen) applyTheme(appStore.currentTheme)
    clearFormSecrets(formData.value)
  }
})
watch(() => !!formData.value?.prefer_steam_launch, (enabled) => {
  if (enabled && formData.value) {
    formData.value.use_workshop_mods = false
  }
})
watch(detectedIsSteam, (isSteam) => {
  if (!isSteam && formData.value?.prefer_steam_launch) {
    formData.value.prefer_steam_launch = false
  }
})
watch(hasWorkshopPath, (available) => {
  if (!available && formData.value?.use_workshop_mods) {
    formData.value.use_workshop_mods = false
  }
})

// 监听当前页面切换
const changeTab = (tab) => {
  currentTab.value = tab
}

const shouldPreferSteamLaunch = () => {
  const checkInfo = formData.value?.check_info || {}
  const installCheck = checkInfo.game_install_path || {}
  const steamCheck = checkInfo.steam_path || {}
  return !!(
    installCheck.pass
    && installCheck.data?.is_steam
    && steamCheck.pass
    && !formData.value?.use_workshop_mods
  )
}

const applySteamLaunchDefault = () => {
  if (steamLaunchTouched.value || !formData.value) return
  if (shouldPreferSteamLaunch() && !formData.value.prefer_steam_launch) {
    formData.value.prefer_steam_launch = true
  }
}

const markSteamLaunchTouched = () => {
  steamLaunchTouched.value = true
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
const checkPath = async (type, path) => {
  console.debug('检查单项路径:', type, path)
  if (!formData.value['check_info']) {
    formData.value['check_info'] = {};
  }
  if (!String(path || '').trim()) {
    formData.value['check_info'][type] = {
      pass: false,
      type: 'warn',
      msg: '未填写路径',
    }
    return
  }
  const res = await appStore.checkPath(type, path)
  formData.value['check_info'][type] = res
  if (res?.pass && res?.data && type === 'ripgrep_path') {
    formData.value.ripgrep_path = res.data
  }
  if (['game_install_path', 'steam_path'].includes(type)) {
    applySteamLaunchDefault()
  }
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
    applySteamLaunchDefault()
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
  // 校验拦截
  // const hasError = Object.values(formData.value.check_info || {}).some(info => info && !info.pass)
  // if (hasError) {
  //   toast.error("存在无效路径，请修正后再保存！")
  //   return
  // }
  if (formData.value?.ui) {
    formData.value.ui.theme_id = appStore.settings.ui?.theme_id || DEFAULT_THEME_ID
  }
  saving.value = true
  try {
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
