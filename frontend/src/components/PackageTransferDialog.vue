<template>
  <CommonModalShell :show="appStore.uiState.showPackageTransferDialog" :title="dialogTitle" :description="dialogDesc" size="custom" :z-index="140" accent="primary"
    panel-class="max-h-[88vh] w-4/5 border-accent-primary/20" content-class="min-h-0 flex flex-col"
    @close="closeDialog" >
      <div class="absolute -top-18 -left-12 h-52 w-52 rounded-full bg-accent-primary/30 blur-3xl pointer-events-none"></div>
      <div class="absolute -bottom-18 -right-12 h-52 w-52 rounded-full bg-accent-special/10 blur-3xl pointer-events-none"></div>

      <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
        <div v-if="isImportMode" class="space-y-4">
          <section class="modal-section p-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-bold text-text-main">导入包文件</div>
                <div class="mt-1 text-xs text-text-dim">
                  {{ selectedBundlePath || '尚未选择文件' }}
                </div>
              </div>
              <button class="shrink-0 rounded-xl bg-accent-primary px-4 py-2 text-xs font-black text-on-accent-primary transition-all hover:bg-accent-primary/85"
                @click="pickImportBundle" >
                选择文件
              </button>
            </div>
          </section>

          <section v-if="inspectData" class="modal-section p-4">
            <div class="text-sm font-bold text-text-main">包摘要</div>
            <div class="mt-3 grid grid-cols-6 gap-3 text-xs text-text-dim">
              <div class="modal-section-subtle col-span-2 px-3 py-2">
                <div class="text-text-dim">格式</div>
                <div class="mt-1 font-mono text-text-main">{{ inspectData.format || '未知' }}</div>
              </div>
              <div class="modal-section-subtle col-span-2 px-3 py-2">
                <div class="text-text-dim">导出时间</div>
                <div class="mt-1 font-mono text-text-main">{{ inspectData.exported_at || '未知' }}</div>
              </div>
              <div v-if="dialogMode === 'mod-import'" class="modal-section-subtle px-3 py-2">
                <div class="text-text-dim">模组数量</div>
                <div class="mt-1 font-mono text-text-main">{{ inspectData.mods?.length || 0 }}</div>
              </div>
              <div class="modal-section-subtle px-3 py-2">
                <div class="text-text-dim">环境数据</div>
                <div class="mt-1 font-mono text-text-main">
                  {{ inspectData.has_environment_data || (inspectData.profiles?.length > 0) ? `包含 ${inspectData.profiles?.length || 0} 项` : '未附带' }}
                </div>
              </div>
              <div v-if="archiveSummary" class="modal-section-subtle col-span-2 px-3 py-2">
                <div class="text-text-dim">压缩包大小</div>
                <div class="mt-1 font-mono text-text-main">{{ archiveSummary.bundleSize }}</div>
              </div>
              <div v-if="archiveSummary" class="modal-section-subtle col-span-2 px-3 py-2">
                <div class="text-text-dim">预计解压后大小</div>
                <div class="mt-1 font-mono text-text-main">{{ archiveSummary.unpackedSize }}</div>
              </div>
              <div v-if="archiveSummary" class="modal-section-subtle col-span-2 px-3 py-2">
                <div class="text-text-dim">体积变化</div>
                <div class="mt-1 font-mono text-text-main">{{ archiveSummary.ratioText }}</div>
              </div>
              <div v-if="dialogMode === 'mod-import' && targetDiskSpaceSummary" class="rounded-xl border px-3 py-2 col-span-6"
                :class="targetDiskSpaceSummary.enough ? 'border-accent-tip/20 bg-accent-tip/8' : 'border-accent-danger/25 bg-accent-danger/8'" >
                <div class="text-text-dim">目标磁盘空间</div>
                <div class="mt-1 font-mono" :class="targetDiskSpaceSummary.enough ? 'text-text-main' : 'text-accent-danger'">
                  {{ targetDiskSpaceSummary.text }}
                </div>
              </div>
            </div>
          </section>

          <template v-if="dialogMode === 'mod-import' && inspectData">
            <section class="modal-section p-4">
              <div class="mb-3">
                <div class="text-sm font-bold text-text-main">导入设置</div>
                <div class="mt-1 text-xs text-text-dim">可以同时处理环境和模组。导入到当前环境目录或管理器目录时，当前列表会自动刷新。</div>
              </div>

              <div class="space-y-4">
                <label class="modal-section-subtle flex items-start gap-3 px-3 py-3">
                  <input v-model="modImportForm.import_mods" class="mt-0.5 accent-accent-primary" type="checkbox">
                  <div>
                    <div class="text-sm font-bold text-text-main">导入模组文件</div>
                    <div class="mt-1 text-xs leading-relaxed text-text-dim">
                      如果遇到同名文件夹，会按右侧规则处理。导入到管理器目录后，对应环境需要开启“使用管理器模组”。
                    </div>
                  </div>
                </label>

                <div v-if="modImportForm.import_mods" class="grid grid-cols-2 gap-3">
                  <label class="rounded-xl border px-3 py-3" :class="modImportForm.target_kind === 'game_install' ? 'border-accent-primary/35 bg-accent-primary/8' : 'border-border-base/10 bg-bg-inset/55'">
                    <div class="flex items-start gap-3">
                      <input v-model="modImportForm.target_kind" value="game_install" class="mt-0.5 accent-accent-primary" type="radio">
                      <div class="min-w-0">
                        <div class="text-sm font-bold text-text-main">导入到游戏模组目录</div>
                        <div class="mt-1 text-xs text-text-dim">会直接放进你选中的游戏目录里。</div>
                      </div>
                    </div>
                  </label>
                  <label class="rounded-xl border px-3 py-3" :class="modImportForm.target_kind === 'self_mods' ? 'border-accent-primary/35 bg-accent-primary/8' : 'border-border-base/10 bg-bg-inset/55'">
                    <div class="flex items-start gap-3">
                      <input v-model="modImportForm.target_kind" value="self_mods" class="mt-0.5 accent-accent-primary" type="radio">
                      <div class="min-w-0">
                        <div class="text-sm font-bold text-text-main">导入到管理器模组目录</div>
                        <div class="mt-1 text-xs leading-relaxed text-text-dim">
                          {{ selfModsPath || '还没有设置管理器模组目录' }}
                        </div>
                      </div>
                    </div>
                  </label>
                </div>

                <div v-if="modImportForm.import_mods && modImportForm.target_kind === 'game_install'" class="space-y-2">
                  <CommonSelect v-model="modImportForm.game_install_path" label="目标游戏本体" :options="availableInstallOptions" />
                  <div v-if="availableInstalls.length === 0" class="text-xs leading-relaxed text-accent-warn">
                    当前未发现有效游戏本体。仍可导入到管理器模组目录，或先配置有效本体后再导入。
                  </div>
                </div>

                <div v-if="modImportForm.import_mods && modImportForm.target_kind === 'self_mods'" class="rounded-xl border border-accent-warn/20 bg-accent-warn/8 px-3 py-3 text-xs leading-relaxed text-text-dim">
                  导入到管理器模组目录后，需要在对应环境开启 <span class="font-bold text-accent-warn">使用管理器模组</span> 才能正常使用。
                </div>

                <label v-if="inspectData.has_environment_data" class="modal-section-subtle flex items-start gap-3 px-3 py-3">
                  <input v-model="modImportForm.apply_environment_data" class="mt-0.5 accent-accent-primary" type="checkbox">
                  <div>
                    <div class="text-sm font-bold text-text-main">同时应用环境数据</div>
                    <div class="mt-1 text-xs leading-relaxed text-text-dim">
                      覆盖现有环境时，只会替换这个环境的实际使用数据，不会改名称、说明和绑定关系。新建环境时，会尽量保留原来的环境信息。
                    </div>
                  </div>
                </label>
              </div>
            </section>

            <section v-if="inspectData.has_environment_data"
              class="modal-section p-4" >
              <div class="mb-3">
                <div class="text-sm font-bold text-text-main">环境数据处理</div>
                <div class="mt-1 text-xs text-text-dim">环境重名时按名称判断。覆盖只替换实际使用数据，新建会尽量保留导入包里的环境信息。</div>
              </div>

              <div v-if="modImportForm.apply_environment_data && inspectData.profiles?.length" class="space-y-3">
                <div class="rounded-xl border border-accent-danger/20 bg-accent-danger/8 px-3 py-3 text-xs leading-relaxed text-text-dim">
                  覆盖环境会替换这个环境里的游戏设置、模组设置和存档排序等内容。
                </div>
                <ProfileConflictPlanEditor :rows="profilePlanRows" :available-installs="availableInstalls" @strategy="applyProfileStrategy" />
              </div>
              <div v-else class="modal-section-subtle px-3 py-3 text-xs leading-relaxed text-text-dim">
                当前包附带 {{ inspectData.profiles?.length || 0 }} 个环境。勾选“同时应用环境数据”后，再在这里选择重名环境的处理方式。
              </div>
            </section>
            

              <section class="modal-section p-4">
                <div class="mb-3">
                  <div class="text-sm font-bold text-text-main">同名模组处理</div>
                  <div class="mt-1 text-xs text-text-dim">这里只处理同名文件夹。你可以统一替换、跳过、另存为新文件夹，也可以逐项调整。</div>
                </div>

                <div v-if="modImportForm.import_mods && modConflictRows.length > 0" class="space-y-3">
                  <div class="modal-section-subtle px-3 py-3 text-xs leading-relaxed text-text-dim">
                    当前发现 {{ modConflictRows.length }} 个同名模组，导入时会按这里的规则处理。
                  </div>
                  <ModConflictPlanEditor
                    :rows="modConflictRows"
                    @strategy="applyModConflictStrategy"
                  />
                </div>
                <div v-else-if="modImportForm.import_mods" class="rounded-xl border border-accent-tip/20 bg-accent-tip/8 px-3 py-3 text-xs leading-relaxed text-text-dim">
                  当前没有发现同名模组，导入时会直接写入目标目录。
                </div>
                <div v-else class="modal-section-subtle px-3 py-3 text-xs leading-relaxed text-text-dim">
                  本次未勾选“导入模组文件”，这里只需要处理环境数据。
                </div>
              </section>
          </template>

          <section v-if="dialogMode === 'data-import' && inspectData" class="modal-section p-4">
            <div class="mb-3 text-sm font-bold text-text-main">环境导入冲突处理</div>
            <div class="mb-3 rounded-xl border border-accent-danger/20 bg-accent-danger/8 px-3 py-3 text-xs leading-relaxed text-text-dim">
              这里统一处理所有同名环境。覆盖时只替换环境里的实际使用数据；新建时会尽量保留导入包里的环境信息。
            </div>
            <ProfileConflictPlanEditor
              :rows="profilePlanRows"
              :available-installs="availableInstalls"
              @strategy="applyProfileStrategy"
            />
          </section>
        </div>

        <div v-else-if="dialogMode === 'mod-export'" class="space-y-4">
          <section class="modal-section p-4">
            <div class="text-sm font-bold text-text-main">导出来源</div>
            <div class="mt-2 text-xs leading-relaxed text-text-dim">{{ exportSummary }}</div>
          </section>

          <section v-if="exportScopeOptions.length > 0" class="modal-section p-4">
            <div class="mb-2 text-sm font-bold text-text-main">导出范围</div>
            <div class="grid grid-cols-2 gap-3">
              <label v-for="option in exportScopeOptions" :key="option.value" class="rounded-xl border px-3 py-3"
                :class="exportForm.export_scope === option.value ? 'border-accent-primary/35 bg-accent-primary/8' : 'border-border-base/10 bg-bg-inset/55'" >
                <div class="flex items-start gap-3">
                  <input v-model="exportForm.export_scope" class="mt-0.5 accent-accent-primary" :value="option.value" type="radio">
                  <div>
                    <div class="text-sm font-bold text-text-main">{{ option.label }}</div>
                    <div class="mt-1 text-xs text-text-dim">{{ option.description }}</div>
                  </div>
                </div>
              </label>
            </div>
          </section>

          <section v-if="showExportExtraOptions" class="modal-section p-4">
            <div class="mb-2 text-sm font-bold text-text-main">附加导出选项</div>
            <div class="modal-section-subtle mb-3 px-3 py-2 text-xs text-text-dim">
              {{ extraExportSummary }}
            </div>
            <div class="grid grid-cols-3 gap-3">
              <label class="modal-section-subtle px-3 py-3">
                <div class="flex items-start gap-3">
                  <input v-model="exportForm.include_dependencies" class="mt-0.5 accent-accent-primary" type="checkbox">
                  <div>
                    <div class="text-sm font-bold text-text-main">附带依赖</div>
                    <div class="mt-1 text-xs text-text-dim">把相关依赖一起带上，减少导入后缺项。</div>
                  </div>
                </div>
              </label>
              <label class="modal-section-subtle px-3 py-3">
                <div class="flex items-start gap-3">
                  <input v-model="exportForm.include_interlocks" class="mt-0.5 accent-accent-primary" type="checkbox">
                  <div>
                    <div class="text-sm font-bold text-text-main">附带联锁项</div>
                    <div class="mt-1 text-xs text-text-dim">把成套使用的相关模组一起带上。</div>
                  </div>
                </div>
              </label>
              <label class="modal-section-subtle px-3 py-3">
                <div class="flex items-start gap-3">
                  <input v-model="exportForm.include_language_packs" class="mt-0.5 accent-accent-primary" type="checkbox">
                  <div>
                    <div class="text-sm font-bold text-text-main">附带语言包</div>
                    <div class="mt-1 text-xs text-text-dim">把相关汉化或语言包一起带上。</div>
                  </div>
                </div>
              </label>
            </div>
          </section>

          <section class="modal-section p-4 grid grid-cols-2 gap-3">
            <label v-if="allowExportEnvironmentAttach" class="modal-section-subtle flex items-start gap-3 px-3 py-3">
              <input v-model="exportForm.include_environment_data" class="mt-0.5 accent-accent-primary" type="checkbox">
              <div>
                <div class="text-sm font-bold text-text-main">附带当前环境数据</div>
                <div class="mt-1 text-xs leading-relaxed text-text-dim">
                  会把当前环境数据一起带上，包括模组排序、配置文件等，方便在另一台机器上继续使用。
                </div>
              </div>
            </label>
          
            <CommonSelect v-model="exportForm.folder_name_type" label="包内Mod文件夹命名" showBottom
              description="只影响导出包里的文件夹名称，不会改动原始Mod目录。遇到不适合作为文件名的字符会自动替换，重名会自动追加序号。"
              :options="modFolderNameTypeOptions" />
          </section>
        </div>
      </div>

<template #footer>
      <div class="flex items-center justify-between gap-4">
        <div class="text-xs leading-relaxed text-text-dim">
          <template v-if="dialogMode === 'mod-import'">
            导入到当前环境目录或管理器目录时会自动刷新当前模组列表。缺少本地文件的模组会跳过并提醒你。
          </template>
          <template v-else-if="dialogMode === 'data-import'">
            环境重名时会按你的选择处理，其它数据仍按原流程导入。
          </template>
          <template v-else>
            如果同一个模组有多个来源，会优先带上你当前正在使用的版本，重复副本会自动跳过。
          </template>
        </div>
        <div class="flex items-center gap-2">
          <button class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-xs font-bold text-text-main transition-all hover:bg-bg-overlay/10"
            @click="closeDialog" >
            关闭
          </button>
          <button class="rounded-xl bg-accent-primary px-5 py-2 text-sm font-black text-on-accent-primary transition-all hover:bg-accent-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canSubmit" @click="handleSubmit" >
            {{ submitLabel }}
          </button>
        </div>
      </div>
    </template>
  </CommonModalShell>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useAppStore } from '../stores/appStore'
import { useModStore } from '../stores/modStore'
import { useProfileStore } from '../stores/profileStore'
import { formatFileSize } from '../utils/format'
import { toast } from '../utils/common'
import CommonSelect from './common/input/CommonSelect.vue'
import ProfileConflictPlanEditor from './packageTransfer/ProfileConflictPlanEditor.vue'
import ModConflictPlanEditor from './packageTransfer/ModConflictPlanEditor.vue'
import CommonModalShell from './common/CommonModalShell.vue'

const appStore = useAppStore()
const modStore = useModStore()
const profileStore = useProfileStore()

const dialogMode = computed(() => String(appStore.packageTransferDialog.mode || 'mod-import'))
const dialogPreset = computed(() => appStore.packageTransferDialog.preset || {})
const isImportMode = computed(() => dialogMode.value === 'mod-import' || dialogMode.value === 'data-import')

const modPackageSchema = ref(null)
const dataBundleSchema = ref(null)
const inspectData = ref(null)
const selectedBundlePath = ref('')
const lastPreparedImportTargetKey = ref('')

const exportForm = reactive({
  profile_id: '',
  export_scope: 'custom',
  mod_ids: [],
  folder_name_type: 'default',
  include_dependencies: false,
  include_interlocks: false,
  include_language_packs: false,
  include_environment_data: false,
})

const modFolderNameTypeOptions = [
  { label: '默认', value: 'default' },
  { label: '按别名', value: 'alias_name' },
  { label: '按原模组名', value: 'name' },
  { label: '按工坊ID', value: 'workshop_id' },
  { label: '按包名', value: 'package_id' },
]

const modImportForm = reactive({
  import_mods: true,
  target_kind: 'game_install',
  game_install_path: '',
  apply_environment_data: false,
})

const profilePlanRows = ref([])
const modConflictRows = ref([])

const availableInstalls = computed(() => {
  const raw = inspectData.value?.available_installs || modPackageSchema.value?.available_installs || dataBundleSchema.value?.available_installs || []
  return Array.isArray(raw) ? raw : []
})
const availableInstallOptions = computed(() => {
  const options = availableInstalls.value.map(install => ({
    value: String(install.install_path || ''),
    label: `${install.game_version || '版本未知'} | ${install.install_path || '路径未知'}`,
  }))
  return [
    {
      value: '',
      label: availableInstalls.value.length ? '请选择一个可用游戏本体' : '当前无可用游戏本体',
    },
    ...options,
  ]
})
const selfModsPath = computed(() => String(modPackageSchema.value?.self_mods_path || appStore.settings.self_mods_path || '').trim())
const archiveSummary = computed(() => {
  const archiveStats = inspectData.value?.archive_stats || {}
  const bundleSizeBytes = Number(inspectData.value?.bundle_size_bytes || 0)
  const unpackedBytes = Number(archiveStats.uncompressed_bytes || 0)
  const expansionRatio = Number(archiveStats.expansion_ratio || 0)
  if (bundleSizeBytes <= 0 && unpackedBytes <= 0) return null
  return {
    bundleSize: formatFileSize(bundleSizeBytes || Number(archiveStats.compressed_bytes || 0)),
    unpackedSize: formatFileSize(unpackedBytes),
    ratioText: expansionRatio > 0
      ? `解压后约为压缩内容的 ${expansionRatio.toFixed(2)} 倍`
      : '当前无法估算体积变化',
  }
})
const targetDiskSpaceSummary = computed(() => {
  const disk = inspectData.value?.target_disk_space
  if (!disk) return null
  const enough = !!disk.enough
  const freeText = formatFileSize(Number(disk.free_bytes || 0))
  const recommendedText = formatFileSize(Number(disk.recommended_bytes || 0))
  return {
    enough,
    text: `当前剩余 ${freeText}，按这次导入建议至少预留 ${recommendedText}`,
  }
})

const dialogTitle = computed(() => {
  if (dialogMode.value === 'mod-export') return dialogPreset.value?.title || '导出模组打包'
  if (dialogMode.value === 'data-import') return '导入软件数据包'
  return '导入模组打包'
})

const dialogDesc = computed(() => {
  if (dialogMode.value === 'mod-export') return dialogPreset.value?.description || '把模组文件打成一个包，按需把当前环境数据一起带上。'
  if (dialogMode.value === 'data-import') return '导入软件数据，遇到重名环境时按你的选择处理。'
  return '导入模组包，目标可选游戏目录或管理器模组目录。'
})

const exportScopeOptions = computed(() => {
  const options = Array.isArray(dialogPreset.value?.scopeOptions) ? dialogPreset.value.scopeOptions : []
  return options
})
const allowExportEnvironmentAttach = computed(() => !!dialogPreset.value?.sourceProfile)
const showExportExtraOptions = computed(() => dialogMode.value === 'mod-export' && !!dialogPreset.value?.allowExtraOptions)
const exportPreview = computed(() => {
  if (dialogMode.value !== 'mod-export') return null
  return modStore.resolveCurrentExportPlan({
    exportScope: exportForm.export_scope,
    modIds: exportForm.mod_ids,
    includeDependencies: exportForm.include_dependencies,
    includeInterlocks: exportForm.include_interlocks,
    includeLanguagePacks: exportForm.include_language_packs,
  })
})
const resolvedExportModIds = computed(() => {
  if (dialogMode.value !== 'mod-export') return []
  const resolvedIds = Array.isArray(exportPreview.value?.mod_ids) ? exportPreview.value.mod_ids : exportForm.mod_ids
  return [...new Set((resolvedIds || []).map(id => String(id || '').trim()).filter(Boolean))]
})
const formatExportPlanSummary = (selectedCount = 0, resolvedCount = 0, extraCount = 0, compact = false) => {
  if (extraCount > 0) {
    return compact
      ? `当前选中 ${selectedCount} 个，预计会多带上 ${extraCount} 个相关模组，合计导出 ${resolvedCount} 个。`
      : `当前选中 ${selectedCount} 个模组，预计导出 ${resolvedCount} 个，其中附加带上 ${extraCount} 个。`
  }
  return `当前选中 ${selectedCount} 个${compact ? '' : '模组'}，预计导出 ${resolvedCount} 个。`
}
const exportSummary = computed(() => {
  if (dialogMode.value === 'mod-export' && exportPreview.value) {
    const selectedCount = Number(exportPreview.value?.selected_count || 0)
    const resolvedCount = Number(exportPreview.value?.mod_count || selectedCount || 0)
    const extraCount = Number(exportPreview.value?.extra_count || 0)
    const summary = formatExportPlanSummary(selectedCount, resolvedCount, extraCount, false)
    if (dialogPreset.value?.sourceProfile) {
      const profileName = dialogPreset.value?.profileName || profileStore.currentProfile?.name || '当前环境'
      if (dialogPreset.value?.scopeOptionsLoading) {
        return `当前来源：${profileName}。正在读取这个环境的模组统计。`
      }
      return `当前来源：${profileName}。${summary}`
    }
    return summary
  }
  if (dialogPreset.value?.summary) return dialogPreset.value.summary
  const count = Array.isArray(dialogPreset.value?.mod_ids) ? dialogPreset.value.mod_ids.length : 0
  return count > 0 ? `已选 ${count} 个模组。` : '将按当前设置导出。'
})
const extraExportSummary = computed(() => {
  const selectedCount = Number(exportPreview.value?.selected_count || 0)
  const resolvedCount = Number(exportPreview.value?.mod_count || selectedCount || 0)
  const extraCount = Number(exportPreview.value?.extra_count || 0)
  return formatExportPlanSummary(selectedCount, resolvedCount, extraCount, true)
})

const canSubmit = computed(() => {
  if (dialogMode.value === 'mod-export') {
    if (!exportForm.profile_id && dialogPreset.value?.sourceProfile) return false
    return resolvedExportModIds.value.length > 0
  }
  if (!selectedBundlePath.value || !inspectData.value) return false
  if (dialogMode.value === 'data-import') return validateProfileRows()
  if (!modImportForm.import_mods && !modImportForm.apply_environment_data) return false
  if (modImportForm.import_mods) {
    if (modImportForm.target_kind === 'game_install' && !modImportForm.game_install_path) return false
    if (modImportForm.target_kind === 'self_mods' && !selfModsPath.value) return false
  }
  if (modImportForm.apply_environment_data && !validateProfileRows()) return false
  if (modImportForm.import_mods && !validateModConflictRows()) return false
  return true
})

const submitLabel = computed(() => {
  if (dialogMode.value === 'mod-export') return '开始导出'
  return '开始导入'
})

const closeDialog = () => {
  appStore.closePackageTransferDialog()
}

const buildImportTargetKey = () => (
  `${selectedBundlePath.value}::${modImportForm.target_kind}::${modImportForm.game_install_path}`
)

const resetState = () => {
  selectedBundlePath.value = String(dialogPreset.value?.bundlePath || '')
  inspectData.value = dialogPreset.value?.inspectData || null
  profilePlanRows.value = buildProfileRows(inspectData.value)
  modConflictRows.value = buildModConflictRows(inspectData.value)
  exportForm.profile_id = String(dialogPreset.value?.profileId || profileStore.currentProfile?.id || appStore.settings.current_profile_id || 'default')
  exportForm.export_scope = String(dialogPreset.value?.export_scope || (exportScopeOptions.value[0]?.value || 'custom'))
  exportForm.mod_ids = Array.isArray(dialogPreset.value?.mod_ids) ? [...dialogPreset.value.mod_ids] : []
  exportForm.folder_name_type = String(dialogPreset.value?.folder_name_type || dialogPreset.value?.folderNameType || appStore.settings.bundle_mod_folder_name_type || 'default')
  exportForm.include_dependencies = !!dialogPreset.value?.include_dependencies
  exportForm.include_interlocks = !!dialogPreset.value?.include_interlocks
  exportForm.include_language_packs = !!dialogPreset.value?.include_language_packs
  exportForm.include_environment_data = !!dialogPreset.value?.include_environment_data
  modImportForm.import_mods = dialogMode.value === 'mod-import'
  modImportForm.target_kind = String(dialogPreset.value?.targetKind || (availableInstalls.value.length > 0 ? 'game_install' : 'self_mods'))
  modImportForm.game_install_path = String(dialogPreset.value?.gameInstallPath || availableInstalls.value[0]?.install_path || '')
  modImportForm.apply_environment_data = false
  lastPreparedImportTargetKey.value = (dialogMode.value === 'mod-import' && inspectData.value)
    ? buildImportTargetKey()
    : ''
}

const loadSchemas = async () => {
  if (dialogMode.value === 'mod-import' || dialogMode.value === 'mod-export') {
    modPackageSchema.value = dialogPreset.value?.modPackageSchema || modPackageSchema.value
    if (!modPackageSchema.value) {
      modPackageSchema.value = await appStore.getModPackageSchema()
    }
  }
  if (dialogMode.value === 'data-import') {
    dataBundleSchema.value = dialogPreset.value?.dataBundleSchema || dataBundleSchema.value
    if (!dataBundleSchema.value) {
      dataBundleSchema.value = await appStore.getDataBundleSchema()
    }
  }
}

watch(
  () => appStore.uiState.showPackageTransferDialog,
  async (visible) => {
    if (!visible) return
    await loadSchemas()
    resetState()
  }
)

const buildProfileRows = (inspect) => {
  const entries = Array.isArray(inspect?.profile_conflicts) ? inspect.profile_conflicts : []
  return entries.map((entry) => {
    const conflicts = Array.isArray(entry?.conflicts) ? entry.conflicts : []
    return reactive({
      archive_key: String(entry?.archive_key || ''),
      name: String(entry?.name || ''),
      conflicts,
      mode: 'create',
      target_profile_id: conflicts[0]?.profile_id || '',
      game_install_path: '',
    })
  })
}

const applyProfileStrategy = (strategy) => {
  profilePlanRows.value.forEach((row) => {
    if (strategy === 'overwrite_all' && row.conflicts.length > 0) {
      row.mode = 'overwrite'
      row.target_profile_id = row.target_profile_id || row.conflicts[0]?.profile_id || ''
      return
    }
    if (strategy === 'skip_all') {
      row.mode = 'skip'
      return
    }
    if (strategy === 'create_all') {
      row.mode = 'create'
    }
  })
}

const buildModConflictRows = (inspect) => {
  const entries = Array.isArray(inspect?.mod_conflicts) ? inspect.mod_conflicts : []
  return entries.map((entry) => reactive({
    folder_name: String(entry?.folder_name || ''),
    existing_path: String(entry?.existing_path || ''),
    mode: 'overwrite',
    rename_to: '',
  }))
}

const applyModConflictStrategy = (strategy) => {
  modConflictRows.value.forEach((row) => {
    if (strategy === 'overwrite_all') row.mode = 'overwrite'
    else if (strategy === 'skip_all') row.mode = 'skip'
    else if (strategy === 'rename_all') row.mode = 'rename'
  })
}

const validateProfileRows = () => {
  for (const row of profilePlanRows.value) {
    if (row.mode === 'overwrite' && !row.target_profile_id) return false
  }
  return true
}

const validateModConflictRows = () => {
  for (const row of modConflictRows.value) {
    if (row.mode === 'rename' && row.rename_to && (row.rename_to.includes('/') || row.rename_to.includes('\\'))) return false
  }
  return true
}

const getBundleFilters = () => {
  if (dialogMode.value === 'data-import') {
    const extensions = [
      dataBundleSchema.value?.file_extension || '.rmmdata.zip',
      ...(Array.isArray(dataBundleSchema.value?.legacy_file_extensions) ? dataBundleSchema.value.legacy_file_extensions : ['.rmmdata']),
    ]
      .map(item => String(item || '').trim())
      .filter(Boolean)
    return [`RMM Data Package (${extensions.map(item => `*${item}`).join(';')})`, 'All Files (*.*)']
  }
  return [`RMM Mod Package (*${modPackageSchema.value?.file_extension || '.rmmmods.zip'})`, 'All Files (*.*)']
}

const pickImportBundle = async () => {
  const bundlePath = await appStore.getFilePath('', getBundleFilters())
  if (!bundlePath) return
  selectedBundlePath.value = bundlePath
  if (dialogMode.value === 'data-import') {
    inspectData.value = await appStore.inspectDataBundle(bundlePath)
  } else {
    inspectData.value = await appStore.prepareModPackageImport(bundlePath, {
      target_kind: modImportForm.target_kind,
      game_install_path: modImportForm.game_install_path,
    })
  }
  if (!inspectData.value) return
  lastPreparedImportTargetKey.value = dialogMode.value === 'mod-import' ? buildImportTargetKey() : ''
  profilePlanRows.value = buildProfileRows(inspectData.value)
  modConflictRows.value = buildModConflictRows(inspectData.value)
}

watch(
  () => [modImportForm.target_kind, modImportForm.game_install_path],
  async () => {
    if (dialogMode.value !== 'mod-import' || !selectedBundlePath.value) return
    const targetKey = buildImportTargetKey()
    if (targetKey === lastPreparedImportTargetKey.value) return
    inspectData.value = await appStore.prepareModPackageImport(selectedBundlePath.value, {
      target_kind: modImportForm.target_kind,
      game_install_path: modImportForm.game_install_path,
    })
    if (!inspectData.value) return
    lastPreparedImportTargetKey.value = targetKey
    modConflictRows.value = buildModConflictRows(inspectData.value)
  }
)

const buildProfileImportPlan = () => profilePlanRows.value.map((row) => ({
  archive_key: row.archive_key,
  mode: row.mode,
  target_profile_id: row.mode === 'overwrite' ? row.target_profile_id : '',
  game_install_path: row.mode === 'create' ? row.game_install_path : '',
}))

const buildModConflictPlan = () => modConflictRows.value.map((row) => ({
  folder_name: row.folder_name,
  mode: row.mode,
  rename_to: row.mode === 'rename' ? String(row.rename_to || '').trim() : '',
}))

const handleSubmit = async () => {
  if (dialogMode.value === 'mod-export') {
    const exportPromise = appStore.exportModPackage({
      profile_id: exportForm.profile_id,
      export_scope: exportForm.export_scope,
      mod_ids: resolvedExportModIds.value,
      include_dependencies: showExportExtraOptions.value ? false : exportForm.include_dependencies,
      include_interlocks: showExportExtraOptions.value ? false : exportForm.include_interlocks,
      include_language_packs: showExportExtraOptions.value ? false : exportForm.include_language_packs,
      include_environment_data: allowExportEnvironmentAttach.value && exportForm.include_environment_data,
      folder_name_type: exportForm.folder_name_type || 'default',
    })
    closeDialog()
    const exported = await exportPromise
    if (!exported) return
    return
  }

  if (dialogMode.value === 'data-import') {
    const imported = await appStore.importDataBundle(selectedBundlePath.value, {
      profile_import_plan: buildProfileImportPlan(),
    })
    if (imported) closeDialog()
    return
  }

  const imported = await appStore.importModPackage(selectedBundlePath.value, {
    import_mods: modImportForm.import_mods,
    target_kind: modImportForm.target_kind,
    game_install_path: modImportForm.game_install_path,
    apply_environment_data: modImportForm.apply_environment_data,
    profile_import_plan: buildProfileImportPlan(),
    mod_conflict_plan: buildModConflictPlan(),
  })
  if (imported) closeDialog()
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border-subtle);
  border-radius: 999px;
}
</style>
