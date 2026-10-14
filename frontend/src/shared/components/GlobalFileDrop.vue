<template>
  <div
    id="global-file-drop-zone"
    class="pointer-events-none fixed inset-0 z-20"
  >
    <Transition name="fade-drop">
      <div v-if="showOverlay" class="pointer-events-auto absolute inset-0 flex items-center justify-center bg-bg-deep/70 backdrop-blur-sm">
        <div class="mx-4 w-full max-w-md rounded-2xl border border-accent-primary/30 bg-accent-primary/10 px-6 py-8 text-center shadow-[0_0_40px_rgba(var(--rgb-accent-primary),0.18)]">
          <div class="text-base font-bold tracking-wide text-text-main">{{ t('ui.global_drop.title', '拖入文件') }}</div>
          <div class="mt-2 text-sm leading-relaxed text-text-dim">{{ t('ui.global_drop.description', '松手后会自动识别排序文件或软件数据包。') }}</div>
          <div class="mt-3 text-xs text-text-dim">{{ t('ui.global_drop.formats', '排序文件：xml / rws / rml / json / txt / list；软件数据包：rimcrowdata.zip') }}</div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { toast } from '../lib/common.js'
import { useAppStore } from '../../app/stores/appStore.js'
import { useOrderStore } from '../../features/load-order/orderStore.js'
import { useProfileStore } from '../../features/profiles/profileStore.js'
import { isBrowserRuntime } from '../../app/bridge/runtimeBridge.js'
import { t } from '../i18n.js'

const appStore = useAppStore()
const orderStore = useOrderStore()
const profileStore = useProfileStore()
const showOverlay = ref(false)
const dragDepth = ref(0)
const activeDrop = ref('')
const lastDrop = ref({ key: '', time: 0 })
const browserMode = computed(() => isBrowserRuntime())
const profileId = computed(() => profileStore.currentProfileId || appStore.settings.current_profile_id || 'default')
const ORDER_EXTENSIONS = new Set(['xml', 'rws', 'rml', 'json', 'txt', 'list'])
const DATA_EXTENSIONS = ['rimcrowdata.zip', 'rmmdata.zip', 'rmmdata']

const fileName = (fileOrPath) => String(fileOrPath?.name || fileOrPath || '').trim().toLowerCase()
const isDataBundle = (value) => DATA_EXTENSIONS.some(extension => fileName(value).endsWith(extension))
const isOrderFile = (value) => ORDER_EXTENSIONS.has(fileName(value).split('.').pop())
const dropKey = (file) => file?.path || [file?.name, file?.size, file?.lastModified].join(':')
const isFileDrag = (event) => {
  const types = Array.from(event?.dataTransfer?.types || [])
  return types.includes('Files')
}
const reset = () => { dragDepth.value = 0; showOverlay.value = false }
const canProcess = (key) => {
  if (!key || activeDrop.value === key) return false
  const last = lastDrop.value
  return !(last.key === key && Date.now() - last.time < 2500)
}

const processDataBundle = async (path) => {
  if (browserMode.value) {
    toast.info(t('toast.global_drop.data_bundle_browser', '浏览器模式无法直接读取拖入的软件数据包，请到“设置 → 数据管理 → 导入数据包”选择文件。'))
    return false
  }
  const schema = await appStore.getDataBundleSchema()
  const inspectData = await appStore.inspectDataBundle(path)
  if (!schema || !inspectData) return false
  appStore.openPackageTransferDialog('data-import', {
    title: t('ui.settings.data.import_data_bundle_title', '导入软件数据包'),
    bundlePath: path,
    inspectData,
    dataBundleSchema: schema,
  })
  return true
}

const processPath = async (path) => {
  const normalized = String(path || '').trim()
  if (!normalized || !canProcess(normalized)) return false
  activeDrop.value = normalized
  lastDrop.value = { key: normalized, time: Date.now() }
  try {
    if (isDataBundle(normalized)) return await processDataBundle(normalized)
    if (isOrderFile(normalized)) {
      const data = await orderStore.importExternalOrder(normalized, profileId.value)
      if (data) appStore.uiState.showDiffDrawer = true
      return !!data
    }
    toast.warning(t('toast.global_drop.unsupported_file', '无法识别该文件。支持排序文件和软件数据包。'))
    return false
  } finally {
    activeDrop.value = ''
  }
}

const processBrowserFile = async (file) => {
  const key = dropKey(file)
  if (!canProcess(key)) return false
  activeDrop.value = key
  lastDrop.value = { key, time: Date.now() }
  if (isDataBundle(file)) {
    try {
      return await processDataBundle(file.name)
    } finally {
      activeDrop.value = ''
    }
  }
  if (!isOrderFile(file)) {
    activeDrop.value = ''
    toast.warning(t('toast.global_drop.unsupported_file', '无法识别该文件。支持排序文件和软件数据包。'))
    return false
  }
  try {
    const data = await orderStore.importPayloadFile(file, profileId.value)
    if (data) appStore.uiState.showDiffDrawer = true
    return !!data
  } finally {
    activeDrop.value = ''
  }
}

const extractPath = (event) => {
  for (const item of Array.from(event?.dataTransfer?.items || [])) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile?.()
    if (file?.path) return file.path
  }
  return Array.from(event?.dataTransfer?.files || []).find(file => file.path)?.path || ''
}

const handleNativeDrop = async (paths = []) => {
  reset()
  const files = Array.isArray(paths) ? paths.map(item => String(item || '').trim()).filter(Boolean) : []
  if (files.length > 1) toast.info(t('toast.global_drop.first_file_only', '一次只能导入一个文件，已使用第一个文件。'))
  const path = files[0]
  if (!path) return toast.warning(t('toast.global_drop.no_file', '未检测到可导入文件'))
  await processPath(path)
}
const handleDragEnter = (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault(); dragDepth.value += 1; showOverlay.value = true
}
const handleDragOver = (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; showOverlay.value = true
}
const handleDragLeave = (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault(); dragDepth.value = Math.max(0, dragDepth.value - 1)
  if (!dragDepth.value) showOverlay.value = false
}
const handleDrop = async (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault(); reset()
  const files = Array.from(event?.dataTransfer?.files || [])
  if (files.length > 1) toast.info(t('toast.global_drop.first_file_only', '一次只能导入一个文件，已使用第一个文件。'))
  const path = extractPath(event)
  if (path) return processPath(path)
  if (files[0]) return processBrowserFile(files[0])
  toast.warning(t('toast.global_drop.no_file', '未检测到可导入文件'))
}

const bindNativeDrop = async () => {
  if (browserMode.value || !window.pywebview?.api?.bind_global_file_drop_zone) return
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const result = await window.pywebview.api.bind_global_file_drop_zone('app-shell')
    if (result?.status === 'success' || result?.status === 'error') return
    await new Promise(resolve => window.setTimeout(resolve, 250))
  }
}

onMounted(() => {
  window.__handleNativeFileDrop = handleNativeDrop
  window.addEventListener('dragenter', handleDragEnter)
  window.addEventListener('dragover', handleDragOver)
  window.addEventListener('dragleave', handleDragLeave)
  window.addEventListener('drop', handleDrop)
  if (!browserMode.value) window.setTimeout(bindNativeDrop, 0)
})
onUnmounted(() => {
  window.removeEventListener('dragenter', handleDragEnter)
  window.removeEventListener('dragover', handleDragOver)
  window.removeEventListener('dragleave', handleDragLeave)
  window.removeEventListener('drop', handleDrop)
  if (window.__handleNativeFileDrop === handleNativeDrop) delete window.__handleNativeFileDrop
})
</script>

<style scoped>
.fade-drop-enter-active, .fade-drop-leave-active { transition: opacity 0.18s ease; }
.fade-drop-enter-from, .fade-drop-leave-to { opacity: 0; }
</style>
