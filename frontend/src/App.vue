<template>
  <div v-if="appStore.isSuspended" class="relative h-[100vh] w-full overflow-hidden font-sans select-none bg-[#0f172a] text-slate-200">
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(56,189,248,0.12),transparent_28%),linear-gradient(160deg,#0f172a_0%,#111827_100%)]"></div>
    <div class="relative z-10 flex h-full flex-col items-center justify-center px-6 text-center">
      <div class="mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/8 px-4 py-1.5 text-xs font-bold uppercase tracking-[0.22em] text-cyan-300">
        <span class="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.8)] animate-pulse"></span>
        RimWorld Running
      </div>
      <h1 class="text-3xl font-black tracking-wide text-slate-100">RimWorld 正在运行</h1>
      <p class="mt-4 max-w-2xl text-sm leading-7 text-slate-400">
        管理器已切换到浏览器静默挂起状态。游戏退出后会自动恢复主界面；也可以手动唤醒。
      </p>
      <div class="mt-10 flex flex-wrap items-center justify-center gap-3">
        <button
          class="rounded-full border border-cyan-400/30 bg-cyan-400/12 px-5 py-2.5 text-sm font-bold tracking-wide text-cyan-200 transition-all hover:-translate-y-0.5 hover:bg-cyan-400/24 hover:text-white"
          @click="appStore.exitSleepMode()"
        >
          唤醒管理界面
        </button>
      </div>
    </div>
  </div>

  <div v-else class="relative h-[100vh] w-full flex flex-col p-1 overflow-hidden font-sans bg-bg-deep text-text-main select-none">
    <RimHeader class="z-100" />
    
    <!-- 主工作区 -->
    <div class="flex-1 flex flex-col min-h-0 relative">
      <!-- 容器 -->
      <div ref="containerRef" class="flex flex-1 w-full overflow-hidden relative">
        
        <!-- 遍历 visibleColumns，同时根据 index 获取 colWidths -->
        <template v-for="(col, index) in visibleColumns" :key="col.id">
          
          <!-- 列容器 -->
          <div class="h-full p-1 transition-opacity relative" :style="{ width: (colWidths[index] || 0) + 'px' }" >
            <!-- 1. 详情 (Details) -->
            <div v-if="col.id === 'details'" class="h-full rounded-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-text-main/5 shadow-2xl">
              <ModDetails data-tour="details-column" />
            </div>

            <!-- 2. 待选库 (Library) -->
            <div v-else-if="col.id === 'library'" class="h-full">
              <ModList v-model="modStore.inactiveIds" title="未启用" listColor="primary" listId="inactive" data-tour="inactive-list" />
            </div>

            <!-- 3. 启用/排序 (Active) - 包含规则编辑器逻辑 -->
            <div v-else-if="col.id === 'active'" class="h-full">
              <ModList v-model="modStore.activeIds" title="启用" :hasSidebar="true" listColor="success" listId="active" data-tour="active-list" />
            </div>

            <!-- 4. 辅助/分组 (Sidebar Tabs) -->
            <div v-else-if="col.id === 'sidebar'" class="h-full">
              <div class="h-full flex flex-col relative" data-tour="sidebar-column">
                <div class="flex-1 overflow-hidden grid grid-cols-1 grid-rows-1">
                  <!-- 如果有规则ID，显示编辑器，否则显示列表 -->
                  <ModRuleEditor v-if="ruleStore.currentId" title="规则" listColor="warn" class="rounded-b-none col-start-1 row-start-1 w-full" />
                  <Transition v-else
                    enter-active-class="transition-opacity duration-300 ease-out"
                    enter-from-class="opacity-0"
                    enter-to-class="opacity-100"
                    leave-active-class="transition-opacity duration-300 ease-in"
                    leave-from-class="opacity-100"
                    leave-to-class="opacity-0">
                    <KeepAlive>
                      <ModList v-if="appStore.activeSidebarTab === 'temp'" v-model="modStore.tempIds" title="临时" listColor="warning" listId="temp" class="rounded-b-none col-start-1 row-start-1 w-full"/>
                      <GroupList v-else-if="appStore.activeSidebarTab === 'group'" v-model="groupStore.groupList" title="分组" listColor="special" class="rounded-b-none col-start-1 row-start-1 w-full"/>
                      <BackupList v-else-if="appStore.activeSidebarTab === 'backup'" class="rounded-b-none col-start-1 row-start-1 w-full"/>
                    </KeepAlive>
                  </Transition>
                </div>
                
                <!-- 标签页切换 -->
                <div class="absolute left-5.5 top-0.5 p-0.5 h-8 flex text-sm font-bold" data-tour="sidebar-tab">
                  <!-- <FocusTabs v-model="activeTab" :tabs="tabs" :blurAmount="3" borderColor="#059669" class="top-0 opacity-100"/> -->
                  <SegmentedTabs v-model="appStore.activeSidebarTab" :options="appStore.SIDEBAR_TABS" @click="ruleStore.currentId=null" />
                </div>

                <!-- 底部按钮组 -->
                <div class="p-3 rounded-b-2xl grid grid-cols-3 gap-2 bg-bg-surface/80 shadow-2xl backdrop-blur-md border-t border-text-main/5" data-tour="base-button-group">
            
                  <!-- 刷新按钮 -->
                  <div :class="{'scan': appStore.isScanRunning}" v-tooltip="'默认增量扫描文件，只扫描存在变动的文件'"
                    data-tour="refresh-button"
                    class="col-span-1 py-1 rounded-lg bg-text-main/5 border border-text-main/5 group
                          text-sm text-gray-300 font-bold uppercase tracking-wider relative cursor-pointer
                          hover:bg-text-main/10 hover:text-text-main hover:border-text-main/20
                          active:scale-95 transition-all duration-200 group flex items-center justify-center gap-1"
                    @click="modStore.scanMods()"
                    :disabled="appStore.isScanRunning"
                  >
                    <!-- 这里保留注释位，必要时可恢复独立图标 -->
                    <span >{{ appStore.isScanRunning ? '扫描中...' : '刷新' }}</span>
                    
                    <button v-show="!appStore.isScanRunning" v-tooltip="'强制刷新，会扫描所有文件，包括未变动的文件，比较耗时'"
                      class="absolute bottom-full py-1 px-2 mb-1.5 rounded-lg bg-accent-secondary/50 border border-text-main/10 transition-all duration-500
                          text-sm text-text-dim font-bold uppercase tracking-wider opacity-0 invisible group-hover:opacity-100 group-hover:visible
                          hover:bg-accent-secondary/80 hover:text-text-main hover:border-text-main"
                          @click.stop="modStore.scanMods(null, true)">
                      强制刷新
                    </button>

                  </div>
                  <!-- 自动排序按钮 -->
                  <button data-tour="autosort-button" class="col-span-1 py-1 rounded-lg text-sm font-bold uppercase tracking-wider bg-accent-tip/80 text-black hover:bg-accent-tip shadow-lg shadow-accent-primary/10
                          flex items-center justify-center gap-1 transition-all duration-300 relative overflow-hidden"
                          @click="modStore.autoSortMods()" v-tooltip="'根据规则设定自动排序当前启用的所有模组，如果排序效果不如旧版理想，可在设置中切换回旧版排序逻辑。'"
                  >
                    <span >自动排序</span>
                  </button>

                  <!-- 保存按钮 (Dirty 状态提示) -->
                  <button data-tour="save-button" class="col-span-1 py-1 rounded-lg text-sm font-bold uppercase tracking-wider
                          flex items-center justify-center gap-1 transition-all duration-300 relative overflow-hidden"
                    :class="[modStore.isDirty 
                        ? 'bg-accent-secondary text-black hover:bg-accent-warn shadow-[0_0_15px_rgba(234,179,8,0.4)] animate-pulse-soft' 
                        : 'bg-accent-primary/60 text-black hover:bg-accent-primary shadow-lg shadow-accent-primary/10'
                    ]"
                    @click="orderStore.saveLoadOrder()"
                  >
                    <!-- Dirty 状态下的流光效果 -->
                    <div v-if="modStore.isDirty" class="absolute inset-0 bg-text-main/20 -translate-x-full animate-shimmer skew-x-12"></div>
                    
                    <svg v-if="modStore.isDirty" class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg>
                    <svg v-else class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                    
                    <span>{{ modStore.isDirty ? '保存变动' : '保存' }}</span>
                  </button>

                  <!-- 启动游戏 -->
                  <button data-tour="launch-button" class="col-span-3 py-3 mt-1 rounded-lg bg-accent-success text-text-main text-mdfont-bold 
                          shadow-lg shadow-accent-success/20 flex items-center justify-center gap-2 
                          transition-all duration-200 uppercase tracking-widest
                          hover:bg-[#059669] hover:shadow-accent-success/40 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
                    @click="appStore.launchGame()"
                  >
                    <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M5 3l14 9-14 9V3z"/></svg>
                    启动游戏
                  </button>

                </div>

              </div>
            </div>

          </div>

          <!-- 动态分割线 -->
          <Resizer v-if="index < visibleColumns.length - 1" :active="resizeState.activeIndex === index" 
            @mousedown="startResize(index, $event)" />

        </template>
        
      </div>

    </div>

    <!-- 游戏运行中的临时浮动指示器 -->
    <Transition
      enter-active-class="transition-all duration-500 ease-out"
      enter-from-class="-translate-y-full opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition-all duration-300 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="-translate-y-full opacity-0"
    >
      <div v-if="appStore.isGameRunning" 
        class="fixed top-5 left-1/2 -translate-x-1/2 z-9999 flex items-center bg-black/80 backdrop-blur-md border border-accent-tip/30 p-1.5 pl-4 rounded-full shadow-[0_10px_30px_rgba(0,0,0,0.8)]">
        
        <div class="flex items-center gap-2 mr-4 text-sm font-bold text-text-main">
          <span class="relative flex h-3 w-3">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-tip opacity-75"></span>
            <span class="relative inline-flex rounded-full h-3 w-3 bg-accent-tip shadow-[0_0_10px_#eab308]"></span>
          </span>
          游戏正在后台运行
        </div>

        <button @click="appStore.enterSleepMode()"
          class="px-4 py-1.5 bg-accent-primary/20 hover:bg-accent-tip text-accent-tip hover:text-black rounded-full text-xs font-bold transition-all border border-accent-tip/30">
          恢复低功耗休眠
        </button>
      </div>
    </Transition>

    <!-- 列表对比抽屉 -->
    <ListDiffView
      :list-a="modStore.activeIds"
      title-a="当前启用"
      :list-b="orderStore.backupDisplayIds || []"
      :title-b="currentBackupDisplayTitle"
      :name-map-a="modStore.nameMap"
      :name-map-b="orderStore.backupNameMap"
    />
    

    <!-- 日志 -->
    <LogViewer />

    <!-- 测试 -->
    <div v-if="appStore.settings.debug_mode">
      <TestPage class="fixed bottom-4 left-4 " v-show="appStore.uiState.showTestDrawer" />
      <DebugPanel />
    </div>
    <!-- 重复包名冲突弹窗 -->
    <ConflictResolver />

    <!-- AI 生成数据弹窗 -->
    <ModAliasReviewModal />
    <!-- AI 会话链路弹窗 -->
    <AiSessionTraceModal />
    <!-- 文件搜索工作台 -->
    <FileSearchWorkbench />
    <!-- AI 定义管理器 -->
    <AIDefinitionManager />

    <!-- 工坊更新管理中心 -->
    <WorkspaceOverlay />

    <!-- 贴图优化功能面板 -->
    <TextureOptModal />

    <!-- 模组配置弹窗 -->
    <ModConfigManagerModal
      :visible="appStore.uiState.showModConfigManager"
      @close="appStore.uiState.showModConfigManager = false"
    />

    <!-- 环境管理抽屉 -->
    <ProfileDrawer /> 

    <!-- 缺失项下载管理 -->
    <MissingInstallDialog />

    <!-- 引导中心浮动按钮 -->
    <GuideCenter />
    
    <!-- 设置弹窗 -->
    <SettingsModal />

    <!-- 模组包/数据包传输弹窗 -->
    <PackageTransferDialog />

    <!-- 规则面板 -->
    <RulePanel />

    <!-- 确认弹窗 -->
    <Confirm />

    <!-- 补充建议弹窗 -->
    <SupplementSelectionDialog />

    <!-- 更新弹窗 -->
    <UpdateModal />

    <!-- 右键菜单 -->
    <ContextMenu />

    <!-- 悬浮面板 -->
    <HoverPanel />

    <!-- 状态条 -->
    <StatusBar class="relative z-20 flex-none" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick, defineAsyncComponent, h } from 'vue'
import { useModStore } from './stores/modStore'
import { useAppStore } from './stores/appStore'
import { useRuleStore } from './stores/ruleStore'
import { useGroupStore } from './stores/groupStore'
import { useOrderStore } from './stores/orderStore'
import { useGuideStore } from './stores/guideStore'
import RimHeader from './components/RimHeader.vue'
import ModDetails from './components/ModDetails.vue'
import ModList from './components/ModList.vue'
import GroupList from './components/GroupList.vue'
import SettingsModal from './components/SettingsPanel.vue'
import StatusBar from './components/StatusBar.vue'
import FocusTabs from './components/utils/FocusTabs.vue'
import ContextMenu from './components/common/ContextMenu/ContextMenu.vue'
import HoverPanel from './components/common/HoverPanel.vue'
import BackupList from './components/BackupList.vue'
import ListDiffView from './components/ListDiffView.vue'
import LogViewer from './components/LogViewer.vue'
import ConflictResolver from './components/ConflictResolver.vue'
import DebugPanel from './components/DebugPanel.vue'
import RulePanel from './components/RulePanel.vue'
import ModRuleEditor from './components/ModRuleEditor.vue'
import Confirm from './components/common/Confirm.vue'
import SegmentedTabs from './components/utils/SegmentedTabs.vue'
import ProfileDrawer from './components/ProfileDrawer.vue'
import Test from './components/temp/test.vue'
import ModAliasReviewModal from './components/ModAliasReviewModal.vue'
import AiSessionTraceModal from './components/AiSessionTraceModal.vue'
import FileSearchWorkbench from './components/FileSearchWorkbench.vue'
import AIDefinitionManager from './components/AIDefinitionManager.vue'
import WorkspaceOverlay from './components/workspace/WorkspaceOverlay.vue'
import UpdateModal from './components/UpdateModal.vue'
import GuideCenter from './components/GuideCenter.vue'
import TextureOptModal from './components/TextureOptModal.vue'
import ModConfigManagerModal from './components/ModConfigManagerModal.vue'
import SupplementSelectionDialog from './components/SupplementSelectionDialog.vue'
import MissingInstallDialog from './components/MissingInstallDialog.vue'
import PackageTransferDialog from './components/PackageTransferDialog.vue'

const updateModal = ref(null);

const appStore = useAppStore()
const modStore = useModStore()
const ruleStore = useRuleStore()
const groupStore = useGroupStore()
const orderStore = useOrderStore()
const guideStore = useGuideStore()

const tabs = ['临时', '分组', '备份']
const activeTab = ref(tabs[0])
const currentBackupDisplayTitle = computed(() => {
  // 优先显示导入文件声明的列表名，其次再回退到文件名。
  if (orderStore.currentBackupName) return orderStore.currentBackupName
  if (orderStore.currentBackupFile) {
    return orderStore.currentBackupFile.split(/[/\\]/).pop()
  }
  return '对比文件'
})

// --- 拖拽调整宽度逻辑 ---
const containerRef = ref(null)


// 计算当前可见的列
const visibleColumns = computed(() => {
  return appStore.settings.ui.main_layout.filter(col => col['visible'])
})

// 动态宽度管理
const MIN_WIDTH = 200
const colWidths = ref([]) // 变成了 ref 数组，长度动态变化

// 初始化或重置宽度（平均分配）
const distributeEvenly = () => {
  if (!containerRef.value) return
  const totalW = containerRef.value.clientWidth
  const count = visibleColumns.value.length
  if (count === 0) return
  const avg = totalW / count
  colWidths.value = new Array(count).fill(avg)
}

// 监听可见列数量变化
// 当用户切换设置显示/隐藏列时，重新计算布局
watch(
  () => visibleColumns.value.length,
  () => {
    // 这是一个简单策略：列数变动时重置为平分
    // 如果想要更高级的（保留其他列宽度），逻辑会复杂很多，平分是最稳健的
    nextTick(() => distributeEvenly())
  },
  { flush: 'post' } // 确保 DOM 更新后执行
)

// 拖拽调整逻辑
const resizeState = reactive({
  isDragging: false,
  activeIndex: -1, // 指向分割线左侧的列索引
  startX: 0,
  startLeftW: 0,
  startRightW: 0
})

const startResize = (index, e) => {
  e.preventDefault()
  resizeState.isDragging = true
  resizeState.activeIndex = index
  resizeState.startX = e.clientX
  
  // 记录受影响的两个列：index 和 index+1
  resizeState.startLeftW = colWidths.value[index]
  resizeState.startRightW = colWidths.value[index + 1]

  // 全局监听
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize' // 强制光标
  document.body.style.userSelect = 'none'   // 防止选中文字
}
// 拖动中
const onMouseMove = (e) => {
  if (!resizeState.isDragging) return
  const idx = resizeState.activeIndex
  const delta = e.clientX - resizeState.startX
  // 理论新宽度
  let newLeft = resizeState.startLeftW + delta
  let newRight = resizeState.startRightW - delta
  // 约束检查
  if (newLeft < MIN_WIDTH) {
    const diff = MIN_WIDTH - newLeft
    newLeft = MIN_WIDTH
    newRight -= diff
  }
  // 如果右边太小
  if (newRight < MIN_WIDTH) {
    const diff = MIN_WIDTH - newRight
    newRight = MIN_WIDTH
    newLeft -= diff
  }
  // 更新数组
  colWidths.value[idx] = newLeft
  colWidths.value[idx + 1] = newRight
}
// 停止拖动
const stopResize = () => {
  resizeState.isDragging = false
  resizeState.activeIndex = -1
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
const isEditableHistoryTarget = (target) => {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return !!target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')
}
const handleListHistoryKeydown = (event) => {
  if (isEditableHistoryTarget(event.target)) return
  const key = String(event.key || '').toLowerCase()
  const isModifierPressed = event.ctrlKey || event.metaKey
  const isUndo = isModifierPressed && !event.shiftKey && key === 'z'
  const isRedo = isModifierPressed && (key === 'y' || (event.shiftKey && key === 'z'))
  if (!isUndo && !isRedo) return

  if (isUndo && modStore.canUndoListHistory) {
    event.preventDefault()
    modStore.undoListHistory()
  } else if (isRedo && modStore.canRedoListHistory) {
    event.preventDefault()
    modStore.redoListHistory()
  }
}
// 处理更新弹窗
function handleUpdate(changelog) {
  // updateModal.value.show(changelog); // 注意要加 .value
}

// 生命周期与自适应
let resizeObserver = null
onMounted(() => {
  console.log("应用已启动，正在初始化存储……")
  window.addEventListener('keydown', handleListHistoryKeydown)
  // 确保 API 存在
  if (window.pywebview) {
    window.pywebview.api.monitor_frontend_ready()
  } else {
    window.addEventListener('pywebviewready', () => {
      window.pywebview.api.monitor_frontend_ready()
    })
  }
  // 确保数据初始化
  appStore.initialize()
  // 监听后端传递过来的升级上下文
  watch(() => appStore.upgradeContext, (ctx) => {
    if (ctx && ctx.version_changed) {
      if (ctx.pending_actions && ctx.pending_actions.includes('show_update_news')) {
        // 直接通过状态控制弹窗显示，不传参，组件内部会自己读 context
        appStore.uiState.showUpdateModal = true
      }
    }
  }, { immediate: true }) // 立即执行一次以防数据已经加载

  // === 动态尺寸调整 ===
  distributeEvenly()  // 初始平均分配宽度
  // 监听容器尺寸变化
  if (containerRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const newTotalWidth = entry.contentRect.width
        // 计算当前记录的总宽
        const currentTotalWidth = colWidths.value.reduce((a, b) => a + b, 0)
        // 如果是首次加载或者误差过大，或者列数对不上，重置
        if (currentTotalWidth === 0 || colWidths.value.length !== visibleColumns.value.length) {
          distributeEvenly()
          return
        }
        // 按比例缩放所有列
        const scale = newTotalWidth / currentTotalWidth
        // 避免除以0或无效缩放
        if (!isFinite(scale) || scale === 0) return 
        colWidths.value = colWidths.value.map(w => w * scale)
      }
    })
    resizeObserver.observe(containerRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleListHistoryKeydown)
  orderStore.saveInactiveOrder();  // 退出前先保存停用列表顺序
  if (resizeObserver) resizeObserver.disconnect()
  stopResize()
})
</script>

<script>
// 调节线组件
const Resizer = (props, { emit }) => {
  return h('div', {
    // 容器：透明，宽热区，z-index高，负margin抵消宽度以保持布局紧凑
    class: [
      'w-4 h-full cursor-col-resize z-50 flex justify-center items-center flex-shrink-0 -mx-2 select-none outline-none touch-none', 
      'group' // 用于 hover 状态控制子元素
    ],
    onMousedown: (e) => emit('mousedown', e)
  }, [
    // 视觉线：平时是细线，Active/Hover 时变色
    h('div', { class: ['w-px rounded-full transition-all duration-200 ease-out pointer-events-none',
        // 高度变化：平时短一点显得优雅，交互时变全高
        props.active ? 'h-9/10' : 'h-2/5 group-hover:h-8/10',
        // 颜色与发光变化
        props.active 
          ? 'bg-accent-special w-2 shadow-[0_0_10px_rgba(var(--color-accent-special),0.8)]' 
          : 'bg-text-main/10 group-hover:bg-accent-special/50'
      ]
    })
  ])
}
// 定义异步组件
const TestPage = defineAsyncComponent({
  // 加载函数：利用 Vite 的环境变量模式
  loader: () => {
    // 只有在开发模式下才尝试加载，生产模式直接返回一个空组件
    if (import.meta.env.DEV) {
      return import('./components/temp/test.vue').catch(() => {
        // console.warn('测试组件加载失败，可能文件已被删除。')
        return { render: () => null } // 加载失败时返回一个什么都不渲染的组件
      })
    }
    return Promise.resolve({ render: () => null }) // 生产环境逻辑
  },
  // 加载失败时使用的组件 (可选)
  errorComponent: { render: () => null },
  // 如果加载时间超过此值，则显示加载中组件 (可选)
  timeout: 3000
})
</script>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active { transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(100%); }
/* 自定义动画 Keyframes */
@keyframes shimmer {
  0% { transform: translateX(-100%) skewX(-12deg); }
  100% { transform: translateX(200%) skewX(-12deg); }
}
.animate-shimmer {
  animation: shimmer 2s infinite linear;
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.95; transform: scale(0.98); }
}
.animate-pulse-soft {
  animation: pulse-soft 2s ease-in-out infinite;
}

/* Vue Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 扫描效果 */
.scan {
  position: relative;
  font-weight: 600;
}
.scan span {
  animation: cut 2s infinite;
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.scan:hover {
  scale: 1.05;
}
.scan::after {
  position: absolute;
  content: "";
  width: 100%;
  height: 6px;
  border-radius: 4px;
  background-color: rgba(0, 242, 234, 0.5);
  top: 0px;
  filter: blur(10px);
  animation: scan 2s infinite;
  left: 0;
  z-index: 0;
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.scan::before {
  position: absolute;
  content: "";
  width: 98%;
  height: 6px;
  background: linear-gradient(
      to bottom,
      transparent 0%,
      rgba(0, 242, 234, 0.1) 48%,
      rgba(0, 242, 234, 0.5) 50%,
      rgba(0, 242, 234, 0.1) 52%,
      transparent 100%
    );
  top: 0px;
  animation: scan 2s infinite;
  left: 1%;
  z-index: 1;
  filter: opacity(0.9);
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
@keyframes scan {
  0% {
    top: 10%;
  }
  25% {
    top: 80%;
  }
  50% {
    top: 10%;
  }
  75% {
    top: 80%;
  }
}
@keyframes cut {
  0% {
    clip-path: inset(0 0 0 0);
  }
  25% {
    clip-path: inset(100% 0 0 0);
  }
  50% {
    clip-path: inset(0 0 100% 0);
  }
  75% {
    clip-path: inset(0 0 0 0);
  }
}
</style>
