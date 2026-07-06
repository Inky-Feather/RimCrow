<template>
  <CommonModalShell :show="show" size="compact" accent="special" panel-class="border-accent-special/20"
    content-class="min-h-0 flex flex-col" :title="resolvedTitle"
    :description="t('dialog.recommendation_export.description', '导出「{sourceName}」中的 {count} 个模组介绍。', { sourceName: resolvedSourceName, count: exportMods.length })"
    @close="emit('close')">
    <div class="flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
      <div class="grid grid-cols-2 gap-3">
        <CommonInput class="col-span-2" :label="t('dialog.recommendation_export.export_name', '导出名称')" v-model="form.exportName" :placeholder="t('dialog.recommendation_export.export_name_placeholder', '例如：RimWorld 必备模组推荐')" />
        <CommonSelect :label="t('dialog.recommendation_export.format_label', '导出格式')" v-model="form.format" :options="formatOptions" />
        <CommonSelect :label="t('dialog.recommendation_export.body_source', '介绍内容')" v-model="form.bodySource" :options="bodySourceOptions" />
        <CommonSelect v-if="form.format === 'image'" :label="t('dialog.recommendation_export.image_name_source', '图片文件名')" v-model="form.imageNameSource" :options="imageNameOptions" />
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <CommonSwitch :label="t('dialog.recommendation_export.option.sequence', '序号')" v-model="form.includeSequence" :description="t('dialog.recommendation_export.option.sequence_desc', '在每个模组前显示 001、002 这类序号。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.cover', '封面图')" v-model="form.includeCover" :description="coverDescription" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.tags', '标签')" v-model="form.includeTags" :description="t('dialog.recommendation_export.option.tags_desc', '导出为 #tag1 #tag2 形式。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.groups', '分组')" v-model="form.includeGroupNames" :description="t('dialog.recommendation_export.option.groups_desc', '导出该模组所属分组名称。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.authors', '作者')" v-model="form.includeAuthors" :description="t('dialog.recommendation_export.option.authors_desc', '导出模组作者名称。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.supported_versions', '支持版本')" v-model="form.includeSupportedVersions" :description="t('dialog.recommendation_export.option.supported_versions_desc', '导出模组支持的游戏版本。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.language_packs', '附加语言包')" v-model="form.includeLanguagePacks" :description="t('dialog.recommendation_export.option.language_packs_desc', '把匹配的语言包名称和网址附在对应模组后。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.workshop_id', '工坊 ID')" v-model="form.includeWorkshopId" :description="t('dialog.recommendation_export.option.workshop_id_desc', '导出 Steam 创意工坊 ID。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.url', '网址')" v-model="form.includeUrl" :description="t('dialog.recommendation_export.option.url_desc', '导出模组来源网址。')" />
        <CommonSwitch :label="t('dialog.recommendation_export.option.package_id', '包名')" v-model="form.includePackageId" :description="t('dialog.recommendation_export.option.package_id_desc', '默认隐藏，适合需要精确定位时开启。')" />
      </div>

      <div class="mt-4 rounded-lg border border-border-base/10 bg-bg-inset/45 px-3 py-2">
        <div class="flex items-center justify-between gap-3">
          <span class="text-xs font-bold text-text-dim uppercase tracking-wider">{{ t('dialog.recommendation_export.preview_title', '预览') }}</span>
          <span class="text-xs text-text-dim">{{ t('dialog.recommendation_export.mod_count', '{count} 个模组', { count: exportMods.length }) }}</span>
        </div>
        <pre class="mt-2 max-h-44 overflow-auto whitespace-pre-wrap wrap-break-word text-xs leading-relaxed text-text-soft custom-scrollbar">{{ previewText }}</pre>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-between gap-4">
        <p class="min-w-0 text-xs leading-relaxed text-text-dim">
          <span v-html="footerTip"></span>
        </p>
        <button @click="handleExport" :disabled="isExporting || exportMods.length === 0"
          class="shrink-0 rounded-xl bg-accent-special px-5 py-2 text-sm font-black text-on-accent-special transition-all hover:bg-accent-special/85 disabled:cursor-not-allowed disabled:opacity-50">
          {{ isExporting ? t('dialog.recommendation_export.exporting', '导出中...') : t('dialog.recommendation_export.start_export', '开始导出') }}
        </button>
      </div>
    </template>
  </CommonModalShell>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import CommonInput from '../../shared/components/input/CommonInput.vue'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'
import { checkResult, toast } from '../../shared/lib/common'
import { useAppStore } from '../../app/stores/appStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useGroupStore } from './stores/groupStore'
import { useModStore } from './stores/modStore'
import { t } from '../../shared/i18n'

const props = defineProps({
  show: Boolean,
  title: { type: String, default: '' },
  sourceName: { type: String, default: '' },
  modIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['close'])

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const groupStore = useGroupStore()
const modStore = useModStore()

const isExporting = ref(false)
const form = reactive({
  exportName: '',
  format: 'markdown',
  bodySource: 'notes',
  imageNameSource: 'alias',
  includeSequence: true,
  includeCover: true,
  includeTags: true,
  includeGroupNames: true,
  includeAuthors: true,
  includeSupportedVersions: true,
  includeLanguagePacks: false,
  includePackageId: false,
  includeWorkshopId: true,
  includeUrl: true,
})

const formatOptions = computed(() => [
  { value: 'clipboard', label: t('dialog.recommendation_export.format.clipboard', '复制纯文本') },
  { value: 'txt', label: 'TXT' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'docx', label: 'DOCX' },
  { value: 'pdf', label: 'PDF' },
  { value: 'image', label: t('dialog.recommendation_export.format.image', '纯图片') },
])
const bodySourceOptions = computed(() => [
  { value: 'notes', label: t('dialog.recommendation_export.body.notes', '备注') },
  { value: 'description', label: t('dialog.recommendation_export.body.description', '原始描述') },
])
const imageNameOptions = computed(() => [
  { value: 'alias', label: t('dialog.recommendation_export.image_name.alias', '别名') },
  { value: 'original', label: t('dialog.recommendation_export.image_name.original', '原名') },
])

// 弹窗打开时只接收 ID，模组内容实时从 store 取，避免导出前编辑别名/备注后仍使用旧快照。
const exportMods = computed(() => (
  [...new Set((props.modIds || []).map(id => String(id || '').trim()).filter(Boolean))]
    .map(id => modStore.takeModById(id))
    .filter(Boolean)
    .filter(mod => !modStore.isLanguagePackMod(mod))
))
const resolvedTitle = computed(() => String(props.title || '').trim() || t('dialog.recommendation_export.title', '推荐导出'))
const resolvedSourceName = computed(() => String(props.sourceName || '').trim() || t('ui.app.recommendation_export.source_selected_mods', '已选模组'))
const defaultExportName = computed(() => {
  const sourceName = resolvedSourceName.value
  return sourceName && sourceName !== t('ui.app.recommendation_export.source_selected_mods', '已选模组')
    ? t('dialog.recommendation_export.default_name_with_source', '{sourceName}推荐清单', { sourceName })
    : t('dialog.recommendation_export.default_name', '模组推荐清单')
})
const exportName = computed(() => String(form.exportName || '').trim() || defaultExportName.value)
const coverDescription = computed(() => (
  ['clipboard', 'txt'].includes(form.format)
    ? t('dialog.recommendation_export.cover_plain_desc', '纯文本和 TXT 不包含图片。')
    : t('dialog.recommendation_export.cover_rich_desc', 'Markdown 会复制图片，DOCX/PDF/纯图片会嵌入封面。')
))
const footerTip = computed(() => t('dialog.recommendation_export.footer_tip', 'Markdown 会在导出目录内创建 <span class="font-bold text-accent-special">img</span> 文件夹；纯图片会按导出名称新建文件夹，每个模组一张图。'))

const normalizeTextList = (values) => {
  // 导出内容里分组和作者都按列表处理，先清理空值和重复项，避免生成结果出现多余分隔符。
  const source = Array.isArray(values) ? values : [values]
  return [...new Set(source.map(value => String(value || '').trim()).filter(Boolean))]
}

const takeGroupNamesByMod = (mod) => {
  const groups = groupStore.takeGroupsByModId(mod?.package_id)
  return normalizeTextList(groups.map(group => group?.name))
}

const normalizePackageId = (value) => String(value || '').trim().toLowerCase()
const activeCanonicalIdSet = computed(() => new Set((modStore.activeIds || []).map(normalizePackageId).filter(Boolean)))

const takeLanguagePacksByMod = (mod) => {
  if (!form.includeLanguagePacks || !mod || modStore.isLanguagePackMod(mod) || modStore.isDeclaredForCurrentLanguage(mod)) return []
  const ownerId = normalizePackageId(mod.package_id)
  if (!ownerId) return []
  const strictPacks = []
  const fallbackPacks = []
  for (const languagePack of modStore.allModsMap.values()) {
    if (!modStore.isLanguagePackMod(languagePack) || !modStore.canUseLanguagePackForIssueDetection(languagePack)) continue
    if (!modStore.getLanguagePackOwnerIds(languagePack).includes(ownerId)) continue
    ;(modStore.isDeclaredForCurrentLanguage(languagePack) ? strictPacks : fallbackPacks).push(languagePack)
  }
  const activePack = [...strictPacks, ...fallbackPacks].find(languagePack => (
    activeCanonicalIdSet.value.has(normalizePackageId(languagePack?.package_id))
  ))
  const pickedPack = activePack || strictPacks[0] || fallbackPacks[0]
  return pickedPack ? [pickedPack] : []
}

// 只把推荐导出需要的字段传给后端，避免把完整 Mod 对象里的运行态字段写进文档。
const buildPayload = () => ({
  format: form.format,
  source_name: exportName.value,
  options: {
    include_sequence: form.includeSequence,
    include_cover: form.includeCover,
    include_tags: form.includeTags,
    include_group_names: form.includeGroupNames,
    include_authors: form.includeAuthors,
    include_supported_versions: form.includeSupportedVersions,
    include_language_packs: form.includeLanguagePacks,
    include_package_id: form.includePackageId,
    include_workshop_id: form.includeWorkshopId,
    include_url: form.includeUrl,
    body_source: form.bodySource,
    image_name_source: form.imageNameSource,
  },
  mods: exportMods.value.map(mod => ({
    package_id: mod.package_id,
    package_id_raw: mod.package_id_raw || mod.package_id,
    name: mod.name,
    display_name: modStore.displayModName(mod),
    alias_name: mod.alias_name,
    notes: mod.notes,
    description: mod.description,
    tags: mod.tags || [],
    group_names: takeGroupNamesByMod(mod),
    author: normalizeTextList(mod.author || []),
    supported_versions: normalizeTextList(mod.supported_versions || []),
    language_packs: takeLanguagePacksByMod(mod).map(languagePack => ({
      name: languagePack.name || languagePack.package_id,
      url: languagePack.url,
    })),
    workshop_id: mod.workshop_id,
    url: mod.url,
    preview_path: mod.preview_path,
    icon_path: mod.icon_path,
  })),
})

const previewText = computed(() => {
  const mod = exportMods.value[0]
  if (!mod) return t('dialog.recommendation_export.preview_empty', '当前没有可导出的模组。')
  // 预览只展示第一个模组，用来确认字段顺序和开关效果，不渲染完整清单以免弹窗过重。
  const lines = []
  const name = modStore.displayModName(mod)
  const originalName = mod.name || mod.package_id || t('common.entity.unknown_mod', '未知模组')
  const titleOnlyFormat = ['markdown', 'docx', 'pdf', 'image'].includes(form.format)
  if (form.includeSequence || titleOnlyFormat) {
    lines.push(`${form.includeSequence ? '001. ' : ''}${name}`)
  } else {
    lines.push(t('dialog.recommendation_export.preview.name', '名称：{name}', { name }))
  }
  if (mod.alias_name && mod.alias_name !== originalName) {
    lines.push(t('dialog.recommendation_export.preview.original_name', '原名：{name}', { name: originalName }))
  }
  if (form.includeTags && mod.tags?.length) lines.push(mod.tags.map(tag => `#${tag}`).join(' '))
  const groupNames = takeGroupNamesByMod(mod)
  if (form.includeGroupNames && groupNames.length) lines.push(t('dialog.recommendation_export.preview.groups', '分组：{groups}', { groups: groupNames.join('、') }))
  const authors = normalizeTextList(mod.author || [])
  if (form.includeAuthors && authors.length) lines.push(t('dialog.recommendation_export.preview.authors', '作者：{authors}', { authors: authors.join('、') }))
  const supportedVersions = normalizeTextList(mod.supported_versions || [])
  if (form.includeSupportedVersions && supportedVersions.length) lines.push(t('dialog.recommendation_export.preview.supported_versions', '支持版本：{versions}', { versions: supportedVersions.join('、') }))
  lines.push(t('dialog.recommendation_export.preview.intro', '介绍：{text}', { text: form.bodySource === 'description' ? (mod.description || t('ui.common.no_description', '暂无介绍')) : (mod.notes || t('ui.common.no_description', '暂无介绍')) }))
  if (form.includePackageId) lines.push(t('dialog.recommendation_export.preview.package_id', '包名：{packageId}', { packageId: mod.package_id_raw || mod.package_id }))
  if (form.includeWorkshopId && mod.workshop_id) lines.push(t('dialog.recommendation_export.preview.workshop_id', '工坊ID：{workshopId}', { workshopId: mod.workshop_id }))
  if (form.includeUrl && mod.url) lines.push(t('dialog.recommendation_export.preview.url', '网址：{url}', { url: mod.url }))
  takeLanguagePacksByMod(mod).forEach(languagePack => {
    lines.push(t('dialog.recommendation_export.preview.language_pack', '语言包：{name}', { name: languagePack.name || languagePack.package_id }))
    if (languagePack.url) lines.push(t('dialog.recommendation_export.preview.language_pack_url', '语言包网址：{url}', { url: languagePack.url }))
  })
  return lines.join('\n')
})

const copyTextToClipboard = async (text) => {
  const value = String(text || '')
  if (!value) return false
  try {
    // 浏览器剪贴板 API 必须在前端调用，后端只负责返回已生成的纯文本。
    await navigator.clipboard.writeText(value)
    return true
  } catch (error) {
    console.warn('推荐文本复制失败:', error)
    return false
  }
}

const showExportComplete = async (result) => {
  if (form.format === 'clipboard') {
    toast.success(t('toast.recommendation_export.copied', '推荐文本已复制到剪贴板'))
    return
  }
  const targetPath = result?.path || ''
  if (!targetPath) {
    // 目录型导出可能只返回目录或文件列表，这里保留一个兜底完成提示。
    toast.success(t('toast.recommendation_export.completed', '推荐导出完成'))
    return
  }
  const action = await confirmStore.confirmAction(
    t('dialog.recommendation_export.completed_title', '推荐导出完成'),
    t('dialog.recommendation_export.completed_message', '导出路径：{path}', { path: targetPath }),
    {
      type: 'success',
      actionButtons: [
        { label: t('dialog.recommendation_export.open_output_dir', '打开导出目录'), value: 'open', kind: 'primary' },
        { label: t('common.action.close', '关闭'), value: 'close', kind: 'secondary' },
      ],
    }
  )
  if (action === 'open') {
    await appStore.openPath(targetPath)
  }
}

const handleExport = async () => {
  if (!window.pywebview || exportMods.value.length === 0 || isExporting.value) return
  isExporting.value = true
  try {
    const res = await window.pywebview.api.recommendation_export(buildPayload())
    if (!checkResult(res, t('check.recommendation_export', '推荐导出'), form.format !== 'clipboard')) return
    if (form.format === 'clipboard') {
      // 剪贴板导出没有文件路径，必须等后端生成文本后再写入系统剪贴板。
      const copied = await copyTextToClipboard(res.data?.text || '')
      if (!copied) {
        toast.error(t('toast.recommendation_export.copy_failed', '复制失败，可能是浏览器权限限制'))
        return
      }
    }
    emit('close')
    await showExportComplete(res.data)
  } finally {
    isExporting.value = false
  }
}

watch(() => props.show, (visible) => {
  if (visible) {
    // 每次打开都根据入口名称刷新默认导出名，用户仍可在输入框里手动改。
    form.exportName = defaultExportName.value
  }
  if (!visible) {
    isExporting.value = false
  }
})
</script>
