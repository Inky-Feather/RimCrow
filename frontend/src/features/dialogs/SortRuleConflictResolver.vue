<template>
  <CommonModalShell :show="visible" :z-index="100" accent="danger" size="custom" :title="t('dialog.sort_conflict.title', '排序规则冲突')"
    :description="t('dialog.sort_conflict.subtitle', '{mods} 个 Mod 的排序规则形成闭环，任何顺序都会违反至少一条规则。', { mods: graph.nodes.length })"
    content-class="min-h-0 flex flex-col" footer-class="bg-bg-inset/70" panel-class="h-[min(50rem,92vh)] w-[min(70rem,94vw)] border-accent-danger/20"
    @close="cancel" >
    <template #icon>
      <AlertCircle class="size-5 text-accent-danger" />
    </template>

    <!-- 标题右侧：只展示冲突组数量，不承载操作，避免和下方规则开关混在一起 -->
    <template #title-extra>
      <span class="rounded border border-accent-danger/25 bg-accent-danger/10 px-1.5 py-0.5 text-[0.68rem] font-bold text-accent-danger">
        {{ t('dialog.sort_conflict.count', '{count} 组循环', { count: groups.length }) }}
      </span>
    </template>

      <!-- 主内容：左侧 3/5 负责冲突链路图，右侧 2/5 负责规则解释与处理 -->
      <div class="grid min-h-0 flex-1 grid-cols-5 overflow-hidden">
        <aside class="col-span-3 flex min-h-0 flex-col overflow-y-auto border-r border-border-base/10 bg-bg-inset/45 p-4 custom-scrollbar">
          <div class="mb-3 flex items-center justify-between gap-2">
            <div class="text-[0.65rem] font-black uppercase tracking-wider text-text-dim">{{ t('dialog.sort_conflict.groups_title', '冲突链路') }}</div>
            <div class="flex items-center gap-1.5">
              <span class="rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[0.65rem] text-text-dim">
                {{ t('dialog.sort_conflict.edge_count', '{count} 条规则线', { count: graph.edges.length }) }}
              </span>
              <div v-if="groups.length > 1" class="flex rounded-lg border border-border-base/10 bg-bg-overlay/5 p-0.5">
                <button type="button" class="rounded-md px-2 py-0.5 text-[0.65rem] font-bold transition-colors"
                  :class="viewMode === 'group' ? 'bg-accent-danger/15 text-accent-danger' : 'text-text-dim hover:text-text-main'"
                  @click="setViewMode('group')" >
                  {{ t('dialog.sort_conflict.view_group', '单组') }}
                </button>
                <button type="button" class="rounded-md px-2 py-0.5 text-[0.65rem] font-bold transition-colors"
                  :class="viewMode === 'all' ? 'bg-accent-danger/15 text-accent-danger' : 'text-text-dim hover:text-text-main'"
                  @click="setViewMode('all')" >
                  {{ t('dialog.sort_conflict.view_all', '总览') }}
                </button>
              </div>
            </div>
          </div>

          <!-- 多个独立循环时使用横向标签切换；详细链路放 tooltip，避免挤占图形区域。 -->
          <div v-if="groups.length > 1 && viewMode === 'group'" class="mb-4 flex gap-1.5 overflow-x-auto pb-1 custom-scrollbar">
            <button v-for="(group, index) in groups" :key="group.key" type="button"
              v-tooltip="groupSummary(group)"
              class="inline-flex shrink-0 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors"
              :class="activeGroupIndex === index ? 'border-accent-danger/35 bg-accent-danger/10 text-text-main' : 'border-border-base/10 bg-bg-inset/55 text-text-dim hover:text-text-main'"
              @click="selectGroup(index)" >
              <span class="font-bold">{{ t('dialog.sort_conflict.group_number', '冲突 {index}', { index: index + 1 }) }}</span>
              <span class="rounded bg-bg-overlay/8 px-1.5 py-0.5 text-[0.65rem]">{{ group.cycle.length }}</span>
            </button>
          </div>

          <!-- 冲突链路图：节点按当前最优排序从上到下排列，线条表示规则所属模组指向目标模组 -->
          <div ref="graphViewportRef" class="min-h-0 flex-1 overflow-auto custom-scrollbar" @wheel="handleGraphWheel">
            <div class="flex min-h-full w-full" :class="[graphAlignClass, graphJustifyClass]">
              <svg class="block shrink-0" :style="graphStyle" :viewBox="`0 0 ${graph.width} ${graph.height}`" preserveAspectRatio="xMidYMid meet" role="img" :aria-label="t('dialog.sort_conflict.map_title', '无法同时满足的最小闭环')">
              <defs>
                <marker v-for="marker in sourceMarkers" :id="marker.id" :key="marker.id" :markerWidth="ruleArrow.width" :markerHeight="ruleArrow.height" :refX="ruleArrow.refX" :refY="ruleArrow.refY" orient="auto">
                  <polygon :points="ruleArrow.points" :class="marker.fillClass" />
                </marker>
              </defs>

              <!-- 规则线：红线表示最优排序中被忽略的约束；其它颜色按规则来源区分 -->
              <g v-for="edge in graph.edges" v-show="edge.previewVisible" :key="edge.key" v-tooltip="edgeTooltip(edge)" class="sort-conflict-edge cursor-pointer outline-none" focusable="false" tabindex="-1" @click="selectEdge(edge.index, edge)">
                <path :d="edge.path" fill="none" stroke="transparent" stroke-width="20" />
                <path :d="edge.path" fill="none" stroke-linecap="round" :marker-end="`url(#${edge.markerId})`" class="rule-flow-line pointer-events-none transition-all" :class="[edge.strokeClass, edge.previewIgnored ? 'rule-danger-line' : '', edge.active ? 'stroke-3 opacity-100' : edge.dim ? 'stroke-2 opacity-25' : 'stroke-2 opacity-75']" />
                <g class="pointer-events-none transition-opacity" :class="edge.dim ? 'opacity-20' : edge.active ? 'opacity-100' : 'opacity-75'">
                  <g v-for="label in edge.labels" :key="label.key">
                    <rect :x="label.x" :y="label.y" :width="label.width" :height="label.height" rx="4" :class="label.bgClass" />
                    <text :x="label.x + label.width / 2" :y="label.y + label.height - 4" text-anchor="middle" class="text-[10px] font-bold" :class="label.textClass">
                      {{ label.text }}
                    </text>
                  </g>
                </g>
                <g class="pointer-events-none transition-opacity" :class="edge.dim ? 'opacity-25' : 'opacity-100'">
                  <template v-if="edge.showBreakMark && edge.previewIgnored">
                    <circle :cx="edge.markX" :cy="edge.markY" r="8.5" class="fill-bg-base stroke-accent-danger stroke-[1.5]" />
                    <path :d="`M ${edge.markX - 3.2} ${edge.markY - 3.2} L ${edge.markX + 3.2} ${edge.markY + 3.2} M ${edge.markX + 3.2} ${edge.markY - 3.2} L ${edge.markX - 3.2} ${edge.markY + 3.2}`" class="stroke-accent-danger stroke-[1.5]" stroke-linecap="round" />
                  </template>
                </g>
              </g>

              <!-- 模组节点：悬停显示模组卡片；选中规则线后按“所属/目标关系类型”高亮两端节点 -->
              <g v-for="node in graph.nodes" :key="node.id" v-preview="modPreview(node.id)">
                <rect :x="node.x" :y="node.y" :width="graph.nodeWidth" :height="graph.nodeHeight" rx="8" class="transition-colors" :class="node.class" />
                <text :x="node.x + graph.nodeWidth / 2" :y="node.y + graph.nodeHeight / 2 + 3.5" text-anchor="middle" class="fill-text-main text-[10.5px] font-bold">
                  {{ node.label }}
                </text>
              </g>
              </svg>
            </div>
          </div>

          <div class="w-full -mb-3 -mr-3 flex items-center justify-between">
            <p class="shrink-0 text-center text-[0.68rem] text-text-disabled">
              {{ t('dialog.sort_conflict.graph_hint', '悬停查看规则来源，点击规则线查看和处理') }}
            </p>
            <div class="flex rounded-lg border border-border-base/10 bg-bg-overlay/5 p-0.5">
              <button type="button" class="rounded-md p-1 text-text-dim transition-colors hover:text-text-main disabled:opacity-40" :disabled="graphZoom <= graphZoomMin" @click="zoomGraph(-graphZoomStep)">
                <ZoomOut class="size-3.5" />
              </button>
              <button type="button" class="rounded-md px-1.5 text-[0.65rem] font-bold text-text-dim transition-colors hover:text-text-main" @click="resetGraphZoom">
                {{ Math.round(graphZoom * 100) }}%
              </button>
              <button type="button" class="rounded-md p-1 text-text-dim transition-colors hover:text-text-main disabled:opacity-40" :disabled="graphZoom >= graphZoomMax" @click="zoomGraph(graphZoomStep)">
                <ZoomIn class="size-3.5" />
              </button>
            </div>
          </div>
        </aside>

        <main class="col-span-2 flex min-h-0 flex-col overflow-hidden">
          <div class="min-h-0 flex-1 overflow-y-auto p-5 custom-scrollbar">
            <!-- 未选中线条时直接显示图上的规则线清单，右侧信息和左侧视觉模型保持一致 -->
            <template v-if="selectedEdgeIndex === null">
              <div class="mb-4 text-[0.65rem] font-black uppercase tracking-wider text-text-dim">{{ t('dialog.sort_conflict.line_overview_title', '冲突规则线') }}</div>
              <div class="space-y-2">
                <button v-for="edge in graph.edges" :key="edge.key" type="button"
                  class="flex flex-col w-full items-center gap-3 rounded-lg border border-border-base/10 bg-bg-overlay/3 px-2 py-2 text-left transition-colors hover:border-accent-danger/20 hover:bg-accent-danger/6"
                  @click="selectEdge(edge.index, edge)" >
                  <div class="flex items-center justify-between w-full">
                    <span class="flex shrink-0 flex-wrap items-center justify-end gap-1">
                      <span class="size-2 shrink-0 rounded-full" :class="edge.ignored ? 'bg-accent-danger' : sourceDotClass(lineSources(edge)[0])"></span>
                      <span v-if="edge.ignored" class="rounded bg-accent-danger/12 px-1.5 py-0.5 text-[0.65rem] font-bold text-accent-danger">
                        {{ t('dialog.sort_conflict.ignored_rule', '已忽略') }}
                      </span>
                      <span v-else class="rounded bg-bg-overlay/6 px-1.5 py-0.5 text-[0.65rem] font-bold text-text-dim">
                        {{ t('dialog.sort_conflict.kept_rule', '已保留') }}
                      </span>
                      <span v-for="source in lineSources(edge)" :key="source" class="rounded px-1.5 py-0.5 text-[0.65rem] font-bold" :class="sourceTagClass(source)">
                        {{ sourceShortLabel(source) }}
                      </span>
                    </span>
                    <span class="rounded bg-bg-overlay/6 px-1.5 py-0.5 text-[0.65rem] font-bold text-text-dim">
                      {{ t('dialog.sort_conflict.rule_count', '{count} 条', { count: edge.rules.length }) }}
                    </span>
                  </div>

                  <span class="flex w-full flex-1 flex-wrap items-center gap-1.5 text-xs font-bold text-text-main">
                    <template v-for="part in lineSentenceParts(edge)" :key="part.key">
                      <span v-if="part.type === 'text'" class="font-normal text-text-dim">{{ part.text }}</span>
                      <span v-else-if="part.type === 'relation'" class="rounded-md border px-1.5 py-0.5 text-[0.68rem] font-bold" :class="toneChipClass(part.tone)">{{ part.text }}</span>
                      <span v-else v-preview="modPreview(part.id)" class="min-w-0 max-w-full rounded-md border px-1.5 py-0.5 text-[0.68rem] font-bold" :class="toneChipClass(part.tone)">
                        <span class="truncate">{{ part.text }}</span>
                      </span>
                    </template>
                  </span>
                </button>
              </div>
            </template>

            <!-- 选中线条后显示规则详情：上方是直观句子，下方是该来源/模组的完整规则卡片 -->
            <template v-else>
              <button class="mb-4 flex items-center gap-1 text-xs text-text-dim transition-colors hover:text-text-main" type="button" @click="clearEdgeSelection">
                <ChevronLeft class="size-3.5" />
                <span>{{ t('dialog.sort_conflict.back_to_overview', '全部规则线') }}</span>
                <span class="ml-2 text-text-disabled">{{ selectedLinePosition }} / {{ graph.edges.length }}</span>
              </button>

              <!-- 当前规则线：只解释用户点击的这条线，避免和下方“完整规则卡片”混淆 -->
              <section v-if="selectedRuleGroups.length" class="mb-3 rounded-lg border border-border-base/10 bg-bg-overlay/3 p-3">
                <div class="mb-2 text-[0.65rem] font-black uppercase tracking-wider text-text-dim">{{ t('dialog.sort_conflict.selected_line_rules', '当前规则线') }}</div>
                <div class="space-y-2">
                  <div v-for="group in selectedRuleGroups" :key="group.source" class="space-y-1.5">
                    <div class="flex items-center gap-1.5">
                      <span class="rounded px-1.5 py-0.5 text-[0.65rem] font-bold" :class="sourceTagClass(group.source)">{{ sourceTooltipLabel(group.source) }}</span>
                      <span class="text-[0.65rem] text-text-disabled">{{ t('dialog.sort_conflict.rule_count', '{count} 条', { count: group.rules.length }) }}</span>
                    </div>
                    <div v-for="(rule, ruleIndex) in group.rules" :key="`${group.source}-${ruleIndex}`" class="flex flex-wrap items-center gap-1.5 text-xs">
                      <template v-for="part in ruleSentenceWithRelationParts(rule)" :key="part.key">
                        <span v-if="part.type === 'text'" class="text-text-dim">{{ part.text }}</span>
                        <span v-else-if="part.type === 'relation'" class="font-black" :class="toneChipClass(part.tone)">{{ part.text }}</span>
                        <span v-else v-preview="modPreview(part.id)" class="rounded-md border px-1.5 py-0.5 font-black" :class="toneChipClass(part.tone)">
                          {{ part.text }}
                        </span>
                      </template>
                    </div>
                  </div>
                </div>
              </section>

              <!-- 规则卡片：一张卡代表“某个模组在某个规则来源中的完整关系规则” -->
              <section class="space-y-2.5">
                <article v-for="card in ruleCards" :key="card.key" class="rounded-lg border bg-bg-overlay/3 p-3" :class="sourceBorderClass(card.source)">
                  <div class="mb-1 flex items-start justify-between gap-3" v-tooltip="card.description">
                    <div class="min-w-0 flex-1 flex flex-wrap items-center gap-2">
                      <span class="rounded px-1.5 py-0.5 text-xs font-bold" :class="sourceTagClass(card.source)">{{ sourceLabel(card.source) }}</span>
                      <span v-preview="modPreview(card.modId)" class="truncate text-xs font-bold text-text-main">{{ modName(card.modId) }}</span>
                    </div>
                    <button v-if="card.action" type="button" v-tooltip="card.action.tooltip"
                      class="shrink-0 rounded-lg border -mt-1 -mr-1 p-1 transition-colors hover:bg-bg-overlay/10"
                      :class="pendingActionClass(card.action, card.action.enabled)"
                      @click="togglePendingAction(card.action)" >
                      <CircleCheckBig v-if="previewActionEnabled(card.action, card.action.enabled)" class="size-4" />
                      <CircleOff v-else class="size-4" />
                    </button>
                    <Info v-else v-tooltip="card.actionTooltip" class=" size-4 shrink-0 text-text-disabled" />
                  </div>

                  <div class="space-y-2">
                    <div v-for="section in card.sections" :key="section.type" class="space-y-1">
                      <div class="text-xs font-bold uppercase" :class="relationSectionLabelClass(section.type)">{{ relationSectionLabel(section.type) }}</div>
                      <div class="flex flex-wrap gap-1.5">
                        <span v-for="item in section.items" :key="item.id" v-tooltip="relationItemTooltip(item.id, item.info)"
                          class="inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[0.75rem] text-text-main"
                          :class="relationSectionChipClass(section.type)" >
                          <span v-preview="modPreview(item.id)" class="truncate">{{ relationTargetName(item.id, item.info) }}</span>
                          <button v-if="card.source === 'user'" type="button"
                            v-tooltip="t('dialog.sort_conflict.delete_user_relation', '删除这条模组关系规则')"
                            class="rounded p-0.5 text-text-disabled transition-colors hover:bg-accent-danger/10 hover:text-accent-danger"
                            :class="isPendingAction(userRelationDeleteAction(card.modId, section.type, item.id)) ? 'bg-accent-warn/12 text-accent-warn' : ''"
                            @click.stop="confirmDeleteUserRelation(card.modId, section.type, item.id, $event)" >
                            <Trash2 class="size-3" />
                          </button>
                        </span>
                      </div>
                    </div>
                  </div>
                </article>
              </section>
            </template>

            <p v-if="feedback" class="mt-4 rounded-lg border border-accent-danger/25 bg-accent-danger/10 p-2 text-xs text-accent-danger">{{ feedback }}</p>
          </div>

          <!-- 规则来源开关固定在右栏底部，只控制本次冲突涉及的整套规则来源。 -->
          <section v-if="involvedGlobalSources.length" class="shrink-0 flex flex-wrap gap-3 border-t border-border-base/10 bg-bg-inset/70 px-1 py-1.5">
            <div v-for="source in involvedGlobalSources" :key="source" class="rounded-lg transition-colors" >
              <CommonSwitch mini :label="sourceLabel(source)" :description="globalSourceTooltip(source)"
                :model-value="previewGlobalSourceEnabled(source)"
                @update:modelValue="togglePendingAction(globalSourceAction(source))" />
            </div>
          </section>
        </main>
      </div>

    <!-- 底部操作区：规则操作先进入待保存列表，点击保存后统一落盘并自动重排 -->
    <template #footer>
      <div class="flex items-center justify-between gap-4">
        <div class="text-xs whitespace-pre-wrap leading-relaxed text-text-dim">
          {{ pendingActionList.length ? t('dialog.sort_conflict.footer_pending_hint', '已选择 {count} 项规则修改，左侧视图已预览影响；保存后会写入配置并重新排序。', { count: pendingActionList.length }) : t('dialog.sort_conflict.footer_hint', '已按当前能满足最多规则的顺序完成排序；红色规则线是本次被忽略的规则。\n可选择要调整的规则，保存后会写入规则配置并自动重新排序。') }}
        </div>
        <div class="flex items-center gap-2">
          <button class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-xs font-bold text-text-main transition-all hover:bg-bg-overlay/10" type="button" @click="cancel">
            {{ t('common.action.cancel', '取消') }}
          </button>
          <button :disabled="processing || pendingActionList.length === 0" class="rounded-xl px-5 py-2 text-sm font-black transition-all disabled:cursor-not-allowed disabled:opacity-50"
            :class="pendingActionList.length ? 'bg-accent-warn text-on-accent-warn hover:bg-accent-warn/85' : 'bg-bg-overlay/8 text-text-disabled'"
            type="button" @click="applyPendingActions">
            {{ processing ? t('common.status.processing', '处理中') : t('dialog.sort_conflict.apply', '保存并重新排序') }}
          </button>
        </div>
      </div>
    </template>
  </CommonModalShell>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, CircleCheckBig, CircleOff, Info, Trash2, ZoomIn, ZoomOut } from 'lucide-vue-next'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useModStore } from '../mod/stores/modStore'
import { useRuleStore } from '../rules/ruleStore'
import { stripPackageTokenSuffix } from '../mod/lib/modIdentity'
import { t } from '../../shared/i18n.js'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'

const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()

// --- 组件状态 ---
// 规则操作先进入 pendingActions；只有点击底部保存按钮才会持久化并重新排序。
const processing = ref(false)
const feedback = ref('')
const pendingActions = ref({})
const activeGroupIndex = ref(0)
const viewMode = ref('group')
const selectedEdgeIndex = ref(null)
const selectedLineKey = ref(null)
const selectedLine = ref(null)
const graphViewportRef = ref(null)
const graphViewportSize = ref({ width: 0, height: 0 })
const graphZoom = ref(1)

// 视图缩放：优先按可用高度显示；如果算出的宽度太窄，就使用这个最小宽度并允许滚动。
const graphMinDisplayWidth = 420
const graphZoomMin = 0.6
const graphZoomMax = 2.5
const graphZoomStep = 0.1
let graphResizeObserver = null

const visible = computed(() => !!modStore.pendingSortConflict)

watch(visible, (isVisible) => {
  if (isVisible) void ruleStore.ensureRulesLoaded()
}, { immediate: true })

watch(graphViewportRef, (el) => {
  graphResizeObserver?.disconnect()
  if (!el) return
  graphResizeObserver = new ResizeObserver(([entry]) => {
    const { width, height } = entry.contentRect
    graphViewportSize.value = { width, height }
  })
  graphResizeObserver.observe(el)
}, { immediate: true })

onBeforeUnmount(() => graphResizeObserver?.disconnect())

// --- 规则来源定义 ---
// 同一来源在图线、图例、列表标签和卡片边框里使用同一套颜色，降低用户识别成本。
const sourceMarkers = [
  { id: 'sort-conflict-arrow-danger', fillClass: 'fill-accent-danger' },
  { id: 'sort-conflict-arrow-user', fillClass: 'fill-accent-success' },
  { id: 'sort-conflict-arrow-community', fillClass: 'fill-accent-cool' },
  { id: 'sort-conflict-arrow-workshop', fillClass: 'fill-accent-special' },
  { id: 'sort-conflict-arrow-dynamic', fillClass: 'fill-accent-warn' },
  { id: 'sort-conflict-arrow-native', fillClass: 'fill-text-disabled' },
  { id: 'sort-conflict-arrow-unknown', fillClass: 'fill-text-dim' },
]
// --- 线段与箭头尺寸 ---
// ruleLineGap 是“线段本体”离模组项边缘的距离：起点和终点都不直接贴住模组项。
// ruleArrow.refX = 0 表示 marker 的基点在箭头尾部，箭头会沿线段方向向外伸出；
// 因此当箭头长度接近 ruleLineGap 时，线段仍留白，箭头尖端可以刚好贴到目标模组项边缘。
const ruleLineGap = 5
const ruleArrow = {
  width: ruleLineGap,
  height: 5,
  refX: 0,
  refY: 2.5,
  points: `0 0, ${ruleLineGap/2} 2.5, 0 5`,
}
const sourceLabel = (type) => ({
  user: t('ui.rule_panel.source.user', '用户规则'), community: t('ui.rule_panel.source.community', '社区规则'),
  workshop: t('ui.rule_panel.source.workshop', '创意工坊规则'), dynamic: t('ui.rule_panel.source.dynamic', '动态规则'), native: t('ui.rule_panel.source.native', '原生规则'),
}[type] || t('common.status.unknown', '未知'))
const sourceShortLabel = (type) => ({
  user: t('dialog.sort_conflict.source_short_user', '用户'), community: t('dialog.sort_conflict.source_short_community', '社区'),
  workshop: t('dialog.sort_conflict.source_short_workshop', '工坊'), dynamic: t('dialog.sort_conflict.source_short_dynamic', '动态'), native: t('dialog.sort_conflict.source_short_native', '原生'),
}[type] || t('common.status.unknown', '未知'))
const sourceTagClass = (type) => ({
  user: 'bg-accent-success/12 text-accent-success',
  community: 'bg-accent-cool/12 text-accent-cool',
  workshop: 'bg-accent-special/12 text-accent-special',
  dynamic: 'bg-accent-warn/12 text-accent-warn',
  native: 'bg-bg-overlay/6 text-text-disabled',
}[type] || 'bg-bg-overlay/6 text-text-dim')
const sourceDotClass = (type) => ({
  user: 'bg-accent-success',
  community: 'bg-accent-cool',
  workshop: 'bg-accent-special',
  dynamic: 'bg-accent-warn',
  native: 'bg-text-disabled',
}[type] || 'bg-text-dim')
const sourceBorderClass = (type) => ({
  user: 'border-accent-success/18',
  community: 'border-accent-cool/18',
  workshop: 'border-accent-special/18',
  dynamic: 'border-accent-warn/18',
  native: 'border-border-base/10',
}[type] || 'border-border-base/10')
const sourceStrokeClass = (type) => ({
  user: 'stroke-accent-success',
  community: 'stroke-accent-cool',
  workshop: 'stroke-accent-special',
  dynamic: 'stroke-accent-warn',
  native: 'stroke-text-disabled',
}[type] || 'stroke-text-dim')
const sourceLabelSvgClass = (type) => ({
  user: { bgClass: 'fill-accent-success/12', textClass: 'fill-accent-success' },
  community: { bgClass: 'fill-accent-cool/12', textClass: 'fill-accent-cool' },
  workshop: { bgClass: 'fill-accent-special/12', textClass: 'fill-accent-special' },
  dynamic: { bgClass: 'fill-accent-warn/12', textClass: 'fill-accent-warn' },
  native: { bgClass: 'fill-bg-overlay/6', textClass: 'fill-text-disabled' },
}[type] || { bgClass: 'fill-bg-overlay/6', textClass: 'fill-text-dim' })

// --- 关系语义定义 ---
// owner 是规则所属模组；predecessor/successor/dependency 分别对应前置/后置/依赖模组。
// 这组颜色对齐 Mod 详情页，避免同一关系在不同界面用不同颜色。
const toneHex = {
  owner: '#8b5cf6',
  predecessor: '#eab308',
  successor: '#06b6d4',
  dependency: '#ec4899',
}
const toneChipClass = (tone) => ({
  owner: 'border-accent-special/18 bg-accent-special/8 text-accent-special',
  predecessor: 'border-accent-warn/18 bg-accent-warn/8 text-accent-warn',
  successor: 'border-accent-primary/18 bg-accent-primary/8 text-accent-primary',
  dependency: 'border-accent-highlight/18 bg-accent-highlight/8 text-accent-highlight',
}[tone] || 'border-border-base/10 bg-bg-overlay/5 text-text-main')
const toneNodeClass = (tone) => ({
  owner: 'fill-accent-special/10 stroke-accent-special/55 stroke-[1.5]',
  predecessor: 'fill-accent-warn/10 stroke-accent-warn/55 stroke-[1.5]',
  successor: 'fill-accent-primary/10 stroke-accent-primary/55 stroke-[1.5]',
  dependency: 'fill-accent-highlight/10 stroke-accent-highlight/55 stroke-[1.5]',
}[tone] || 'fill-bg-overlay/4 stroke-border-base/10')
const colorText = (text, tone) => `{{${toneHex[tone] || '#e5e7eb'}|${text}}}`
const edgeKey = (edge, index) => `${edge.from_id}>${edge.to_id}:${index}`
const modName = (id) => modStore.displayModName(id)
const shortText = (text, max = 18) => String(text || '').length > max ? `${String(text).slice(0, max - 1)}…` : String(text || '')
const normalizeEdgeId = (id = '') => stripPackageTokenSuffix(id)
const modPreview = (id) => modStore.takeModById(id)
const isDependencyRule = (rule) => {
  const text = [
    rule?.rule_source?.name,
    rule?.rule_source?.detail?.type,
    rule?.rule_source?.detail?.rule_type,
    rule?.rule_source?.detail?.category,
  ].map(value => String(value || '').toLowerCase()).join(' ')
  return text.includes('depend') || text.includes('依赖')
}
const relationLabel = (rule = {}) => {
  if (isDependencyRule(rule)) return t('dialog.sort_conflict.relation_dependency', '依赖模组')
  return rule.relation_type === 'before'
    ? t('dialog.sort_conflict.relation_successor', '后置模组')
    : t('dialog.sort_conflict.relation_predecessor', '前置模组')
}
const relationTone = (rule = {}) => {
  if (isDependencyRule(rule)) return 'dependency'
  return rule.relation_type === 'before' ? 'successor' : 'predecessor'
}
const relationToneForRules = (rules = []) => rules.some(rule => isDependencyRule(rule)) ? 'dependency' : relationTone(rules[0])
const ruleShadowedText = (rule = {}) => rule.effective === false
  ? t('dialog.sort_conflict.shadowed_rule_suffix', '（被{source}覆盖）', { source: sourceLabel(rule.shadowed_by?.type) })
  : ''
const richRuleSentence = (rule = {}) => `${t('dialog.sort_conflict.rule_sentence', '{target} 是 {owner} 的 {relation}', {
  target: colorText(modName(rule.target_mod), relationTone(rule)),
  owner: colorText(modName(rule.source_mod), 'owner'),
  relation: colorText(relationLabel(rule), relationTone(rule)),
})}${ruleShadowedText(rule)}`
const ruleSentenceParts = (rule = {}) => [
  { key: 'target', type: 'mod', role: 'target', tone: relationTone(rule), id: rule.target_mod, text: modName(rule.target_mod) },
  { key: 'is', type: 'text', text: t('dialog.sort_conflict.rule_sentence_is', '是') },
  { key: 'owner', type: 'mod', role: 'owner', tone: 'owner', id: rule.source_mod, text: modName(rule.source_mod) },
  { key: 'of', type: 'text', text: t('dialog.sort_conflict.rule_sentence_of', '的') },
]
const ruleSentenceWithRelationParts = (rule = {}) => [
  ...ruleSentenceParts(rule),
  { key: 'relation', type: 'relation', tone: relationTone(rule), text: relationLabel(rule) },
  ...(ruleShadowedText(rule) ? [{ key: 'shadowed', type: 'text', text: ruleShadowedText(rule) }] : []),
]
const edgePrimaryRule = (edge = {}) => edge.rules?.[0] || { source_mod: edge.to_id, target_mod: edge.from_id, relation_type: 'after' }
const relationTextForRules = (rules = []) => [...new Set((rules.length ? rules : [{}]).map(rule => relationLabel(rule)))].join(' / ')
const ruleLineSentenceParts = (rules = [], fallbackRule = {}) => {
  const availableRules = rules.length ? rules : [fallbackRule]
  return [
    ...ruleSentenceParts(availableRules[0]),
    { key: 'relation', type: 'relation', tone: relationToneForRules(availableRules), text: relationTextForRules(availableRules) },
  ]
}
const lineSentenceParts = (line = {}) => ruleLineSentenceParts(line.rules || [], edgePrimaryRule(line.source || line))
const lineSources = (line = {}) => [...new Set((line.rules || []).map(rule => rule.rule_source?.type).filter(Boolean))]
const ruleGroupsBySource = (rules = []) => {
  const groups = new Map()
  for (const rule of rules) {
    const source = rule.rule_source?.type || 'unknown'
    if (!groups.has(source)) groups.set(source, [])
    groups.get(source).push(rule)
  }
  return Array.from(groups, ([source, groupedRules]) => ({ source, rules: groupedRules }))
}
const ruleIdentity = (rule = {}) => [
  normalizeEdgeId(rule.source_mod),
  normalizeEdgeId(rule.target_mod),
  rule.relation_type,
  rule.rule_source?.type,
  rule.rule_source?.name,
  rule.rule_source?.detail?.rule_id || JSON.stringify(rule.rule_source?.detail || {}),
  rule.effective === false ? 'shadowed' : 'effective',
].join('|')

// --- 冲突组数据 ---
// 后端可能为同一个最小环返回多条 culprit rule，这里按 cycle 去重，只展示一组链路。
const groups = computed(() => {
  const result = new Map()
  for (const warning of modStore.pendingSortConflict?.warnings || []) {
    const cycle = warning.cycle || []
    if (!cycle.length) continue
    const key = cycle.map(edge => `${edge.from_id}>${edge.to_id}`).join('|')
    if (!result.has(key)) result.set(key, { key, cycle: cycle.map((edge, index) => ({ ...edge, ignored: index === 0 || !!edge.ignored })) })
  }
  return Array.from(result.values())
})
const activeGroup = computed(() => groups.value[activeGroupIndex.value] || groups.value[0] || { key: '', cycle: [] })
const allConflictGroup = computed(() => {
  const merged = new Map()
  for (const [groupIndex, group] of groups.value.entries()) {
    for (const edge of group.cycle) {
      const key = `${normalizeEdgeId(edge.from_id)}>${normalizeEdgeId(edge.to_id)}`
      if (!merged.has(key)) {
        merged.set(key, { ...edge, key, groupIndexes: [groupIndex], ignoredGroupIndexes: edge.ignored ? [groupIndex] : [], rules: [], ruleKeys: new Set() })
      }
      const current = merged.get(key)
      current.ignored = current.ignored || edge.ignored
      if (!current.groupIndexes.includes(groupIndex)) current.groupIndexes.push(groupIndex)
      if (edge.ignored && !current.ignoredGroupIndexes.includes(groupIndex)) current.ignoredGroupIndexes.push(groupIndex)
      for (const rule of edge.rules || []) {
        const ruleKey = ruleIdentity(rule)
        if (current.ruleKeys.has(ruleKey)) continue
        current.ruleKeys.add(ruleKey)
        current.rules.push(rule)
      }
    }
  }
  return { key: 'all', cycle: [...merged.values()].map(({ ruleKeys, ...edge }) => edge) }
})
const displayGroup = computed(() => viewMode.value === 'all' ? allConflictGroup.value : activeGroup.value)
const selectedEdge = computed(() => selectedEdgeIndex.value === null ? null : displayGroup.value.cycle[selectedEdgeIndex.value] || null)
const selectedRules = computed(() => selectedLine.value?.rules?.length ? selectedLine.value.rules : selectedEdge.value?.rules || [])
const selectedRuleGroups = computed(() => ruleGroupsBySource(selectedRules.value))
const globalSourceKeys = ['user', 'community', 'workshop', 'dynamic']
const displayGroupRules = computed(() => displayGroup.value.cycle.flatMap(edge => edge.rules || []))
const involvedGlobalSources = computed(() => [...new Set(displayGroupRules.value.map(rule => rule.rule_source?.type).filter(source => globalSourceKeys.includes(source)))])
const sectionRelationType = (sectionType) => ({ loadAfter: 'after', loadBefore: 'before' }[sectionType])
const isRulePreviewDisabled = (rule = {}) => {
  for (const action of Object.values(pendingActions.value)) {
    if (!action || action.targetEnabled !== false && action.kind !== 'deleteUserRelation') continue
    const source = rule.rule_source?.type || 'unknown'
    const ownerId = normalizeEdgeId(rule.source_mod)
    const targetId = normalizeEdgeId(rule.target_mod)
    if (action.kind === 'global' && action.source === source) return true
    if (action.kind === 'mod' && action.source === source && normalizeEdgeId(action.modId) === ownerId) return true
    if (action.kind === 'dynamic' && source === 'dynamic' && rule.rule_source?.detail?.rule_id === action.ruleId) return true
    if (action.kind === 'deleteUserRelation'
      && source === 'user'
      && normalizeEdgeId(action.modId) === ownerId
      && normalizeEdgeId(action.targetId) === targetId
      && sectionRelationType(action.sectionType) === rule.relation_type) return true
  }
  return false
}
const previewRulesOf = (rules = []) => (rules || []).filter(rule => !isRulePreviewDisabled(rule))

// --- SVG 图形布局 ---
// 节点按当前最优排序从上到下排列；被忽略的规则通常会落到外层，便于直接看到冲突来源。
const graph = computed(() => {
  const cycle = displayGroup.value.cycle || []
  const previewHandledGroups = new Set()
  for (const [groupIndex, group] of groups.value.entries()) {
    if (viewMode.value === 'group' && groupIndex !== activeGroupIndex.value) continue
    if ((group.cycle || []).some(edge => (edge.rules || []).length && !previewRulesOf(edge.rules).length)) {
      previewHandledGroups.add(groupIndex)
    }
  }
  const cycleIdMap = new Map()
  for (const edge of cycle) {
    cycleIdMap.set(normalizeEdgeId(edge.from_id), edge.from_id)
    cycleIdMap.set(normalizeEdgeId(edge.to_id), edge.to_id)
  }

  // 优先使用后端返回的 sortedIds 作为节点顺序；如果有边端点不在 sortedIds 中，再兜底追加。
  // 这样图里的上下顺序和用户当前看到的最终排序结果一致。
  const ids = []
  const orderSource = modStore.pendingSortConflict?.sortedIds?.length ? modStore.pendingSortConflict.sortedIds : modStore.activeIds
  for (const id of orderSource || []) {
    const actualId = cycleIdMap.get(normalizeEdgeId(id))
    if (actualId && !ids.includes(actualId)) ids.push(actualId)
  }
  for (const edge of cycle) {
    if (!ids.includes(edge.from_id)) ids.push(edge.from_id)
    if (!ids.includes(edge.to_id)) ids.push(edge.to_id)
  }

  const maxSourceLabelCount = Math.max(1, ...cycle.map(edge => new Set(previewRulesOf(edge.rules || []).map(rule => rule.rule_source?.type || 'unknown')).size))
  const labelOverflow = Math.max(0, maxSourceLabelCount - 2)
  const nodeX = 30
  const nodeWidth = 150
  const nodeHeight = 34
  const nodeGap = 40 + labelOverflow * 16
  const firstY = 8
  const centerX = nodeX + nodeWidth / 2
  const rightX = nodeX + nodeWidth
  const sourceGap = ruleLineGap
  const outerTrackStartX = rightX + 58 + labelOverflow * 28
  const outerTrackGap = 18
  const width = Math.max(200, outerTrackStartX + 84 + labelOverflow * 10)
  const height = Math.max(220, firstY + ids.length * (nodeHeight + nodeGap) - nodeGap + 16)
  // 后端 cycle 的 from/to 表示“排序约束边”：from 必须在 to 前。
  // 用户读规则时更关心“谁定义了规则 → 规则指向谁”，所以图形箭头按 source_mod → target_mod 画；
  // 但红色忽略状态仍按后端约束边判断，不能用视觉箭头方向替代，否则 load_after 会被看反。
  const visualOf = (edge, rule = edgePrimaryRule(edge)) => ({ fromId: rule.source_mod || edge.from_id, toId: rule.target_mod || edge.to_id })
  const selectedFallbackRule = selectedEdge.value ? edgePrimaryRule(selectedEdge.value) : null
  const selectedVisualLine = selectedLine.value?.visual
    ? selectedLine.value
    : selectedFallbackRule
      ? { visual: visualOf(selectedEdge.value, selectedFallbackRule), rules: [selectedFallbackRule] }
      : null
  const selectedVisual = selectedVisualLine?.visual || null

  // 节点保持紧凑，只有选中规则线时才高亮两端：
  // 规则所属模组用 special，目标模组用前置/后置/依赖对应色。
  const nodes = ids.map((id, index) => {
    const y = firstY + index * (nodeHeight + nodeGap)
    return {
      id, x: nodeX, y, label: shortText(modName(id), 22),
      class: selectedVisual && normalizeEdgeId(selectedVisual.fromId) === normalizeEdgeId(id)
        ? toneNodeClass('owner')
        : selectedVisual && normalizeEdgeId(selectedVisual.toId) === normalizeEdgeId(id)
          ? toneNodeClass(relationToneForRules(selectedVisualLine?.rules || []))
          : 'fill-bg-overlay/4 stroke-border-base/10',
    }
  })
  const indexMap = Object.fromEntries(nodes.map((node, index) => [node.id, index]))
  const cy = (index) => nodes[index].y + nodeHeight / 2
  const pairKeyOf = (fromId, toId) => [normalizeEdgeId(fromId), normalizeEdgeId(toId)].sort().join('~')
  const directionKeyOf = (fromId, toId) => `${normalizeEdgeId(fromId)}>${normalizeEdgeId(toId)}`
  // 一条后端约束边可能由多条规则共同形成，例如：
  // A 声明 B 是自己的后置模组，同时 B 声明 A 是自己的前置/依赖模组。
  // 后端看它们是同一个排序约束，界面按“规则所属模组 -> 目标模组”分成视觉线；
  // 同一指向的多条规则共用一条线，并在 tooltip 中按来源列明。
  const visualEntries = cycle.flatMap((edge, edgeIndex) => {
    const rules = edge.rules?.length ? edge.rules : [edgePrimaryRule(edge)]
    return rules.map((rule, ruleIndex) => ({ edge, edgeIndex, rule, ruleIndex, visual: visualOf(edge, rule) }))
  })
  const visualGroups = []
  const visualGroupMap = new Map()
  for (const entry of visualEntries) {
    const visualKey = `${entry.edgeIndex}:${normalizeEdgeId(entry.visual.fromId)}>${normalizeEdgeId(entry.visual.toId)}`
    if (!visualGroupMap.has(visualKey)) {
      const group = {
        key: visualKey,
        edge: entry.edge,
        edgeIndex: entry.edgeIndex,
        visual: entry.visual,
        rules: [],
      }
      visualGroupMap.set(visualKey, group)
      visualGroups.push(group)
    }
    visualGroupMap.get(visualKey).rules.push(entry.rule)
  }
  const firstGroupByEdge = new Map()
  visualGroups.forEach((group, groupIndex) => {
    group.groupIndex = groupIndex
    if (!firstGroupByEdge.has(group.edgeIndex)) firstGroupByEdge.set(group.edgeIndex, groupIndex)
  })

  // 双向规则共用同一组模组对，但两条反向线要平行分开，避免互相压住。
  // 相邻模组会显示成两条贴近的上下反向箭头，跨模组绕行也会在同一轨道附近错开。
  const pairDirections = new Map()
  const sameDirectionGroups = new Map()
  for (const group of visualGroups) {
    const pairKey = pairKeyOf(group.visual.fromId, group.visual.toId)
    const directionKey = directionKeyOf(group.visual.fromId, group.visual.toId)
    if (!pairDirections.has(pairKey)) pairDirections.set(pairKey, new Set())
    pairDirections.get(pairKey).add(directionKey)
    const sameDirectionKey = `${pairKey}:${directionKey}`
    if (!sameDirectionGroups.has(sameDirectionKey)) sameDirectionGroups.set(sameDirectionKey, [])
    sameDirectionGroups.get(sameDirectionKey).push(group)
  }
  const trackMap = new Map()
  const trackX = (pairKey) => {
    if (!trackMap.has(pairKey)) trackMap.set(pairKey, trackMap.size)
    return outerTrackStartX + trackMap.get(pairKey) * outerTrackGap
  }
  const bidirectionalOffset = (fromId, toId) => {
    const pairKey = pairKeyOf(fromId, toId)
    if ((pairDirections.get(pairKey)?.size || 0) < 2) return 0
    return directionKeyOf(fromId, toId) === [...pairDirections.get(pairKey)].sort()[0] ? -8 : 8
  }
  const sameDirectionOffset = (group) => {
    const pairKey = pairKeyOf(group.visual.fromId, group.visual.toId)
    const directionKey = directionKeyOf(group.visual.fromId, group.visual.toId)
    const groups = sameDirectionGroups.get(`${pairKey}:${directionKey}`) || []
    if (groups.length < 2) return 0
    return (groups.indexOf(group) - (groups.length - 1) / 2) * 7
  }
  const adjacentLabelX = (group, x) => {
    const pairKey = pairKeyOf(group.visual.fromId, group.visual.toId)
    const directions = [...(pairDirections.get(pairKey) || [])].sort()
    if (directions.length < 2) return x + 18
    return directionKeyOf(group.visual.fromId, group.visual.toId) === directions[0] ? x - 56 : x + 18
  }

  // 规则来源标签跟随视觉线；同一指向上如果有多个来源，就在同一条线上堆叠多个来源标签。
  const buildLabels = (group, x, y, rules = group.rules) => {
    const sources = [...new Set(rules.map(rule => rule.rule_source?.type || 'unknown'))]
    const width = 38
    const height = 17
    return sources.map((source, sourceIndex) => {
      const styles = sourceLabelSvgClass(source)
      return {
        key: `${group.key}-${source}`,
        source,
        text: sourceShortLabel(source),
        x,
        y: y + (sourceIndex - (sources.length - 1) / 2) * 20 - height / 2,
        width,
        height,
        ...styles,
      }
    })
  }
  const edges = visualGroups.map((group) => {
    const { edge, edgeIndex, visual } = group
    const previewRules = previewRulesOf(group.rules)
    const constraintFromIndex = indexMap[edge.from_id]
    const constraintToIndex = indexMap[edge.to_id]
    const fromIndex = indexMap[visual.fromId]
    const toIndex = indexMap[visual.toId]
    if (constraintFromIndex === undefined || constraintToIndex === undefined || fromIndex === undefined || toIndex === undefined) return null
    const ignored = !!edge.ignored || constraintFromIndex > constraintToIndex
    const groupIndexes = edge.groupIndexes || [activeGroupIndex.value]
    const ignoredGroupIndexes = edge.ignoredGroupIndexes || (ignored ? groupIndexes : [])
    const previewIgnored = ignoredGroupIndexes.some(groupIndex => !previewHandledGroups.has(groupIndex))
    const key = `${edgeKey(edge, edgeIndex)}:${group.key}`
    const active = selectedLineKey.value ? selectedLineKey.value === key : selectedEdgeIndex.value === edgeIndex
    const dim = selectedLineKey.value ? !active : selectedEdgeIndex.value !== null && !active
    const primarySource = previewRules[0]?.rule_source?.type || group.rules[0]?.rule_source?.type || 'unknown'
    const markerSource = previewIgnored ? 'danger' : primarySource
    const base = {
      key,
      index: edgeIndex,
      source: edge,
      visual,
      rules: group.rules,
      previewRules,
      previewVisible: previewRules.length > 0,
      ignored,
      previewIgnored,
      showBreakMark: ignored && firstGroupByEdge.get(edgeIndex) === group.groupIndex,
      active,
      dim,
      markerId: `sort-conflict-arrow-${markerSource}`,
      strokeClass: previewIgnored ? 'stroke-accent-danger' : sourceStrokeClass(primarySource),
    }
    const down = toIndex > fromIndex
    const adjacent = Math.abs(toIndex - fromIndex) === 1
    const offset = sameDirectionOffset(group) + bidirectionalOffset(visual.fromId, visual.toId)
    if (adjacent) {
      // 相邻模组的规则直上直下，只占两个节点之间的空隙；起点离开来源节点，箭头贴住目标节点。
      const x = centerX + offset
      const y1 = down ? nodes[fromIndex].y + nodeHeight + sourceGap : nodes[fromIndex].y - sourceGap
      const y2 = down ? nodes[toIndex].y - sourceGap : nodes[toIndex].y + nodeHeight + sourceGap
      const markY = Math.round((y1 + y2) / 2)
      return { ...base, path: `M ${x} ${y1} L ${x} ${y2}`, markX: x, markY, labels: buildLabels(group, adjacentLabelX(group, x), markY, previewRules) }
    }
    const y1 = cy(fromIndex)
    const y2 = cy(toIndex)
    const x = trackX(pairKeyOf(visual.fromId, visual.toId)) + offset
    const markY = Math.round((y1 + y2) / 2)
    // 跨模组规则走右侧外层垂直轨道，避免长线压在模组节点上；同一模组对复用轨道，不同模组对错开。
    return { ...base, path: `M ${rightX + sourceGap} ${y1} L ${x} ${y1} L ${x} ${y2} L ${rightX + sourceGap} ${y2}`, markX: x, markY, labels: buildLabels(group, x - 50, markY, previewRules) }
  }).filter(Boolean)
  return { width, nodes, edges, height, nodeWidth, nodeHeight }
})
const graphDisplaySize = computed(() => {
  const viewportWidth = Math.max(0, graphViewportSize.value.width - 8)
  const viewportHeight = Math.max(0, graphViewportSize.value.height - 8)
  if (!viewportHeight || !graph.value.width || !graph.value.height) {
    return { width: graphMinDisplayWidth, height: graphMinDisplayWidth * graph.value.height / graph.value.width }
  }
  const heightFitWidth = viewportHeight * graph.value.width / graph.value.height
  const autoWidth = viewportWidth >= graphMinDisplayWidth
    ? Math.min(Math.max(graphMinDisplayWidth, heightFitWidth), viewportWidth)
    : Math.max(graphMinDisplayWidth, heightFitWidth)
  const width = autoWidth * graphZoom.value
  return { width, height: width * graph.value.height / graph.value.width }
})
const graphStyle = computed(() => ({
  width: `${graphDisplaySize.value.width}px`,
  height: `${graphDisplaySize.value.height}px`,
}))
const graphAlignClass = computed(() => graphDisplaySize.value.height > graphViewportSize.value.height ? 'items-start' : 'items-center')
const graphJustifyClass = computed(() => graphDisplaySize.value.width > graphViewportSize.value.width ? 'justify-start' : 'justify-center')
const clamp = (value, min, max) => Math.min(max, Math.max(min, value))
const zoomGraph = (delta) => {
  graphZoom.value = Math.round(clamp(graphZoom.value + delta, graphZoomMin, graphZoomMax) * 100) / 100
}
const resetGraphZoom = () => {
  graphZoom.value = 1
}
const handleGraphWheel = (event) => {
  if (!event.ctrlKey) return
  event.preventDefault()
  zoomGraph(event.deltaY < 0 ? graphZoomStep : -graphZoomStep)
}
const selectedLinePosition = computed(() => {
  if (!selectedLineKey.value) return selectedEdgeIndex.value === null ? 0 : selectedEdgeIndex.value + 1
  const index = graph.value.edges.findIndex(edge => edge.key === selectedLineKey.value)
  return index >= 0 ? index + 1 : 0
})

// 冲突组变化时重置选择，避免右侧还停留在上一条链路的详情。
watch(groups, () => {
  if (activeGroupIndex.value >= groups.value.length) activeGroupIndex.value = 0
  if (groups.value.length <= 1) viewMode.value = 'group'
  selectedEdgeIndex.value = null
  selectedLineKey.value = null
  selectedLine.value = null
}, { immediate: true })

const groupSummary = (group) => (group?.cycle || []).map(edge => `${modName(edge.from_id)} → ${modName(edge.to_id)}`).join('  /  ')
const sourceTooltipLabel = (source) => ({
  native: t('ui.rule_panel.source.native', '原生规则'),
  user: t('ui.rule_panel.source.user', '用户规则'),
  community: t('ui.rule_panel.source.community', '社区规则'),
  workshop: t('ui.rule_panel.source.workshop', '创意工坊规则'),
  dynamic: t('ui.rule_panel.source.dynamic', '动态规则'),
}[source] || t('common.status.unknown', '未知'))

// 线条 tooltip 只列出“这条视觉指向线”上的规则；同来源连续展示，不重复来源标题。
const edgeTooltip = (edge) => {
  return ruleGroupsBySource(edge.previewRules?.length ? edge.previewRules : edge.rules || []).map(({ source, rules }) => [
    `**${sourceTooltipLabel(source)}：**`,
    ...rules.map(rule => richRuleSentence(rule)),
  ].join('\n')).join('\n\n')
}

// --- 规则卡片定义 ---
// 对齐 RulePanel 的字段和颜色：一张卡展示某个模组在某类规则来源中的完整关系。
const relationSectionMeta = {
  dependencies: {
    label: () => t('ui.rule_panel.relation.dependencies', '依赖:'),
    labelClass: 'text-accent-highlight',
    chipClass: 'border-accent-highlight/20 bg-accent-highlight/10',
  },
  loadAfter: {
    label: () => t('ui.rule_panel.relation.load_after', '前置:'),
    labelClass: 'text-accent-warn',
    chipClass: 'border-accent-warn/20 bg-accent-warn/10',
  },
  loadBefore: {
    label: () => t('ui.rule_panel.relation.load_before', '后置:'),
    labelClass: 'text-accent-primary',
    chipClass: 'border-accent-primary/20 bg-accent-primary/10',
  },
  incompatibleWith: {
    label: () => t('ui.rule_panel.relation.incompatible', '冲突:'),
    labelClass: 'text-accent-danger',
    chipClass: 'border-accent-danger/20 bg-accent-danger/10',
  },
}
const relationSectionLabel = (type) => relationSectionMeta[type]?.label() || type
const relationSectionLabelClass = (type) => relationSectionMeta[type]?.labelClass || 'text-text-dim'
const relationSectionChipClass = (type) => relationSectionMeta[type]?.chipClass || 'border-border-base/10 bg-bg-overlay/5'
const relationTargetName = (id, info) => modStore.displayModName(id, Array.isArray(info?.name) ? info.name[0] : info?.name)
const relationItemTooltip = (targetId, info) => {
  let text = `ID: ${targetId}`
  if (!info) return text
  if (typeof info === 'string') return `${text}\n\n${t('common.field.explanation', '说明')}:\n${info}`
  if (info.name) text += `\nName: ${Array.isArray(info.name) ? info.name[0] : info.name}`
  if (info.comment) text += `\n\n${t('common.field.explanation', '说明')}:\n${Array.isArray(info.comment) ? info.comment.join('\n') : info.comment}`
  return text
}
const objectItems = (value = {}) => Object.entries(value || {}).map(([id, info]) => ({ id, info }))
const modRelationItems = (items = []) => (items || []).map(item => ({ id: item.package_id || item.id || item, info: item }))
const dynamicRule = (ruleId) => ruleStore.userDynamicRules.find(rule => rule.rule_id === ruleId)

// 动态规则只有一个 action，这里只把会形成排序边的 load_after/load_before 转成关系区。
const dynamicRuleSection = (rule) => {
  const action = rule?.action || {}
  if (action.type === 'load_after') return { type: 'loadAfter', items: [{ id: action.value, info: { name: [modName(action.value)] } }] }
  if (action.type === 'load_before') return { type: 'loadBefore', items: [{ id: action.value, info: { name: [modName(action.value)] } }] }
  return null
}
const sourceRules = (source, modId, ruleId = '') => {
  const pid = normalizeEdgeId(modId)
  // 详情卡片展示“该模组在某个规则来源里的完整关系”，而不是只重复冲突边本身。
  // 这样用户能直接看到禁用/删除按钮会影响哪些依赖、前置、后置和冲突关系。
  if (source === 'native') {
    const mod = modStore.takeModById(modId)
    return {
      dependencies: modRelationItems(mod?.dependencies_mods),
      loadAfter: modRelationItems(mod?.load_after_mods),
      loadBefore: modRelationItems(mod?.load_before_mods),
      incompatibleWith: modRelationItems(mod?.incompatible_mods),
    }
  }
  if (source === 'community') {
    const rules = ruleStore.communityModRules[pid] || {}
    return { loadAfter: objectItems(rules.loadAfter), loadBefore: objectItems(rules.loadBefore), incompatibleWith: objectItems(rules.incompatibleWith) }
  }
  if (source === 'user') {
    const rules = ruleStore.userModRules[pid] || {}
    return { loadAfter: objectItems(rules.loadAfter), loadBefore: objectItems(rules.loadBefore), incompatibleWith: objectItems(rules.incompatibleWith) }
  }
  if (source === 'workshop') {
    const rules = ruleStore.workshopModRules[pid] || {}
    return { dependencies: objectItems(rules.dependencies), loadAfter: objectItems(rules.loadAfter) }
  }
  if (source === 'dynamic') {
    const section = dynamicRuleSection(dynamicRule(ruleId))
    return section ? { [section.type]: section.items } : {}
  }
  return {}
}
const sourceExcludedSet = (source) => ({
  user: ruleStore.settings?.excluded_user_mods,
  community: ruleStore.settings?.excluded_community_mods,
  workshop: ruleStore.settings?.excluded_workshop_mods,
}[source] || [])
const isModSourceEnabled = (source, modId) => !sourceExcludedSet(source).includes(normalizeEdgeId(modId))

// 顶部全局开关只显示当前链路涉及的来源；原生规则没有持久开关，所以不进入这里。
const isGlobalSourceEnabled = (source) => !!ruleStore.settings?.[{
  user: 'user_mod_rules_enabled',
  community: 'community_mod_rules_enabled',
  workshop: 'workshop_mod_rules_enabled',
  dynamic: 'dynamic_rules_enabled',
}[source]]
const pendingActionList = computed(() => Object.values(pendingActions.value))
const isPendingAction = (action) => !!action?.key && !!pendingActions.value[action.key]
const globalSourceAction = (source) => {
  const enabled = isGlobalSourceEnabled(source)
  return { key: `global:${source}`, kind: 'global', source, enabled, targetEnabled: !enabled }
}
const previewGlobalSourceEnabled = (source) => {
  const action = globalSourceAction(source)
  return isPendingAction(action) ? action.targetEnabled : action.enabled
}
const previewActionEnabled = (action, fallback) => isPendingAction(action) ? action.targetEnabled : fallback
const pendingActionClass = (action, currentEnabled) => {
  if (isPendingAction(action)) return 'border-accent-warn/25 bg-accent-warn/12 text-accent-warn hover:bg-accent-warn/18'
  return currentEnabled
    ? 'border-accent-success/18 bg-accent-success/10 text-accent-success hover:bg-accent-success/16'
    : 'border-accent-danger/18 bg-accent-danger/10 text-accent-danger hover:bg-accent-danger/16'
}
const togglePendingAction = (action) => {
  if (!action?.key) return
  const next = { ...pendingActions.value }
  if (next[action.key]) delete next[action.key]
  else next[action.key] = action
  pendingActions.value = next
}
const globalSourceTooltip = (source) => previewGlobalSourceEnabled(source)
  ? t('dialog.sort_conflict.global_disable_tooltip', '关闭整套{source}，该来源的排序规则将不会参与自动排序与冲突计算。', { source: sourceLabel(source) })
  : t('dialog.sort_conflict.global_enable_tooltip', '启用整套{source}，该来源的排序规则将会参与自动排序与冲突计算。', { source: sourceLabel(source) })

// 右侧卡片按“规则来源 + 规则所属模组 + 动态规则 ID”去重。
// 同一条冲突边可能有多个贡献规则，但处理动作面向的是完整规则来源，而不是单条提示文本。
const ruleCards = computed(() => {
  const cards = new Map()
  for (const rule of selectedRules.value) {
    const source = rule.rule_source?.type || 'unknown'
    const ruleId = rule.rule_source?.detail?.rule_id || ''
    const key = `${source}:${normalizeEdgeId(rule.source_mod)}:${ruleId}`
    if (cards.has(key)) continue
    const sections = Object.entries(sourceRules(source, rule.source_mod, ruleId))
      .map(([type, items]) => ({ type, items: (items || []).filter(item => item.id) }))
      .filter(section => section.items.length)
    const dynamic = source === 'dynamic' ? dynamicRule(ruleId) : null
    const enabled = source === 'dynamic' ? !!dynamic?.enabled : isModSourceEnabled(source, rule.source_mod)
    cards.set(key, {
      key,
      source,
      modId: rule.source_mod,
      ruleId,
      sections,
      description: source === 'dynamic'
        ? (dynamic?.name || rule.rule_source?.name || sourceLabel('dynamic'))
        : t('dialog.sort_conflict.card_description', '该模组在{source}中的完整关系规则', { source: sourceLabel(source) }),
      action: ['user', 'community', 'workshop', 'dynamic'].includes(source)
        ? {
            key: source === 'dynamic' ? `dynamic:${ruleId}` : `mod:${source}:${normalizeEdgeId(rule.source_mod)}`,
            kind: source === 'dynamic' ? 'dynamic' : 'mod',
            source,
            modId: rule.source_mod,
            ruleId,
            enabled,
            targetEnabled: !enabled,
            tooltip: enabled
              ? t('dialog.sort_conflict.card_disable_tooltip', '保存后停用 {mod} 的{source}，会影响卡片内显示的全部关系。', { mod: modName(rule.source_mod), source: sourceLabel(source) })
              : t('dialog.sort_conflict.card_enable_tooltip', '保存后启用 {mod} 的{source}。', { mod: modName(rule.source_mod), source: sourceLabel(source) }),
          }
        : null,
      actionTooltip: t('dialog.sort_conflict.native_hint', '原生规则由 Mod 内部声明，不能单独禁用。'),
    })
  }
  return [...cards.values()]
})
const selectGroup = (index) => {
  activeGroupIndex.value = index
  viewMode.value = 'group'
  clearEdgeSelection()
}
const setViewMode = (mode) => {
  viewMode.value = mode
  clearEdgeSelection()
}
const clearEdgeSelection = () => {
  selectedEdgeIndex.value = null
  selectedLineKey.value = null
  selectedLine.value = null
}
const selectEdge = (index, line = null) => {
  selectedEdgeIndex.value = index
  selectedLineKey.value = line?.key || null
  selectedLine.value = line?.visual ? { visual: line.visual, rules: line.rules || [] } : null
}
const cancel = () => {
  pendingActions.value = {}
  feedback.value = ''
  modStore.clearPendingSortConflict()
}

// --- 持久化操作 ---
// 所有操作先记录到 pendingActions；只有保存时才真正写入规则配置并重新自动排序。
const applyPendingActions = async () => {
  if (!pendingActionList.value.length || processing.value) return
  processing.value = true
  feedback.value = ''
  try {
    for (const action of pendingActionList.value) {
      let success = false
      if (action.kind === 'global') {
        success = await ruleStore.setGlobalEnable(action.source, action.targetEnabled)
      } else if (action.kind === 'mod') {
        success = await ruleStore.toggleModRule(action.source, action.modId, !action.targetEnabled)
      } else if (action.kind === 'dynamic') {
        const rule = dynamicRule(action.ruleId)
        success = !!rule && await ruleStore.toggleDynamicRule(rule, action.targetEnabled)
      } else if (action.kind === 'deleteUserRelation') {
        success = await ruleStore.removeUserModRuleItem(action.modId, action.sectionType, action.targetId)
      }
      if (success === false) throw new Error(t('dialog.sort_conflict.action_failed', '规则操作保存失败'))
    }
    pendingActions.value = {}
    await modStore.retryAutoSortAfterRuleChange()
  } catch (error) {
    feedback.value = error?.message || t('dialog.sort_conflict.apply_failed', '保存规则失败，请重试。')
  } finally {
    processing.value = false
  }
}
const userRelationDeleteAction = (modId, sectionType, targetId) => ({
  key: `delete-user-relation:${normalizeEdgeId(modId)}:${sectionType}:${normalizeEdgeId(targetId)}`,
  kind: 'deleteUserRelation',
  modId,
  sectionType,
  targetId,
})
const confirmDeleteUserRelation = async (modId, sectionType, targetId, event) => {
  if (!['loadAfter', 'loadBefore', 'incompatibleWith'].includes(sectionType)) return
  const action = userRelationDeleteAction(modId, sectionType, targetId)
  if (isPendingAction(action)) {
    togglePendingAction(action)
    return
  }
  const ok = await confirmStore.open({
    title: t('ui.rule_panel.action.delete_relation', '删除模组关系规则'),
    message: t('dialog.sort_conflict.delete_relation_message', '保存后会删除 {owner} 与 {target} 的这条模组关系规则。', { owner: modName(modId), target: modName(targetId) }),
    mode: 'confirm',
    type: 'warning',
    confirmText: t('common.action.delete', '删除'),
    cancelText: t('common.action.cancel', '取消'),
  }, event)
  if (ok) togglePendingAction(action)
}
</script>

<style scoped>
.rule-flow-line {
  stroke-dasharray: 8 6;
  animation: sort-rule-flow 1.35s linear infinite;
}

.rule-danger-line {
  stroke-dasharray: 10 6;
  animation-duration: 0.95s;
}

.sort-conflict-edge,
.sort-conflict-edge * {
  outline: none;
}

@keyframes sort-rule-flow {
  to {
    stroke-dashoffset: -14;
  }
}
</style>
