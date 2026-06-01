<template>
  <CommonModalShell :show="appStore.uiState.showSettingsPanel" persistent
    :show-header="false" :close-on-backdrop="false" size="custom" :z-index="100"
    accent="primary"
    panel-class="w-[75%] h-[80%] border-border-base/18" content-class="h-full flex"
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
                :profile-store="profileStore"
                :steam-launch-disabled="steamLaunchDisabled"
                :workshop-mods-disabled="workshopModsDisabled"
                :load-order-dir-mode-options="LOAD_ORDER_DIR_MODE_OPTIONS"
                :auto-detect="autoDetect"
                :handle-game-browse="handleGameBrowse"
                :handle-browse="handleBrowse"
                :check-path="checkPath"
                :handle-check-steamcmd-mods="handleCheckSteamcmdMods"
              />
              <SettingsGeneralTab
                v-if="currentTab === 'general'"
                :form-data="formData"
                :app-store="appStore"
                :guide-store="guideStore"
                :current-theme-id="currentThemeId"
                :get-data-by-id="getDataById"
                :get-layout-drag-class="getLayoutDragClass"
                :handle-layout-drag-start="handleLayoutDragStart"
                :handle-layout-drag-over="handleLayoutDragOver"
                :handle-layout-drop="handleLayoutDrop"
                :handle-layout-drag-end="handleLayoutDragEnd"
                @update:current-theme-id="currentThemeId = $event"
                @open-theme-create="openThemeCreate"
                @open-theme-edit="openThemeEdit"
                @delete-theme="handleThemeDelete"
              />
              <SettingsFeaturesTab v-if="currentTab === 'features'" :form-data="formData" />
              <SettingsExternalTab
                v-if="currentTab === 'community'"
                :form-data="formData"
                :rule-store="ruleStore"
                :download-state="downloadState"
                :reset-to-default-external-paths="resetToDefaultExternalPaths"
                :handle-check-tools="handleCheckTools"
                :handle-check-external-data="handleCheckExternalData"
                :handle-browse="handleBrowse"
                :check-path="checkPath"
                :update-external-d-b="updateExternalDB"
              />
              <SettingsNetworkTab v-if="currentTab === 'network'" :form-data="formData" :open-url-on-steam="openUrlOnSteam" />
              <SettingsAiTab
                v-if="currentTab === 'ai'"
                :form-data="formData"
                :app-store="appStore"
                :ai-store="aiStore"
                :current-ai-providers="currentAiProviders"
                :current-ai-models="currentAiModels"
                :test-prompt="testPrompt"
                :test-response="testResponse"
                :test-raw-response="testRawResponse"
                :pretty-test-raw-response="prettyTestRawResponse"
                :handle-provider-change="handleProviderChange"
                :fetch-ai-models="fetchAiModels"
                :test-model="testModel"
                :clear-test-result="clearTestResult"
                @update:test-prompt="testPrompt = $event"
              />
              <SettingsDevTab
                v-if="currentTab === 'dev'"
                :form-data="formData"
                :app-store="appStore"
                :profile-store="profileStore"
                :handle-clear-remote-image-cache="handleClearRemoteImageCache"
                :open-data-bundle-import-dialog="openDataBundleImportDialog"
                :open-data-bundle-modal="openDataBundleModal"
                :open-mod-package-import-dialog="openModPackageImportDialog"
                :open-current-profile-export-dialog="openCurrentProfileExportDialog"
                :handle-repair="handleRepair"
                :handle-reset="handleReset"
              />

            </div>
          </div>

          <!-- D. 底部操作栏 -->
          <footer class="modal-footer flex items-center justify-end gap-4 px-10 py-3">
            <button id="btn-cancel" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">放弃修改</button>
            <button data-tour="settings-save-button" @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-on-accent-primary font-black text-sm shadow-[0_0_20px_rgba(var(--rgb-accent-primary),0.3)] hover:scale-105 active:scale-95 transition-all group">
              <div class="absolute inset-0 bg-bg-overlay/10 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              应用并保存配置
            </button>
          </footer>
        </main>

  </CommonModalShell>

  <DataBundleExportModal
    :show="showDataBundleModal && appStore.uiState.showSettingsPanel"
    :bundle-module-defs="bundleModuleDefs"
    :bundle-profile-defs="bundleProfileDefs"
    :data-bundle-module-selection="dataBundleModuleSelection"
    :data-bundle-profile-selection="dataBundleProfileSelection"
    :show-bundle-profile-picker="showBundleProfilePicker"
    :is-bundle-profile-module-selected="isBundleProfileModuleSelected"
    :build-bundle-module-tooltip="buildBundleModuleTooltip"
    :toggle-data-bundle-module="toggleDataBundleModule"
    :close-data-bundle-modal="closeDataBundleModal"
    :handle-export-data-bundle="handleExportDataBundle"
    @update:data-bundle-profile-selection="dataBundleProfileSelection = $event"
    @update:show-bundle-profile-picker="showBundleProfilePicker = $event"
  />
</template>

<script setup>
import { ref, watch, onMounted, nextTick, h, computed } from 'vue'
import { FolderTree, AppWindow, Globe, Cpu, Terminal, Search, Component, Settings } from 'lucide-vue-next'
import { deepClone, toast } from '../../shared/lib/common'
import { flashComponent, shakeComponent } from '../../shared/lib/domEffects'

// 导入 Common UI
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import SettingsPathsTab from './panel/SettingsPathsTab.vue'
import SettingsGeneralTab from './panel/SettingsGeneralTab.vue'
import SettingsFeaturesTab from './panel/SettingsFeaturesTab.vue'
import SettingsExternalTab from './panel/SettingsExternalTab.vue'
import SettingsNetworkTab from './panel/SettingsNetworkTab.vue'
import SettingsAiTab from './panel/SettingsAiTab.vue'
import SettingsDevTab from './panel/SettingsDevTab.vue'
import DataBundleExportModal from './panel/DataBundleExportModal.vue'
import { formatFileSize } from '../../shared/lib/format'
import { DEFAULT_THEME_ID, applyTheme, createEditableThemeFrom, findThemeById, normalizeTheme } from './theme/themeManager'
import { useRuleStore } from '../rules/ruleStore'
import { useAppStore } from '../../app/stores/appStore'
import { useAiStore } from '../ai/aiStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useProfileStore } from '../profiles/profileStore'
import { useModStore } from '../mod/modStore'
import { useGuideStore } from '../guide/guideStore'

const appStore = useAppStore()
const aiStore = useAiStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()
const profileStore = useProfileStore()
const modStore = useModStore()
const guideStore = useGuideStore()

const currentTab = ref('paths')
const formData = ref({})
const layoutDragState = ref({ key: '', fromIndex: -1, overIndex: -1 })

const selectedFormTheme = computed(() => {
  return findThemeById(appStore.themes, currentThemeId.value)
})
const currentThemeId = computed({
  get: () => appStore.settings.ui?.theme_id || DEFAULT_THEME_ID,
  set: async (themeId) => {
    if (!appStore.settings.ui) appStore.settings.ui = {}
    appStore.settings.ui.theme_id = themeId || DEFAULT_THEME_ID
    applyTheme(findThemeById(appStore.themes, appStore.settings.ui.theme_id))
    await appStore.saveSetting('ui', appStore.settings.ui)
  },
})

const openThemeCreate = () => {
  appStore.themeEditor.theme = createEditableThemeFrom(selectedFormTheme.value)
  appStore.themeEditor.isOpen = true
}
const openThemeEdit = (theme) => {
  if (!theme || theme.builtin) return
  appStore.themeEditor.theme = normalizeTheme(theme)
  appStore.themeEditor.isOpen = true
}
const handleThemeDelete = async (theme) => {
  if (!theme || theme.builtin) return
  const ok = await confirmStore.confirmAction('删除主题', `确定要删除自定义主题「${theme.name}」吗？此操作不可撤销。`, { type: 'error' })
  if (!ok) return
  const deleted = await appStore.deleteUserTheme(theme.id)
  if (deleted && currentThemeId.value === theme.id) {
    currentThemeId.value = DEFAULT_THEME_ID
  }
}

const getLayoutList = (layoutKey) => {
  const list = formData.value?.ui?.[layoutKey]
  return Array.isArray(list) ? list : []
}
const handleLayoutDragStart = (layoutKey, index, event) => {
  // 设置页只有少量布局项，不需要再依赖 SortableJS。
  // 这里用原生拖拽维护“从哪个布局、哪个下标开始拖”，drop 时直接重排数组即可。
  const list = getLayoutList(layoutKey)
  if (!list[index]) return
  layoutDragState.value = { key: layoutKey, fromIndex: index, overIndex: index }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', `${layoutKey}:${index}`)
}
const handleLayoutDragOver = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return
  layoutDragState.value = { ...layoutDragState.value, overIndex: index }
}
const handleLayoutDrop = (layoutKey, toIndex) => {
  const { key, fromIndex } = layoutDragState.value
  const list = getLayoutList(layoutKey)
  if (key !== layoutKey || fromIndex < 0 || toIndex < 0 || fromIndex === toIndex || !list[fromIndex]) {
    handleLayoutDragEnd()
    return
  }
  const nextList = [...list]
  const [moving] = nextList.splice(fromIndex, 1)
  nextList.splice(toIndex, 0, moving)
  formData.value.ui[layoutKey] = nextList
  handleLayoutDragEnd()
}
const handleLayoutDragEnd = () => {
  layoutDragState.value = { key: '', fromIndex: -1, overIndex: -1 }
}
const getLayoutDragClass = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return ''
  if (layoutDragState.value.fromIndex === index) return 'opacity-50 scale-[0.98]'
  if (layoutDragState.value.overIndex === index) return 'translate-y-0 ring-1 ring-accent-primary/60 rounded-xl'
  return ''
}
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
  { id: 'community', label: '外部依赖', icon: Steam },
  { id: 'network', label: '网络连接', icon: Globe },
  { id: 'ai', label: 'AI 集成', icon: Cpu },
  { id: 'dev', label: '开发调试', icon: Terminal },
]

const currentTabLabel = computed(() => (
  tabs.find(item => item.id === currentTab.value)?.label || currentTab.value
))

const LOAD_ORDER_DIR_MODE_OPTIONS = [
  { label: '默认', value: 'default' },
  { label: '记忆', value: 'remember' },
  { label: '自定义', value: 'custom' },
]


const downloadState = ref({
  workshop_db: false,
  instead_db: false,
})
const currentAiProviders = computed(() => aiStore.listAiProviders())
const currentAiModels = computed(() => aiStore.getCachedAiModelOptions(formData.value?.ai || {}))
const dataBundleSchema = ref({
  modules: [],
  profiles: [],
  presets: {},
  file_extension: '.rmmdata.zip',
})
const showDataBundleModal = ref(false)
const showBundleProfilePicker = ref(false)
const dataBundleModuleSelection = ref({})
const dataBundleProfileSelection = ref([])

const bundleModuleDefs = computed(() => dataBundleSchema.value?.modules || [])
const bundleProfileDefs = computed(() => dataBundleSchema.value?.profiles || [])
const selectedBundleModuleKeys = computed(() => (
  bundleModuleDefs.value
    .filter(module => !!dataBundleModuleSelection.value?.[module.key])
    .map(module => module.key)
))
const isBundleProfileModuleSelected = computed(() => !!dataBundleModuleSelection.value?.profiles)

const resetDataBundleSelections = () => {
  dataBundleModuleSelection.value = Object.fromEntries(
    bundleModuleDefs.value.map(module => [module.key, false])
  )
  dataBundleProfileSelection.value = []
}

const ensureModuleEnabled = (moduleKey, selection) => {
  const target = bundleModuleDefs.value.find(module => module.key === moduleKey)
  if (!target) return
  selection[moduleKey] = true
  for (const dependencyKey of target.dependencies || []) {
    ensureModuleEnabled(dependencyKey, selection)
  }
}

const disableModuleAndDependents = (moduleKey, selection) => {
  selection[moduleKey] = false
  const dependentKeys = bundleModuleDefs.value
    .filter(module => (module.dependencies || []).includes(moduleKey))
    .map(module => module.key)
  for (const dependentKey of dependentKeys) {
    disableModuleAndDependents(dependentKey, selection)
  }
}

const toggleDataBundleModule = (moduleKey, enabled) => {
  const nextSelection = { ...(dataBundleModuleSelection.value || {}) }
  if (enabled) {
    ensureModuleEnabled(moduleKey, nextSelection)
  } else {
    disableModuleAndDependents(moduleKey, nextSelection)
  }
  dataBundleModuleSelection.value = nextSelection
  if (!nextSelection.profiles) {
    dataBundleProfileSelection.value = []
    showBundleProfilePicker.value = false
  } else if (moduleKey === 'profiles' && enabled) {
    showBundleProfilePicker.value = true
  }
}

const loadDataBundleSchema = async () => {
  const schema = await appStore.getDataBundleSchema()
  if (!schema) return
  dataBundleSchema.value = schema
  resetDataBundleSelections()
}

const openDataBundleModal = async () => {
  if (!bundleModuleDefs.value.length) {
    await loadDataBundleSchema()
  }
  showDataBundleModal.value = true
}

const closeDataBundleModal = () => {
  showDataBundleModal.value = false
}

const buildBundleModuleTooltip = (module) => {
  const lines = []
  if (module?.description) {
    lines.push(module.description)
  }
  const dependencyLabels = (module?.dependencies || [])
    .map(key => bundleModuleDefs.value.find(item => item.key === key)?.label || key)
  if (dependencyLabels.length) {
    lines.push(`依赖：${dependencyLabels.join('、')}`)
  }
  return lines.join('\n')
}

// 数据同步：打开时深度拷贝
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    // 利用 requestAnimationFrame 或 setTimeout
    // 让浏览器先渲染出弹窗的“背景”和“动画第一帧”，然后再去塞数据
    requestAnimationFrame(async () => {
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
      // 如果当前上下文不健康，自动检测路径
      if (!profileStore.activeContext || profileStore.activeContext.is_healthy === false) {
        await autoDetect()
      }
      // 检测所有路径是否有效
      await checkPaths()
      await loadDataBundleSchema()
      await appStore.refreshRemoteImageCacheStats()
      // AI 厂商定义已在 aiStore 初始化时一并获取。
      // 模型列表仍按需请求，但优先复用 aiStore 缓存，避免设置面板维护重复状态。
      if (formData.value.ai) {
        hydrateAiProviderDrafts()
        if (formData.value.ai.provider) {
          await fetchAiModels({ silent: true })
        }
      }
    })
  } else {
    showDataBundleModal.value = false
    showBundleProfilePicker.value = false
    if (!appStore.themeEditor.isOpen) applyTheme(appStore.currentTheme)
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
  // 检测所有路径是否有效
  // if (['paths','community'].includes(tab)) {
  //   checkPaths()
  // }
}

// 通过ID获取数据项
const getDataById = (id, datas) => {
  return datas.find(item => item.id === id)
}

// 自动检测路径
const autoDetect = async () => {
  const paths = await appStore.autoDetectPaths(false)
  if (paths) Object.assign(formData.value, paths)
}
// 重置外部依赖路径为默认值
const resetToDefaultExternalPaths = async () => {
  const paths = await appStore.getDefaultExternalPaths()
  if (!paths) return
  const { texture_opt, ...rest } = paths
  Object.assign(formData.value, rest)
  if (texture_opt && typeof texture_opt === 'object') {
    formData.value.texture_opt = {
      ...(formData.value.texture_opt || {}),
      ...texture_opt,
    }
  }
}

// 检查游戏路径是否有效
const checkPath = async (type, path) => {
  console.log('checkPath:', type, path)
  const res = await appStore.checkPath(type, path)
  if (!formData.value['check_info']) {
    formData.value['check_info'] = {};
  }
  formData.value['check_info'][type] = res
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

// 手动选择游戏路径
const handleGameBrowse = async () => {
  let current = formData.value
  const res = await appStore.getFolderPath(current['game_install_path'])
  if (res) {
    current['game_install_path'] = res
    // 自动获取游戏信息
    checkPath('game_install_path', current['game_install_path'])
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

// 手动选择其他路径
const handleBrowse = async (pathKey, fileTypes, checkTarget = undefined) => {
  console.log('路径选择',pathKey, fileTypes)
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

// ======= AI 集成 ======
// 测试提示词
const testPrompt = ref("介绍一下自己")
const testResponse = ref("")
const testRawResponse = ref(null)
const prettyTestRawResponse = computed(() => {
  if (testRawResponse.value == null) return ''
  try {
    return JSON.stringify(testRawResponse.value, null, 2)
  } catch {
    return String(testRawResponse.value)
  }
})
const clearTestResult = () => {
  testResponse.value = ""
  testRawResponse.value = null
}
const aiProviderDrafts = ref({})

const DEFAULT_AI_BASE_URLS = {
  openai_compatible: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

const normalizeAiProvider = (provider = '') => {
  const normalized = String(provider || '').trim().toLowerCase()
  if (['openai', 'custom_openai'].includes(normalized)) return 'openai_compatible'
  return normalized || 'openai_compatible'
}

const createAiProviderDraft = (ai = {}) => ({
  provider: normalizeAiProvider(ai.provider),
  base_url: String(ai.base_url || '').trim(),
  api_key: String(ai.api_key || '').trim(),
  model: String(ai.model || '').trim(),
  endpoint_mode: String(ai.endpoint_mode || 'auto').trim().toLowerCase() || 'auto',
})

const syncCurrentAiProviderDraft = () => {
  const ai = formData.value?.ai
  if (!ai) return
  const provider = normalizeAiProvider(ai.provider)
  aiProviderDrafts.value[provider] = createAiProviderDraft(ai)
}

const hydrateAiProviderDrafts = () => {
  const ai = formData.value?.ai
  if (!ai) return
  aiProviderDrafts.value = {
    [normalizeAiProvider(ai.provider)]: createAiProviderDraft(ai),
  }
}

const applyAiDraftForProvider = (provider) => {
  const ai = formData.value?.ai
  if (!ai) return
  const normalizedProvider = normalizeAiProvider(provider)
  const hasDraft = Object.prototype.hasOwnProperty.call(aiProviderDrafts.value, normalizedProvider)
  const draft = hasDraft ? aiProviderDrafts.value[normalizedProvider] : null
  ai.provider = normalizedProvider
  ai.base_url = draft ? String(draft.base_url || '') : (DEFAULT_AI_BASE_URLS[normalizedProvider] || '')
  ai.api_key = draft ? String(draft.api_key || '') : ''
  ai.model = draft ? String(draft.model || '') : ''
  ai.endpoint_mode = draft ? (String(draft.endpoint_mode || 'auto').trim().toLowerCase() || 'auto') : 'auto'
}

// 测试模型
const testModel = async () => {
  clearTestResult()
  const res = await aiStore.chatWithAI(testPrompt.value, formData.value.ai)
  testRawResponse.value = res?.raw ?? null
  if (res?.ok) {
    testResponse.value = res.text
    toast.success("模型测试成功")
    return
  }
  if (res?.isEmpty) {
    testResponse.value = '模型已返回，但内容为空。可尝试切换模型、检查代理兼容策略或改用正式助手会话测试。'
    toast.warning('模型返回了空内容')
    return
  }
  testResponse.value = res?.error || '模型测试失败'
  toast.error(res?.error || '模型测试失败')
}

// 切换协议只重置连接表单，不主动探测模型列表；模型列表由下拉展开或手动刷新触发。
const handleProviderChange = (selectedProvider) => {
  syncCurrentAiProviderDraft()
  const nextProvider = normalizeAiProvider(selectedProvider?.value ?? selectedProvider ?? formData.value?.ai?.provider)
  applyAiDraftForProvider(nextProvider)
}
// 拉取模型列表 (兼容旧的，组装为 CommonSelect 接受的结构)
const fetchAiModels = async ({ forceRefresh = false, warnOnEmpty = false, silent = true } = {}) => {
  if (!formData.value.ai.provider || !formData.value.ai.enabled) {
    return
  }
  await aiStore.getAiModels(formData.value.ai, { forceRefresh, warnOnEmpty, silent })
}

const openUrlOnSteam = (url) => {
  window.open('steam://openurl/'+url, '_blank')
}

// 更新外部数据库
const updateExternalDB = async (dbType) => {
  downloadState.value[dbType] = true
  await appStore.updateExternalDB(dbType)
  downloadState.value[dbType] = false
}

const handleCheckTools = async () => {
  await appStore.checkToolMaintenance({ manual: true, prompt: true })
}

const handleCheckExternalData = async () => {
  await appStore.checkExternalDataUpdates({ manual: true, prompt: true })
}

const handleCheckSteamcmdMods = async () => {
  await appStore.checkSteamcmdModUpdates({ manual: true, prompt: true })
}

const handleClearRemoteImageCache = async () => {
  const ok = await confirmStore.confirmAction(
    '确认清理网络图片缓存',
    '这会删除当前已缓存的远程图片文件。后续再次显示这些图片时，会按需重新下载。',
    { type: 'warning', confirmText: '立即清理', cancelText: '取消' }
  )
  if (!ok) return
  const cleared = await appStore.clearRemoteImageCache()
  if (!cleared) return
  const clearedCount = Number(cleared?.cleared?.file_count || 0)
  const clearedBytes = formatFileSize(cleared?.cleared?.total_bytes || 0)
  toast.success(`已清理 ${clearedCount} 张缓存图片，释放 ${clearedBytes}`)
}

const handleExportDataBundle = async () => {
  const moduleKeys = selectedBundleModuleKeys.value
  if (moduleKeys.length === 0) {
    toast.warning('请至少勾选一个要导出的数据模块')
    return
  }
  if (moduleKeys.includes('profiles') && dataBundleProfileSelection.value.length === 0) {
    toast.warning('已勾选环境数据，请至少选择一个环境')
    return
  }

  const exported = await appStore.exportDataBundle({
    preset: 'custom',
    module_keys: moduleKeys,
    profile_ids: dataBundleProfileSelection.value,
  })
  if (exported) {
    closeDataBundleModal()
  }
}

const openDataBundleImportDialog = async () => {
  const schema = await appStore.getDataBundleSchema()
  if (!schema) return

  const extensions = [
    schema.file_extension || '.rmmdata.zip',
    ...(Array.isArray(schema.legacy_file_extensions) ? schema.legacy_file_extensions : ['.rmmdata']),
  ]
    .map(item => String(item || '').trim())
    .filter(Boolean)
  const bundlePath = await appStore.getFilePath('', [
    `RMM Data Package (${extensions.map(item => `*${item}`).join(';')})`,
    'All Files (*.*)',
  ])
  if (!bundlePath) return

  const inspectData = await appStore.inspectDataBundle(bundlePath)
  if (!inspectData) return

  appStore.openPackageTransferDialog('data-import', {
    title: '导入软件数据包',
    bundlePath,
    inspectData,
    dataBundleSchema: schema,
  })
}

const openModPackageImportDialog = async () => {
  const schema = await appStore.getModPackageSchema()
  if (!schema) return

  const bundlePath = await appStore.getFilePath('', [
    `RMM Mod Package (*${schema.file_extension || '.rmmmods.zip'})`,
    'All Files (*.*)',
  ])
  if (!bundlePath) return

  const availableInstalls = Array.isArray(schema.available_installs) ? schema.available_installs : []
  const targetKind = availableInstalls.length > 0 ? 'game_install' : 'self_mods'
  const gameInstallPath = String(availableInstalls[0]?.install_path || '')
  const inspectData = await appStore.prepareModPackageImport(bundlePath, {
    target_kind: targetKind,
    game_install_path: gameInstallPath,
  })
  if (!inspectData) return

  appStore.openPackageTransferDialog('mod-import', {
    title: '导入模组包',
    bundlePath,
    inspectData,
    modPackageSchema: schema,
    targetKind,
    gameInstallPath,
  })
}

const openCurrentProfileExportDialog = () => {
  const currentProfile = profileStore.currentProfile || {}
  appStore.openPackageTransferDialog('mod-export', {
    title: '导出当前环境模组',
    description: '可在导出前选择当前环境有效模组或当前启用模组，并按需附带环境数据。',
    sourceProfile: true,
    profileId: currentProfile.id || appStore.settings.current_profile_id || 'default',
    profileName: currentProfile.name || '当前环境',
    scopeOptions: [
      { value: 'profile-effective', label: `当前环境有效模组（${modStore.exportableVisibleCount}）`, description: '导出当前环境里能正常使用的模组。' },
      { value: 'profile-active', label: `当前环境启用模组（${modStore.exportableActiveCount}）`, description: '只导出当前环境里已经启用的模组。' },
    ],
    export_scope: 'profile-effective',
    folder_name_type: formData.value?.bundle_mod_folder_name_type || appStore.settings.bundle_mod_folder_name_type || 'default',
  })
}

// ====== 数据处理 ======
const handleReset = async () => {
  const ok = await confirmStore.confirmAction('确认重置', '重置后，分组、备注等本地数据将被清空，且无法撤销。确定继续吗？', { type: 'error' })
  if (ok) appStore.resetDatabase()
}

const handleRepair = async () => {
  const ok = await confirmStore.confirmAction(
    '确认修复',
    '这会尝试修复当前数据库。修复成功后需要重启软件才能生效。\n确定继续吗？',
    { type: 'warning', confirmText: '开始修复' }
  )
  if (!ok) return

  const res = await appStore.repairDatabase()
  if (!res || res.status !== 'success') {
    // 主动修复失败时不自动切换任何数据库，直接提示用户转向更保守的重置方案。
    const shouldReset = await confirmStore.confirmAction(
      '修复失败',
      '数据库修复失败，当前数据可能无法正常使用。建议立即重置数据库。',
      { type: 'error', confirmText: '立即重置', cancelText: '稍后处理' }
    )
    if (shouldReset) {
      await appStore.resetDatabase()
    }
    return
  }

  if (res.data?.initialized) {
    appStore.closeSettingsPanel()
    toast.success('未找到本地数据库，已重新创建。')
    return
  }

  const restartNow = await confirmStore.confirmAction(
    '修复完成',
    '数据库修复已完成。现在重启软件即可生效；如果暂不重启，当前仍会继续使用旧状态。',
    { type: 'success', confirmText: '立即重启', cancelText: '稍后重启' }
  )

  if (!restartNow) {
    toast.info('修复已完成，重启软件后生效。', { timeout: 4000 })
    return
  }

  appStore.closeSettingsPanel()
  await appStore.restartApplication()
}

const save = async () => {
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
