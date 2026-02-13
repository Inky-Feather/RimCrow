<template>
  <div class="flex flex-col h-full w-full bg-black/20">
    
    <!-- 1. 功能栏 -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-text-main/5 bg-text-main/2">
      <!-- 左侧：文件与刷新 -->
      <div class="flex items-center gap-2">
        <!-- 游戏日志文件选择器 (仅游戏模式显示) -->
        <div class="flex items-center gap-2">
          <div class="relative group/file z-30">
            <button class="flex items-center gap-2 px-3 py-1 bg-black/30 hover:bg-text-main/5 border border-text-main/10 rounded-lg text-sm text-accent-cool transition-colors min-w-40 justify-between">
              <span class="truncate">{{ selectedFile || '选择文件...' }}</span>
              <svg class="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <!-- 下拉菜单 -->
            <div class="absolute left-0 top-full mt-1 w-64 bg-bg-deep/95 border border-text-main/10 rounded-lg shadow-2xl backdrop-blur-xl opacity-0 invisible group-hover/file:opacity-100 group-hover/file:visible transition-all duration-200 transform origin-top-right">
              <div v-for="file in files" :key="file.name" 
                   @click="loadFile(file.name)"
                   class="px-3 py-2 hover:bg-text-main/10 cursor-pointer flex items-center justify-between group/item">
                <div class="flex flex-col min-w-0">
                  <span class="text-sm text-text-main font-mono truncate">{{ file.name }}</span>
                  <span class="text-xs text-text-dim">{{ file.mtime }}</span>
                </div>
                <span class="text-xs text-accent-primary bg-accent-primary/10 px-1 rounded">{{ formatBytes(file.size) }}</span>
              </div>
              <div class="border-t border-text-main/10 p-1">
                <button @click="openLogFolder" class="w-full text-center text-xs text-text-dim hover:text-text-main py-1 hover:bg-text-main/5 rounded">打开所在文件夹</button>
              </div>
            </div>
          </div>
        </div>
        
        <button @click="loadFile(selectedFile)" class="p-1.5 hover:bg-text-main/10 rounded text-text-dim hover:text-text-main" title="刷新">
          <svg class="w-3.5 h-3.5" :class="{'animate-spin': loading}" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
        </button>
      </div>

      <!-- 中间：筛选器 -->
      <div class="flex items-center gap-1 bg-black/20 p-0.5 rounded border border-text-main/5">
        <button v-for="lvl in ['INFO','WARNING','ERROR']" :key="lvl"
          @click="filters[lvl] = !filters[lvl]"
          class="px-2 py-0.5 text-xs font-bold rounded transition-all"
          :class="filters[lvl] ? getBtnColor(lvl) : 'text-text-dim opacity-50'">
          {{ lvl }}
        </button>
      </div>

      
    </div>

    <!-- 2. 内容区 (虚拟滚动) -->
    <div class="flex-1 relative min-h-0 bg-[#111]">
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center z-10 bg-black/50 backdrop-blur-sm">
        <span class="text-accent-primary font-mono text-sm">Loading...</span>
      </div>

      <DynamicScroller
        v-if="filteredLogs.length"
        :items="filteredLogs"
        :min-item-size="30"
        class="h-full custom-scrollbar px-2 pt-2"
        key-field="id"
        v-slot="{ item, index, active }"
      >
        <DynamicScrollerItem :item="item" :active="active" :data-index="index">
          <div class="flex gap-2 group/row rounded-sm border-l-2 transition-colors select-text text-sm font-mono wrap-break-word leading-relaxed hover:bg-text-main/5"
               :class="[
                 item.level === 'ERROR' ? 'border-accent-danger/50 bg-accent-danger/5' : 
                 item.level === 'WARNING' ? 'border-accent-warn/30' : 'border-transparent'
               ]"
               @contextmenu.prevent="handleContextMenu($event, item)">
            
            <!-- 1. 行号 -->
            <div class="shrink-0 w-10 flex items-center justify-end text-right text-text-dim/30 select-none pt-0.5">
               <span >{{ index + 1 }}</span>
            </div>

            <!-- 2. 内容主体 -->
            <div class="flex-1 min-w-0 py-0.5 pr-2">
              

              <!-- 标题行 (支持 Unity Rich Text) -->
              <div class="whitespace-pre-wrap" v-html="renderLogText(item.text.split('\n')[0])"></div>

              <!-- 堆栈/详情 (折叠区域) -->
              <div v-if="item.has_stack || item.details" class="mt-1">
                <!-- 展开按钮 -->
                <button @click="item._expanded = !item._expanded" 
                  class="flex items-center gap-1 text-xs text-text-dim hover:text-text-main transition-colors select-none mb-1">
                  <svg class="w-3 h-3 transition-transform duration-200" :class="item._expanded ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
                  <span>{{ item._expanded ? '收起详情' : '展开详情' }}</span>
                  <span class="opacity-50 ml-1 text-[0.7rem]">(StackTrace)</span>
                </button>

                <!-- 展开的内容 -->
                <div v-if="item._expanded && item.has_stack" 
                     class="pl-2 border-l border-text-main/10 text-text-dim/70 text-[0.8rem] bg-black/30 rounded p-2 overflow-x-auto">
                   <!-- 游戏日志堆栈 -->
                   <!-- <template >
                      <div v-for="(line, i) in getStackLines(item)" :key="i" class="whitespace-pre hover:text-text-main/90">
                        
                      </div>
                   </template> -->
                   {{ item.text.substring(item.text.indexOf('\n') + 1) }}
                </div>
              </div>

            </div>
            
              <!-- 计数徽章 (折叠重复项) -->
              <div v-if="item.count > 1" class="shrink-0 pt-0.5 mr-1">
                <span class="bg-text-main/10 text-text-main text-[0.7rem] font-bold px-1.5 py-0.5 rounded-full font-mono">
                  x{{ item.count }}
                </span>
              </div>
          </div>
        </DynamicScrollerItem>
      </DynamicScroller>

      <!-- 空状态 -->
      <div v-else-if="!loading" class="h-full flex items-center justify-center text-text-dim/30">
        No logs found.
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'vue-toastification'
import { parseUnityRichText } from '../../utils/unityTextParser'
import { useContextMenuStore } from '../../stores/contextMenuStore'
import { useAppStore } from '../../stores/appStore'

const appStroe = useAppStore()
const menuStore = useContextMenuStore()
const toast = useToast()
const files = ref([])
const selectedFile = ref('')
const logs = ref([])
const loading = ref(false)
const filters = ref({ INFO: true, WARNING: true, ERROR: true })

const filteredLogs = computed(() => {
  return logs.value.filter(l => filters.value[l.level])
})

const init = async () => {
  if (!window.pywebview) return
  const res = await window.pywebview.api.get_game_log_files()
  if (appStroe.checkResult(res, '获取游戏日志文件列表')) {
    files.value = res.data
    if (files.value.length > 0) {
      selectedFile.value = files.value[0].name
      loadFile(selectedFile.value)
    }
  }
}

const loadFile = async (filename) => {
  if (!filename || !window.pywebview) return
  loading.value = true
  selectedFile.value = filename
  try {
    const res = await window.pywebview.api.read_game_log(filename)
    if (appS) {
      // 后端已经做好了去重和分块，直接使用
      logs.value = res.data.blocks.map(b => ({
        ...b,
        _expanded: false
      }))
      if (res.data.is_truncated) toast.warning('日志过大，仅显示最后 10MB')
    } else {
      toast.error(res.message)
    }
  } finally {
    loading.value = false
  }
}
const formatBytes = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
const openLogFolder = () => {
  if (window.pywebview) window.pywebview.api.open_log_folder()
}

const analyzeLogs = () => {
  // AI 逻辑
  toast.info('正在提取上下文并发送给 AI...')
}

// 样式辅助
const formatSize = (bytes) => (bytes / 1024 / 1024).toFixed(2) + ' MB'

// 解析 Unity 富文本 (支持颜色、字体大小)
const renderLogText = (text) => {
    // 颜色 (Hex 或 英文名)
  const coloredText = text.replace(/<color="?(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)"?>/gi, '<span style="color:$1">')
    .replace(/<\/color>/gi, '</span>')
    // 字体大小
    .replace(/<size=(\d+)>/gi, '<span style="font-size:$1px">')
    .replace(/<\/size>/gi, '</span>')
  return coloredText
}

const getBtnColor = (lvl) => {
  if (lvl === 'INFO') return 'bg-accent-success/20 text-accent-success border-accent-success/30'
  if (lvl === 'WARNING') return 'bg-accent-warn/20 text-accent-warn border-accent-warn/30'
  return 'bg-accent-danger/20 text-accent-danger border-accent-danger/30'
}

const getBorderClass = (lvl) => {
  if (lvl === 'ERROR') return 'border-accent-danger'
  if (lvl === 'WARNING') return 'border-accent-warn'
  return 'border-transparent' // INFO 无边框或透明
}

// 上下文菜单
const handleContextMenu = (event, item) => {
  const textToCopy = item._fullText
  
  menuStore.open(event, [
    { label: '复制内容', action: () => navigator.clipboard.writeText(textToCopy) },
    { divider: true },
    { 
      label: 'AI 分析此条目', 
      icon: 'sparkles', // 假设 ContextMenu 支持图标名
      action: () => {}
    }
  ])
}

onMounted(init)
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 8px; }
.custom-scrollbar::-webkit-scrollbar-track { background: #111; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #444; }
</style>