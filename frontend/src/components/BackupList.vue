<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm border-2 border-white/5 rounded-2xl overflow-hidden shadow-2xl">
    
    <!-- 标题栏 -->
    <div class="px-3 h-8 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-black/10">
      <span :class="`text-xs font-bold text-accent-primary uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-primary shadow-[0_0_8px_var(--color-accent-primary)]`"></div>
        备份
      </span>
      <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-primary`">
        {{ dataCount.total }}
      </span>
    </div>
    <!-- 功能栏 -->
    <div class="px-2 py-1 shadow-xl flex justify-end items-center">
      <!-- <div class="">
        <div class="gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
          <button class="group z-50 h-6 px-3 relative rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center tracking-wide transition-all duration-300 
          text-text-dim/70 bg-accent-primary/1 
          hover:bg-accent-primary/30 hover:text-accent-primary hover:scale-110 active:scale-100
          group-hover:bg-accent-primary/10 group-hover:text-text-dim group-hover:shadow-2xl/20">
            <span class="relative transition duration-300 only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
          <button class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
          text-text-dim/70 bg-accent-primary/1 
          hover:bg-accent-primary/30 hover:text-accent-primary hover:scale-110 active:scale-100
          group-hover:bg-accent-primary/10 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100">
            <span class="relative only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
          <button class="delay-[0.10s] w-0 h-0 px-1 translate-x-6 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
          text-text-dim/70 bg-accent-primary/1 
          hover:bg-accent-primary/30 hover:text-accent-primary hover:scale-110 active:scale-100
          group-hover:bg-accent-primary/10 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100">
            <span class="relative only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
          <button class="delay-[0.15s] w-0 h-0 px-1 translate-x-9 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
          text-text-dim/70 bg-accent-primary/1 
          hover:bg-accent-primary/30 hover:text-accent-primary hover:scale-110 active:scale-100
          group-hover:bg-accent-primary/10 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100">
            <span class="relative only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
        </div>
      </div> -->
      <button @click="loadOrder('0')" v-tooltip="'导入Mod加载序列'" 
        class="rounded-lg hover:bg-white/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" height="18" width="18" viewBox="0 -960 960 960" fill="currentColor"><path d="M240-80q-33 0-56.5-23.5T160-160v-640q0-33 23.5-56.5T240-880h320l240 240v240h-80v-200H520v-200H240v640h360v80H240Zm638 15L760-183v89h-80v-226h226v80h-90l118 118-56 57Zm-638-95v-640 640Z"/></svg>
      </button>
      <button @click="exportOrder()" v-tooltip="'导出Mod加载序列'" 
        class="rounded-lg hover:bg-white/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" height="18" width="18" viewBox="0 -960 960 960" fill="currentColor"><path d="M480-480ZM202-65l-56-57 118-118h-90v-80h226v226h-80v-89L202-65Zm278-15v-80h240v-440H520v-200H240v400h-80v-400q0-33 23.5-56.5T240-880h320l240 240v480q0 33-23.5 56.5T720-80H480Z"/></svg>
      </button>
      <button @click="refresh" v-tooltip="'备份设置'" 
        class="rounded-lg hover:bg-white/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-calendar-cog-icon lucide-calendar-cog"><path d="m15.228 16.852-.923-.383"/><path d="m15.228 19.148-.923.383"/><path d="M16 2v4"/><path d="m16.47 14.305.382.923"/><path d="m16.852 20.772-.383.924"/><path d="m19.148 15.228.383-.923"/><path d="m19.53 21.696-.382-.924"/><path d="m20.772 16.852.924-.383"/><path d="m20.772 19.148.924.383"/><path d="M21 10.592V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/><path d="M3 10h18"/><path d="M8 2v4"/><circle cx="18" cy="18" r="3"/></svg>
      </button>
      <button @click="store.openBackupPath" v-tooltip="'打开备份文件夹'" 
        class="rounded-lg hover:bg-white/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-folder-open-icon lucide-folder-open"><path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>
      </button>
      <button @click="refresh" v-tooltip="'刷新'"
        class="rounded-lg hover:bg-white/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg :class="{'spin-once-reverse': loading}" @animationend.self="loading = false" width="17" height="17" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-rotate-ccw-icon lucide-rotate-ccw"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
      </button>
    </div>

    <!-- 列表内容区 -->
    <div class="flex-1 overflow-y-auto p-2 space-y-4 scrollbar-thin">
      
      <!-- 0. 临时导入 (import) -->
      <section v-if="parsedData.import.length > 0">
        <div class="px-2 mb-2 text-[10px] font-bold text-accent-warn uppercase opacity-80 flex items-center gap-2">
          <span>临时导入</span>
          <div class="h-px flex-1 bg-accent-warn/20"></div>
        </div>
        <div class="space-y-1">
          <BackupItem 
            v-for="item in parsedData.import" 
            :key="item.path"
            :item="item"
            :is-selected="selectedPath === item.path"
            @select="selectItem"
            @load="handleLoad"
            @delete="handleDelete"
          />
        </div>
      </section>

      <!-- 1. 今日备份 (Today) -->
      <section v-if="parsedData.today.length > 0">
        <div class="px-2 mb-2 text-[10px] font-bold text-accent-primary uppercase opacity-80 flex items-center gap-2">
          <span>今日动态</span>
          <div class="h-px flex-1 bg-accent-primary/20"></div>
        </div>
        <div class="space-y-1">
          <BackupItem 
            v-for="item in parsedData.today" 
            :key="item.path"
            :item="item"
            :is-selected="selectedPath === item.path"
            @select="selectItem"
            @load="handleLoad"
            @delete="handleDelete"
          />
        </div>
      </section>

      <!-- 2. 早期归档 (Earlier) -->
      <section v-if="parsedData.earlier.length > 0">
        <div class="px-2 mt-4 mb-2 text-[10px] font-bold text-text-dim uppercase opacity-60 flex items-center gap-2">
          <span>历史归档</span>
          <div class="h-px flex-1 bg-white/5"></div>
        </div>
        <div class="space-y-1">
          <BackupItem 
            v-for="item in parsedData.earlier" 
            :key="item.path"
            :item="item"
            :is-selected="selectedPath === item.path"
            @select="selectItem"
            @load="handleLoad"
            @delete="handleDelete"
          />
        </div>
      </section>

      <!-- 3. 其他备份 (Other) -->
      <section v-if="parsedData.other.length > 0">
        <div class="px-2 mt-4 mb-2 text-[10px] font-bold text-text-dim uppercase opacity-60 flex items-center gap-2">
          <span>手动备份</span>
          <div class="h-px flex-1 bg-white/5"></div>
        </div>
        <div class="space-y-1">
          <BackupItem 
            v-for="item in parsedData.other" 
            :key="item.path"
            :item="item"
            :is-selected="selectedPath === item.path"
            @select="selectItem"
            @load="handleLoad"
            @delete="handleDelete"
          />
        </div>
      </section>

      <!-- 空状态 -->
      <div v-if="isEmpty" class="flex flex-col items-center justify-center h-40 text-text-dim/40">
        <svg class="w-12 h-12 mb-2 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        <span class="text-xs">暂无备份记录</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useModStore } from '../stores/modStore'
import { parse, formatDistanceToNow, differenceInCalendarDays, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'

// --- 子组件：BackupItem ---
const BackupItem = {
  props: ['item', 'isSelected'],
  emits: ['select', 'load', 'delete', 'exportOrder'],
  template: `
    <div 
      class="relative flex items-center py-1 px-2 rounded-lg border transition-all duration-200 cursor-pointer select-none"
      :class="[isSelected ? 'bg-accent-primary/10 border-accent-primary/30 shadow-[inset_0_0_10px_rgba(var(--color-accent-rgb),0.1)]' 
          : 'bg-white/[0.02] border-white/5 hover:bg-white/5 hover:border-white/10'
      ]"
      @click="$emit('select', item)"
    >
      

      <!-- 中间信息 -->
      <div class="flex-1 min-w-0 flex flex-col justify-center">
        <!-- 距离时间/文件名 -->
        
        <div class="flex items-center gap-2">
            <!-- 左侧图标 -->
            <div v-if="!item.displayTitle" class="rounded-md px-1 py-0.5 w-17 flex items-center justify-center transition-colors text-[10px] gap-0.5"
                :class="isSelected ? 'bg-accent-primary/30 text-accent-primary' : 'bg-accent-primary/20 text-text-dim group-hover:text-white'">
                <svg v-if="item.type === 'today'" class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                <svg v-else-if="item.type === 'earlier'" class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"></path></svg>
                <svg v-else class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                <span>{{ item.distanceNow }}</span>
            </div>
            <!-- 具体时间 -->
            <div class="flex-1 text-[10px] text-text-dim truncate font-mono mt-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
              <span v-if="item.displayTitle" v-tooltip="item.displayTitle" class="text-xs font-medium truncate flex items-center gap-1" :class="isSelected ? 'text-white' : 'text-text-main'">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                {{ item.displayTitle }}
              </span>
              <span v-else>{{ item.displayTime }}</span>
            </div>
        </div>
      </div>

      <!-- 右侧操作 (Hover显示) -->
      <div class="relative w-6 h-6 flex items-center justify-center">
        <div class="absolute -right-2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
          <button @click.stop="$emit('load', item)" class="group z-50 h-6 px-3 relative rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-primary/10 
            hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100 
            group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
            v-tooltip="'加载文件'">
            <span class="relative transition duration-300 only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
          <button @click.stop="$emit('delete', item)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-danger/10 
            hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
            group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100"
            v-tooltip="'删除文件'">
            <span class="relative only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash2-icon lucide-trash-2"><path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </span>
          </button>
          <!--<button @click.stop="$emit('exportOrder', item)" class="delay-[0.10s] w-0 h-0 px-1 translate-x-6 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-primary/10 
            hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100
            group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100"
            v-tooltip="'另存为'">
            <span class="relative only:-mx-6">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-restore-icon lucide-archive-restore"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>-->
        </div>
      </div>

    </div>
  `
}

const store = useModStore()
const loading = ref(false)
const selectedPath = computed(() => store.currentBackupFile)

// 原始数据
const rawData = ref({ today: [], earlier: [], other: [], import: [] })

// 数据长度统计
const dataCount = computed(() => {
    return {
        today: rawData.value.today.length,
        earlier: rawData.value.earlier.length,
        other: rawData.value.other.length,
        auto: rawData.value.today.length + rawData.value.earlier.length,
        total: rawData.value.today.length + rawData.value.earlier.length + rawData.value.other.length
    }
})

// 辅助：从文件名解析时间
// 格式: ModsConfig_YYYYMMDD_HHMMSS.xml
const parseFileTime = (filename) => {
    const match = filename.match(/ModsConfig_(\d{8})_(\d{6})\.xml/)
    if (match) {
        return parse(`${match[1]}${match[2]}`, 'yyyyMMddHHmmss', new Date())
    }
    return null
}

// 核心：处理数据并生成显示文本
const parsedData = computed(() => {
    const process = (files, type) => {
        return files.map(file => { // file 是 path string
            const name = file.split(/[/\\]/).pop()
            const time = parseFileTime(name)
            
            let displayTitle = ''
            let displayTime = '未知时间'
            let distanceNow = '未知时间'

            if (time) {
                const now = new Date()
                // 生成 displayTime (具体时间)
                displayTime = time.toLocaleString('zh-CN', { 
                    year: 'numeric', month: '2-digit', day: '2-digit', 
                    hour: '2-digit', minute: '2-digit', second: '2-digit' 
                })

                // 生成 displayTitle (相对时间)
                if (type === 'today') {
                    // Today: 刚刚, xx分钟前, xx小时前
                    distanceNow = formatDistanceToNow(time, { locale: zhCN, addSuffix: true })
                        .replace('大约 ', '')
                } else if (type === 'earlier') {
                    // Earlier: 昨天, 前天, xx天前
                    const diffDays = differenceInCalendarDays(now, time)
                    if (diffDays === 1) distanceNow = '昨天'
                    else if (diffDays === 2) distanceNow = '前天'
                    else distanceNow = `${diffDays} 天前`
                }
            } else {
                // 如果是 other 或无法解析时间，直接显示文件名去后缀
                displayTitle = name.replace('.xml', '')
            }

            return {
                path: file,
                name: name,
                type: type,
                time: time, // Date object or null
                distanceNow,
                displayTitle,
                displayTime
            }
        }).sort((a, b) => {
            // 按时间倒序
            if (a.time && b.time) return b.time - a.time
            return a.name.localeCompare(b.name)
        })
    }

    return {
        today: process(rawData.value.today || [], 'today'),
        earlier: process(rawData.value.earlier || [], 'earlier'),
        other: process(rawData.value.other || [], 'other'),
        import: process(rawData.value.import || [], 'import')
    }
})

const isEmpty = computed(() => {
    return parsedData.value.today.length === 0 && 
           parsedData.value.earlier.length === 0 && 
           parsedData.value.other.length === 0 && 
           parsedData.value.import.length === 0
})

// --- Actions ---

const refresh = async () => {
    loading.value = true
    try {
        await store.getBackups()
        // 从 store 同步数据 (假设 store.backups 结构是 {today:[], ...})
        if (store.backups) {
            Object.assign(rawData.value, store.backups)
        }
    } finally {
        // loading.value = false
    }
}

const selectItem = async (item) => {
    // selectedPath.value = item.path
    await store.getBackupOrder(item.path)
    store.showDiffDrawer = true
}

const handleLoad = async (item) => {
  if (!confirm(`确定要将配置恢复到 [${item.displayTitle}] 的状态吗？\n当前未保存的更改将丢失。`)) return
  await store.getLoadOrder(item.path)
}

const handleDelete = async (item) => {
    if (!confirm(`确定要删除此备份文件吗？`)) return
    // 调用后端删除接口
    await store.deletePath(item.path)
    refresh()
}

const exportOrder = async (path) => {
    // 调用后端另存为接口
    await store.exportLoadOrder(path)
    refresh()
}

const loadOrder = async (path) => {
    // 调用后端加载接口
    const data = await store.getFileOrder(path)
    if (data.file) {
      rawData.value.import.push(data.file)
      await store.getBackupOrder(data.file)
      store.showDiffDrawer = true
    }
    refresh()
}

onMounted(() => {
    refresh()
})
</script>

<style scoped>
.spin-once-reverse {
  animation: spin-reverse 0.8s linear 1; /* 1表示只执行1次，0.8s旋转速度，可改 */
}
@keyframes spin-reverse {
  from { transform: rotate(0deg); }
  to { transform: rotate(-360deg); } /* 逆时针一圈 */
}
</style>