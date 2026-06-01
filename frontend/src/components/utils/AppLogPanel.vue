<template>
  <div class="h-full flex flex-col font-mono text-xs selection:bg-accent-primary/30 selection:text-text-main">
    <!-- B. 工具栏：筛选与搜索 -->
      <div class="px-4 py-2 flex items-center gap-3 border-b border-border-base/5">
        
        <!-- 文件选择 -->
        <div class="relative group/file">
          <button class="flex items-center gap-2 px-3 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs text-text-main transition-colors">
            <svg class="w-3.5 h-3.5 text-accent-cool" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <span class="max-w-100 truncate">{{ activeFileName }}</span>
            <svg class="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
          </button>
          <!-- 下拉菜单预留位 -->
        </div>

        <div class="h-4 w-px bg-bg-overlay/10 mx-1"></div>

        <!-- 搜索框 -->
        <div class="flex-1 relative group/search">
          <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-dim group-focus-within/search:text-accent-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input v-model="searchQuery" type="text" placeholder="搜索日志内容 (支持 Regex)..." 
            class="input-glass w-full py-1.5 pl-8 pr-8 font-mono text-xs text-text-main placeholder:text-text-disabled focus:outline-none" />
          <button v-if="searchQuery" @click="searchQuery = ''" class="absolute right-2 top-1/2 -translate-y-1/2 text-text-dim hover:text-text-main">
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- 级别筛选 Checkbox -->
        <div class="flex items-center gap-1 rounded-lg border border-border-base/10 bg-bg-inset/70 p-1">
          <button v-for="option in filterOptions" :key="option.key" class="px-2 py-0.5 rounded text-xs font-bold border transition-all duration-200 select-none"
            :class="filters[option.key] ? [option.color, 'bg-bg-overlay/10 border-border-base/10 shadow-sm'] : 'text-text-dim opacity-50 border-transparent hover:opacity-80'"
            @click="filters[option.key] = !filters[option.key]">
            {{ option.label }}
          </button>
        </div>

        <div class="h-4 w-px bg-bg-overlay/10 mx-1"></div>

        <!-- 自动滚动开关 -->
        <button @click="autoScroll = !autoScroll" 
          class="p-1.5 rounded-lg border transition-all"
          :class="autoScroll ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' : 'bg-transparent text-text-dim border-transparent hover:bg-bg-overlay/5'"
          v-tooltip="'自动滚动到底部'">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>
        </button>

        <!-- 刷新/清空 -->
        <button @click="clearLogs" class="p-1.5 rounded-lg text-text-dim hover:text-accent-danger hover:bg-accent-danger/10 transition-colors" v-tooltip="'清空显示'">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
        </button>

      </div>

      <div class="flex-1 flex flex-col overflow-y-auto" ref="scrollContainer">
        <!-- 空状态 -->
        <div v-if="filteredLogs.length === 0" class="h-full flex flex-col items-center justify-center text-text-disabled pointer-events-none">
          <svg class="w-16 h-16 mb-2 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          <span class="text-sm tracking-widest uppercase">No Logs Found</span>
        </div>

        <!-- 列表渲染 -->
        <template v-else>
          <!-- 虚拟滚动优化 -->
          <div v-for="(log, index) in filteredLogs" :key="log.id || index"
              class="group/row flex gap-2 py-0.5 px-2 hover:bg-bg-overlay/5 rounded-sm border-l-2 border-transparent transition-colors wrap-break-word"
              :class="getLevelBorderClass(log.level)">
            
            <!-- 时间戳 -->
            <span class="shrink-0 text-text-disabled select-none w-15">{{ formatTime(log.timestamp) }}</span>
            
            <!-- 级别标记 -->
            <span class="shrink-0 w-12 font-bold" :class="getLevelColorClass(log.level)">
              {{ log.level }}
            </span>
            <!-- 内容主体 -->
            <div class="flex-1 min-w-0 ">
              <!-- App Log Mode: 结构化展示 -->
              <div class="flex items-baseline gap-2">
                <span class="text-accent-special opacity-80 select-none">[{{ log.module }}]</span>
                <span :class="{'text-text-main': log.level !== 'DEBUG', 'text-text-dim': log.level === 'DEBUG'}">
                  {{ log.message }}
                </span>
              </div>
              <!-- 详情折叠区 (如果有 details) -->
              <div v-if="log.details" class="mt-1 ml-1 rounded border-l border-border-base/10 bg-bg-inset/55 p-1 pl-2 font-mono text-xs whitespace-pre-wrap text-text-dim">
                {{ log.details }}
              </div>
            </div>

          </div>
        </template>

      </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

const appLogs = ref([])
const activeFileName = ref('app.log')
const searchQuery = ref('')
const autoScroll = ref(true)
const scrollContainer = ref(null)

// 过滤器状态
const filters = ref({
  info: true,
  warn: true,
  error: true,
  debug: false
})
const filterOptions = [
  { key: 'info', label: 'INFO', color: 'text-text-main' },
  { key: 'warn', label: 'WARN', color: 'text-accent-warn' },
  { key: 'error', label: 'ERR', color: 'text-accent-danger' },
  { key: 'debug', label: 'DEBUG', color: 'text-accent-cool' },
]

// --- 核心逻辑 ---

// 1. 初始化 & 监听
onMounted(() => {
  // 监听后端 EventBus 推送的 'app-log'
  window.addEventListener('app-log', handleAppLogEntry)
})

onUnmounted(() => {
  window.removeEventListener('app-log', handleAppLogEntry)
})

// 处理后端推送的单条日志
const handleAppLogEntry = (event) => {
  const entry = event.detail
  // 简单的去重（防止热重载重复添加）
  if (appLogs.value.some(l => l.id === entry.id)) return
  
  appLogs.value.push(entry)
  
  // 限制最大条数 (如 2000)，防止前端卡顿
  if (appLogs.value.length > 2000) appLogs.value.shift()
  
  if (autoScroll.value) scrollToBottom()
}

// 2. 筛选逻辑
const filteredLogs = computed(() => {
  const query = searchQuery.value.toLowerCase()
  // 尝试编译正则
  let regex = null
  if (query) {
    try { regex = new RegExp(query, 'i') } catch(e) {}
  }

  return appLogs.value.filter(log => {
    // A. 级别筛选
    const lvl = log.level.toUpperCase()
    if (lvl === 'INFO' && !filters.value.info) return false
    if (lvl === 'WARNING' && !filters.value.warn) return false
    if (lvl === 'ERROR' && !filters.value.error) return false
    if (lvl === 'DEBUG' && !filters.value.debug) return false

    // B. 搜索筛选
    if (query) {
      const content = (log.message + (log.details || '') + (log.module || '')).toLowerCase()
      if (regex) return regex.test(content)
      return content.includes(query)
    }
    
    return true
  })
})

// 3. 统计逻辑
const stats = computed(() => {
  const source = appLogs.value
  return {
    errors: source.filter(l => l.level === 'ERROR').length,
    warnings: source.filter(l => l.level === 'WARNING').length
  }
})

// 4. 滚动逻辑
const scrollToBottom = () => {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

const clearLogs = () => {
  appLogs.value = []
}

const formatTime = (ts) => {
  // 如果是完整时间戳字符串，截取时分秒
  if (typeof ts === 'string' && ts.includes(' ')) return ts.split(' ')[1].split('.')[0]
  return ts
}

const getLevelColorClass = (level) => {
  switch (level) {
    case 'INFO': return 'text-accent-success'
    case 'WARNING': return 'text-accent-warn'
    case 'ERROR': return 'text-accent-danger'
    case 'DEBUG': return 'text-accent-cool'
    default: return 'text-text-dim'
  }
}

const getLevelBorderClass = (level) => {
  switch (level) {
    case 'ERROR': return 'border-accent-danger/50 bg-accent-danger/5'
    case 'WARNING': return 'border-accent-warn/30'
    default: return 'border-transparent'
  }
}

</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 3px; }
</style>
