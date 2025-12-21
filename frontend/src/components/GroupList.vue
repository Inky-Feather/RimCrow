<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
    :class="`border-2 rounded-2xl border-accent-${listColor}/20`">
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-${listColor}`"></div>
        {{ title }}
      </span>
      <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
        {{ groupList.length }}
      </span>
    </div>
    <!-- 搜索栏 -->
    <div class="px-2 py-1 w-full items-center shadow-xl">
      <div class="inline-flex w-full items-center py-0.5" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none focus:bg-bg-deep/90 min-w-0`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
          定位
        </button>
      </div>
      <div class="inline-flex w-full items-center py-1" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none 
          focus:bg-bg-deep/90 min-w-0`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
          筛选
        </button>
      </div>
    </div>

    <!-- 列表区 -->
    <div class="overflow-y-auto flex-1 pb-0.5 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">

      <!-- 列表主体 -->
      <div class="h-full px-1 relative" @click.self="store.clearSelection()">


        <div v-if="groupList.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center text-gray-600 text-xs select-none pointer-events-none">
            可点击右下角 “ + ” 按钮新建分组
        </div>

        <VirtualList v-model="groupList" dataKey="group_id" :keeps="50" class="h-full p-1" 
          placeholderClass="ghost" wrapClass="space-y-1.5 min-h-full"
	        :fallbackOnBody="true" :scrollSpeed="{ x: 0, y: 10 }" handle=".drag-handle"
          :group="{ name: 'groups', pull: true, put: 'groups', revertDrag: true }" :animation="150"
          @sort-end="groupReorder">
          <template v-slot:item="{ record, index, dataKey }">
            <GroupItem :id="dataKey" :key="dataKey" :index="index" :groupData="record" :list-color="listColor"
              :expanded="expandedIds.has(record.group_id)" @toggle="toggle" @delete-group="deleteGroup"
              @remove-item="removeMod">
            </GroupItem>
          </template>
        </VirtualList>

        <!-- 悬浮功能按钮 -->
        <div class="absolute bottom-0 left-0 right-0 h-10 pointer-events-none 
            bg-linear-to-t from-bg-deep/80 to-transparent z-50">
          <div class="absolute bottom-1 right-1 pointer-events-auto flex gap-1.5">
            <button @click="expandAll" title="展开全部分组" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`" >
              <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 9L42 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19L42 19" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 26L24 40L42 26" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button @click="collapseAll" title="收拢全部分组" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
              <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 10L42 10" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 20L42 20" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40L24 26L42 40" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button @click="createGroup" title="新建分组" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
              <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24.0605 10L24.0239 38" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 24L38 24" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useModStore } from '../stores/modStore'
import VirtualList from 'vue-virtual-sortable';
import GroupItem from './utils/GroupItem.vue'

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Groups' },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warm/secondary/warning
})

const store = useModStore()

// 分组列表
const groupList = computed(() => store.groupList)
// 用一个 Set 存储所有被展开的 ID
const expandedIds = computed(() => new Set(groupList.value.filter(item => item.is_expanded).map(item => item.group_id)))

// 切换分组展开状态
const toggle = (id: string) => {
  if (expandedIds.value.has(id)) {
    store.updateGroup(id, { is_expanded: false })
  } else {
    store.updateGroup(id, { is_expanded: true })
  }
}

// 全部展开
const expandAll = () => {
  groupList.value.forEach(group => store.updateGroup(group.group_id, { is_expanded: true }));
}

// 全部折叠
const collapseAll = () => {
  groupList.value.forEach(group => store.updateGroup(group.group_id, { is_expanded: false }));
}

// 新建分组
const createGroup = () => {
  store.createGroup();
}
// 删除分组
const deleteGroup = (groupId: string) => {
  store.deleteGroup(groupId);
  expandedIds.value.delete(groupId); // 同时从展开列表中移除
}
// 分组排序
const groupReorder = () => {
  store.groupReorder();
}

// 移除模组
const removeMod = (groupId: string, modId: Array<string>) => {
  store.groupRemoveMods(groupId, modId);
}

</script>

<style scoped>

</style>