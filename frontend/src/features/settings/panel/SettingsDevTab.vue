<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">开发与调试</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSwitch class="col-span-2" label="调试模式" v-model="formData.debug_mode" description="开启调试模式后重启软件将会出现开发者工具窗口，可查看问题详情。" />
                    <CommonSwitch class="col-span-2" label="浏览器模式启动" v-model="formData.browser_mode" description="默认仍使用内置 WebView。开启后，无启动参数时将改为在本机浏览器中启动；关闭浏览器主页面后程序会自动退出。" />
                    <div class="modal-section col-span-2 p-2">
                      <CommonSwitch class="mb-2" label="自动进入静默模式" v-model="formData.auto_enter_silent_mode" mini description="开启后，检测到 RimWorld 运行时会自动切换到静默模式；关闭后仅保留手动进入能力。" />
                      <div class="grid grid-cols-3 items-center">
                        <p class="col-span-2 text-xs ml-1 leading-relaxed text-text-dim">
                          游戏运行时可切到更轻量的界面，减少资源占用，并可直接查看游戏日志。
                        </p>
                        <CommonSelect class="col-span-1 mr-2" label="默认页面" mini v-model="formData.silent_mode_default_view"
                          :options="[
                            { label: '静默主页', value: 'home' },
                            { label: '游戏日志', value: 'logs' }
                          ]"
                          description="控制自动进入静默模式时，默认先显示主页还是直接进入日志页。"
                        />
                      </div>
                    </div>
                    <CommonSelect label="日志等级" v-model="formData.log_level" :options="[{label:'DEBUG', value:'DEBUG'},{label:'INFO', value:'INFO'},{label:'WARNING', value:'WARNING'}]" />
                    <CommonNumber label="日志保留天数" v-model="formData.log_retention_days" :step="1" :min="0" :max="365" />
                  </div>
                  <div class="modal-section p-4">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">网络图片缓存</h4>
                        <p class="mt-1 text-xs leading-relaxed text-text-dim">
                          远程封面图、截图和富文本图片会先写入本地缓存，再由前端通过本地资源服务读取。
                        </p>
                        <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-text-dim">
                          <span>已缓存 {{ appStore.remoteImageCache.file_count }} 张</span>
                          <span>占用 {{ formatFileSize(appStore.remoteImageCache.total_bytes) }}</span>
                        </div>
                      </div>
                      <button @click="handleClearRemoteImageCache" :disabled="appStore.isLoading"
                        class="shrink-0 px-4 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50">
                        清理缓存图片
                      </button>
                    </div>
                  </div>
                  <div class="p-4 rounded-2xl bg-accent-primary/5 border border-accent-primary/20">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">软件数据迁移</h4>
                        <p class="text-xs text-text-dim leading-relaxed mt-1">
                          导入现有数据包，或打开导出面板选择要打包的软件数据。环境数据会包含对应环境的完整目录。
                        </p>
                      </div>
                      <div class="flex items-center gap-2 shrink-0">
                        <button @click="openDataBundleImportDialog" :disabled="isPending('data-import')" :class="isPending('data-import') ? 'app-action-disabled' : ''"
                          class="px-3 py-1.5 rounded-lg bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 text-xs font-bold transition-all" >
                          <span class="inline-flex items-center gap-1">
                            <LoaderCircle v-if="isPending('data-import')" class="h-3 w-3 animate-spin" />
                            {{ isPending('data-import') ? '读取中' : '导入数据包' }}
                          </span>
                        </button>
                        <button @click="openDataBundleModal" :disabled="isPending('data-export')" :class="isPending('data-export') ? 'app-action-disabled' : ''"
                          class="px-4 py-1.5 rounded-lg bg-accent-primary hover:bg-accent-primary/85 text-on-accent-primary text-xs font-black shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.2)] transition-all" >
                          <span class="inline-flex items-center gap-1">
                            <LoaderCircle v-if="isPending('data-export')" class="h-3 w-3 animate-spin" />
                            {{ isPending('data-export') ? '读取中' : '导出软件数据' }}
                          </span>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div class="p-4 rounded-2xl bg-accent-special/5 border border-accent-special/20">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">环境与模组打包</h4>
                        <p class="text-xs text-text-dim leading-relaxed mt-1">
                          导入导出模组实体包。支持当前环境有效模组、当前启用模组导出，也支持附带环境数据的模组包导入。
                        </p>
                      </div>
                      <div class="flex items-center gap-2 shrink-0">
                        <button @click="openModPackageImportDialog" :disabled="isPending('mod-import')" :class="isPending('mod-import') ? 'app-action-disabled' : ''"
                          class="px-3 py-1.5 rounded-lg bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 text-xs font-bold transition-all" >
                          <span class="inline-flex items-center gap-1">
                            <LoaderCircle v-if="isPending('mod-import')" class="h-3 w-3 animate-spin" />
                            {{ isPending('mod-import') ? '读取中' : '导入模组包' }}
                          </span>
                        </button>
                        <button @click="openCurrentProfileExportDialog"
                          class="px-4 py-1.5 rounded-lg bg-accent-special hover:bg-accent-special/85 text-on-accent-special text-xs font-black shadow-[0_0_15px_rgba(var(--rgb-accent-cool),0.2)] transition-all" >
                          导出环境模组
                        </button>
                      </div>
                    </div>
                    <div class="mt-4 grid grid-cols-3 gap-4 items-center">
                      <div class="col-span-1 text-xs text-text-dim">
                        当前环境：<span class="font-bold text-text-main">{{ profileStore.currentProfile?.name || '未激活' }}</span>
                      </div>
                      <CommonSelect class="col-span-1" label="Mod文件夹重命名" v-model="formData.bundle_mod_folder_name_type" showBottom mini
                        description="影响打包Mod时的文件夹名称，默认原文件夹名称，处理优先级是 别名>模组名>默认，或者 工坊>ID包名>默认，所以即使Mod没有别名，也能按模组原名创建文件夹。"
                        :options="[{label:'默认', value:'default'},{label:'按别名', value:'alias_name'},{label:'按原模组名', value:'name'},{label:'按工坊ID', value:'workshop_id'},{label:'按包名', value:'package_id'}]" />
                      <CommonNumber class="col-span-1" label="打包压缩级别" v-model="formData.bundle_compress_level" :step="1" :min="0" :max="9" mini
                        description="0 最快，9 最省空间。默认 6。压缩级别越高，导出越慢，但包体通常更小。"  />
                    </div>
                  </div>
                  <div class="p-6 rounded-2xl bg-accent-danger/5 border border-accent-danger/20 space-y-4">
                    <h4 class="text-sm font-bold text-accent-danger uppercase">危险操作区</h4>
                    <p class="text-xs text-accent-danger/60 leading-relaxed">修复会尝试恢复当前的本地数据。修复成功后需要重启软件才能生效；如果修复失败，建议直接重置数据库。重置会清空分组、备注等本地数据，且无法撤销，请确认后再继续。</p>
                    <div class="grid grid-cols-2 gap-3">
                      <button @click="handleRepair" :disabled="appStore.isLoading"
                        class="w-full py-2 bg-accent-warn/10 hover:bg-accent-warn text-accent-warn hover:text-text-main border border-accent-warn/30 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50" >
                        强制修复本地数据库
                      </button>
                      <button @click="handleReset" :disabled="appStore.isLoading"
                        class="w-full py-2 bg-accent-danger/10 hover:bg-accent-danger text-accent-danger hover:text-text-main border border-accent-danger/30 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50" >
                        立即重置本地数据库
                      </button>
                    </div>
                  </div>
                </div>
              </section>

  <DataBundleExportModal
    :show="showDataBundleModal && appStore.uiState.showSettingsPanel"
    :schema="dataBundleSchema"
    @close="closeDataBundleModal"
  />
</template>

<script setup>
import { ref, watch } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import { formatFileSize } from '../../../shared/lib/format'
import { toast } from '../../../shared/lib/common'
import { useAppStore } from '../../../app/stores/appStore'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useProfileStore } from '../../profiles/profileStore'
import { useModStore } from '../../mod/stores/modStore'
import DataBundleExportModal from './DataBundleExportModal.vue'

const props = defineProps({
  formData: { type: Object, required: true },
})

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const profileStore = useProfileStore()
const modStore = useModStore()

const dataBundleSchema = ref({
  modules: [],
  profiles: [],
  presets: {},
  file_extension: '.rimcrowdata.zip',
})
const showDataBundleModal = ref(false)
const pendingAction = ref('')
const isPending = (action) => pendingAction.value === action
const runPendingAction = async (action, runner) => {
  if (pendingAction.value) return
  pendingAction.value = action
  try {
    await runner?.()
  } finally {
    pendingAction.value = ''
  }
}
const loadDataBundleSchema = async () => {
  // schema 由后端提供，前端只按模块定义渲染导出项，避免写死可打包范围。
  const schema = await appStore.getDataBundleSchema()
  if (!schema) return
  dataBundleSchema.value = schema
}

const openDataBundleModal = async () => {
  await runPendingAction('data-export', async () => {
    if (!(dataBundleSchema.value?.modules || []).length) {
      await loadDataBundleSchema()
    }
    showDataBundleModal.value = true
  })
}

const closeDataBundleModal = () => {
  showDataBundleModal.value = false
}

const handleClearRemoteImageCache = async () => {
  // 缓存清理不可撤销，先确认再执行，成功后用实际清理结果反馈用户。
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

const openDataBundleImportDialog = async () => {
  await runPendingAction('data-import', async () => {
    // 导入前先检查数据包内容，把冲突处理交给统一的迁移面板。
    const schema = await appStore.getDataBundleSchema()
    if (!schema) return

    const extensions = [
      schema.file_extension || '.rimcrowdata.zip',
      ...(Array.isArray(schema.legacy_file_extensions) ? schema.legacy_file_extensions : ['.rmmdata.zip', '.rmmdata']),
    ]
      .map(item => String(item || '').trim())
      .filter(Boolean)
    const bundlePath = await appStore.getFilePath('', [
      `RimCrow Data Package (${extensions.map(item => `*${item}`).join(';')})`,
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
  })
}

const openModPackageImportDialog = async () => {
  await runPendingAction('mod-import', async () => {
    // 模组包导入需要先根据当前可用安装目录确定默认落点，迁移面板仍允许用户后续调整。
    const schema = await appStore.getModPackageSchema()
    if (!schema) return

    const bundlePath = await appStore.getFilePath('', [
      `RimCrow Mod Package (*${schema.file_extension || '.rimcrowmods.zip'})`,
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
  })
}

const openCurrentProfileExportDialog = () => {
  // 导出当前环境时只提供可感知的范围选项，具体文件收集由打包流程统一处理。
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
    folder_name_type: props.formData?.bundle_mod_folder_name_type || appStore.settings.bundle_mod_folder_name_type || 'default',
  })
}

const handleReset = async () => {
  const ok = await confirmStore.confirmAction('确认重置', '重置后，分组、备注等本地数据将被清空，且无法撤销。确定继续吗？', { type: 'error' })
  if (ok) appStore.resetDatabase()
}

const handleRepair = async () => {
  // 修复成功后必须重启才能切换到修复后的数据库状态。
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

watch(() => appStore.uiState.showSettingsPanel, async (visible) => {
  if (visible) {
    await appStore.refreshRemoteImageCacheStats()
    return
  }
  closeDataBundleModal()
}, { immediate: true })
</script>
