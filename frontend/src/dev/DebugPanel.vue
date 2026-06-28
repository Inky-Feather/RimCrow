<template>
  <div class="fixed bottom-8 left-2 z-9999 font-mono text-xs">
    <!-- 开关按钮 -->
    <button @click="isOpen = !isOpen" 
      class="bg-bg-inset text-accent-primary border border-accent-primary/50 px-2 py-1 rounded shadow-lg hover:bg-bg-inset transition-all mb-1">
      {{ isOpen ? 'Close Debug' : 'Debug State' }}
    </button>

    <!-- 面板主体 -->
    <div v-if="isOpen" 
      class="w-[400px] h-[600px] bg-bg-inset border border-border-base/10 rounded-lg shadow-2xl flex flex-col overflow-hidden">
      
      <!-- 顶部信息 -->
      <div class="p-2 border-b border-border-base/10 bg-bg-overlay/5 flex justify-between">
        <span class="text-accent-success">Store 快照</span>
        <button @click="refresh" class="hover:text-text-main">刷新</button>
      </div>

      <!-- JSON 视图 -->
      <div class="flex-1 overflow-auto custom-scrollbar p-2">
        <json-viewer :value="sanitizedState" :expand-depth="1" copyable boxed sort />
      </div>
    </div>
  </div>
</template>

<script setup >
import { ref, computed } from 'vue'
import { JsonViewer } from "vue3-json-viewer"
import "vue3-json-viewer/dist/vue3-json-viewer.css";
import { useAppStore } from '../app/stores/appStore';
import { useModStore } from '../features/mod/stores/modStore'
import { useGroupStore } from '../features/mod/stores/groupStore'
import { useHoverStore } from '../shared/components/popover/hoverStore'
import { useRuleStore } from '../features/rules/ruleStore'
import { useTaskStore } from '../app/stores/taskStore'
import { normalizePackageToken } from '../features/mod/lib/modIdentity'

const appStore = useAppStore()
const modStore = useModStore()
const groupStore = useGroupStore()
const hoverStore = useHoverStore()
const ruleStore = useRuleStore()
const taskStore = useTaskStore()

const isOpen = ref(false)

// 强制刷新
const refreshKey = ref(0)
const refresh = () => refreshKey.value++

// --- 核心：数据清洗 ---
// 直接展示 modStore.$state 会导致浏览器渲染数万个节点卡死，只提取关键状态，大对象显示摘要
const sanitizedState = computed(() => {
  // 依赖 refreshKey 触发重新计算
  const _ = refreshKey.value 

  return {
    // 1. 基础状态
    PAGE_STATE: appStore.uiState,
    
    // 2. 选择与交互
    SELECTION: {
      selectedIds: modStore.selectedIds,
      selectedMod: modStore.lastSelectedMod,
      selectedStats: modStore.selectedStats,
      currentTargetId: modStore.currentTargetId,
      hovering: hoverStore.isHovering,
      hoverData: hoverStore.data,
    },

    // 3. 列表概览 (只看长度)
    COUNTS: {
      allMods: modStore.allModsMap.size,
      active: modStore.activeIds.length,
      inactive: modStore.inactiveIds.length,
      groups: groupStore.groupList.length,
      issues: modStore.modIssues.size
    },

    // 4. 当前选中的 Mod 详情 (完整显示)
    CURRENT_MOD: modStore.lastSelectedMod ? {
      id: modStore.lastSelectedMod.package_id,
      name: modStore.lastSelectedMod.name,
      tags: modStore.lastSelectedMod.tags,
      groups: groupStore.takeGroupsByModId(modStore.lastSelectedMod.package_id).map(g => g.name),
      issues: modStore.modIssues.get(normalizePackageToken(modStore.lastSelectedMod.active_package_token || modStore.lastSelectedMod.package_id))
    } : null,

    // 5. 进度
    PROGRESS: taskStore.tasks,

    // 6. 规则
    RULES: {
      communityRules: ruleStore.communityModRules,
      userRules: ruleStore.userModRules,
      userDynamicRules: ruleStore.userDynamicRules,
      currentId: ruleStore.currentId,
    }
  }
})
</script>

<style scoped>
/* 覆盖 json-viewer 默认的浅色背景，适配暗色主题 */
:deep(.jv-container) {
  background: transparent !important;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}
:deep(.jv-container.jv-dark) {
  background: transparent !important;
}
:deep(.jv-key) {
  color: #9cdcfe !important;
}
:deep(.jv-string) {
  color: #ce9178 !important;
}
:deep(.jv-boolean) {
  color: #569cd6 !important;
}
:deep(.jv-number) {
  color: #b5cea8 !important;
}
</style>
