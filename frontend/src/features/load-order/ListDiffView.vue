<template>
  <Teleport to="body">
    <Transition 
        enter-active-class="transition-transform duration-300 ease-out"
        enter-from-class="-translate-x-full"
        enter-to-class="translate-x-0"
        leave-active-class="transition-transform duration-300 ease-in"
        leave-from-class="translate-x-0"
        leave-to-class="-translate-x-full"
      >
      <!-- 将抽屉壳体收敛到组件内部，保持原有动画和层级结构不变。 -->
      <div v-if="appStore.uiState.showDiffDrawer" class="fixed inset-y-8 top-18 left-0 w-[50vw] z-100 flex flex-col">
        <!-- 1. 上方内凹边角 -->
        <div class="absolute -top-4.5 left-0 w-5 h-5 z-10">
          <!-- 模糊与背景层：利用 mask 裁剪出内凹形状 -->
          <div class="w-full h-full bg-bg-surface/80 mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]"></div>
          <!-- 边框层：SVG 绘制弧线 -->
          <svg class="absolute inset-0 w-full h-full text-border-default fill-none pointer-events-none" viewBox="0 0 20 20">
            <!-- 从左上(0,0) 画弧到 右下(20,20) -->
            <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="1" />
          </svg>
        </div>

        <!-- 2. 抽屉主体 -->
        <div class="flex-1 flex flex-col bg-transparent backdrop-blur-xl rounded-r-2xl border-y border-r border-border-base/10 shadow-2xl overflow-hidden relative">
          
          <div class="flex flex-col h-full bg-bg-surface/80 overflow-hidden border border-border-base/10 shadow-2xl">
            
            <!-- 1. 顶部工具栏 -->
            <div class="flex items-center justify-between px-3 py-2 bg-bg-overlay/5 border-b border-border-base/5 z-20 shrink-0">
              <!-- 图例 -->
              <div class="flex items-center gap-3 text-xs font-bold uppercase tracking-wider">
                <div class="flex items-center gap-1.5"><span class="w-2 h-2 rounded bg-accent-danger"></span>缺失{{ stats.removed }}</div>
                <div class="flex items-center gap-1.5"><span class="w-2 h-2 rounded bg-accent-success"></span>新增{{ stats.added }}</div>
                <div class="flex items-center gap-1.5"><span class="w-2 h-2 rounded bg-accent-warn"></span>移动{{ stats.moved }}</div>
                <div class="flex items-center gap-1.5"><span class="w-2 h-2 rounded bg-accent-warn/50"></span>偏移{{ stats.movedBlock }}</div>
                <div class="flex items-center gap-1.5"><span class="w-2 h-2 rounded bg-bg-neutral"></span>一致{{ stats.same }}</div>
              </div>
              
              <!-- 开关组 -->
              <div class="flex items-center gap-4">
                <div class="relative flex flex-wrap items-center gap-1">
                  <input v-model="colorfulBlocks" type="checkbox" value="" id="b01" class="relative w-6 h-3 scale-80 transition-colors rounded-lg appearance-none cursor-pointer hover:bg-bg-overlay/10 after:hover:bg-bg-contrast checked:hover:bg-accent-success/40 checked:after:hover:bg-accent-success focus:outline-none checked:focus:bg-accent-success/50 checked:after:focus:bg-accent-success focus-visible:outline-none peer bg-bg-overlay/10 after:absolute after:-top-0.5 after:-left-1.5 after:h-4 after:w-4 after:rounded-full after:bg-bg-neutral after:transition-all checked:bg-accent-success/30 checked:after:left-3 checked:after:bg-accent-success disabled:cursor-not-allowed disabled:bg-bg-overlay/10 disabled:after:bg-bg-overlay/10"/>
                  <label v-tooltip="'为不同的区块使用不同颜色便于区分'" for="b01" class="cursor-pointer text-xs text-text-dim peer-disabled:cursor-not-allowed hover:text-text-main transition-colors">
                    多彩区块
                  </label>
                </div>

                <div class="relative flex flex-wrap items-center gap-1">
                  <input v-model="hideIdentical" type="checkbox" value="" id="b02" class="relative w-6 h-3 scale-80 transition-colors rounded-lg appearance-none cursor-pointer hover:bg-bg-overlay/10 after:hover:bg-bg-contrast checked:hover:bg-accent-success/40 checked:after:hover:bg-accent-success focus:outline-none checked:focus:bg-accent-success/50 checked:after:focus:bg-accent-success focus-visible:outline-none peer bg-bg-overlay/10 after:absolute after:-top-0.5 after:-left-1.5 after:h-4 after:w-4 after:rounded-full after:bg-bg-neutral after:transition-all checked:bg-accent-success/30 checked:after:left-3 checked:after:bg-accent-success disabled:cursor-not-allowed disabled:bg-bg-overlay/10 disabled:after:bg-bg-overlay/10"/>
                  <label v-tooltip="'折叠一致区块'" for="b02" class="cursor-pointer text-xs text-text-dim peer-disabled:cursor-not-allowed hover:text-text-main transition-colors">
                    折叠长区块
                  </label>
                </div>
              </div>

            </div>

            <!-- 2. 标题栏 -->
            <div class="toolbar-surface z-20 flex shrink-0 items-center py-1 text-xs font-bold text-text-dim">
              <div class="flex-1 px-2 text-center text-accent-success border-r border-border-base/5 truncate">{{ titleA }} ({{ listA.length }})</div>
              <div class="flex-1 px-2 text-center truncate">{{ titleB }} ({{ listB.length }})</div>
            </div>

            <!-- 3. 核心对比区 -->
            <div class="flex-1 overflow-y-auto custom-scrollbar relative w-full" ref="scrollContainer" @click.self="clearDiffHighlight">
              <div class="flex min-h-full relative w-full">
                
                <!-- 左侧列表 (List A) -->
                <div class="flex-1 flex flex-col min-w-0" ref="listARef">
                  <template v-for="item in displayListA" :key="item.uiKey">
                    
                    <!-- 普通项 -->
                    <div v-if="!item.isPlaceholder" :data-id="item.id" @click="targetItem(item.id)" :style="getRowStyle(item, 'a')"
                      class="flex items-center h-7 px-2 border-b border-x border-border-base/5 transition-colors relative cursor-pointer">
                      <!-- 指示条 (仅在有色时显示) -->
                      <div v-if="shouldShowIndicator(item, 'a')" class="absolute right-0 top-0 bottom-0 w-0.5 transition-all duration-200" :style="getIndicatorStyle(item, 'a')"></div>
                      <span class="w-6 text-xs font-mono text-text-main text-right mr-2 select-none shrink-0 opacity-80">{{ item.originalIndex + 1 }}</span>
                      
                      <!-- 文字颜色逻辑 -->
                      <div class="flex-1 truncate text-sm font-medium transition-colors" :class="getTextClass(item, 'a')" v-tooltip="displayNameById(item.id, 'a')">
                        {{ displayNameById(item.id, 'a') }}
                      </div>
                    </div>

                    <!-- 折叠项 -->
                    <div v-else class="h-7 flex items-center justify-center border-b border-x border-border-base/5 select-none relative"
                      :style="getRowStyle(item, 'a')">
                      <span class="absolute left-4 text-xl text-text-dim" style="writing-mode: vertical-rl;">···</span>
                      <!-- 指示条也继承 -->
                      <div v-if="shouldShowIndicator(item, 'a')" class="absolute right-0 w-0.5 h-full transition-all duration-200" :style="getIndicatorStyle(item, 'a')"></div>
                      <span class="text-xs text-text-disabled tracking-widest scale-90">
                        ··· 已折叠{{ item.hiddenCount ?? item.count }}项 ···
                      </span>
                    </div>

                  </template>
                </div>

                <!-- 中间画布 (SVG) -->
                <div class="relative z-10 w-[48px] shrink-0 bg-bg-inset/60">
                  <svg class="absolute top-0 left-0 w-full h-full pointer-events-none overflow-visible">
                    <!-- 绘制区块 (fill) -->
                    <path v-for="block in renderBlocks" :key="block.id"
                      :d="block.path"
                      :fill="block.renderColor"
                      :fill-opacity="block.fillOpacity"
                      :stroke="block.strokeColor"
                      :stroke-width="block.strokeWidth"
                      :stroke-opacity="block.strokeOpacity"
                      :style="{ filter: block.filter }"
                      class="transition-all duration-300"
                    />
                    <!-- 绘制线条 (stroke) -->
                    <path v-for="line in renderLines" :key="line.id"
                      :d="line.path"
                      fill="none"
                      :stroke="line.renderColor"
                      :stroke-width="line.strokeWidth"
                      :stroke-opacity="line.strokeOpacity"
                      :style="{ filter: line.filter }"
                      stroke-linecap="round"
                      class="transition-all duration-300"
                    />
                  </svg>
                </div>

                <!-- 右侧列表 (List B) -->
                <div class="flex-1 flex flex-col min-w-0" ref="listBRef">
                  <template v-for="item in displayListB" :key="item.uiKey">
                    <div v-if="!item.isPlaceholder" :data-id="item.id" @click="highlightListBItem(item)"
                        class="group/import flex items-center h-7 px-2 border-b border-x border-border-base/5 transition-colors relative cursor-pointer"
                        :style="getRowStyle(item, 'b')">
                      <div v-if="shouldShowIndicator(item, 'b')" class="absolute left-0 top-0 bottom-0 w-0.5 transition-all duration-200" :style="getIndicatorStyle(item, 'b')"></div>
                      <span class="w-6 text-xs font-mono text-text-main text-right mr-2 select-none shrink-0 opacity-80">{{ item.originalIndex + 1 }}</span>


                      <div v-if="getImportStatusMeta(item.id)" v-tooltip="getImportTooltip(item.id)" class="mr-1 shrink-0 rounded-full border px-2 py-0.5 text-[0.7rem] font-bold"
                        :class="getImportStatusMeta(item.id).badgeClass">
                        {{ getImportStatusMeta(item.id).label }}
                      </div>

                      <div v-if="shouldShowImportActions(item.id)"
                        class="absolute right-1 top-1/2 z-10 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition-opacity group-hover/import:opacity-100">
                        <button
                          v-if="canSubscribeImportItem(item.id)"
                          @click.stop="subscribeImportItem(item.id)"
                          v-tooltip="'订阅该导入项对应的工坊项目'"
                          class="rounded-full bg-accent-primary/85 p-1 text-on-accent-primary transition-transform hover:scale-105">
                          <Flag class="size-3" />
                        </button>
                        <button
                          v-if="canDownloadImportItem(item.id)"
                          @click.stop="downloadImportItem(item.id)"
                          v-tooltip="'下载该导入项对应的工坊项目到管理器'"
                          class="rounded-full bg-accent-success/85 p-1 text-on-accent-success transition-transform hover:scale-105">
                          <Download class="size-3" />
                        </button>
                        <button
                          v-if="canOpenImportWorkshop(item.id)"
                          @click.stop="openImportWorkshop(item.id)"
                          v-tooltip="'打开来源页面'"
                          class="rounded-full bg-accent-special/85 p-1 text-on-accent-special transition-transform hover:scale-105">
                          <Link class="size-3" />
                        </button>
                        <button
                          v-if="canRemoveImportItem(item.id)"
                          @click.stop="removeImportItem(item.id)"
                          v-tooltip="'从当前导入序列中移除该项'"
                          class="rounded-full bg-accent-danger/85 p-1 text-on-accent-danger transition-transform hover:scale-105">
                          <X class="size-3" />
                        </button>
                      </div>
                      <div class="min-w-0 flex-1 pr-22">
                        <div class="truncate text-sm font-medium transition-colors" :class="getTextClass(item, 'b')" v-tooltip="getImportTooltip(item.id) || displayNameById(item.id, 'b')">
                          {{ displayNameById(item.id, 'b') }}
                        </div>
                      </div>
                    </div>

                    <div v-else @click="highlightListBItem(item)" class="h-7 flex items-center justify-center border-b border-x border-border-base/5 select-none relative cursor-pointer transition-colors"
                      :style="getRowStyle(item, 'b')">
                      <span class="absolute left-4 text-xl text-text-dim" style="writing-mode: vertical-rl;">···</span>
                      <!-- 指示条也继承 -->
                      <div v-if="shouldShowIndicator(item, 'b')" class="absolute left-0 w-0.5 h-full transition-all duration-200" 
                          :style="getIndicatorStyle(item, 'b')">
                      </div>
                      <span class="text-xs text-text-disabled tracking-widest scale-90">
                        ··· 已折叠{{ item.hiddenCount ?? item.count }}项 ···
                      </span>
                    </div>

                  </template>
                </div>

              </div>
            </div>
          </div>
  
          <!-- 底部动作栏 -->
          <div class="modal-footer flex items-center justify-between gap-3 p-2 px-5">
            <div class="min-w-0">
              <h2 class="text-text-soft font-bold">Mod序列对比</h2>
            </div>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <button v-if="orderStore.importCheckSummary.missing > 0" @click="orderStore.subscribeImportCheckItems(['missing'])" class="px-3 py-1.5 rounded-lg bg-accent-primary/12 hover:bg-accent-primary/25 text-accent-primary border border-accent-primary/30 text-xs font-bold transition-all">
                订阅缺失项 ({{ orderStore.importCheckSummary.missing }})
              </button>
              <button v-if="orderStore.importCheckSummary.missing > 0" @click="orderStore.downloadImportCheckItems(['missing'])" class="px-3 py-1.5 rounded-lg bg-accent-tip/12 hover:bg-accent-tip/25 text-accent-tip border border-accent-tip/30 text-xs font-bold transition-all">
                下载缺失项 ({{ orderStore.importCheckSummary.missing }})
              </button>
              <button v-if="orderStore.importCheckSummary.missing > 0" @click="orderStore.removeImportCheckItems(['missing'])" class="px-3 py-1.5 rounded-lg bg-accent-warning/10 hover:bg-accent-warning/20 text-accent-warning border border-border-base/10 text-xs font-bold transition-all">
                移除缺失项 ({{ orderStore.importCheckSummary.missing }})
              </button>
              <button v-if="orderStore.actionableReplacementImportItems.length > 0" @click="orderStore.subscribeImportCheckItems(['replacement'])" class="px-3 py-1.5 rounded-lg bg-accent-cool/12 hover:bg-accent-cool/25 text-accent-cool border border-accent-cool/30 text-xs font-bold transition-all">
                订阅替代项 ({{ orderStore.actionableReplacementImportItems.length }})
              </button>
              <button v-if="orderStore.actionableReplacementImportItems.length > 0" @click="orderStore.downloadImportCheckItems(['replacement'])" class="px-3 py-1.5 rounded-lg bg-accent-cool/12 hover:bg-accent-cool/25 text-accent-cool border border-accent-cool/30 text-xs font-bold transition-all">
                下载替代项 ({{ orderStore.actionableReplacementImportItems.length }})
              </button>
              <button v-if="orderStore.importCheckSummary.other_version > 0" @click="orderStore.subscribeImportCheckItems(['other_version'])" class="px-3 py-1.5 rounded-lg bg-accent-warn/12 hover:bg-accent-warn/25 text-accent-warn border border-accent-warn/30 text-xs font-bold transition-all">
                订阅其它版本 ({{ orderStore.importCheckSummary.other_version }})
              </button>
              <button v-if="orderStore.importCheckSummary.other_version > 0" @click="orderStore.downloadImportCheckItems(['other_version'])" class="px-3 py-1.5 rounded-lg bg-accent-warn/12 hover:bg-accent-warn/25 text-accent-warn border border-accent-warn/30 text-xs font-bold transition-all">
                下载其它版本 ({{ orderStore.importCheckSummary.other_version }})
              </button>
              <button v-if="orderStore.importCheckSummary.unknown > 0" @click="orderStore.removeImportCheckItems(['unknown'])" class="px-3 py-1.5 rounded-lg bg-bg-overlay/10 hover:bg-bg-overlay/10 text-text-dim border border-border-base/10 text-xs font-bold transition-all">
                移除未知项 ({{ orderStore.importCheckSummary.unknown }})
              </button>
            </div>
            <div class="flex flex-wrap items-center justify-end gap-2">
              
              <button @click="orderStore.applyBackup()" class="px-3 py-1.5 rounded-lg bg-accent-success/20 hover:bg-accent-success/40 text-accent-success border border-accent-success/30 text-xs font-bold transition-all">应用文件序列</button>
              <button @click="appStore.uiState.showDiffDrawer = false" class="px-3 py-1.5 rounded-lg bg-accent-danger/10 hover:bg-accent-danger/20 text-text-dim border border-border-base/10 text-xs font-bold transition-all">关闭</button>
            </div>
          </div>

        </div>

        <!-- 3. 下方内凹边角 -->
        <div class="absolute -bottom-4.5 left-0 w-5 h-5 z-10">
          <!-- 模糊与背景层 -->
          <div class="w-full h-full bg-transparent backdrop-blur-xl mask-[radial-gradient(circle_at_100%_100%,transparent_1.25rem,black_1.3rem)]">
          </div>
          <!-- 边框层 -->
          <svg class="absolute inset-0 w-full h-full text-border-default fill-none pointer-events-none" viewBox="0 0 20 20">
            <!-- 从右上(20,0) 画弧到 左下(0,20) -->
            <path d="M20,0 A20,20 0 0,0 0,20" stroke="currentColor" stroke-width="1" />
          </svg>
        </div>

      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useModStore } from '../mod/stores/modStore'
import { useDebounceFn } from '@vueuse/core'
import { getTailwindColorHex, hexToRgba } from '../../shared/lib/color'
import { useOrderStore } from './orderStore'
import { useAppStore } from '../../app/stores/appStore'
import { Download, Flag, Link, X } from 'lucide-vue-next'


// 抽屉的显隐和底部操作继续复用现有 store，避免迁移后行为变化。
const appStore = useAppStore()
const orderStore = useOrderStore()

const props = defineProps({
  listA: { type: Array, required: true },
  listB: { type: Array, required: true },
  titleA: { type: String, default: 'List A' },
  titleB: { type: String, default: 'List B' },
  nameMapA: { type: Object, default: () => ({}) },
  nameMapB: { type: Object, default: () => ({}) }
})

const modStore = useModStore()
const hideIdentical = ref(true) // 开关隐藏相同项
const colorfulBlocks = ref(false) // 开关多彩区块
const listARef = ref(null)    // 左侧列表 (List A)
const listBRef = ref(null)    // 右侧列表 (List B)
const scrollContainer = ref(null) // 滚动容器，用于同步滚动
const highlightedBlockId = ref('')
const highlightedListBItemKey = ref('')

const renderBlocks = ref([])  // 绘制区块
const renderLines = ref([])    // 绘制线条

const BLOCK_THRESHOLD = 3    // 块阈值，超过这个距离才认为是块移动

// --- 色彩常量 ---
const BLOCK_COLORS = [
  '#72c8a9', '#8cbbff', '#dcedc1', '#5596ff', '#ffe6a6', '#ffabab', '#8a6ab2', 
  '#ffdb4d', '#ffb300', '#a8e6cf', '#ff8f00', '#c6c9ff', '#ff677d', '#1e88e5'
]
const COLOR_REMOVED = getTailwindColorHex('accent-danger') 
const COLOR_ADDED = getTailwindColorHex('accent-success')   
const COLOR_MOVED = getTailwindColorHex('accent-warn') 
const COLOR_MOVED_GRAY = getTailwindColorHex('text-dim')
const COLOR_HIGHLIGHT = getTailwindColorHex('accent-primary')

const IMPORT_STATUS_META = {
  replacement: { label: '替代', badgeClass: 'border-accent-cool/30 bg-accent-cool/10 text-accent-cool' },
  other_version: { label: '其它版本', badgeClass: 'border-accent-warn/30 bg-accent-warn/10 text-accent-warn' },
  missing: { label: '缺失', badgeClass: 'border-accent-warn/30 bg-accent-warn/10 text-accent-warn' },
  unknown: { label: '未知', badgeClass: 'border-accent-danger/30 bg-accent-danger/10 text-accent-danger' },
}


const displayNameById = (id, side = 'a') => {
  // 右侧导入列表中的缺失项可能不在本地 modStore，需要用导入文件自带名称兜底显示。
  const lowerId = String(id || '').toLowerCase()
  if (lowerId && modStore.hasRealModById(lowerId)) {
    return modStore.displayModName(lowerId)
  }
  const importCheckItem = side === 'b' ? orderStore.getImportCheckItem(lowerId) : null
  if (importCheckItem?.name) return importCheckItem.name
  const fallbackMap = side === 'b' ? props.nameMapB : props.nameMapA
  return fallbackMap?.[lowerId] || modStore.displayModName(id)
}
const isProblemImportStatus = (status) => ['missing', 'replacement', 'other_version', 'unknown'].includes(status)
const getImportCheckItem = (rowKey) => orderStore.getImportCheckItem(rowKey)
const getImportStatusMeta = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  if (!item) return null
  if (item.status === 'replacement' && item.installed_via_replacement) {
    return {
      label: '已安装替代',
      badgeClass: 'border-accent-cool/30 bg-accent-cool/15 text-accent-cool',
    }
  }
  return IMPORT_STATUS_META[item.status] || null
}
const getImportTooltip = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  if (!item) return ''
  return item.reason_text || item.warning || ''
}
const shouldShowImportActions = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  if (!item) return false
  return isProblemImportStatus(item.status)
}
const canSubscribeImportItem = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  const source = orderStore.getImportCheckTargetSource(item)
  return source?.kind === 'workshop' && ['missing', 'replacement', 'other_version'].includes(item.status) && !item?.installed_via_replacement
}
const canDownloadImportItem = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  const source = orderStore.getImportCheckTargetSource(item)
  return !!source && ['missing', 'replacement', 'other_version'].includes(item.status) && !item?.installed_via_replacement
}
const canOpenImportWorkshop = (rowKey) => {
  return !!orderStore.getImportCheckTargetSource(getImportCheckItem(rowKey))
}
const canRemoveImportItem = (rowKey) => {
  const item = getImportCheckItem(rowKey)
  return ['missing', 'unknown'].includes(item?.status)
}
const subscribeImportItem = async (rowKey) => {
  await orderStore.subscribeImportCheckItems([], [rowKey])
}
const downloadImportItem = async (rowKey) => {
  await orderStore.downloadImportCheckItems([], [rowKey])
}
const openImportWorkshop = (rowKey) => {
  orderStore.openImportCheckWorkshop(rowKey)
}
const removeImportItem = async (rowKey) => {
  await orderStore.removeImportCheckItems([], [rowKey])
}
const displayListA = computed(() => foldList(analysis.value.resA))  // 左侧列表 (List A)，经过折叠处理
const displayListB = computed(() => foldList(analysis.value.resB))   // 右侧列表 (List B)，经过折叠处理

// 统计缺失、新增、移动（单项移动）、偏移（块移动）、相同项的数量
const stats = computed(() => {
  const res = { removed: 0, added: 0, moved: 0, movedBlock: 0, same: 0 }
  analysis.value.resA.forEach(item => {
    if (item.type === 'removed') res.removed++
    else if (item.type === 'moved') res.movedBlock++
    else if (item.type === 'same') res.same++
  })
  analysis.value.resB.forEach(item => {
    if (item.type === 'added') res.added++
  })
  analysis.value.blocks.forEach(block => {
    if (block.count=== 1) res.moved++
  })
  res.movedBlock = res.movedBlock - res.moved
  return res
})

// --- 1. 核心算法 ---
/**
 * 计算分析结果，生成渲染数据
 * 主要用于比较两个列表（listA 和 listB）的差异，并识别其中的移动、新增、删除和相同元素。
 * 类似于 diff 算法，但更侧重于识别“块移动”（即连续元素的移动），并支持多彩色标记以增强可视化效果。
 */
const analysis = computed(() => {
  const A = props.listA
  const B = props.listB
  // 1. 初始化结果数组 resA 和 resB
  // 默认假设 A 中的所有元素都被删除了，B 中的所有元素都是新增的。
  // 如果后续匹配成功，会将这些状态修改为 'same' (相同) 或 'moved' (移动)。
  // originalIndex: 记录元素在原始数组中的位置，用于后续可能的回溯或排序。
  // count: 默认为 1，表示单个元素。如果发现是连续移动块，这个值会变成块的长度。
  const resA = A.map((id, i) => ({ id, originalIndex: i, type: 'removed', blockId: null, count: 1 }))
  const resB = B.map((id, i) => ({ id, originalIndex: i, type: 'added', blockId: null, count: 1 }))
  
  // 2. 构建 B 的哈希索引
  // 目的：为了在遍历 A 时，能以 O(1) 的时间复杂度快速找到当前元素在 B 中的位置。
  // 结构：Map<id, Array<indexInB>>
  // 为什么存数组？因为 B 中可能存在重复的 id，需要记录它出现的所有位置。
  const mapB = new Map()
  B.forEach((id, i) => {
    if (!mapB.has(id)) mapB.set(id, [])
    mapB.get(id).push(i)
  })
  
  let blockCounter = 0 // 用于生成唯一的块 ID (blk-0, blk-1, ...)
  const blocks = []    // 存储所有识别出的“块”的信息

  // 遍历 A 数组，尝试在 B 中寻找匹配
  let i = 0
  while (i < A.length) {
    const id = A[i]
    
    // 只有当 A 中的元素在 B 中也存在时，才有可能发生匹配或移动
    if (mapB.has(id)) {
      const possibleIndicesB = mapB.get(id)
      let bestLen = 0       // 记录找到的最长匹配长度
      let bestStartB = -1   // 记录最长匹配在 B 中的起始位置

      // 3. 贪心算法寻找最长公共子串
      // A[i] 可能在 B 中出现多次（possibleIndicesB），需要找到最“划算”的那个位置。
      // “划算”的定义：从该位置开始，能和 A[i] 连续匹配的元素数量最多。
      for (const startB of possibleIndicesB) {
        let len = 0
        // 尝试向后扩展匹配
        while (
          i + len < A.length &&           // A 未越界
          startB + len < B.length &&      // B 未越界
          A[i + len] === B[startB + len] && // 元素值必须相等
          resB[startB + len].type === 'added' // 关键：B 中的元素必须是 'added' 状态
          // 解释：如果 B 中的元素已经是 'same' 或 'moved'，说明它已经被前面的块“吃掉”了，
          // 不能重复匹配。这保证了每个元素只属于一个块。
        ) {
          len++
        }
        // 更新最佳匹配结果
        if (len > bestLen) {
          bestLen = len
          bestStartB = startB
        }
      }

      // 判断是否启用块移动拆分逻辑
      if (bestLen > 0 && bestLen <= BLOCK_THRESHOLD) {
        bestLen = 1
      }

      // 4. 如果找到了有效的匹配块 (长度 > 0)
      if (bestLen > 0) {
        const blockId = `blk-${blockCounter++}`
        
        // 判断是否发生了移动：
        // 如果在 A 中的位置 i 和在 B 中的位置 bestStartB 不一样，说明这块整体移动了。
        const isMoved = i !== bestStartB
        
        // 预分配一个颜色，用于 UI 渲染时区分不同的块（多彩模式）
        const cyclicColor = BLOCK_COLORS[blockCounter % BLOCK_COLORS.length]
        
        // 记录块信息
        blocks.push({
          id: blockId,
          cyclicColor, 
          isMoved,
          startIndexA: i,      // 块在 A 中的起始索引
          count: bestLen,      // 块的长度
          startIndexB: bestStartB // 块在 B 中的起始索引
        })

        // 5. 更新 resA 和 resB 中的元素状态
        for (let k = 0; k < bestLen; k++) {
          // 获取 A 和 B 中对应的元素引用
          const itemA = resA[i + k]
          const itemB = resB[bestStartB + k]
          
          // 更新 A 侧元素状态
          itemA.type = isMoved ? 'moved' : 'same' // 移动 或 未变
          itemA.blockId = blockId                 // 关联块 ID
          itemA.cyclicColor = cyclicColor         // 关联颜色
          itemA.count = bestLen                   // 记录所属块的总长度
          
          // 更新 B 侧元素状态
          itemB.type = isMoved ? 'moved' : 'same'
          itemB.blockId = blockId
          itemB.cyclicColor = cyclicColor
          itemB.count = bestLen
        }
        
        // 6. 跳过已处理的元素
        // 因为处理了一个长度为 bestLen 的块，所以 i 应该直接跳过这个块，
        // 而不是普通的 i++。这提高了效率并防止重复处理。
        i += bestLen
        continue
      }
    }
    // 如果当前元素在 B 中没找到，或者没找到匹配块，则视为纯粹的删除，继续处理下一个
    i++
  }

  // resA: 包含了删除、移动、未变的元素信息
  // resB: 包含了新增、移动、未变的元素信息
  // blocks: 所有识别出的连续块的元数据
  return { resA, resB, blocks }
})

// --- 2. 动态颜色计算逻辑 ---

// 计算最终显示的颜色 (用于背景、线条、指示条)
const getRenderColor = (itemOrBlock) => {
  if (itemOrBlock.type === 'removed') return COLOR_REMOVED
  if (itemOrBlock.type === 'added') return COLOR_ADDED
  if (itemOrBlock.type === 'same') return 'transparent'

  // Moved Logic
  if (itemOrBlock.type === 'moved' || itemOrBlock.isMoved) {
    // 1. 单独移动 (count === 1) -> 始终多彩
    if (itemOrBlock.count === 1) {
      if (colorfulBlocks.value) return itemOrBlock.cyclicColor
      else return COLOR_MOVED
    }
    // 2. 整体移动 (count > 1) -> 根据开关决定
    if (colorfulBlocks.value) return itemOrBlock.cyclicColor
    else return COLOR_MOVED_GRAY
  }
  return 'transparent'
}
// 计算背景色 (基于 RenderColor 加上透明度)
const getBgColor = (item) => {
  const color = getRenderColor(item)
  if (color === 'transparent') return 'transparent'
  if (!color.startsWith('#')) {
    console.error(`Invalid color:`,item,color, COLOR_REMOVED)
  }
  return hexToRgba(color, 0.2) // 统一 10% 透明度
}
const getHighlightColor = (itemOrBlock) => {
  const color = getRenderColor(itemOrBlock)
  return color === 'transparent' ? COLOR_HIGHLIGHT : color
}
const getListBItemKey = (item) => {
  if (!item) return ''
  if (item.isPlaceholder) return `b:${item.uiKey}`
  return `b:${item.id}:${item.originalIndex ?? item.uiKey}`
}
const isHighlightedItem = (item, side = 'a') => {
  if (!item) return false
  if (item.blockId) return item.blockId === highlightedBlockId.value
  return side === 'b' && getListBItemKey(item) === highlightedListBItemKey.value
}
const getRowStyle = (item, side = 'a') => {
  const isHighlighted = isHighlightedItem(item, side)
  const baseColor = isHighlighted ? getHighlightColor(item) : getRenderColor(item)
  return {
    backgroundColor: isHighlighted
      ? hexToRgba(baseColor, item.type === 'same' ? 0.14 : 0.28)
      : getBgColor(item),
    borderColor: isHighlighted ? hexToRgba(baseColor, 0.4) : '',
    boxShadow: isHighlighted
      ? `inset 0 0 0 1px ${hexToRgba(baseColor, 0.7)}, inset 0 0 18px ${hexToRgba(baseColor, 0.18)}`
      : 'none',
    zIndex: isHighlighted ? 1 : 0,
  }
}
// 计算文字样式类
const getTextClass = (item, side = 'a') => {
  const isHighlighted = isHighlightedItem(item, side)
  if (item.type === 'removed') return 'text-accent-danger font-bold'
  if (item.type === 'added') return 'text-accent-success font-bold'
  if (item.type === 'same') return isHighlighted ? 'text-text-main font-semibold' : 'text-text-dim' // 灰色
  
  if (item.type === 'moved') {
    if (item.count === 1) return 'text-accent-warn font-bold' // 单移：橙色
    return isHighlighted ? 'text-accent-warn font-semibold' : 'text-accent-warn/70' // 整移：使用同一警告色降低噪音
  }
  return 'text-text-dim'
}
// 计算侧边指示条样式类
const shouldShowIndicator = (item, side = 'a') => {
  return item.type !== 'same' || isHighlightedItem(item, side)
}
const getIndicatorStyle = (item, side = 'a') => {
  const isHighlighted = isHighlightedItem(item, side)
  const color = isHighlighted ? getHighlightColor(item) : getRenderColor(item)
  return {
    backgroundColor: color,
    width: isHighlighted ? '4px' : '2px',
    opacity: isHighlighted ? 1 : 0.9,
    boxShadow: isHighlighted ? `0 0 12px ${hexToRgba(color, 0.75)}` : 'none',
  }
}
const clearDiffHighlight = () => {
  highlightedBlockId.value = ''
  highlightedListBItemKey.value = ''
}
const highlightListBItem = (item) => {
  const nextBlockId = item?.blockId || ''
  const nextItemKey = getListBItemKey(item)
  const isSameSelection = highlightedBlockId.value === nextBlockId && highlightedListBItemKey.value === nextItemKey

  modStore.currentTargetId = ''
  if (isSameSelection) {
    clearDiffHighlight()
    return
  }

  highlightedBlockId.value = nextBlockId
  highlightedListBItemKey.value = nextItemKey
}

// --- 3. 折叠逻辑 ---
// 折叠逻辑：将连续的 same 和 moved 项折叠为一个占位符，以减少渲染负担
// 注意：折叠后的列表需要重新计算 uiKey，以便正确渲染
const foldList = (list) => {
  if (!hideIdentical.value) return list.map(item => ({ ...item, uiKey: item.id }))

  const result = []
  let blockItems = []

  const flushBlock = () => {
    if (blockItems.length === 0) return
    const firstItem = blockItems[0]
    
    // 折叠条件：类型是 same 或 moved，且长度 > 4
    if ((firstItem.type === 'same' || firstItem.type === 'moved') && blockItems.length > 4) {
      result.push({ ...blockItems[0], uiKey: blockItems[0].id }) // Head
      
      // 占位符继承属性以便正确染色
      result.push({ 
        isPlaceholder: true, 
        hiddenCount: blockItems.length - 2,
        uiKey: `ph-${firstItem.blockId}`,
        blockId: firstItem.blockId,
        // 继承用于颜色计算的关键属性
        type: firstItem.type,
        cyclicColor: firstItem.cyclicColor,
        count: firstItem.count // 这里的count是指block的总大小
      })
      
      result.push({ ...blockItems[blockItems.length-1], uiKey: blockItems[blockItems.length-1].id }) // Tail
    } else {
      blockItems.forEach(item => result.push({ ...item, uiKey: item.id }))
    }
    blockItems = []
  }

  // 这里的遍历逻辑需要改进，确保按blockId分组
  let currentBlockId = null
  
  for (const item of list) {
    // 只有同一 blockId 且 type 不是 added/removed (它们通常也是 blockId null) 
    // 其实 analysis 已经分配了 blockId 给 same 和 moved
    if (item.blockId && item.blockId === currentBlockId) {
      blockItems.push(item)
    } else {
      flushBlock()
      if (item.blockId) {
        currentBlockId = item.blockId
        blockItems.push(item)
      } else {
        currentBlockId = null
        result.push({ ...item, uiKey: item.id })
      }
    }
  }
  flushBlock()
  return result
}

// --- 4. 绘图逻辑 ---
// 绘制块和线
const getCoords = (id, containerRef) => {
  if (!containerRef) return null
  const el = containerRef.querySelector(`[data-id="${id}"]`)
  if (!el) return null
  return {
    top: el.offsetTop,
    height: el.offsetHeight,
    mid: el.offsetTop + el.offsetHeight / 2
  }
}
// 计算块的颜色
const draw = () => {
  const blocks = []
  const lines = []
  const svgWidth = 48 

  analysis.value.blocks.forEach(blk => {
    const isHighlighted = blk.id === highlightedBlockId.value
    // 默认只绘制移动块；当某个组被右侧选中时，临时补出这组的映射关系。
    if (!blk.isMoved && !isHighlighted) return 

    // 获取坐标 (逻辑同前)
    const startIdA = analysis.value.resA[blk.startIndexA].id
    const endIdA = analysis.value.resA[blk.startIndexA + blk.count - 1].id
    const startIdB = analysis.value.resB[blk.startIndexB].id
    const endIdB = analysis.value.resB[blk.startIndexB + blk.count - 1].id

    const coordsStartA = getCoords(startIdA, listARef.value)
    const coordsEndA = getCoords(endIdA, listARef.value)
    const coordsStartB = getCoords(startIdB, listBRef.value)
    const coordsEndB = getCoords(endIdB, listBRef.value)

    if (!coordsStartA || !coordsEndA || !coordsStartB || !coordsEndB) return

    // 实时计算最终颜色
    const finalColor = isHighlighted ? getHighlightColor(blk) : getRenderColor(blk)
    const filter = isHighlighted ? `drop-shadow(0 0 6px ${hexToRgba(finalColor, 0.55)})` : 'none'

    // 控制点
    const cp1x = svgWidth * 0.4
    const cp2x = svgWidth * 0.6

    // 单独移动 (Count === 1) -> 画线
    if (blk.count === 1) {
      const amid = coordsStartA.mid
      const bmid = coordsStartB.mid
      lines.push({
        id: blk.id,
        path: `M 0 ${amid} C ${cp1x} ${amid}, ${cp2x} ${bmid}, ${svgWidth} ${bmid}`,
        renderColor: finalColor,
        strokeWidth: isHighlighted ? 3 : 1.5,
        strokeOpacity: isHighlighted ? 0.95 : 0.5,
        filter,
      })
    } 
    // 整体移动 (Count > 1) -> 画块
    else {
      const ay1 = coordsStartA.top
      const ay2 = coordsEndA.top + coordsEndA.height
      const by1 = coordsStartB.top
      const by2 = coordsEndB.top + coordsEndB.height

      const path = `
        M 0 ${ay1} 
        C ${cp1x} ${ay1}, ${cp2x} ${by1}, ${svgWidth} ${by1}
        L ${svgWidth} ${by2}
        C ${cp2x} ${by2}, ${cp1x} ${ay2}, 0 ${ay2}
        Z
      `
      blocks.push({
        id: blk.id,
        path,
        renderColor: finalColor,
        fillOpacity: isHighlighted ? (blk.isMoved ? 0.34 : 0.22) : 0.15,
        strokeColor: isHighlighted ? finalColor : 'none',
        strokeOpacity: isHighlighted ? 0.8 : 0,
        strokeWidth: isHighlighted ? 1.2 : 0,
        filter,
      })
    }
  })

  renderBlocks.value = blocks
  renderLines.value = lines
}
const debouncedDraw = useDebounceFn(draw, 50) // 50ms 延迟，避免频繁重绘
watch([() => props.listA, () => props.listB], () => {
  clearDiffHighlight()
}, { deep: true })
// 监听开关和选中态，触发重绘
watch([() => props.listA, () => props.listB, hideIdentical, colorfulBlocks, highlightedBlockId], () => {
  nextTick(debouncedDraw)
}, { deep: true, immediate: true })
watch(() => appStore.uiState.showDiffDrawer, (visible) => {
  if (!visible) clearDiffHighlight()
})

let resizeObserver = null
onMounted(() => {
  if (scrollContainer.value) {
    resizeObserver = new ResizeObserver(() => debouncedDraw())
    resizeObserver.observe(scrollContainer.value)
  }
})
onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
})

// 定位Mod位置
const targetItem = (mod_id) => {
  modStore.currentTargetId = mod_id
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  background-color: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: var(--color-border-strong);
  border-radius: 4px;
}
</style>
