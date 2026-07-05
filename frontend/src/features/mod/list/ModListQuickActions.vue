<template>
  <div class="absolute bottom-2 right-2 flex items-center justify-end gap-2"
    :data-tour="listId === ACTIVE_LIST_ID ? 'list-quick-actions' : null">
    <button v-for="action in visibleQuickActions" :key="action.key"
      @click="action.onClick"
      v-tooltip="action.tooltip"
      class="px-1 py-1 rounded-md transition-all"
      :class="action.buttonClass">
      <component :is="action.icon" />
    </button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Download, Megaphone, Trash2 } from 'lucide-vue-next'
import { ISSUE_TYPE } from '../../../shared/lib/constants'
import { useModStore } from '../stores/modStore'
import { useProfileStore } from '../../profiles/profileStore'
import { useSupplementStore } from '../../supplement/supplementStore'
import { useMissingInstallStore } from '../../supplement/missingInstallStore'
import { t } from '../../../shared/i18n'

const props = defineProps({
  listId: { type: String, required: true },
  modelValue: { type: Array, required: true },
  refreshVirtualList: { type: Function, required: true },
})

const modStore = useModStore()
const profileStore = useProfileStore()
const supplementStore = useSupplementStore()
const missingInstallStore = useMissingInstallStore()

const ACTIVE_LIST_ID = 'active'
const ACTION_BUTTON_CLASS = {
  danger: 'bg-accent-danger/80 text-text-main opacity-75 hover:bg-accent-danger hover:opacity-100',
  warn: 'bg-accent-warn/80 text-text-main opacity-75 hover:bg-accent-warn hover:opacity-100',
  primary: 'bg-accent-primary/80 text-text-main opacity-75 hover:bg-accent-primary hover:opacity-100',
  supplementDanger: 'bg-accent-danger/80 text-text-main opacity-75 hover:bg-accent-danger hover:opacity-100',
  supplementWarn: 'bg-accent-warn/80 text-text-main opacity-75 hover:bg-accent-warn hover:opacity-100',
}
const EMPTY_MISSING_INSTALL_SUMMARY = {
  dangerTotal: 0,
  warnTotal: 0,
  infoTotal: 0,
  unknownTotal: 0,
  actionableTotal: 0,
  visibleEntryTotal: 0,
}
const EMPTY_SUPPLEMENT_SUMMARY = {
  groups: [],
  count: 0,
  dangerCount: 0,
  warnCount: 0,
  infoCount: 0,
  visibleCount: 0,
  urgency: 'none',
}

const missingInstallSummary = ref({ ...EMPTY_MISSING_INSTALL_SUMMARY })
let missingInstallSummarySeq = 0
const isActiveList = computed(() => props.listId === ACTIVE_LIST_ID)

// 缺失安装：异步摘要需要序号兜底，避免旧请求覆盖新列表状态。
const refreshMissingInstallSummary = async () => {
  const seq = ++missingInstallSummarySeq
  if (!isActiveList.value) {
    missingInstallSummary.value = { ...EMPTY_MISSING_INSTALL_SUMMARY }
    return
  }
  const summary = await missingInstallStore.getSummaryForActiveList(props.modelValue)
  if (seq !== missingInstallSummarySeq) return
  missingInstallSummary.value = summary
}

watch(
  () => [props.listId, props.modelValue.join('|'), profileStore.activeContext?.game_version || ''],
  () => { refreshMissingInstallSummary() },
  { immediate: true }
)

const hasMissingInstallAction = computed(() => (
  (missingInstallSummary.value.dangerTotal || 0)
  + (missingInstallSummary.value.warnTotal || 0)
  + (missingInstallSummary.value.unknownTotal || 0)
) > 0)

const missingInstallTooltip = computed(() => {
  if (!hasMissingInstallAction.value) return t('tooltip.mod_list.quick_action.missing_install.empty', '当前没有可处理的安装项')
  const lines = []
  if (missingInstallSummary.value.dangerTotal > 0) {
    lines.push(t('tooltip.mod_list.quick_action.missing_install.danger', '!!需处理 {count} 项!!', { count: missingInstallSummary.value.dangerTotal }))
  } else if (missingInstallSummary.value.unknownTotal > 0) {
    lines.push(t('tooltip.mod_list.quick_action.missing_install.unknown', '!!未知来源 {count} 项!!', { count: missingInstallSummary.value.unknownTotal }))
  } else if (missingInstallSummary.value.warnTotal > 0) {
    lines.push(t('tooltip.mod_list.quick_action.missing_install.warn', '^^建议处理 {count} 项^^', { count: missingInstallSummary.value.warnTotal }))
  }
  if (missingInstallSummary.value.dangerTotal > 0) lines.push(t('tooltip.mod_list.quick_action.missing_install.danger_item', '• 必要处理: {count}', { count: missingInstallSummary.value.dangerTotal }))
  if (missingInstallSummary.value.warnTotal > 0) lines.push(t('tooltip.mod_list.quick_action.missing_install.warn_item', '• 警告项: {count}', { count: missingInstallSummary.value.warnTotal }))
  if (missingInstallSummary.value.unknownTotal > 0) lines.push(t('tooltip.mod_list.quick_action.missing_install.unknown_item', '• 未知来源: {count}', { count: missingInstallSummary.value.unknownTotal }))
  lines.push('')
  lines.push(t('tooltip.mod_list.quick_action.missing_install.open', '__[[(点击打开安装处理窗口)]]__'))
  return lines.join('\n')
})

const missingInstallButtonClass = computed(() => {
  if (missingInstallSummary.value.dangerTotal > 0 || missingInstallSummary.value.unknownTotal > 0) {
    return ACTION_BUTTON_CLASS.danger
  }
  const hasWarnOnly = missingInstallSummary.value.warnTotal > 0
    && missingInstallSummary.value.dangerTotal === 0
    && missingInstallSummary.value.unknownTotal === 0
  if (hasWarnOnly) return ACTION_BUTTON_CLASS.warn
  return ACTION_BUTTON_CLASS.primary
})

const supplementSummary = computed(() => {
  if (!isActiveList.value) return EMPTY_SUPPLEMENT_SUMMARY
  return supplementStore.getSuggestionSummary(props.modelValue)
})

const hasSupplementAction = computed(() => supplementSummary.value.visibleCount > 0)

const supplementButtonClass = computed(() => {
  if (supplementSummary.value.urgency === 'danger') {
    return ACTION_BUTTON_CLASS.supplementDanger
  }
  if (supplementSummary.value.urgency === 'warn') {
    return ACTION_BUTTON_CLASS.supplementWarn
  }
  return ACTION_BUTTON_CLASS.supplementWarn
})

const supplementTooltip = computed(() => {
  if (!hasSupplementAction.value) return t('tooltip.mod_list.quick_action.supplement.empty', '当前没有可补齐的未启用模组')
  const groupLines = supplementSummary.value.groups
    .filter(group => group.severity !== 'info')
    .map(group => t('tooltip.mod_list.quick_action.supplement.group_item', '• {title}: {count} 项', { title: group.title, count: group.count }))
    .join('\n')
  const lines = []
  if (supplementSummary.value.dangerCount > 0) {
    lines.push(t('tooltip.mod_list.quick_action.supplement.danger', '!!需处理 {count} 项!!', { count: supplementSummary.value.dangerCount }))
  } else if (supplementSummary.value.warnCount > 0) {
    lines.push(t('tooltip.mod_list.quick_action.supplement.warn', '^^建议处理 {count} 项^^', { count: supplementSummary.value.warnCount }))
  }
  lines.push(t('tooltip.mod_list.quick_action.supplement.found', '发现 {count} 项可补齐内容', { count: supplementSummary.value.visibleCount }))
  if (supplementSummary.value.dangerCount > 0) lines.push(t('tooltip.mod_list.quick_action.supplement.danger_item', '• 必要项: {count}', { count: supplementSummary.value.dangerCount }))
  if (supplementSummary.value.warnCount > 0) lines.push(t('tooltip.mod_list.quick_action.supplement.warn_item', '• 建议项: {count}', { count: supplementSummary.value.warnCount }))
  if (groupLines) lines.push(groupLines)
  lines.push('')
  lines.push(t('tooltip.mod_list.quick_action.supplement.open', '__[[(点击打开补齐窗口)]]__'))
  return lines.join('\n')
})

const issuesSummary = computed(() => modStore.getListIssues(props.listId))
const invalidModsToRemove = computed(() => (
  issuesSummary.value?.stats?.[ISSUE_TYPE.ERROR_MISSING_FILE] || []
))

// 按钮动作统一在这里定义，模板只负责渲染 visibleQuickActions。
const openMissingInstallDialog = async () => {
  await missingInstallStore.openForActiveList(props.modelValue)
}

const openSupplementDialog = async () => {
  if (!isActiveList.value) return
  await supplementStore.openForActiveList({
    activeIds: props.modelValue,
    message: t('ui.mod_list.quick_action.supplement.message', '选择要启用的模组。'),
  })
}

const removeInvalidMod = async () => {
  const invalidMods = invalidModsToRemove.value
  if (invalidMods.length === 0) return
  await modStore.runListHistoryTransaction({
    type: 'batch-remove-list-items',
    label: t('history.mod_list.remove_invalid', '移除 {count} 个无效 Mod', { count: invalidMods.length }),
    trackedModIds: invalidMods
  }, async () => {
    modStore.removeUnavailableIdsCompletely(invalidMods)
  })
  await props.refreshVirtualList()
}

const visibleQuickActions = computed(() => [
  {
    key: 'missing-install',
    visible: isActiveList.value && hasMissingInstallAction.value,
    icon: Download,
    tooltip: missingInstallTooltip.value,
    buttonClass: missingInstallButtonClass.value,
    onClick: openMissingInstallDialog,
  },
  {
    key: 'supplement',
    visible: isActiveList.value && hasSupplementAction.value,
    icon: Megaphone,
    tooltip: supplementTooltip.value,
    buttonClass: supplementButtonClass.value,
    onClick: openSupplementDialog,
  },
  {
    key: 'remove-invalid',
    visible: invalidModsToRemove.value.length > 0,
    icon: Trash2,
    tooltip: t('tooltip.mod_list.quick_action.remove_invalid', '^^一键移除共计 {count} 个无效Mod^^', { count: invalidModsToRemove.value.length }),
    buttonClass: ACTION_BUTTON_CLASS.danger,
    onClick: removeInvalidMod,
  },
].filter(action => action.visible))
</script>
