<!-- src/components/workspace/views/CollectionCommand.vue -->
<template>
  <div class="h-full flex gap-4 p-4 overflow-hidden">
    
    <!-- ==================== 左侧：合集内的 Mod ==================== -->
    <div class="w-[45%] flex flex-col bg-bg-inset/80 border border-border-base/10 rounded-2xl overflow-hidden shadow-2xl relative">
      <div v-if="wsStore.collections.activeDetails" class="flex flex-col h-full">
        <!-- 列表表头 -->
        <div class="p-4 bg-accent-warn/10 border-b border-accent-warn/20 flex flex-col gap-3 z-10 relative" data-tour="workspace-collection-actions">
          <!-- 信息区 -->
          <div class="flex items-center gap-3">
            <div class="size-12 shrink-0 rounded-lg bg-accent-warn/20 flex items-center justify-center overflow-hidden border border-accent-warn/30">
              <img v-if="wsStore.collections.activeDetails.preview_url" :src="appStore.getRemoteUrl(wsStore.collections.activeDetails.preview_url)" class="w-full h-full object-cover" />
              <Layers v-else class="size-6 text-accent-warn" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-black text-text-main truncate" v-tooltip="wsStore.collections.activeDetails.title">
                {{ wsStore.collections.activeDetails.title }}
              </div>
              <div class="text-[0.65rem] text-text-dim mt-1 font-mono">
                共 {{ wsStore.collections.activeChildren.length }} 项 | 
                <span v-if="missingCount > 0" class="text-accent-danger font-bold bg-accent-danger/10 px-1 rounded">缺失 {{ missingCount }}</span>
                <span v-else class="text-accent-success font-bold bg-accent-success/10 px-1 rounded">已全部安装</span>
              </div>
            </div>
          </div>
          <!-- 全局动作区 (一键操作) -->
          <div class="flex gap-2 w-full">
            <button @click="handleUnsubscribeAll" v-tooltip="'将整个合集从 Steam 订阅队列中移除'"
              class="flex-1 py-1.5 min-w-0 bg-accent-danger/20 hover:bg-accent-danger text-accent-danger hover:text-on-accent-danger text-xs font-black rounded-lg border border-accent-danger/30 transition-all flex items-center justify-center gap-1">
              <Flag class="size-3.5" /> 取订全部
            </button>
            <button @click="handleSubscribeAll" v-tooltip="'将整个合集添加到 Steam 订阅队列'"
              class="flex-1 py-1.5 min-w-0 bg-accent-primary/20 hover:bg-accent-primary text-accent-primary hover:text-on-accent-primary text-xs font-black rounded-lg border border-accent-primary/30 transition-all flex items-center justify-center gap-1">
              <Flag class="size-3.5" /> 订阅全部
            </button>
            <button v-if="missingCount > 0" @click="handleDownloadMissing" v-tooltip="'使用 SteamCMD 仅下载缺失项到管理器目录'"
              class="flex-1 py-1.5 bg-accent-success/20 hover:bg-accent-success text-accent-success hover:text-on-accent-success text-xs font-black rounded-lg border border-accent-success/30 transition-all flex items-center justify-center gap-1 shadow-[0_0_10px_rgba(var(--rgb-accent-success),0.2)]">
              <DownloadCloud class="size-3.5" /> 补齐下载 ({{ missingCount }})
            </button>
            <button @click="applyAsLoadOrder" v-tooltip="'应用合集列表顺序为加载顺序，请确保全部已下载！'"
              class="flex-1 px-3 py-1.5 bg-bg-overlay/10 hover:bg-accent-warn hover:text-on-accent-warn text-text-main text-xs font-bold rounded-lg border border-border-base/10 transition-colors flex items-center justify-center gap-1 ">
              <ListOrdered class="size-3.5" /> 应用加载顺序
            </button>
          </div>
        </div>
        <!-- 内容列表 -->
        <div class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1.5 relative">
          <!-- 遮罩加载 -->
          <div v-if="wsStore.collections.isChildrenLoading" class="absolute inset-0 bg-bg-deep/50 backdrop-blur-sm z-20 flex items-center justify-center">
            <div class="size-8 border-4 border-accent-warn border-t-transparent rounded-full animate-spin"></div>
          </div>
          <!-- 单个子 Mod 卡片 -->
          <div v-for="mod in wsStore.activeChildrenWithStatus" :key="mod.workshop_id"
            class="flex items-center gap-3 p-2 rounded-xl border transition-all group hover:bg-bg-overlay/5"
            :class="(mod.is_workshop || mod.is_self || mod.is_local) ? 'border-border-base/10 bg-glass-medium/60' : 'border-accent-danger/30 bg-accent-danger/5 opacity-80'">
            
            <img v-if="mod.preview_url" :src="appStore.getRemoteUrl(mod.preview_url)" class="size-10 rounded-lg object-cover border border-border-base/10 shadow-sm" />
            <div v-else class="size-10 rounded-lg bg-bg-inset/90 border border-border-base/10 flex items-center justify-center"><Package class="size-4 text-text-dim"/></div>
            
            <div class="flex-1 min-w-0">
              <div class="text-xs font-bold truncate" :class="(mod.is_workshop || mod.is_self || mod.is_local) ? 'text-text-main' : 'text-accent-danger'">{{ mod.title }}</div>
              <div class="text-[0.6rem] font-mono text-text-dim opacity-60 flex gap-2">
                <span>ID: {{ mod.workshop_id }}</span>
                <span v-if="(!mod.is_workshop && !mod.is_self && !mod.is_local)" class="text-accent-danger animate-pulse">待补充</span>
              </div>
            </div>
            
            <!-- 状态及单项动作组 (Hover 显示操作) -->
            <div class="shrink-0 flex items-center pr-1 gap-1">
              <!-- 已安装标志，平常显示，hover 隐藏给操作按钮让位 -->
              <Flag v-if="mod.is_workshop" class="size-5 text-accent-success drop-shadow-md group-hover:hidden" />
              <DownloadCloud v-if="mod.is_self" class="size-5 text-accent-success drop-shadow-md group-hover:hidden" />
              <FolderDot v-if="mod.is_local" class="size-5 text-accent-success drop-shadow-md group-hover:hidden" />
              <AlertCircle v-if="(!mod.is_workshop && !mod.is_self && !mod.is_local)" class="size-5 text-accent-danger opacity-50 group-hover:hidden" />

              <!-- 操作按钮组 (Hover 显示) -->
              <div class="hidden group-hover:flex items-center gap-1 bg-glass-medium p-1 rounded-lg backdrop-blur-md border border-border-base/10 shadow-lg">
                <button @click="appStore.openSteamWorkshopById(mod.workshop_id)" v-tooltip="'访问创意工坊页面'" class="p-1.5 rounded-md hover:bg-accent-primary text-text-dim hover:text-on-accent-primary transition-colors"><ExternalLink class="size-3.5" /></button>
                <button v-if="mod.is_workshop" @click="handleUnsubscribeSingle(mod.workshop_id)" v-tooltip="'取消订阅'" class="p-1.5 rounded-md hover:bg-accent-danger text-text-dim hover:text-on-accent-danger transition-colors"><FlagOff class="size-3.5" /></button>
                <button v-else @click="handleSubscribeSingle(mod.workshop_id)" v-tooltip="'Steam 订阅'" class="p-1.5 rounded-md hover:bg-accent-primary text-text-dim hover:text-on-accent-primary transition-colors"><Flag class="size-3.5" /></button>
                <button v-if="!mod.is_self" @click="handleDownloadSingle(mod.workshop_id)" v-tooltip="'SteamCMD 下载'" class="p-1.5 rounded-md hover:bg-accent-success text-text-dim hover:text-on-accent-success transition-colors"><Download class="size-3.5" /></button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 未选中时的默认骨架屏 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center opacity-20 pointer-events-none select-none">
        <BoxSelect class="size-32 mb-4" />
        <span class="text-sm font-black uppercase tracking-widest">选择右侧合集以查看详情</span>
      </div>
    </div>


    <!-- ==================== 右侧：合集 (55%) ==================== -->
    <div class="w-[55%] flex flex-col gap-4" data-tour="workspace-collection-browser">
      
      <!-- 搜索/添加栏 -->
      <div class="bg-bg-inset/80 p-3 rounded-2xl border border-border-base/10 flex items-center gap-3 shadow-lg" data-tour="workspace-collection-input">
        <div class="flex-1 relative">
          <Plus class="absolute left-4 top-1/2 -translate-y-1/2 size-4 text-text-dim" />
          <input v-model="newCollectionInput" @keydown.enter="submitAddCollection"
            placeholder="粘贴 Steam 合集 URL 或直接输入 ID..." 
            class="w-full bg-bg-inset border border-border-base/10 rounded-xl pl-10 pr-4 py-2 text-sm text-text-main outline-none focus:border-accent-warn focus:bg-bg-inset transition-all" />
        </div>
        <button @click="submitAddCollection" :disabled="wsStore.collections.isParsing"
          class="px-6 py-2 bg-accent-warn/10 text-accent-warn hover:bg-accent-warn hover:text-on-accent-warn border border-accent-warn/30 rounded-xl text-sm font-black transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
          <span v-if="wsStore.collections.isParsing" class="animate-spin">⟳</span> 
          <span v-else>导入合集</span>
        </button>
      </div>

      <!-- 合集卡片网格 -->
      <div class="flex-1 relative overflow-hidden">
        <!-- 列表容器 -->
        <div class="h-full overflow-y-auto custom-scrollbar grid grid-cols-2 gap-4 content-start pb-6 pr-2" data-tour="workspace-collection-list">
          <div v-for="coll in wsStore.collections.savedList" :key="coll.id"
            @click="wsStore.selectCollection(coll)"
            class="group relative aspect-16/8 rounded-2xl overflow-hidden border transition-all cursor-pointer shadow-xl flex flex-col"
            :class="wsStore.collections.activeId === coll.id ? 'border-accent-warn ring-1 ring-accent-warn shadow-[0_0_25px_rgba(var(--rgb-accent-warn),0.2)]' : 'border-border-base/10 hover:border-accent-warn/50 hover:shadow-[0_8px_20px_var(--shadow-color)]'">
            
            <!-- 背景图 -->
            <img v-if="coll.preview_url" :src="appStore.getRemoteUrl(coll.preview_url)" class="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-110 opacity-50 group-hover:opacity-70" />
            <div class="absolute inset-0 bg-linear-to-t from-bg-deep/95 via-bg-deep/60 to-transparent"></div>
            <h4 class="absolute inset-2 text-sm font-black text-text-main truncate text-shadow-lg drop-shadow-md leading-tight mb-1" v-tooltip="tooltipFormat(coll)">{{ coll.title || '未知合集' }}</h4>
            <!-- 右上角悬浮动作：删除 -->
            <button @click.stop="confirmRemove(coll)" class="absolute top-2 right-2 p-1.5 rounded-lg bg-bg-inset hover:bg-accent-danger text-text-dim hover:text-on-accent-danger opacity-0 group-hover:opacity-100 transition-all z-20 backdrop-blur-sm border border-border-base/10 hover:border-accent-danger/50" v-tooltip="'删除记录'">
              <Trash2 class="size-4" />
            </button>

            <span class="absolute -bottom-0.5 right-3 text-[0.6rem] font-mono text-text-dim px-1.5 py-0.5 rounded">上传: {{ coll.time_updated ? formatDate(coll.time_updated) : '未知' }}</span>
                
            <!-- 底部信息 -->
            <div class="absolute inset-x-0 bottom-0 p-4 flex flex-col justify-end z-10 pointer-events-none">
              <span class="text-xs font-black text-text-soft text-shadow-lg drop-shadow-md leading-tight mb-1" >{{cleanRichText(coll.description,50) || '暂无说明'}}</span>
              
              <!-- 统计指示条 -->
              <div class="flex items-center justify-between mt-1">
                <span class="text-[0.6rem] font-mono text-text-dim bg-bg-inset px-1.5 py-0.5 rounded border border-border-base/10 backdrop-blur-sm">ID: {{ coll.id }}</span>
                
                <div class="flex gap-1.5">
                  <span v-if="getListMissingCount(coll) > 0" class="px-1.5 py-0.5 rounded bg-accent-danger/20 text-accent-danger text-[0.6rem] font-bold border border-accent-danger/30 flex items-center gap-1">
                    <AlertCircle class="size-2.5"/> 缺 {{ getListMissingCount(coll) }}
                  </span>
                  <span class="px-1.5 py-0.5 rounded bg-bg-overlay/10 text-text-soft text-[0.6rem] font-bold border border-border-base/10 flex items-center gap-1">
                    <Layers class="size-2.5"/> 共 {{ coll.total || 0 }}
                  </span>
                </div>
              </div>
            </div>
            
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!wsStore.collections.isLoading && wsStore.collections.savedList.length === 0" class="absolute inset-0 flex flex-col items-center justify-center text-text-disabled pointer-events-none">
          <FolderArchive class="size-16 mb-4 opacity-50" />
          <span class="text-sm font-bold tracking-widest">您的记录中暂无合集</span>
          <span class="text-xs mt-1">请在上方粘贴链接以接入数据</span>
        </div>
      </div>

    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Layers, Plus, Download, DownloadCloud, BoxSelect, Package, Trash2, ListOrdered, Flag, FlagOff, AlertCircle, FolderArchive, FolderDot, ExternalLink } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useWorkspaceStore } from '../../../stores/workspaceStore'
import { useAppStore } from '../../../stores/appStore'
import { useModStore } from '../../../stores/modStore'
import { useConfirmStore } from '../../../stores/confirmStore'
import { normalizePackageId } from '../../../utils/modIdentity'
import { isOfficialPackageId } from '../../../utils/packageScope'
import { formatDate } from '../../../utils/format'
import { cleanRichText } from '../../../utils/text'

const toast = useToast()
const wsStore = useWorkspaceStore()
const appStore = useAppStore()
const modStore = useModStore()
const confirmStore = useConfirmStore()

// 本地 UI 状态
const newCollectionInput = ref('')

// 计算当前合集的缺失数量
const missingCount = computed(() => wsStore.activeChildrenWithStatus.filter(c => !c.is_installed).length)

// 动态计算列表项的缺失数
const getListMissingCount = (coll) => {
  if (!coll.children) return 0;
  return coll.children.filter(child => {
      const wid = String(child.workshop_id)
      const pid = child.package_id ? String(child.package_id).toLowerCase() : null
      const is_installed =
          wsStore.librariesMods.workshop.some(m => !m.is_missing && String(m.workshop_id) === wid) ||
          wsStore.librariesMods.self.some(m => !m.is_missing && String(m.workshop_id) === wid) ||
          wsStore.librariesMods.local.some(m => !m.is_missing && ((pid && m.package_id?.toLowerCase() === pid) || (m.workshop_id && String(m.workshop_id) === wid)))
      return !is_installed
  }).length;
}

const tooltipFormat = (coll) => {
  const missing = getListMissingCount(coll)
  return `**${coll.title || '未知合集'}**\n\n${cleanRichText(coll.description) || '暂无说明'}\n\n[[共 ${coll.total || 0} 个模组]] | ^^需要下载/订阅: ${missing}^^`
}

// --- 动作：添加与删除合集 ---
const submitAddCollection = async () => {
  const added = await wsStore.addCollection(newCollectionInput.value)
  if (added) {
    newCollectionInput.value = ''
  }
}

const confirmRemove = async (coll) => {
  const ok = await confirmStore.confirmAction("删除记录", `确定要将合集 "${coll.title}" 移出记录吗？\n(这不会删除你已经下载的 Mod 文件)`, { type: 'error' })
  if (ok) {
    wsStore.removeCollection(coll.id)
  }
}

// --- 动作：调用 AppStore 的 Steam 方法 ---

// 1. 订阅全部
const handleSubscribeAll = () => {
  const wids = wsStore.collections.activeChildren.map(m => String(m.workshop_id))
  if (!wids.length) return
  appStore.subscribeWorkshopIds(wids) // 调用 appStore 的统一方法
}
// 2. 取订全部
const handleUnsubscribeAll = () => {
  const wids = wsStore.collections.activeChildren.map(m => String(m.workshop_id))
  if (!wids.length) return
  appStore.unsubscribeWorkshopIds(wids) // 调用 appStore 的统一方法
}


// 2. 仅下载缺失项 (SteamCMD)
const handleDownloadMissing = () => {
  const wids = wsStore.activeChildrenWithStatus.filter(m => (!m.is_workshop && !m.is_self && !m.is_local)).map(m => String(m.workshop_id))
  
  if (!wids.length) {
    toast.info("所有模组均已就绪，无需下载！")
    return
  }
  appStore.downloadWorkshopItems(wids)
}

// 3. 单项操作
const handleSubscribeSingle = (wid) => appStore.subscribeWorkshopIds([String(wid)])
const handleUnsubscribeSingle = (wid) => appStore.unsubscribeWorkshopIds([String(wid)]) // 默认不删除文件
const handleDownloadSingle = (wid) => appStore.downloadWorkshopItems([String(wid)])

// --- 动作：应用加载顺序 ---
const applyAsLoadOrder = async () => {
  if (missingCount.value > 0) {
    const ok = await confirmStore.confirmAction("警示", `当前合集有 ${missingCount.value} 个模组未安装。\n强行应用会导致排序中出现幽灵节点（空项）。强烈建议先下载补齐。\n是否继续强行应用？`, { type: 'warning' })
    if (!ok) return
  }

  const officialIds = modStore.activeIds
    .map(id => normalizePackageId(id))
    .filter(id => id && isOfficialPackageId(id))

  const collectionIds = []
  const seenPackageIds = new Set(officialIds)
  let unresolvedCount = 0
  let duplicateCount = 0

  wsStore.activeChildrenWithStatus.forEach(child => {
    const pid = normalizePackageId(child.package_id)
    if (!pid) {
      unresolvedCount += 1
      return
    }
    if (seenPackageIds.has(pid)) {
      duplicateCount += 1
      return
    }
    seenPackageIds.add(pid)
    collectionIds.push(pid)
  })

  const nextActiveIds = [...officialIds, ...collectionIds]
  if (nextActiveIds.length === 0) {
    toast.error("无法提取包名。可能后端接口未返回 package_id。")
    return
  }
  if (unresolvedCount > 0) {
    toast.warning(`有 ${unresolvedCount} 个合集项无法解析包名，可能是缓存缺失或本地未安装，已跳过这些项。`)
  }
  if (duplicateCount > 0) {
    toast.info(`已跳过 ${duplicateCount} 个重复包名项，避免生成重复加载节点。`)
  }

  await modStore.runListHistoryTransaction({
    type: 'apply-collection-order',
    label: '按合集顺序覆盖启用列表'
  }, async () => {
    modStore.setListIds('active', nextActiveIds)
    modStore.updateInactiveIds()
  })
  toast.success("已按合集顺序覆盖当前启用列表。\n官方 Core/DLC 会按当前启用状态保留，请返回主界面点击【保存】生效。")
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 5px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 4px; border: 1px solid transparent; background-clip: padding-box; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background-color: rgba(var(--rgb-accent-warn),0.5); }
</style>
