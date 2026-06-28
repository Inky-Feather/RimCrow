<template>
  <div data-tour="group-list-panel" class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
    :class="`border-2 rounded-2xl border-accent-${listColor}/20`">
    <!-- 标题栏 -->
    <div data-tour="group-list-header" :class="`px-3 h-8 border-b rounded-t-2xl border-text-main/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-[0_0_8px_var(--color-accent-${listColor})]`"></div>
        {{ title }}
      </span>
      <span :class="`text-xs bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
        {{ groupList.length }}
      </span>
    </div>
    <!-- 搜索栏 -->
    <div class="px-2 py-1 shadow-xl" >
      <div data-tour="group-list-search" class="w-full inline-flex items-center gap-1">
        <input type="text" placeholder="搜索模组名称..." v-model="searchText"
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-text-main/10 text-sm 
          text-text-main placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none focus:bg-bg-deep/90 min-w-0`" />
        <!-- 定位按钮 -->
        <button @click="executeSearch(true)" v-tooltip="'搜索定位下一个符合条件的结果'"
          :class="`px-3 py-1 relative rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all cursor-pointer hover:scale-105 active:scale-95`">定位
          <div v-if="currentSearchIndex !== -1 && searchText" class="text-[0.55rem] absolute -top-2 -left-1 text-text-main bg-accent-highlight px-1 rounded-lg">{{ currentSearchIndex + 1 }} / {{ searchResults.length }}</div>
        </button>
      </div>
      <!-- 操作按钮 -->
      <div data-tour="group-list-actions" class="mt-1 flex items-center justify-between">

        <div class="pointer-events-auto flex gap-1.5">
          <button @click="expandAll" v-tooltip="`展开全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`" >
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 9L42 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19L42 19" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 26L24 40L42 26" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button @click="collapseAll" v-tooltip="`收拢全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 10L42 10" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 20L42 20" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40L24 26L42 40" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button @click="createGroup" v-tooltip="`新建分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24.0605 10L24.0239 38" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 24L38 24" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        <!-- 帮助按钮 -->
        <CircleQuestionMarkIcon data-tour="group-list-help" v-tooltip="groupHelpTooltip" :class="`size-5 text-text-dim hover:text-accent-${listColor} cursor-help transition-all`" />
      </div>

    </div>

    <!-- 列表区 -->
    <div data-tour="group-list-body" class="overflow-y-auto flex-1 pb-0.5 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">

      <!-- 列表主体 -->
      <div class="h-full px-1 relative" @click.self="modStore.clearSelection()">


        <div v-if="groupList.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center text-gray-600 text-xs select-none pointer-events-none">
            可点击 “ + ” 按钮新建分组
        </div>

        <VirtualList v-model="groupList" dataKey="group_id" :keeps="50" class="h-full p-1" 
          placeholderClass="ghost" wrapClass="space-y-2 min-h-full " ref="vListRef" :delay="appStore.settings.ui.drag_delay"
	        :appendToBody="true" :fallbackOnBody="true" :scrollSpeed="{ x: 0, y: 10 }" handle=".drag-handle"
          :group="{ name: 'groups', pull:'clone', put: true, revertDrag: true }" :animation="150"
          @drop="groupReorder" @drag="stratDrag">
          <template v-slot:item="{ record, index, dataKey }">
            <GroupItem :id="dataKey" :key="dataKey" :index="index" :groupData="record" :list-color="listColor"
              :expanded="expandedIds.has(record.group_id)" :isHighlight="currentSearchGroupId === dataKey"
              @toggle="toggle" @delete-group="deleteGroup"
              @remove-item="removeMod" @update-group="updateGroup" @update-children="updateChildren">
            </GroupItem>
          </template>
        </VirtualList>

        <!-- 悬浮功能按钮 -->
        <!-- <div class="absolute bottom-0 left-0 right-0 h-10 pointer-events-none 
            bg-linear-to-t from-bg-deep/80 to-transparent z-50">
          <div class="absolute bottom-1 right-1 pointer-events-auto flex gap-1.5">
            <button @click="expandAll" v-tooltip="`展开全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`" >
              <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 9L42 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19L42 19" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 26L24 40L42 26" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button @click="collapseAll" v-tooltip="`收拢全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
              <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 10L42 10" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 20L42 20" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40L24 26L42 40" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button @click="createGroup" v-tooltip="`新建分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
              <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24.0605 10L24.0239 38" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 24L38 24" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div> -->

      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useModStore } from '../stores/modStore'
import { useGroupStore } from '../stores/groupStore'
import VirtualList from 'vue-virtual-sortable';
import GroupItem from './utils/GroupItem.vue'
import { CircleQuestionMarkIcon } from 'lucide-vue-next';
import { useAppStore } from '../stores/appStore';

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Groups' },
  modelValue: { type: Array, default: () => [] },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const appStore = useAppStore()
const modStore = useModStore()
const groupStore = useGroupStore()

const vListRef = ref<VirtualList>()

// 搜索文本
const searchText = ref('')
const oldSearchText = ref('')
const searchResults = ref([])
const currentSearchIndex = ref(-1)
const currentSearchGroupId = ref('')

const highlightTimer = ref<number>()

// 获取下一个搜索结果索引
const getNextSearchIndex = (currentIndex: number, resultCount: number, forward: boolean) => {
  if (!Number.isInteger(resultCount) || resultCount <= 0) return -1
  const safeCurrentIndex = Number.isInteger(currentIndex) ? currentIndex : -1
  if (forward) {
    return (safeCurrentIndex + 1 + resultCount) % resultCount
  }
  if (safeCurrentIndex < 0) {
    return resultCount - 1
  }
  return (safeCurrentIndex - 1 + resultCount) % resultCount
}


// 用 Set 存储所有被展开的 ID
const expandedIds = computed(() => new Set(groupList.value.filter(item => item.is_expanded).map(item => item.group_id)))

// 分组列表
const groupList = computed({
    get() {
        return props.modelValue
    },
    set(val: any[]) {
        // 正常模式：直接更新
        // emit('update:modelValue', val)
    }
})

// 分组帮助提示
const groupHelpTooltip = computed(() => {
  return `**分组管理说明：**
支持直接将 Mod 从列表中拖拽至任意分组。
在列表上点击右键，可通过菜单快速将 Mod 移入或移出已有分组。
在 Mod 详情页面，可统一管理该 Mod 所属的所有分组。

分组功能类似剪贴板，移入、移出分组均为[[复制]]操作：
 - 无法通过^^移出^^分组来移除 Mod ；
 - 不能在分组之间!!直接移动!! Mod，分组间拖拽 Mod 也只会执行[[复制]]。

分组支持整体拖拽操作：
 - 将分组整体拖入启用列表，可一次性启用该分组下所有 Mod；
 - 将分组整体拖入停用列表，可一次性停用该分组下所有 Mod。`
})



const executeSearch = (forward: boolean) => {
  if (!searchText.value) return
  // 搜索文本改变时更新结果
  if (searchText.value !== oldSearchText.value) {
    // console.log(groupList.value)
    searchResults.value = groupList.value.filter(item => item.name.includes(searchText.value))
    currentSearchIndex.value = -1
  }
  // 搜索无结果时直接退出，避免出现 NaN 索引
  if (searchResults.value.length === 0) {
    currentSearchIndex.value = -1
    currentSearchGroupId.value = ''
    oldSearchText.value = searchText.value
    return
  }
  currentSearchIndex.value = getNextSearchIndex(currentSearchIndex.value, searchResults.value.length, forward)
  // 确保索引有效
  if (currentSearchIndex.value === -1) return
  // 更新当前搜索的分组 ID
  currentSearchGroupId.value = searchResults.value[currentSearchIndex.value].group_id
  const index = groupList.value.findIndex(item => item.group_id === currentSearchGroupId.value)
  if (index !== -1) {
    // 稍微延迟一下确保虚拟列表渲染就绪
    setTimeout(() => {
        if (vListRef.value) {
            vListRef.value.scrollToKey(currentSearchGroupId.value)
        }
    }, 50)
    // 延迟一段时间后移除高亮
    if (highlightTimer.value) {
      clearTimeout(highlightTimer.value)
    }
    highlightTimer.value = setTimeout(() => {
      currentSearchGroupId.value = ''
    }, 2000)
  }
  oldSearchText.value = searchText.value
}

// 切换分组展开状态
const toggle = (id: string) => {
  if (expandedIds.value.has(id)) {
    groupStore.updateGroup(id, { is_expanded: false })
  } else {
    groupStore.updateGroup(id, { is_expanded: true })
  }
}

// 全部展开
const expandAll = async () => {
  await groupStore.changeAllGroupExpansion(true);
}

// 全部折叠
const collapseAll = async () => {
  await groupStore.changeAllGroupExpansion(false);
}

// 新建分组
const createGroup = async () => {
  await groupStore.createGroup();
}
// 删除分组
const deleteGroup = (groupId: string) => {
  groupStore.deleteGroup(groupId);
  expandedIds.value.delete(groupId); // 同时从展开列表中移除
}
// 更新分组信息
const updateGroup = (groupId: string, data = props.groupData) => {
  groupStore.updateGroup(groupId, data);
}
// 更新分组内模组列表
const updateChildren = (groupId: string, newIds: Array<string>) => {
  groupStore.groupContentReorder(groupId, newIds)
}
const stratDrag = () => {
  // 标记当前正在拖动分组
  groupStore.isDraggingGroup = true
}
// 分组排序
const groupReorder = (e) => {
  // const groupIds = groupList.value.map(g => g.group_id)
  // const originGroupIds = groupStore.groupList.map(g => g.group_id)
  // console.log("分组排序:", groupIds)
  // console.log("原始排序:", originGroupIds)
  console.log("分组排序:", e)
  if (e.newIndex === -1 || e.event.target.dataKey) {
    console.log("分组排序错误")
    // 提前返回时也要复位拖拽状态，避免内部列表交互被持续禁用
    groupStore.isDraggingGroup = false
    return
  }
  groupStore.groupReorder();
  // 拖动结束后，重置状态
  groupStore.isDraggingGroup = false
}
// 移除模组
const removeMod =(groupId: string, modId: Array<string>) => {
  groupStore.groupRemoveMods(groupId, modId);
}

</script>

<style scoped>

</style>
