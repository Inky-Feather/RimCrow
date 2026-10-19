import { ref } from 'vue'
import { t } from '../../../shared/i18n.js'

export function useModListDrag({ props, appStore, modStore, vListRef, allowSort, moveIdsToList }) {
  const isDragging = ref(false)

  const finishDragSession = () => {
    isDragging.value = false
    modStore.isDraggingMod = false
  }

  const cancelActiveDrag = () => {
    if (!isDragging.value) return
    vListRef.value?.cancelDrag()
    finishDragSession()
  }

  const startDrag = () => {
    isDragging.value = true
    modStore.isDraggingMod = true
  }

  const updateChildren = async ({ item, index, sameList }) => {
    if (appStore.isLoading || !allowSort.value || !item.mod_ids?.length) return
    if (item.isSection) modStore.selectMods(item.mod_ids, item.id)
    await moveIdsToList({
      ids: item.mod_ids,
      visualIndex: index,
      preferSectionEnd: !!item.isCollapsedSection,
      type: sameList ? 'reorder-list' : 'move-between-lists',
      label: sameList
        ? t('history.mod_list.drag_reorder', '调整 {list} 列表顺序', { list: props.title })
        : t('history.mod_list.drag_move_between', '移动 {count} 项到 {list}', { count: item.mod_ids.length, list: props.title }),
    })
  }

  return { isDragging, finishDragSession, cancelActiveDrag, startDrag, updateChildren }
}
