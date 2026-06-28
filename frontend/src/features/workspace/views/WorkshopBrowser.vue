<!-- src/components/workspace/views/WorkshopBrowser.vue -->
<template>
  <div class="h-full flex gap-4 p-4 overflow-hidden">
    
    <!-- 左侧：列表 -->
    <div class="w-[35%] flex flex-col bg-bg-inset/70 border border-border-base/10 rounded-2xl overflow-hidden shadow-2xl" data-tour="workspace-workshop-results">
      <div class="p-4 bg-accent-primary/5 border-b border-border-base/10 space-y-3 relative z-10 shrink-0" data-tour="workspace-workshop-search">
        <div class="flex justify-between items-center">
          <h3 class="text-sm font-black tracking-widest text-accent-primary flex items-center gap-2 uppercase">
            <Globe class="size-4" /> {{ workspaceStore.workshopSearch.sourceMode === 'online' ? '在线工坊搜索' : '缓存工坊浏览' }}
          </h3>
          <div class="flex items-center gap-3">
            <label class="flex items-center gap-2 text-[0.7rem] font-bold text-text-dim cursor-pointer select-none">
              <input :checked="workspaceStore.workshopSearch.sourceMode === 'online'" type="checkbox" class="accent-cyan-400" @change="toggleOnlineSearch" />
              在线搜索
            </label>
            <span class="text-[0.7rem] text-text-dim font-mono">共 {{ workspaceStore.workshopSearch.total }} 项</span>
          </div>
        </div>
        
        <div class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-text-dim" />
          <!-- 添加了 clearable 交互 -->
          <input v-model="localQuery" @input="debouncedSearch" :placeholder="workspaceStore.workshopSearch.sourceMode === 'online' ? '搜索 Steam 工坊标题或工坊ID...' : '搜索模组名称、包名或工坊ID...'" 
            class="w-full bg-bg-inset border border-border-base/10 rounded-xl pl-9 pr-8 py-2 text-sm text-text-main focus:border-accent-primary focus:bg-bg-inset outline-none transition-all shadow-inner" />
          
          <button v-if="localQuery" @click="clearSearch" class="absolute right-3 top-1/2 -translate-y-1/2 text-text-dim hover:text-text-main">
            <X class="size-4" />
          </button>
        </div>
      </div>

      <!-- 列表内容区 -->
      <div class="content-surface relative flex-1 overflow-hidden">
        
        <!-- 首次加载大遮罩 -->
        <div v-if="workspaceStore.workshopSearch.isLoading" class="absolute inset-0 flex flex-col items-center justify-center text-accent-primary z-10 bg-bg-deep/50 backdrop-blur-sm">
          <div class="size-8 border-2 border-current border-t-transparent rounded-full animate-spin mb-2"></div>
          <span class="text-xs font-bold tracking-widest">正在检索...</span>
        </div>

        <!-- 替换为 RecycleScroller -->
        <RecycleScroller v-if="workspaceStore.workshopSearch.results.length > 0"
          ref="scrollerRef" class="h-full custom-scrollbar p-2 bg-bg-inset/90" :items="workspaceStore.workshopSearch.results" :item-size="itemHeight" key-field="workshop_id"
          @scroll="handleScroll" >
          <template v-slot="{ item }">
            <div class="h-full pb-1">
              <div @click="selectMod(item)" v-tooltip="buildResultTooltip(item)"
                class="h-full px-3 py-2 rounded-md bg-glass-medium/60 border border-border-base/5 cursor-pointer transition-all hover:bg-accent-primary/10 group flex items-center gap-3"
                :class="workspaceStore.workshopSearch.selectedId === item.workshop_id ? 'bg-accent-primary/20 border-r-4 border-r-accent-primary shadow-[inset_2px_0_10px_rgba(var(--rgb-accent-cool),0.1)]' : ''">
                <div v-if="workspaceStore.workshopSearch.sourceMode === 'online'" class="size-12 shrink-0 overflow-hidden rounded-lg border border-border-base/10 bg-bg-inset/90" >
                  <img v-if="item.preview_url" class="h-full w-full object-cover" loading="lazy" :src="appStore.getRemoteUrl(item.preview_url)" />
                  <div v-else class="flex h-full w-full items-center justify-center text-text-disabled">
                    <Image class="size-4" />
                  </div>
                </div>

                <div class="min-w-0 flex-1">
                  <div class="text-sm font-bold truncate transition-colors"
                    :class="workspaceStore.workshopSearch.selectedId === item.workshop_id ? 'text-text-main' : 'text-text-soft group-hover:text-accent-primary'">
                    {{ item.title || item.name || '未知模组' }}
                  </div>
                  <div class="flex justify-between items-center mt-1 gap-2">
                    <div class="flex min-w-0 max-w-[70%] items-center gap-1.5">
                      <span class="min-w-0 truncate text-[0.7rem] font-mono text-text-dim opacity-80" :title="item.package_id || item.short_description || item.author_steam_id || ''">
                        {{ item.package_id || item.short_description || item.author_steam_id || 'N/A' }}
                      </span>
                      <span v-for="version in item.game_versions.slice(0, 3)" :key="`${item.workshop_id}-${version}`"
                        class="shrink-0 rounded border border-accent-primary/20 bg-accent-primary/10 px-1 text-[0.6rem] font-black text-accent-primary">
                        {{ version }}
                      </span>
                    </div>
                    <div class="flex items-center gap-1 text-[0.7rem] shrink-0">
                      <span v-if="item.subscriptions" class="font-bold px-1 rounded bg-accent-primary/10 text-accent-primary border border-accent-primary/20" v-tooltip="'订阅人数'">
                        {{ formatCount(item.subscriptions) }}
                      </span>
                      <div class="font-bold px-1 rounded bg-bg-inset/80 text-text-dim border border-border-base/10" v-tooltip="'工坊ID'">
                        {{ item.workshop_id }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 滚动到底部的 Loading 指示器 (插槽) -->
          <template #after>
            <!-- 修复：加入 isLocalFetching 判定，防止网络请求结束后 Loading 瞬间消失导致高度坍塌 -->
            <div v-if="workspaceStore.workshopSearch.isLoadMore || isLocalFetching" class="py-3 flex justify-center items-center text-text-dim">
              <div class="size-4 border-2 border-accent-primary border-t-transparent rounded-full animate-spin mr-2"></div>
              <span class="text-xs">加载更多...</span>
            </div>
            <div v-else-if="!workspaceStore.workshopSearch.hasMore && workspaceStore.workshopSearch.results.length > 0" class="py-3 text-center text-xs text-text-disabled">
              - 已经到底啦 -
            </div>
          </template>
        </RecycleScroller>

        <!-- 空状态 -->
        <div v-else-if="!workspaceStore.workshopSearch.isLoading" class="absolute inset-0 flex flex-col items-center justify-center text-text-disabled">
          <Cpu class="size-16 mb-4 opacity-50" />
          <span class="text-sm font-bold tracking-widest">暂无结果</span>
        </div>

      </div>
    </div>

    <!-- 右侧：详情展示 -->
    <div class="flex-1 bg-bg-inset/80 border border-border-base/10 rounded-2xl overflow-hidden flex flex-col relative shadow-2xl" data-tour="workspace-workshop-detail">
      
      <template v-if="selectedMod && !workspaceStore.workshopSearch.isDetailLoading">
        <!-- 顶部导航面包屑/后退栏 -->
        <div v-if="workspaceStore.workshopSearch.historyStack.length > 0" class="absolute top-0 left-0 z-20 flex items-center opacity-60">
          <button @click="workspaceStore.goBackWorkshopDetail" 
                  class="flex items-center gap-1 px-3 py-1.5 bg-bg-inset backdrop-blur-md rounded-lg text-xs font-bold text-text-main hover:text-accent-primary border border-border-base/18 hover:border-accent-primary/50 transition-all shadow-lg">
            <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            返回上一层
          </button>
        </div>
        <!-- 头部 Banner -->
        <div class="h-64 shrink-0 p-5 relative overflow-hidden group">
          <img v-if="selectedMod?.preview_url" :src="appStore.getRemoteUrl(selectedMod?.preview_url)" 
            class="absolute inset-0 w-full h-full object-cover blur-md opacity-40 scale-110 transition-transform duration-1000 group-hover:scale-100 group-hover:opacity-60" />
          <div class="absolute inset-0 bg-linear-to-t from-bg-deep via-bg-deep/60 to-transparent"></div>
          
          <div class="w-full">
            <h2 class="text-3xl min-w-0 font-black gap-1 text-text-main text-shadow-lg truncate leading-tight">
              {{ selectedMod?.title || selectedMod?.name }}
            </h2>
          </div>
          
          <div class="pt-3 flex gap-6 items-end">
            
            <img v-if="selectedMod?.preview_url" :src="appStore.getRemoteUrl(selectedMod?.preview_url)" 
              class="size-40 rounded-xl shadow-[0_10px_30px_var(--shadow-color)] border-2 border-border-base/10 object-cover z-10" />
            <div class="size-40 rounded-xl bg-bg-inset/90 border-2 border-dashed border-border-base/18 flex items-center justify-center z-10" v-else>
              <span class="text-xs text-text-dim">NO IMAGE</span>
            </div>

            <div class="flex-1 min-w-0 pb-2 z-10">
              <div class="flex flex-col gap-2.5 mt-3">
                <!-- 第一行：标识符 -->
                <div class="flex flex-wrap gap-2">
                  <span class="px-2 py-1 rounded bg-accent-primary/20 text-accent-primary text-[0.6rem] font-black border border-accent-primary/30 uppercase tracking-widest">
                    WID: {{ selectedId }}
                  </span>
                  <span class="px-2 py-1 rounded bg-bg-inset/80 text-text-dim text-[0.6rem] font-mono border border-border-base/10 flex items-center gap-1.5">
                    <Fingerprint class="size-3 opacity-50" />
                    {{ selectedMod?.package_id || 'N/A' }}
                  </span>
                </div>
                <!-- 第二行：作者与时间 -->
                <div class="flex flex-wrap gap-2 items-center">
                  <span class="px-2 py-1 rounded bg-bg-inset text-text-main text-[0.65rem] font-bold border border-border-base/18 flex items-center gap-1.5 backdrop-blur-sm">
                    <UserRound class="size-3 text-accent-success" />
                    {{ selectedMod?.author || selectedMod?.author_steam_id || '未知作者' }}
                  </span>
                  <span v-if="selectedMod?.time_updated" class="px-2 py-1 rounded bg-bg-inset text-text-main text-[0.65rem] font-bold border border-border-base/18 flex items-center gap-1.5 backdrop-blur-sm">
                    <Calendar class="size-3 text-text-dim"/>
                    {{ formatDate(selectedMod?.time_updated) }}
                  </span>
                  <span v-if="selectedMod?.subscriptions" class="px-2 py-1 rounded bg-bg-inset text-text-main text-[0.65rem] font-bold border border-border-base/18 flex items-center gap-1.5 backdrop-blur-sm">
                    <CloudDownload class="size-3 text-accent-primary" />
                    {{ formatCount(selectedMod?.subscriptions) }} 订阅
                  </span>
                </div>
                <!-- 第三行：适用游戏版本 (List) -->
                <div v-if="selectedMod?.game_versions?.length" class="flex flex-wrap gap-1.5 items-center">
                  <div class="flex items-center gap-1 text-text-dim mr-1">
                    <Layers class="size-3" />
                    <span class="text-[0.7rem] font-bold uppercase tracking-tighter">适用版本:</span>
                  </div>
                  <span v-for="version in selectedMod.game_versions" :key="version"
                    class="px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary text-[0.55rem] font-black border border-accent-primary/20">
                    {{ version }}
                  </span>
                </div>
                <div v-else class="text-[0.7rem] text-text-disabled italic font-mono flex items-center gap-1">
                  <Layers class="size-3" /> 未标注适用版本
                </div>
              </div>
            </div>
            
            <!-- 动作按钮 -->
            <div class="flex flex-col gap-2 z-10 shrink-0" data-tour="workspace-workshop-actions">
              <button v-if="!isSubscribed([selectedId])" @click="handleSubscribe([selectedId])" class="w-36 py-2 rounded-xl bg-accent-primary/20 text-accent-primary text-sm border border-accent-primary/40 font-bold hover:scale-105 hover:bg-accent-primary active:scale-95 transition-all hover:text-on-accent-primary flex items-center justify-center gap-2">
                <CloudDownload class="size-4" /> 订阅
              </button>
              <button v-else @click="handleUnsubscribe([selectedId])" class="w-36 py-2 rounded-xl bg-accent-danger/20 text-accent-danger border border-accent-danger/40 font-bold text-sm hover:bg-accent-danger hover:text-on-accent-danger hover:shadow-[0_0_15px_rgba(var(--rgb-accent-danger),0.3)] transition-all flex items-center justify-center gap-2">
                <CloudDownload class="size-4" /> 取消订阅
              </button>
              <button @click="handleDownload([selectedId])" class="w-36 py-2 rounded-xl bg-accent-success/20 text-accent-success border border-accent-success/40 font-bold text-sm hover:bg-accent-success hover:text-on-accent-success hover:shadow-[0_0_15px_rgba(var(--rgb-accent-success),0.3)] transition-all flex items-center justify-center gap-2">
                <Download class="size-4" /> 管理器下载
              </button>
              <span @click="openWebUrl(selectedId)" title="打开创意工坊页面" class="px-2.5 py-1 rounded bg-bg-inset text-[0.65rem] text-text-dim hover:text-accent-primary cursor-pointer transition-all font-bold border border-border-base/18 flex items-center gap-1 backdrop-blur-sm">
                <Link class="size-2.5" />
                打开创意工坊页面
              </span>
            </div>

          </div>
        </div>

        <!-- 内容区 (使用 Tailwind Typography) -->
        <div class="workshop-detail-scroll content-surface flex-1 overflow-y-auto p-5 custom-scrollbar">
          <!-- 依赖提示框 (如果是解析得到的) -->
          <div v-if="selectedMod?.dependencies_mods && dependencies_ids.length > 0" data-tour="workspace-workshop-dependencies"
            class="mb-6 p-3 rounded-xl bg-accent-warn/10 border border-accent-warn/30">
            <div class="flex justify-between items-center mb-2">
              <h4 class="text-xs font-bold text-accent-warn uppercase tracking-widest flex items-center gap-1">
                <Link class="size-3" /> 侦测到前置依赖
              </h4>
              <div class="flex gap-1">
                <button @click="handleUnsubscribe(dependencies_ids)" class="px-2.5 py-1 cursor-pointer rounded bg-accent-danger/20 text-accent-danger text-[0.65rem] font-bold border border-accent-danger/30 hover:scale-105 hover:text-text-main hover:bg-accent-danger active:scale-95 transition-all uppercase tracking-widest">
                  取订所有依赖
                </button>
                <button @click="handleSubscribe(dependencies_ids)" class="px-2.5 py-1 cursor-pointer rounded bg-accent-primary/20 text-accent-primary text-[0.65rem] font-bold border border-accent-primary/30 hover:scale-105 hover:text-text-main hover:bg-accent-primary active:scale-95 transition-all uppercase tracking-widest">
                  订阅所有依赖
                </button>
                <button @click="handleDownload(dependencies_ids)" class="px-2.5 py-1 cursor-pointer rounded bg-accent-primary/20 text-accent-success text-[0.65rem] font-bold border border-accent-success/30 hover:scale-105 hover:text-text-main hover:bg-accent-success active:scale-95 transition-all uppercase tracking-widest">
                  下载所有依赖
                </button>
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <span v-for="(name, wid) in selectedMod?.dependencies_mods" :key="wid"
                class="px-2 py-0.5 text-sm group relative rounded border border-border-base/10 font-mono cursor-pointer"
                :class="[isSubscribed([wid]) ? 'bg-accent-primary/20 text-accent-primary' : isInstalled([wid]) ? 'bg-accent-success/20 text-accent-success' : 'bg-bg-overlay/10 text-text-dim']"
                @click="handleNavigateInside(wid)"
                >
                {{ name }} <span class="opacity-50 text-[0.6rem]">({{ wid }})</span>
                <div class="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto flex gap-0.5 justify-center items-center text-[0.6rem] transition-all">
                  <button @click.stop="openWebUrl(wid)" v-tooltip="'打开创意工坊页面'" class="p-1.5 cursor-pointer rounded-full bg-accent-special/80 hover:bg-accent-special scale-90 hover:scale-105 text-on-accent-special transition-all"><Link class="size-3" /></button>
                  <button v-if="isSubscribed([wid])" @click.stop="handleUnsubscribe([wid])" v-tooltip="'取消订阅'" class="p-1.5 cursor-pointer rounded-full bg-accent-danger/80 hover:bg-accent-danger scale-90 hover:scale-105 text-on-accent-danger transition-all"><FlagOff class="size-3" /></button>
                  <button v-else @click.stop="handleSubscribe([wid])" v-tooltip="'Steam 订阅'" class="p-1.5 cursor-pointer rounded-full bg-accent-primary/80 hover:bg-accent-primary scale-90 text-on-accent-primary hover:scale-105 transition-all"><Flag class="size-3" /></button>
                  <button @click.stop="handleDownloadSingle([wid])" v-tooltip="'下载到管理器'" class="p-1.5 cursor-pointer rounded-full bg-accent-success/80 hover:bg-accent-success scale-90 text-on-accent-success hover:scale-105 transition-all"><Download class="size-3" /></button>
                </div>
              </span>
            </div>
          </div>

          <!-- 游戏截图画廊 (Horizontal Scroll) -->
          <div v-if="selectedMod?.screenshots?.length > 0" class="space-y-2">
            <h4 class="text-xs font-bold text-text-dim uppercase tracking-widest flex items-center gap-1">
              <Image class="size-3" /> 截图
            </h4>
            <!-- 使用 flex nowrap 和 overflow-x-auto 实现横向滚动 -->
            <div v-viewer.rebuild="screenshotViewerOptions" class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <div v-for="(img, idx) in selectedMod.screenshots" :key="idx"
                class="relative h-32 w-56 shrink-0 snap-start overflow-hidden rounded-lg border border-border-base/10 bg-bg-inset/80"
              >
                <div v-if="!loadedScreenshotMap[img]" class="absolute inset-0 flex items-center justify-center bg-bg-inset/90" >
                  <svg viewBox="0 0 160 96" class="h-12 w-20 text-text-disabled" fill="none" aria-hidden="true">
                    <rect x="10" y="10" width="140" height="76" rx="10" stroke="currentColor" stroke-width="4" stroke-dasharray="6 6" />
                    <circle cx="48" cy="38" r="10" fill="currentColor" class="opacity-60" />
                    <path d="M24 72L58 48L80 66L106 42L136 72" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" class="opacity-70" />
                  </svg>
                </div>
                <img class="h-full w-full object-cover transition-transform hover:scale-[1.02] cursor-zoom-in"
                  :src="appStore.getRemoteUrl(img)" @load="markScreenshotLoaded(img)" @error="markScreenshotLoaded(img)" />
              </div>
            </div>
          </div>

          <div class="prose prose-invert prose-sm md:prose-base max-w-none prose-img:rounded-xl prose-a:text-accent-primary select-text">
            <div v-if="parsedDescription" v-html="parsedDescription"></div>
            <div v-else class="text-text-dim italic">该模组没有提供详细描述。</div>
          </div>

          <div v-if="selectedMod?.children?.length > 0" class="space-y-2 border-t border-border-base/10 pt-4">
            <h4 class="text-xs font-bold text-accent-tip uppercase tracking-widest flex items-center gap-1">
              <Link class="size-3" /> 工坊关联项
            </h4>
            <div class="flex flex-wrap gap-2">
              <button v-for="child in selectedMod.children" :key="`${child.workshop_id}-${child.sort_order}`"
                class="px-2 py-1 rounded bg-bg-inset/80 text-text-soft text-xs border border-border-base/10 hover:border-accent-primary/40 hover:text-accent-primary transition-colors"
                @click="handleNavigateInside(child.workshop_id)" >
                {{ child.workshop_id }}
              </button>
            </div>
          </div>

          <!-- 反向依赖推荐 (有谁依赖了我) -->
          <div v-if="selectedMod.dependents_mods?.length > 0" class="space-y-2 mt-3 border-t border-border-base/10 pt-4">
            <h4 class="text-xs font-bold text-accent-primary uppercase tracking-widest flex items-center gap-1">
              <Network class="size-3" /> 生态关联 (被以下模组依赖)
            </h4>
            <div class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <MiniModCard v-for="mod in selectedMod.dependents_mods" :key="mod.workshop_id" 
                :mod="mod" class="snap-start" 
                @navigate="handleNavigateInside" />
            </div>
          </div>

          <!-- 同作者的其他作品 -->
          <div v-if="selectedMod.same_author_mods?.length > 0" class="space-y-2 border-t border-border-base/10 pt-4">
            <h4 class="text-xs font-bold text-accent-success uppercase tracking-widest flex items-center gap-1">
              <User class="size-3" /> 作者的其他作品
            </h4>
            <div class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <MiniModCard v-for="mod in selectedMod.same_author_mods" :key="mod.workshop_id" :mod="mod" class="snap-start" @navigate="handleNavigateInside" />
            </div>
          </div>

        </div>
      </template>

      <!-- 加载遮罩 -->
      <div v-if="workspaceStore.workshopSearch.isDetailLoading" class="absolute inset-0 bg-bg-deep flex flex-col items-center justify-center z-50">
        <div class="relative flex items-center justify-center">
          <div class="size-16 border-2 border-border-base/10 rounded-full"></div>
          <div class="absolute size-16 border-2 border-accent-primary border-t-transparent rounded-full animate-spin"></div>
          <Globe class="size-6 text-accent-primary absolute animate-pulse" />
        </div>
        <span class="text-xs font-mono text-text-dim mt-6 tracking-widest">从 Steam 获取详情中...</span>
      </div>

    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css' // 确保引入 CSS
import { Search, Globe, X, Cpu, Calendar, CloudDownload, Download, Link, Flag, FlagOff, Network, User, Image, Layers, UserRound, Fingerprint } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import { useToast } from 'vue-toastification'
import { parseUnityRichText } from '../../../shared/lib/text'
import { useWorkspaceStore } from '../workspaceStore'
import MiniModCard from '../components/MiniModCard.vue'

const appStore = useAppStore()
const toast = useToast()
const workspaceStore = useWorkspaceStore()

// 本地搜索词绑定，用于防抖
const localQuery = ref(workspaceStore.workshopSearch.query)
let searchTimeout = null
const scrollerRef = ref(null)
const isLocalFetching = ref(false)  // 局部硬锁，绝对同步，防穿透
const loadedScreenshotMap = ref({})
const blurActiveViewerFocus = () => {
  const activeElement = document.activeElement
  if (activeElement?.closest?.('.viewer-container')) {
    activeElement.blur()
  }
}
const screenshotViewerOptions = {
  focus: false,
  navbar: false,
  title: false,
  toolbar: true,
  tooltip: true,
  movable: true,
  zoomable: true,
  rotatable: true,
  scalable: true,
  transition: false,
  zIndex: 100000,
  hide: blurActiveViewerFocus,
}

// 仅在用户真正打开工坊页且当前没有任何结果时，才触发默认搜索。
onMounted(() => {
  if (workspaceStore.workshopSearch.results.length === 0) {
    void workspaceStore.doWorkshopSearch('')
  }
})

onUnmounted(() => {
  if (searchTimeout) clearTimeout(searchTimeout)
})
const itemHeight = computed(() => appStore.scalePx(76))

const selectedMod = computed(() => {
  return workspaceStore.workshopSearch.detailData
})
const selectedId = computed(() => {
  return workspaceStore.workshopSearch.selectedId
})
const dependencies_ids = computed(() => {
  return Object.keys(workspaceStore.workshopSearch.detailData?.dependencies_mods || {})
})
// 解析富文本描述
const parsedDescription = computed(() => {
  if (!workspaceStore.workshopSearch.detailData?.description) return ''
  return parseUnityRichText(
    workspaceStore.workshopSearch.detailData?.description,
    false,
    (url) => appStore.getRemoteUrl(url),
  )
})

const formatCount = (value) => {
  const num = Number(value || 0)
  if (!num) return '0'
  if (num >= 10000) return `${(num / 10000).toFixed(1)}w`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
  return String(num)
}

const buildResultTooltip = (item = {}) => {
  const summary = String(item.short_description || '').trim()
  if (!summary) return ''
  return summary
}

const isSubscribed = (workshop_ids) => {
  if (!workshop_ids.length) return false
  return workshop_ids.every(id => workspaceStore.subscribedWorkshopIds.has(id))
}
const isInstalled = (workshop_ids) => {
  if (!workshop_ids.length) return false
  return workshop_ids.every(id => workspaceStore.installedAllIds.has(id))
}

// 防抖搜索 (重置分页)
const debouncedSearch = () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    // 搜索时滚动条回滚到顶部
    if (scrollerRef.value) {
      scrollerRef.value.$el.scrollTop = 0
    }
    workspaceStore.doWorkshopSearch(localQuery.value.trim(), false)
  }, 500)
}

const clearSearch = () => {
  localQuery.value = ''
  debouncedSearch()
}

// 以图片地址为键记录加载完成状态，避免切换详情时旧状态串到新截图。
const markScreenshotLoaded = (url) => {
  if (!url) return
  loadedScreenshotMap.value = {
    ...loadedScreenshotMap.value,
    [url]: true
  }
}

const toggleOnlineSearch = async (event) => {
  const enabled = !!event?.target?.checked
  const switched = await workspaceStore.setWorkshopSearchMode(enabled ? 'online' : 'offline')
  if (!switched && event?.target) {
    event.target.checked = workspaceStore.workshopSearch.sourceMode === 'online'
  }
}

// 选中查看详情, 点击左侧主列表 (会清空历史栈)
const selectMod = (item) => {
  loadedScreenshotMap.value = {}
  workspaceStore.fetchWorkshopDetails(item.workshop_id, false)
}
// 点击详情页内的推荐卡片 (会压入历史栈)
const handleNavigateInside = (workshop_id) => {
  // 滚动条回到顶部 (可选，提升体验)
  const scrollContainer = document.querySelector('.workshop-detail-scroll')
  if (scrollContainer) scrollContainer.scrollTop = 0
  loadedScreenshotMap.value = {}
  workspaceStore.fetchWorkshopDetails(workshop_id, true)
}

// 核心：处理无限滚动
// RecycleScroller 原生触发滚动事件
const handleScroll = async (event) => {
  const target = event.target;
  // 2. 修复精度问题：使用 Math.ceil 向上取整，兼容高分屏和缩放导致的小数 scrollTop
  const isBottom = Math.ceil(target.scrollTop + target.clientHeight) >= target.scrollHeight - 150;
  // 1. 拦截条件
  if (
    !isBottom || 
    !workspaceStore.workshopSearch.hasMore || 
    workspaceStore.workshopSearch.isLoadMore || 
    isLocalFetching.value // 改为 .value
  ) {
    return;
  }
  // 2. 瞬间开启局部硬锁
  isLocalFetching.value = true;
  try {
    // 3. 等待后端请求完成
    await workspaceStore.doWorkshopSearch(localQuery.value.trim(), true);
    // 4. 极其关键：nextTick 对 RecycleScroller 不够！
    // 虚拟列表依赖 ResizeObserver 或内置 watcher，需要给它一点物理时间去生成新 DOM 并撑开容器。
    // 使用 100ms 延时可以完美避免高度瞬间缩水引发的二次触发。
    await new Promise(resolve => setTimeout(resolve, 100));
  } catch (error) {
    console.error("加载下一页失败:", error);
  } finally {
    // 5. 确保虚拟DOM完全撑开后，再释放局部硬锁
    isLocalFetching.value = false;
  }
}


const formatDate = (ts) => ts ? new Date(ts).toLocaleDateString() : '未知'

// 打开网页
const openWebUrl = (url, on_steam=true) => {
  if(!url) return
  workspaceStore.openSteamWorkshopUrl(url, on_steam)
}
// 订阅模组
const handleSubscribe = (workshop_ids) => {
  appStore.subscribeWorkshopIds(workshop_ids)
}
// 取消订阅
const handleUnsubscribe = (workshop_ids) => {
  appStore.unsubscribeWorkshopIds(workshop_ids)
}
// 下载模组
const handleDownload = (workshop_ids) => {
  appStore.downloadWorkshopItems(workshop_ids)
}
const handleDownloadSingle = (workshop_ids) => {
  handleDownload(workshop_ids)
}

</script>
