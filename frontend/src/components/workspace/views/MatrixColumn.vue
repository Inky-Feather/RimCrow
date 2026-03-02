<!-- src/components/workspace/views/MatrixColumn.vue -->
<template>
  <div class="flex-1 flex flex-col bg-black/30 border border-text-main/10 rounded-2xl overflow-hidden shadow-2xl relative">
    
    <!-- 1. 看板表头 -->
    <div class="px-4 py-3 bg-text-main/5 border-b border-text-main/10 flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-bold text-text-main flex items-center gap-2 cursor-help" v-tooltip="tooltip">
          <div class="w-2.5 h-2.5 rounded-full shadow-lg" :class="iconColor.replace('text-', 'bg-')"></div>
          {{ title }}
        </h3>
        <div class="flex gap-2">
          <span class="text-[0.65rem] font-mono text-text-dim bg-black/40 px-2 py-0.5 rounded-md border border-text-main/5">
            {{ formatFileSize(workspaceStore.librariesSize[storeType]) }}
          </span>
          <span class="text-[0.65rem] font-mono text-text-main bg-black/40 px-2 py-0.5 rounded-md border border-text-main/5">
            {{ mods.length }} 项
          </span>
        </div>
      </div>

      <!-- 搜索与排序 -->
      <div class="flex flex-col items-center gap-2">
        <div class="relative w-full">
          <input v-model="searchQuery" placeholder="在此域检索..." 
            class="w-full bg-black/60 border border-text-main/10 rounded-lg pl-3 pr-2 py-1.5 text-xs text-text-main focus:border-accent-primary outline-none transition-colors" />
        </div>
        <div class="flex items-center w-full justify-end gap-2">
          <CommonSelect v-model="filterState" mini 
            :options="[
              { label: '显示所有', value: 'default' }, 
              { label: '仅显示已变动', value: 'change' }, 
              { label: '仅显示可更新', value: 'update' }, 
              { label: '仅显示新增', value: 'new' }, 
              { label: '仅显示已禁用', value: 'disabled' }, 
              { label: '仅显示已删除', value: 'deleted' }, 
            ]">
          </CommonSelect>

          <CommonSelect v-model="sortBy" mini 
            :options="[
              { label: '按变动时间', value: 'change' }, 
              { label: '按修改时间', value: 'mtime' }, 
              { label: '按创建时间', value: 'ctime' }, 
              { label: '按文件体积', value: 'size' }, 
              { label: '按名称 A-Z', value: 'name' }
            ]">
          </CommonSelect>
          <!-- 排序切换按钮 -->
          <Motion :class="`p-1 size-7 rounded-md bg-text-dim/10 border border-text-main/10 hover:text-text-main hover:bg-text-dim/20 text-xs font-bold flex items-center justify-center cursor-pointer `"
            :initial="{ rotateX: 0, opacity: 1 }"
            :animate="{ rotateX: isSortDsc ? 0 : 180 /*切换时旋转180度*/}" 
            :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
            @click="isSortDsc=!isSortDsc" v-tooltip="isSortDsc?'切换为升序排列':'切换为降序排列'"
          >
            <span v-if="isSortDsc" class="rotate-x-180">
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
            </span>
            <span v-else>
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
            </span>
          </Motion>
        </div>
      </div>
    </div>

    <!-- 2. 列表区 -->
    <div class="flex-1 overflow-hidden relative p-1">
      <VirtualList 
        v-if="displayMods.length > 0"
        v-model="displayMods" dataKey="path_hash" 
        class="h-full custom-scrollbar pb-10"
        :keeps="40" :sortable="false" group="none" :disabled="true"
      >
        <template v-slot:item="{ record, index, dataKey }">
          <div class="relative group">
            
            <MatrixItem class="timeline-trigger"
              :mod="record"
              :storeType="storeType"
              :lastPlayedTime="lastPlayedTime"
              @contextmenu="handleContextMenu"
              @click="$emit('open-timeline', record)"
            />

          </div>
        </template>
      </VirtualList>

      <div v-else class="absolute inset-0 flex flex-col items-center justify-center text-text-dim/30">
        <svg class="size-12 mb-2 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
        <span class="text-xs font-bold tracking-widest uppercase">库内暂无数据</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import VirtualList from 'vue-virtual-sortable'
import { useAppStore } from '../../../stores/appStore'
import { useContextMenuStore } from '../../../stores/contextMenuStore'
import { formatFileSize } from '../../../utils/uiHelper'
import { useModStore } from '../../../stores/modStore'
import MatrixItem from '../components/MatrixItem.vue'
import { useProfileStore } from '../../../stores/profileStore'
import { useWorkspaceStore } from '../../../stores/workspaceStore'
import CommonSelect from '../../common/input/CommonSelect.vue'
import { Motion } from 'motion-v'
import { Activity, Copy, DownloadCloud, ExternalLink, Flag, FlagOff, FolderDot, FolderInput, Lock, LockOpen, Trash2 } from 'lucide-vue-next'
import { IconSelf, IconSteam } from '../../../utils/constants'
import { useConfirmStore } from '../../../stores/confirmStore'

const props = defineProps({
  title: String,
  iconColor: String,
  storeType: String,
  mods: Array,
  tooltip: String
})

const emit = defineEmits(['open-timeline'])
const appStore = useAppStore()
const profileStore = useProfileStore()
const menuStore = useContextMenuStore()
const modStore = useModStore()
const workspaceStore = useWorkspaceStore()
const confirmStore = useConfirmStore()

const searchQuery = ref('')
const sortBy = ref('change')
const isSortDsc = ref(true)
const filterState = ref('default')


const lastPlayedTime = computed(() => profileStore.currentProfile?.last_played_time || 0)

// 过滤和排序逻辑
const displayMods = computed(() => {
  let list = [...props.mods]
  // 关键词过滤
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(m => 
      (m.name || '').toLowerCase().includes(q) || 
      (m.package_id || '').toLowerCase().includes(q)
    )
  }
  // 状态过滤
  if (filterState.value !== 'default') {
    list = list.filter(m => {
      if (filterState.value === 'change') return isChange(m)
      if (filterState.value === 'update') return m.has_update || m.steam_status?.needs_update
      if (filterState.value === 'new') return isNew(m)
      if (filterState.value === 'disabled') return m.disabled
      if (filterState.value === 'deleted') return !m.path
      return false
    })
  }

  list.sort((a, b) => {
    if (sortBy.value === 'name') return (a.name || '').localeCompare(b.name || '')
    if (sortBy.value === 'size') return (b.file_size || 0) - (a.file_size || 0)
    if (sortBy.value === 'mtime') return (b.file_modify_time || 0) - (a.file_modify_time || 0)
    if (sortBy.value === 'ctime') return (b.file_create_time || 0) - (a.file_create_time || 0)
    if (sortBy.value === 'change') {
      if (props.storeType === 'workshop') return (b.steam_status?.time_last_sync || 0) - (a.steam_status?.time_last_sync || 0)
      else if(props.storeType === 'self') return (b.steam_status?.time_download || 0) - (a.steam_status?.time_download || 0)
      else return (b.file_modify_time || 0) - (a.file_modify_time || 0)
    }
    
    return 0
  })

  return isSortDsc.value ? list : list.reverse()
})


// === 角标逻辑 ===
const isNew = (mod) => {
  if (!mod || !mod.file_create_time) return false
  const lastPlayed = lastPlayedTime.value || 0
  // 如果文件的修改或创建时间大于上次游玩时间
  return mod.file_create_time > lastPlayed
}
const isChange = (mod) => {
  if (!mod ) return false
  const lastPlayed = lastPlayedTime.value || 0
  // 如果文件的修改或创建时间大于上次游玩时间
  return mod.steam_status?.time_last_sync > lastPlayed || mod.file_modify_time > lastPlayed
}

// 辅助方法：给 MatrixItem 传完整的 mod 对象
const getModData = (id) => {
  return props.mods.find(m => m.package_id.toLowerCase() === id.toLowerCase()) || {}
}

// 取消订阅模组
const unsubscribeMod = async (targetMod,delete_file = false) => {
  // 只选择包含workshop_id的项目
  const paths = [targetMod.path];
  const workshop_ids = [targetMod.workshop_id];
  // 遍历数组，同时收集两个字段
  // modStore.selectedMods.forEach(m => {
  //   // 只选择包含 workshop_id 的项目
  //   if (m.workshop_id) {
  //     paths.push(m.path);
  //     workshop_ids.push(m.workshop_id);
  //   }
  // });

  const check = await confirmStore.confirmAction('警告',`确定要取消订阅选中项${delete_file?'并删除文件':''}（${workshop_ids.length} 项）吗？${delete_file?'软件将主动删除Mod文件':'Steam 会自动删除已取消订阅的文件！'}`,{type:'error'})
  if(check) {
    const res = await appStore.unsubscribeMod(workshop_ids)
    if (res && delete_file) {
      appStore.deletePaths(paths)
    }
  }
}

const downloadMod = async (targetMod) => {
  const res = await appStore.downloadWorkshopItems([targetMod.workshop_id])
}


// === 右键菜单 ===
const handleContextMenu = (event, targetMod) => {
  event.preventDefault()
  if (!targetMod) return

  // 菜单
  const menuItems = [
    // { divider: true },
    { label: '查看变动', icon: Activity, action: () => emit('open-timeline', targetMod) },
    { label: '访问网页', disabled: !targetMod.url, icon: ExternalLink, action: () => appStore.openUrl(targetMod.url) },
    { label: '打开文件夹', disabled: !targetMod.path, icon: FolderInput, action: () => appStore.openPath(targetMod.path) },
    { label: '下载/更新到管理器', disabled: !targetMod.workshop_id, icon: DownloadCloud, action: () => downloadMod(targetMod) },
    { label: 'Steam操作', icon: IconSteam, disabled: targetMod.source!=='workshop', children: [
      { label: '访问创意工坊', disabled: targetMod.source!=='workshop', icon: IconSteam, action: () => appStore.openSteamWorkshopUrl(targetMod.url) },
      { label: '订阅模组', disabled: (!targetMod.workshop_id || targetMod.steam_status?.is_subscribed), icon: Flag, action: () => appStore.subscribeMod(targetMod.package_id) },
      { label: '取消订阅', disabled: targetMod.store!=='workshop', icon: FlagOff, level: 'danger', action: () => unsubscribeMod(targetMod) },
      { label: '取订并删除', disabled: targetMod.store!=='workshop', icon: Trash2, level: 'danger', action: () => unsubscribeMod(targetMod,true) },
    ]},
    { label: '复制到', icon: Copy, children: [
      { label: '本地', disabled: targetMod.store=='local', icon: FolderDot, action: () => appStore.openSteamWorkshopUrl(targetMod.url) },
      { label: '创意工坊', disabled: targetMod.store=='workshop', icon: IconSteam, action: () => appStore.subscribeMod(props.item_id) },
      { label: '管理器', disabled: targetMod.store=='self', icon: IconSelf, action: () => unsubscribeMod() },
    ]},
    { label: targetMod.disabled?'解禁':'禁用', disabled: !targetMod.path, icon: targetMod.disabled? LockOpen: Lock, level: targetMod.disabled?'warn':'danger', action: () => modStore.disableMods([targetMod.path_hash],!targetMod.disabled) },
    { label: '删除', disabled: !targetMod.path, icon: Trash2, level: 'danger', action: () => appStore.deletePaths([targetMod.path]) },
  ]
  menuStore.open(event, menuItems)
}




const handleTransfer = async (mod, targetType) => {
  // 复用现有的 localize 逻辑（需要改造后端接收单项或在前端组装）
  // 为了稳定，直接借用 modStore 原有的方法（需要确保该项已被选中）
  modStore.clearSelection()
  modStore.selectMods(mod.package_id)
  if (targetType === 'local') {
    await modStore.localizeSelectedMods()
  }
}
</script>