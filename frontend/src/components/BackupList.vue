<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm border-2 border-text-main/5 rounded-2xl overflow-hidden shadow-2xl">
    
    <!-- 标题栏 -->
    <div class="px-3 h-8 border-b rounded-t-2xl border-text-main/5 flex justify-between items-center bg-black/10">
      <span :class="`text-sm font-bold text-accent-primary uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-primary shadow-[0_0_8px_var(--color-accent-primary)]`"></div>
        备份
      </span>
      <span :class="`text-xs bg-black/30 px-2 py-0.5 rounded text-accent-primary`">
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
      <HelpCircle v-tooltip="backupRulesTooltip" class="size-5 m-1 text-text-dim transition-colors duration-200 cursor-help hover:text-accent-primary"></HelpCircle>
      <button @click="loadOrder('0')" v-tooltip="'导入Mod加载序列'" 
        class="rounded-lg hover:bg-text-main/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg class="size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>
      </button>
      <button @click="exportOrder()" v-tooltip="'导出Mod加载序列'" 
        class="rounded-lg hover:bg-text-main/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg class="size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M11 14h10"/><path d="M16 4h2a2 2 0 0 1 2 2v1.344"/><path d="m17 18 4-4-4-4"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 1.793-1.113"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>
      </button>
      <!-- <button @click="refresh" v-tooltip="'备份设置'" 
        class="rounded-lg hover:bg-text-main/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg class="size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m15.228 16.852-.923-.383"/><path d="m15.228 19.148-.923.383"/><path d="M16 2v4"/><path d="m16.47 14.305.382.923"/><path d="m16.852 20.772-.383.924"/><path d="m19.148 15.228.383-.923"/><path d="m19.53 21.696-.382-.924"/><path d="m20.772 16.852.924-.383"/><path d="m20.772 19.148.924.383"/><path d="M21 10.592V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/><path d="M3 10h18"/><path d="M8 2v4"/><circle cx="18" cy="18" r="3"/></svg>
      </button> -->
      <button @click="orderStore.openBackupPath" v-tooltip="'打开备份文件夹'" 
        class="rounded-lg hover:bg-text-main/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg class="size-5"  xmlns="http://www.w3.org/2000/svg"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>
      </button>
      <button @click="refresh" v-tooltip="'刷新'"
        class="rounded-lg hover:bg-text-main/5 size-7 text-text-dim transition-colors cursor-pointer flex items-center justify-center">
        <svg :class="{'spin-once-reverse': loading}" @animationend.self="loading = false" class="size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
      </button>
    </div>

    <!-- 列表内容区 -->
    <div class="flex-1 overflow-y-auto p-2 space-y-4 scrollbar-thin">
      
      <!-- 0. 临时导入 (import) -->
      <section v-if="parsedData.import.length > 0">
        <div class="px-2 mb-2 text-xs font-bold text-accent-warn uppercase opacity-80 flex items-center gap-2">
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
            @remove="handleRemove"
          />
        </div>
      </section>

      <!-- 1. 今日备份 (Today) -->
      <section v-if="parsedData.today.length > 0">
        <div class="px-2 mb-2 text-xs font-bold text-accent-primary uppercase opacity-80 flex items-center gap-2">
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
        <div class="px-2 mt-4 mb-2 text-xs font-bold text-text-dim uppercase opacity-60 flex items-center gap-2">
          <span>历史归档</span>
          <div class="h-px flex-1 bg-text-main/5"></div>
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
        <div class="px-2 mt-4 mb-2 text-xs font-bold text-text-dim uppercase opacity-60 flex items-center gap-2">
          <span>手动备份</span>
          <div class="h-px flex-1 bg-text-main/5"></div>
        </div>
        <div class="space-y-1">
          <BackupItem v-for="item in parsedData.other" 
            :key="item.path" :item="item"
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
        <span class="text-sm">暂无备份记录</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useOrderStore } from '../stores/orderStore'
import { useAppStore } from '../stores/appStore'
import { useConfirmStore } from '../stores/confirmStore'
import { parse, formatDistanceToNow, differenceInCalendarDays, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { HelpCircle } from 'lucide-vue-next'

// --- 子组件：BackupItem ---
const BackupItem = {
  props: ['item', 'isSelected'],
  emits: ['select', 'load', 'delete', 'remove', 'exportOrder'],
  template: `
    <div class="relative flex items-center py-1 px-2 rounded-lg border transition-all duration-200 cursor-pointer select-none"
      :class="[isSelected ? 'bg-accent-primary/10 border-accent-primary/30 shadow-[inset_0_0_10px_rgba(var(--color-accent-rgb),0.1)]' : 'bg-text-main/[0.02] border-text-main/5 hover:bg-text-main/5 hover:border-text-main/10' ]"
      @click="$emit('select', item)">
      <!-- 中间信息 -->
      <div class="flex-1 min-w-0 flex flex-col justify-center">
        <!-- 距离时间/文件名 -->
        
        <div class="flex items-center gap-2">
          <!-- 左侧图标 -->
          <div v-if="!item.displayTitle" class="rounded-md px-1 py-0.5 w-17 flex items-center justify-center transition-colors text-[0.6rem] gap-0.5"
            :class="isSelected ? 'bg-accent-primary/30 text-accent-primary' : 'bg-accent-primary/20 text-text-dim group-hover:text-text-main'">
            <svg v-if="item.type === 'today'" class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <svg v-else-if="item.type === 'earlier'" class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/><path d="M16 18h.01"/></svg>
            <svg v-else class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
            <span>{{ item.distanceNow }}</span>
          </div>
          <!-- 具体时间 -->
          <div class="flex-1 text-[0.8rem] text-text-dim truncate font-mono mt-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
            <span v-if="item.displayTitle" v-tooltip="item.displayTitle" class="text-sm font-medium truncate flex items-center gap-1" :class="isSelected ? 'text-text-main' : 'text-text-main'">
              <svg class="w-3 h-3 min-w-4 min-h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
              {{ item.displayTitle }}
            </span>
            <span >{{ item.displayTime }}</span>
          </div>
        </div>
      </div>

      <!-- 右侧操作 (Hover显示) -->
      <div class="relative w-6 h-6 flex items-center justify-center">
        <div class="absolute -right-2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
          <button @click.stop="$emit('load',$event, item)" class="group z-50 h-6 px-3 relative rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-primary/10 
            hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100 
            group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
            v-tooltip="'加载文件'">
            <span class="relative transition duration-300 only:-mx-6">
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>
          <button v-if="item.type === 'import'" @click.stop="$emit('remove', item)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-danger/10 
            hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
            group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100"
            v-tooltip="'从列表移除'">
            <span class="relative only:-mx-6">
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
            </span>
          </button>
          <button v-else @click.stop="$emit('delete', $event, item)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
            inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
            text-text-dim/70 bg-accent-danger/10 
            hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
            group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
            group-hover:h-6 group-hover:w-6 group-hover:translate-x-0 group-hover:opacity-100"
            v-tooltip="'删除文件'">
            <span class="relative only:-mx-6">
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
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
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/></svg>
            </span>
          </button>-->
        </div>
      </div>

    </div>
  `
}

const appStore = useAppStore()
const orderStore = useOrderStore()
const confirmStore = useConfirmStore()
const loading = ref(false)
const selectedPath = computed(() => orderStore.currentBackupFile)

// 原始数据
const rawData = ref({ today: [], earlier: [], other: [], import: [] })

// 监听备份列表变化，更新原始数据
watch(() => orderStore.backups, (newVal) => {
    Object.assign(rawData.value, newVal)
})
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

// 备份规则说明
const backupRulesTooltip = computed(() => {
    return `**[[自动备份与手动备份说明：]]**
^^短期备份：^^每次保存或运行操作后，系统会自动备份当前配置文件(有变动才会备份)。短期备份默认保留 1 天，过期自动删除（每次启动时清理），仅保留最近一个作为当天的备份，归入长期备份。
^^长期备份：^^默认保留最近 30 天的自动长期备份，过期将会删除。
^^手动备份：^^用户可手动触发备份，文件将保存至指定目录，不会被自动删除。
__备份文件格式：ModsConfig_YYYYMMDD_HHMMSS.xml__`
})

// 核心：处理数据并生成显示文本
const parsedData = computed(() => {
  const process = (files, type) => {
    return files.map(file => { // file 是 path string
      const name = file.path.split(/[/\\]/).pop()
      const time = parseFileTime(name) || new Date(file.modify_time) || null
      
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
          distanceNow = formatDistanceToNow(time, { locale: zhCN, addSuffix: true }).replace('大约 ', '')
        } else if (type === 'earlier') {
          // Earlier: 昨天, 前天, xx天前
          const diffDays = differenceInCalendarDays(now, time)
          if (diffDays === 1) distanceNow = '昨天'
          else if (diffDays === 2) distanceNow = '前天'
          else distanceNow = `${diffDays} 天前`
        } else {
          // Other: 直接显示文件名去后缀
          displayTitle = name.replace('.xml', '')
        }
      } else {
        // 如果是 other 或无法解析时间，直接显示文件名去后缀
        displayTitle = name.replace('.xml', '')
      }

      return {
        path: file.path,
        name: name,
        type: type,
        time: time,
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
// 检查所有备份列表是否为空
const isEmpty = computed(() => {
  return parsedData.value.today.length === 0 && 
          parsedData.value.earlier.length === 0 && 
          parsedData.value.other.length === 0 && 
          parsedData.value.import.length === 0
})

// 刷新备份列表
const refresh = async () => {
  loading.value = true
  await orderStore.getBackups()
}
// 选择备份项
const selectItem = async (item) => {
  // selectedPath.value = item.path
  await orderStore.getBackupOrder(item.path)
  appStore.uiState.showDiffDrawer = true
}
// 从备份列表加载
const handleLoad = async (e, item) => {
  const confirmed = await confirmStore.open({
    title: '加载确认',
    message: `确定要恢复到此备份文件的状态吗？\n当前未保存的更改将丢失。`,
    mode: 'confirm',
    type: 'warning'
  }, e.target)
  if (!confirmed) return
  await orderStore.getLoadOrder(item.path)
}
// 删除备份文件
const handleDelete = async (e, item) => {
  const confirmed = await confirmStore.open({
    title: '删除确认',
    message: '确定要删除此备份文件吗？',
    mode: 'confirm',
    type: 'error'
  }, e.target)
  if (!confirmed) return
  // 调用后端删除接口
  await orderStore.deletePath(item.path)
  refresh()
}
// 从导入列表移除
const handleRemove = async (item) => {
  // 调用后端删除接口
  rawData.value.import = rawData.value.import.filter(i => i.path !== item.path)
  if (orderStore.currentBackupFile == item.path) {
    orderStore.currentBackupFile = ''
    orderStore.backupIds = []
  }
  refresh()
}
// 导出当前加载顺序
const exportOrder = async (path) => {
  // 调用后端另存为接口
  await orderStore.exportLoadOrder(path)
  refresh()
}
// 从导入列表加载
const loadOrder = async (path) => {
  // 调用后端加载接口
  const data = await orderStore.getBackupOrder(path)
  if (data) {
    // console.log(data)
    rawData.value.import.push(data)
    appStore.uiState.showDiffDrawer = true
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