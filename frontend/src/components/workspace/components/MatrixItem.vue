<!-- src/components/workspace/components/MatrixItem.vue -->
<template>
  <div class="relative py-1" :data-id="mod.path_hash">
    <!-- 主卡片 -->
    <div ref="itemRef" 
      @contextmenu.prevent="openContextMenu"
      @mouseenter="handleMouseEnter"
      @mouseleave="handleMouseLeave"
      class="matrix-select-trigger flex items-center gap-2 p-1.5 rounded-lg border transition-all cursor-pointer group bg-text-dim/10"
      :class="[
        mod.is_missing ? 'opacity-70 grayscale border-dashed border-accent-danger/50 bg-accent-danger/5 hover:bg-accent-danger/10 hover:border-accent-danger/30' :
        storeType === 'workshop' ? 'border-accent-primary/10 hover:bg-accent-primary/10 hover:border-accent-primary/30' :
        storeType === 'self' ? 'border-accent-success/10 hover:bg-accent-success/10 hover:border-accent-success/30' :
        'border-accent-warn/10 hover:bg-accent-warn/10 hover:border-accent-warn/30', 
        isSelected ? 'border-accent-tip/60 ring-1 ring-accent-tip/90 hover:bg-accent-tip/20 hover:border-accent-tip/90':''
      ]">
      
      <!-- 图标 -->
      <img v-if="mod.preview_path" :src="appStore.getThumbUrl(mod.package_id, mod.preview_path)" class="size-10 rounded object-cover border border-text-main/10 shadow-sm opacity-80 group-hover:opacity-100" />
      <div v-else class="size-10 rounded bg-black/40 border border-text-main/10 flex items-center justify-center">
        <span class="text-[0.6rem] text-text-dim/50 font-bold uppercase">NO IMG</span>
      </div>

      <!-- 信息 -->
      <div class="flex-1 min-w-0">
        <div class="text-xs font-bold text-text-main truncate group-hover:text-white transition-colors">
          {{ mod.name || mod.package_id }}
        </div>
        <div v-if="mod.package_id" title="包名" class="text-[0.65rem] truncate text-text-dim font-mono mt-0.5 opacity-60">
          {{ mod.package_id }}
        </div>
        <div v-if="mod.workshop_id" title="创意工坊ID" class="text-[0.65rem] truncate text-text-dim font-mono mt-0.5 opacity-60">
          {{ mod.workshop_id }}
        </div>
      </div>

      <!-- 右侧时间与大小 -->
      <div class="shrink-0 flex flex-col items-end gap-1 pr-2">
        <span v-if="mod.steam_status?.time_last_sync" class="text-[0.65rem] font-mono" :class="isChange ? 'text-accent-tip font-black' : 'text-text-dim'">
          更新：{{ formatTime(mod.steam_status?.time_last_sync) }}
        </span>
        <span v-else class="text-[0.65rem] font-mono" :class="isNew ? 'text-accent-tip font-black' : 'text-text-dim'">
          修改：{{ formatTime(mod.file_modify_time) }}
        </span>
        <span class="text-[0.65rem] font-mono" :class="isNew ? 'text-accent-primary font-black' : 'text-text-dim'">
          创建：{{ formatTime(mod.file_modify_time) }}
        </span>
        <span class="text-[0.6rem] font-mono text-text-dim opacity-50 bg-black/40 px-1 rounded">
          {{ formatFileSize(mod.file_size) }}
        </span>
      </div>

      <!-- 状态角标 -->
      <div class="absolute top-0 left-1 z-100 scale-90 flex items-center justify-center gap-1">
        <span v-if="isNew" title="新增" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-primary animate-pulse">
          NEW
        </span>
        <span v-if="isChange && !isNew" title="变更" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-tip animate-pulse">
          CHANGE
        </span>
        <span v-if="mod.steam_status?.needs_update || mod.has_update" title="可更新" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-warn animate-pulse">
          UPDATE
        </span>
        <span v-if="mod.disabled" title="已禁用" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-danger animate-pulse">
          DISABLED
        </span>
        <span v-if="!mod.path" title="已删除" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-danger animate-pulse">
          DELETED
        </span>
        <span v-if="mod.is_missing" title="文件缺失" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-black bg-accent-danger animate-pulse">
          MISSING
        </span>
      </div>
    </div>

    <!-- 智能悬浮/弹出层 (Smart Popover) -->
    <Teleport to="body">
      <Transition :name="popoverDirection === 'right' ? 'slide-right' : 'slide-left'">

        <div v-if="showPopover" 
          @mouseenter="clearHideTimer"
          @mouseleave="hidePopover"
          class="fixed z-9999 w-72 bg-bg-deep/95 backdrop-blur-3xl border border-text-main/10 rounded-xl shadow-2xl p-4 flex flex-col gap-3"
          :style="popoverStyle">
          
          <!-- 详细内容区 -->
          <div class="flex items-center gap-3 border-b border-text-main/10 pb-2">
            <component :is="sourceIcon" class="size-5" :class="sourceColor" />
            <div class="min-w-0">
              <div class="text-sm font-black text-text-main truncate">{{ mod.name }}</div>
              <div class="text-xs text-text-dim font-mono">v {{ mod.version || 'Unknown' }}</div>
            </div>
          </div>
          
          <div class="space-y-1.5 text-xs text-text-dim font-mono">
            <div class="flex justify-between"><span class="opacity-60">创建时间:</span> <span>{{ formatTime(mod.file_create_time, true) }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">修改时间:</span> <span>{{ formatTime(mod.file_modify_time, true) }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">上传时间:</span> <span>{{ formatTime(mod.steam_status?.latest_version_time, true) || '无记录' }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">同步时间:</span> <span>{{ formatTime(mod.steam_status?.time_last_sync, true) || '无记录' }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">下载时间:</span> <span>{{ formatTime(mod.steam_status?.time_downloaded, true) || '无记录' }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">订阅时间:</span> <span>{{ formatTime(mod.steam_status?.time_subscribed, true) || '无记录' }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">取订时间:</span> <span>{{ formatTime(mod.steam_status?.time_unsubscribed, true) || '无记录' }}</span></div>
            <div class="flex justify-between"><span class="opacity-60">储存占用:</span> <span>{{ formatFileSize(mod.file_size) }}</span></div>
          </div>

          <div v-if="mod.path" class="mt-2 p-2 bg-black/40 rounded-lg border border-text-main/5 text-[10px] text-text-dim break-all cursor-text select-text">
            {{ mod.path }}
          </div>
          
          <div class="text-[0.65rem] text-text-dim/50 mt-1 italic text-center">右键点击卡片可查看变动时间线与更多操作</div>
        </div>

      </Transition>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Folder, CloudDownload, Disc } from 'lucide-vue-next'
import { formatFileSize } from '../../../utils/uiHelper'
import FixedPopover from '../../common/FixedPopover.vue'
import { useAppStore } from '../../../stores/appStore'

const appStore = useAppStore()

const props = defineProps({
  mod: Object,
  storeType: String,
  lastPlayedTime: Number,
  isSelected: Boolean,
})

const emit = defineEmits(['contextmenu'])

const itemRef = ref(null)
const showPopover = ref(false)
const popoverStyle = ref({})
const popoverDirection = ref('right')
let hideTimer = null
let showTimer = null

// --- 状态计算 ---
const isNew = computed(() => {
  if (!props.lastPlayedTime) return false
  return  props.mod.file_create_time > props.lastPlayedTime
})
const isChange = computed(() => {
  if (!props.lastPlayedTime) return false
  return (props.mod.steam_status?.time_last_sync || props.mod.file_modify_time) > props.lastPlayedTime
})

const sourceIcon = computed(() => {
  if (props.storeType === 'workshop') return CloudDownload
  if (props.storeType === 'self') return Disc
  return Folder
})

const sourceColor = computed(() => {
  if (props.storeType === 'workshop') return 'text-accent-primary'
  if (props.storeType === 'self') return 'text-accent-success'
  return 'text-accent-warn'
})

const formatTime = (ts, full = false) => {
  if (!ts) return 'N/A'
  const d = new Date(ts)
  if (full) return d.toLocaleString()
  const options = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }
  return d.toLocaleDateString('zh-CN', options)
}

// --- 智能悬浮层逻辑 ---
const handleMouseEnter = () => {
  clearHideTimer()
  // 延迟 400ms 弹出，防止鼠标划过时闪烁
  showTimer = setTimeout(() => {
    calculatePosition()
    showPopover.value = true
  }, 400)
}
const handleMouseLeave = () => {
  if (showTimer) clearTimeout(showTimer)
  hideTimer = setTimeout(() => {
    showPopover.value = false
  }, 200) // 给 200ms 时间让鼠标可以移到 popover 上
}
const clearHideTimer = () => {
  if (hideTimer) clearTimeout(hideTimer)
}
const hidePopover = () => {
  handleMouseLeave()
}
const calculatePosition = () => {
  if (!itemRef.value) return
  const rect = itemRef.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const popoverWidth = 288 // 72rem = 288px
  const gap = 16

  // 判断中线，决定左右弹出
  const isLeftSide = rect.left < vw / 2;
  const isBottomHalf = rect.top > vh / 2;

  // 设置弹出层方向
  popoverDirection.value = isLeftSide ? 'right' : 'left';
  // 初始化样式对象
  const baseStyle = {};
  // 根据左右位置设置水平方向
  if (isLeftSide) {
    baseStyle.left = `${rect.right + gap}px`;
  } else {
    baseStyle.right = `${vw - rect.left + gap}px`; // 原逻辑右侧的left赋值是笔误，已修正
  }
  // 根据上下位置设置垂直方向
  if (isBottomHalf) {
    baseStyle.bottom = `${Math.max(20, vh - rect.bottom - 20)}px`;
  } else {
    baseStyle.top = `${Math.max(20, rect.top - 20)}px`;
  }
  // 最终赋值
  popoverStyle.value = baseStyle;

}

// 代理右键事件给父组件
const openContextMenu = (e) => {
  emit('contextmenu', e, props.mod)
  hidePopover() // 打开菜单时隐藏详情
}


</script>

<style scoped>
.slide-right-enter-active, .slide-right-leave-active,
.slide-left-enter-active, .slide-left-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-right-enter-from, .slide-right-leave-to { opacity: 0; transform: translateX(-15px) scale(0.95); }
.slide-left-enter-from, .slide-left-leave-to { opacity: 0; transform: translateX(15px) scale(0.95); }
</style>