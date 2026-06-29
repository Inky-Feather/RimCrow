<template>
  <div :class="groupClass">
    <slot name="before" :workshop-id="normalizedWorkshopId" :payload="workshopPayload" />
    <template v-for="action in normalizedBeforeActions" :key="action.key">
      <button type="button" :class="[buttonClass, action.class]" :disabled="isPendingAction(action.key) || action.disabled" :aria-label="action.ariaLabel || action.label" v-tooltip="actionTooltip(action)" @click.stop="runExtraAction(action)">
        <LoaderCircle v-if="isPendingAction(action.key)" :class="[iconSizeClass, 'animate-spin']" />
        <component v-else-if="action.icon" :is="action.icon" />
        <span v-if="showLabels && action.label" class="text-[0.68rem] font-bold leading-none">{{ action.label }}</span>
      </button>
    </template>

    <button v-if="!showUnsubscribe" type="button" :class="[buttonClass, builtInActionClass.primary]"
      :disabled="isPendingAction('subscribe') || !canSubscribe" aria-label="订阅" v-tooltip="isPendingAction('subscribe') ? '正在发送订阅请求' : '订阅该工坊项目到 Steam'" @click.stop="subscribe">
      <LoaderCircle v-if="isPendingAction('subscribe')" :class="[iconSizeClass, 'animate-spin']" />
      <Flag v-else :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">订阅</span>
    </button>

    <button v-if="showUnsubscribe" type="button" :class="[buttonClass, builtInActionClass.danger]"
      :disabled="isPendingAction('unsubscribe') || !canUnsubscribe" aria-label="取订" v-tooltip="isPendingAction('unsubscribe') ? '正在发送取消订阅请求' : '取消订阅该工坊项目'"  @click.stop="unsubscribe">
      <LoaderCircle v-if="isPendingAction('unsubscribe')" :class="[iconSizeClass, 'animate-spin']" />
      <FlagOff v-else :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">取订</span>
    </button>

    <button type="button" :class="[buttonClass, builtInActionClass.success]"
      :disabled="isPendingAction('download') || !canDownload" aria-label="下载" v-tooltip="isPendingAction('download') ? '正在发送下载请求' : '下载该工坊项目到管理器'" @click.stop="download">
      <LoaderCircle v-if="isPendingAction('download')" :class="[iconSizeClass, 'animate-spin']" />
      <Download v-else :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">下载</span>
    </button>

    <button v-if="showLink" type="button" :class="[buttonClass, builtInActionClass.cool]"
      :disabled="!canOpenWeb" aria-label="打开网页工坊页面" v-tooltip="'打开网页工坊页面'" @click.stop="openWeb">
      <Link :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">网页</span>
    </button>

    <button v-if="showLink" type="button" :class="[buttonClass, builtInActionClass.special]"
      :disabled="!canOpenSteam" aria-label="打开 Steam 客户端工坊页面" v-tooltip="'打开 Steam 客户端页面'" @click.stop="openSteam">
      <IconSteam :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">Steam</span>
    </button>

    <button v-if="showDelete" type="button" :class="[buttonClass, builtInActionClass.danger]"
      :disabled="deleteDisabled" :aria-label="deleteLabel" v-tooltip="deleteTooltip || deleteLabel" @click.stop="deleteItem">
      <Trash2 :class="iconSizeClass" />
      <span v-if="showLabels" class="text-[0.68rem] font-bold leading-none">{{ deleteLabel }}</span>
    </button>

    <template v-for="action in normalizedAfterActions" :key="action.key">
      <button type="button" :class="[buttonClass, action.class]" :disabled="isPendingAction(action.key) || action.disabled" :aria-label="action.ariaLabel || action.label" v-tooltip="actionTooltip(action)" @click.stop="runExtraAction(action)">
        <LoaderCircle v-if="isPendingAction(action.key)" :class="[iconSizeClass, 'animate-spin']" />
        <component v-else-if="action.icon" :is="action.icon" />
        <span v-if="showLabels && action.label" class="text-[0.68rem] font-bold leading-none">{{ action.label }}</span>
      </button>
    </template>
    <slot name="after" :workshop-id="normalizedWorkshopId" :payload="workshopPayload" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Download, Flag, FlagOff, Link, LoaderCircle, Trash2 } from 'lucide-vue-next'
import { useAppStore } from '../../app/stores/appStore'
import { useTaskStore } from '../../app/stores/taskStore'
import { IconSteam } from '../lib/constants'

const props = defineProps({
  workshopId: { type: [String, Number], default: '' },
  webUrl: { type: String, default: '' },
  layout: { type: String, default: 'row' },
  mode: { type: String, default: 'panel' },
  colorful: { type: Boolean, default: false },
  size: { type: String, default: 'sm' },
  showLabels: { type: Boolean, default: false },
  showLink: { type: Boolean, default: true },
  showUnsubscribe: { type: Boolean, default: false },
  showDelete: { type: Boolean, default: false },
  deleteLabel: { type: String, default: '删除' },
  deletePayload: { type: null, default: undefined },
  deleteDisabled: { type: Boolean, default: false },
  deleteTooltip: { type: String, default: '' },
  onDelete: { type: Function, default: null },
  beforeActions: { type: Array, default: () => [] },
  afterActions: { type: Array, default: () => [] },
})

const emit = defineEmits(['subscribe', 'unsubscribe', 'download', 'delete', 'action'])

const appStore = useAppStore()
const taskStore = useTaskStore()
const pendingActions = ref(new Set())

const normalizedWorkshopId = computed(() => String(props.workshopId || '').trim())
const workshopPayload = computed(() => normalizedWorkshopId.value)
const normalizedWebUrl = computed(() => {
  const rawUrl = String(props.webUrl || '').trim()
  if (rawUrl) return rawUrl
  if (!normalizedWorkshopId.value) return ''
  return `https://steamcommunity.com/sharedfiles/filedetails/?id=${normalizedWorkshopId.value}`
})
const normalizedBeforeActions = computed(() => normalizeActions(props.beforeActions, 'before'))
const normalizedAfterActions = computed(() => normalizeActions(props.afterActions, 'after'))
const canOpenWeb = computed(() => !!(normalizedWorkshopId.value || normalizedWebUrl.value))
const canOpenSteam = computed(() => !!(normalizedWorkshopId.value || normalizedWebUrl.value))
const canSubscribe = computed(() => !!(normalizedWorkshopId.value || normalizedWebUrl.value))
const canUnsubscribe = computed(() => !!(normalizedWorkshopId.value || normalizedWebUrl.value))
const canDownload = computed(() => !!(normalizedWorkshopId.value || normalizedWebUrl.value))

const groupClass = computed(() => ([
  'inline-flex w-fit items-center',
  !props.colorful ? 'border border-border-base/10 bg-bg-overlay/5 shadow-[inset_0_0.0625rem_0_rgba(255,255,255,0.04),0_0.375rem_1rem_rgba(2,6,23,0.16)] backdrop-blur-md' : '',
  props.layout === 'stacked' ? 'flex-col' : '',
  !props.colorful && props.mode === 'floating' ? 'border-border-base/18 bg-bg-inset/70 shadow-[inset_0_0.0625rem_0_rgba(255,255,255,0.05),0_0.625rem_1.5rem_rgba(2,6,23,0.28)]' : '',
  props.size === 'xs' ? 'gap-[0.15rem] rounded-[0.5rem] p-[0.12rem]' : '',
  props.size === 'md' ? 'gap-[0.3rem] rounded-[0.85rem] p-[0.22rem]' : '',
  !['xs', 'md'].includes(props.size) ? 'gap-[0.25rem] rounded-[0.75rem] p-[0.18rem]' : '',
]))
const buttonSizeClass = computed(() => {
  if (props.showLabels) return 'w-auto py-0.5 ps-[0.55rem] pe-[0.55rem] rounded-[0.5rem]'
  if (props.size === 'xs') return 'size-6 rounded-[0.4rem]'
  if (props.size === 'md') return 'size-[2.2rem] rounded-[0.7rem]'
  return 'size-[1.95rem] rounded-[0.6rem]'
})
const iconSizeClass = computed(() => {
  if (props.showLabels) return 'size-4'
  if (props.size === 'xs') return 'size-3'
  if (props.size === 'md') return 'size-5'
  return 'size-4'
})
const buttonClass = computed(() => ([
  'inline-flex items-center justify-center gap-[0.35rem] border transition-all duration-200 cursor-pointer',
  props.colorful
    ? 'border-transparent text-text-main hover:scale-110 focus-visible:scale-110 active:scale-95 rounded-full'
    : 'border-transparent bg-transparent text-text-dim hover:-translate-y-[0.03125rem] hover:border-border-base/10 hover:bg-bg-overlay/10',
  'focus-visible:border-accent-primary/40 focus-visible:ring-2 focus-visible:ring-accent-primary/20 focus-visible:outline-none',
  'disabled:cursor-not-allowed disabled:opacity-45',
  buttonSizeClass.value,
]))
const plainActionClass = {
  primary: 'hover:text-accent-primary focus-visible:text-accent-primary',
  success: 'hover:text-accent-success focus-visible:text-accent-success',
  danger: 'hover:text-accent-danger focus-visible:text-accent-danger',
  cool: 'hover:text-accent-cool focus-visible:text-accent-cool',
  special: 'hover:text-accent-special focus-visible:text-accent-special',
}
const colorfulActionClass = {
  primary: 'bg-accent-primary/80 hover:bg-accent-primary',
  success: 'bg-accent-success/80 hover:bg-accent-success',
  danger: 'bg-accent-danger/80 hover:bg-accent-danger',
  cool: 'bg-accent-cool/80 hover:bg-accent-cool',
  special: 'bg-accent-special/80 hover:bg-accent-special',
}
const builtInActionClass = computed(() => ({
  primary: props.colorful ? colorfulActionClass.primary : plainActionClass.primary,
  success: props.colorful ? colorfulActionClass.success : plainActionClass.success,
  danger: props.colorful ? colorfulActionClass.danger : plainActionClass.danger,
  cool: props.colorful ? colorfulActionClass.cool : plainActionClass.cool,
  special: props.colorful ? colorfulActionClass.special : plainActionClass.special,
}))

const normalizeActions = (actions = [], group = '') => (
  (actions || []).filter(Boolean).map((action, index) => ({
    key: action.key || `${group}-${index}-${action.label || 'action'}`,
    label: action.label || '',
    tooltip: action.tooltip || action.label || '',
    ariaLabel: action.ariaLabel || '',
    icon: action.icon || null,
    disabled: !!action.disabled,
    class: action.class || '',
    payload: action.payload,
    onClick: action.onClick,
  }))
)

const openWeb = () => {
  if (!canOpenWeb.value) return
  if (normalizedWorkshopId.value) {
    appStore.openSteamWorkshopById(normalizedWorkshopId.value, false)
    return
  }
  appStore.openUrl(normalizedWebUrl.value)
}
const openSteam = () => {
  if (!canOpenSteam.value) return
  if (normalizedWorkshopId.value) {
    appStore.openSteamWorkshopById(normalizedWorkshopId.value, true)
    return
  }
  appStore.openSteamWorkshopUrl(normalizedWebUrl.value)
}
const isPendingAction = (key) => pendingActions.value.has(key)
const setPendingAction = (key, pending) => {
  const next = new Set(pendingActions.value)
  if (pending) next.add(key)
  else next.delete(key)
  pendingActions.value = next
}
const actionTooltip = (action) => (
  isPendingAction(action?.key) ? `${action?.label || '操作'}处理中` : (action?.tooltip || action?.label || '')
)
const getTaskIdFromResult = (result) => String(result?.taskId || result?.task_id || result?.data?.task_id || '')
const waitForActionTask = async (types, startedAt, result) => {
  const taskId = getTaskIdFromResult(result)
  if (taskId) {
    await taskStore.waitForTaskCompletion(taskId).catch(() => null)
    return
  }
  if (!types) return
  await taskStore.waitForLatestTaskByType(types, { since: startedAt, startTimeout: 5000 }).catch(() => null)
}
const runWithPending = async (key, runner, taskTypes = null) => {
  if (isPendingAction(key)) return
  const startedAt = Date.now()
  setPendingAction(key, true)
  try {
    const result = await runner?.()
    await waitForActionTask(taskTypes, startedAt, result)
    return result
  } finally {
    setPendingAction(key, false)
  }
}
const subscribe = async () => {
  if (!canSubscribe.value) return
  await runWithPending('subscribe', async () => {
    const result = await appStore.subscribeWorkshopIds([workshopPayload.value])
    if (result) emit('subscribe', workshopPayload.value)
    return result
  }, 'steam-subscribe')
}
const unsubscribe = async () => {
  if (!canUnsubscribe.value) return
  await runWithPending('unsubscribe', async () => {
    const result = await appStore.unsubscribeWorkshopIds([workshopPayload.value])
    if (result) emit('unsubscribe', workshopPayload.value)
    return result
  }, 'steam-unsubscribe')
}
const download = async () => {
  if (!canDownload.value) return
  await runWithPending('download', async () => {
    const result = await appStore.downloadWorkshopItems([workshopPayload.value])
    if (result) emit('download', workshopPayload.value)
    return result
  }, 'steamcmd-download')
}
const deleteItem = () => {
  const payload = props.deletePayload === undefined ? workshopPayload.value : props.deletePayload
  if (props.onDelete) props.onDelete(payload)
  emit('delete', payload)
}
const runExtraAction = async (action) => {
  if (!action || action.disabled) return
  await runWithPending(action.key, async () => {
    const payload = action.payload === undefined ? workshopPayload.value : action.payload
    if (typeof action.onClick === 'function') await action.onClick(payload, action)
    emit('action', { action, payload })
  })
}
</script>
