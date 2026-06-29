<template>
  <CommonModalShell
    :show="dialog.visible"
    :title="dialog.title"
    :description="dialog.message"
    size="compact"
    :z-index="160"
    accent="warn"
    content-class="flex min-h-0 flex-col px-2 py-1"
    footer-class="flex flex-wrap items-center justify-end gap-2"
    @close="workspaceStore.closeStartupInventoryDialog"
  >
    <template #icon>
      <CircleAlert class="size-5 text-accent-warn" />
    </template>

    <div class="max-h-[min(62vh,560px)] min-h-0 overflow-y-auto py-1">
      <div v-if="dialog.groups.length" class="space-y-3">
        <section v-for="group in dialog.groups" :key="group.id" class="overflow-hidden rounded-xl border border-border-base/10 bg-bg-inset/60">
          <div class="flex items-start justify-between gap-3 border-b border-border-base/10 bg-bg-elevated px-3 py-2">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <div class="text-sm font-black" :class="groupTitleClass(group.id)">{{ group.title }}</div>
                <span class="rounded-md border bg-bg-overlay/5 px-1.5 py-0.5 text-[10px]" :class="groupCountClass(group.id)">{{ group.items.length }} 项</span>
              </div>
              <div class="mt-1 text-xs leading-relaxed text-text-dim">{{ group.description }}</div>
            </div>
            <div class="flex shrink-0 flex-wrap justify-end gap-1">
              <button v-for="action in groupActions(group)" :key="action.id" :disabled="isGroupActionDisabled(group, action.id)"
                class="rmm-inventory-action" :class="actionClass(action.kind)"
                @click="runGroupAction(group, action.id)" >
                <Loader2 v-if="isGroupActionPending(group, action.id)" class="size-3.5 animate-spin" />
                <span>{{ action.label }}</span>
              </button>
            </div>
          </div>

          <div class="divide-y divide-border-base/10">
            <div v-for="item in group.items" :key="item.id" class="flex items-start justify-between gap-3 px-3 py-2" >
              <div class="min-w-0">
                <div class="break-all text-sm font-bold text-text-main">{{ item.title }}</div>
                <div v-if="item.description" class="mt-1 break-all text-xs leading-relaxed text-text-dim">{{ item.description }}</div>
                <div v-if="item.meta.length" class="mt-1 flex flex-wrap gap-1">
                  <span v-for="meta in item.meta" :key="meta" class="rounded-md border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[10px] text-text-dim" >
                    {{ meta }}
                  </span>
                </div>
              </div>
              <button
                v-if="itemAction(group.id, item)"
                :disabled="isItemActionDisabled(group.id, item)"
                class="rmm-inventory-action shrink-0"
                :class="actionClass(itemAction(group.id, item).kind)"
                @click="runItemAction(group, item)"
              >
                <Loader2 v-if="isPending(itemAction(group.id, item).id, item.id)" class="size-3.5 animate-spin" />
                <span>{{ itemAction(group.id, item).label }}</span>
              </button>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="rounded-xl border border-border-base/10 bg-bg-inset/60 px-3 py-4 text-sm text-text-dim">
        当前没有需要处理的库存项。
      </div>
    </div>

    <template #footer>
      <button
        v-if="hasDeletedItems"
        :disabled="isBatchActionDisabled('cleanup_deleted', 'all:deleted')"
        class="rmm-inventory-action px-4 py-1.5"
        :class="actionClass('danger')"
        @click="runAllAction('deleted', 'cleanup_deleted')"
      >
        <Loader2 v-if="isPending('cleanup_deleted', 'all:deleted')" class="size-3.5 animate-spin" />
        <span>清理删除项数据</span>
      </button>
      <button
        v-if="hasMissingItems"
        :disabled="isBatchActionDisabled('download_missing', 'all:missing')"
        class="rmm-inventory-action px-4 py-1.5"
        :class="actionClass('primary')"
        @click="runAllAction('missing', 'download_missing')"
      >
        <Loader2 v-if="isBatchActionPending('download_missing', 'all:missing')" class="size-3.5 animate-spin" />
        <span>重新下载缺失项</span>
      </button>
      <button
        class="rmm-inventory-action px-4 py-1.5"
        :class="actionClass('secondary')"
        @click="workspaceStore.closeStartupInventoryDialog"
      >
        确认
      </button>
    </template>
  </CommonModalShell>
</template>

<script setup>
import { computed } from 'vue'
import { CircleAlert, Loader2 } from 'lucide-vue-next'
import CommonModalShell from '../../../shared/components/modal/CommonModalShell.vue'
import { useWorkspaceStore } from '../workspaceStore'

const workspaceStore = useWorkspaceStore()
const dialog = workspaceStore.startupInventoryDialog

const pendingKey = (actionId, targetId) => `${actionId}:${targetId}`
const isPending = (actionId, targetId) => dialog.pendingActions.includes(pendingKey(actionId, targetId))
const hasPendingActions = computed(() => dialog.pendingActions.length > 0)
const hasDeletedItems = computed(() => dialog.groups.some(group => group.id === 'deleted' && group.items.length > 0))
const hasMissingItems = computed(() => dialog.groups.some(group => group.id === 'missing' && group.items.length > 0))
const hasDownloadBatchPending = computed(() =>
  isPending('download_missing', 'missing') || isPending('download_missing', 'all:missing')
)
const actionClass = (kind = 'secondary') => {
  if (kind === 'danger') return 'bg-accent-danger/90 text-on-accent-danger shadow-lg shadow-accent-danger/20 hover:bg-accent-danger'
  if (kind === 'primary') return 'bg-accent-primary text-on-accent-primary shadow-lg shadow-accent-primary/20 hover:bg-accent-primary/90'
  return 'border border-border-base/10 text-text-dim hover:border-border-base/18 hover:bg-bg-overlay/10 hover:text-text-main'
}
const groupTitleClass = (groupId) => {
  if (groupId === 'deleted') return 'text-accent-danger'
  if (groupId === 'missing') return 'text-accent-warn'
  if (groupId === 'changed') return 'text-accent-primary'
  return 'text-text-main'
}
const groupCountClass = (groupId) => {
  if (groupId === 'deleted') return 'border-accent-danger/20 text-accent-danger'
  if (groupId === 'missing') return 'border-accent-warn/20 text-accent-warn'
  if (groupId === 'changed') return 'border-accent-primary/20 text-accent-primary'
  return 'border-border-base/10 text-text-dim'
}

const groupActions = (group) => {
  const actions = []
  if (group.id === 'deleted') actions.push({ id: 'cleanup_deleted', label: `清理残留数据（${group.items.length}项）`, kind: 'danger' })
  if (group.id === 'missing') actions.push({ id: 'download_missing', label: `重新下载（${group.items.length}项）`, kind: 'primary' })
  actions.push({ id: 'details', label: '查看详情', kind: 'secondary' })
  return actions
}

const itemAction = (groupId, item) => {
  if (groupId === 'deleted') return { id: 'cleanup_deleted', label: '清理数据', kind: 'danger' }
  if (groupId === 'missing' && item.workshopId) return { id: 'download_missing', label: '重新下载', kind: 'primary' }
  return null
}

const isItemDownloadPending = (item) => isPending('download_missing', item.id)
const isItemActionDisabled = (groupId, item) => {
  const action = itemAction(groupId, item)
  if (!action) return true
  if (action.id === 'download_missing') return hasDownloadBatchPending.value || isItemDownloadPending(item)
  return isPending(action.id, item.id)
}
const isBatchActionPending = (actionId, targetId) => {
  if (actionId === 'download_missing') return hasDownloadBatchPending.value
  return isPending(actionId, targetId)
}
const isBatchActionDisabled = (actionId, targetId) => {
  if (actionId === 'download_missing') return hasDownloadBatchPending.value
  return isPending(actionId, targetId)
}
const isGroupActionPending = (group, actionId) => isBatchActionPending(actionId, group.id)
const isGroupActionDisabled = (group, actionId) => {
  if (!group.items.length) return true
  if (actionId === 'details') return hasPendingActions.value
  return isBatchActionDisabled(actionId, group.id)
}
const filterRunnableItems = (actionId, items = []) => {
  if (actionId !== 'download_missing') return items
  return items.filter(item => !isItemDownloadPending(item))
}

const runItemAction = async (group, item) => {
  const action = itemAction(group.id, item)
  if (!action) return
  await workspaceStore.runStartupInventoryDialogAction(action.id, [item], { pendingTarget: item.id })
}

const runGroupAction = async (group, actionId) => {
  if (actionId === 'details') {
    await workspaceStore.openStartupInventoryDialogDetails(group.id)
    return
  }
  const items = filterRunnableItems(actionId, group.items)
  if (!items.length) return
  await workspaceStore.runStartupInventoryDialogAction(actionId, items, { pendingTarget: group.id })
}

const runAllAction = async (groupId, actionId) => {
  const group = dialog.groups.find(candidate => candidate.id === groupId)
  if (!group?.items.length) return
  const items = filterRunnableItems(actionId, group.items)
  if (!items.length) return
  await workspaceStore.runStartupInventoryDialogAction(actionId, items, { pendingTarget: `all:${groupId}` })
}
</script>

<style scoped>
.rmm-inventory-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  min-height: 1.75rem;
  border-radius: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1;
  transition: color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease, opacity 0.18s ease;
}

.rmm-inventory-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
