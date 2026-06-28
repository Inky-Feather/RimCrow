<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-md rounded-2xl overflow-hidden border border-white/10 shadow-2xl relative group">
    
    <!-- ================= 1. 顶部控制台 (Header & Toolbar) ================= -->
    <div class="shrink-0 bg-bg-deep/50 border-b border-white/5 backdrop-blur-xl z-20">
      
      <!-- A. 顶栏：标签页与统计 -->
      <div class="flex items-center justify-between px-4 h-12">
        <!-- 模式切换 Tabs -->
        <div class="flex p-1 bg-black/20 rounded-lg border border-white/5">
          <button v-for="tab in tabs" :key="tab.id" @click="currentTab = tab.id"
            class="px-4 py-1 rounded-md text-xs font-bold transition-all duration-300 flex items-center gap-2 relative overflow-hidden"
            :class="currentTab === tab.id ? 'text-white shadow-lg bg-white/10' : 'text-text-dim hover:text-white hover:bg-white/5'">
            <!-- 激活时的底部光条 -->
            <div v-if="currentTab === tab.id" class="absolute bottom-0 left-0 w-full h-0.5 bg-accent-primary shadow-[0_0_8px_var(--color-accent-primary)]"></div>
            <component :is="tab.icon" class="w-3.5 h-3.5" />
            {{ tab.label }}
          </button>
        </div>

        <!-- 实时统计看板 -->
        <div class="flex items-center gap-4 text-[10px] font-mono select-none">
          <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-accent-danger/10 border border-accent-danger/20 text-accent-danger">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            <span class="font-bold">{{ stats.errors }}</span> ERR
          </div>
          <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-accent-warn/10 border border-accent-warn/20 text-accent-warn">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            <span class="font-bold">{{ stats.warnings }}</span> WARN
          </div>
          <div class="px-2 py-1 text-text-dim opacity-60">
            TOTAL: {{ stats.total }}
          </div>
        </div>
      </div>

    </div>

    <!-- ================= 2. 日志内容区 (Log Stream) ================= -->
    <div class="flex-1 min-h-0 bg-black/20 font-mono text-xs selection:bg-accent-primary/30 selection:text-white">
      
      <KeepAlive>
        <component :is="currentTabComponent" />
      </KeepAlive>
      
      <!-- 底部锚点 -->
      <div id="log-bottom-anchor"></div>
    </div>

    <!-- ================= 3. AI 智能辅助栏 (Footer) ================= -->
    <div class="bg-bg-deep/80 border-t border-white/10 p-3 backdrop-blur-xl z-30">
      <div class="flex items-center gap-2">
        <!-- AI 图标 -->
        <div class="w-8 h-8 rounded-lg bg-linear-to-br from-accent-special to-accent-highlight p-0.5 shadow-lg shadow-accent-special/20 animate-pulse-slow">
          <div class="w-full h-full bg-bg-deep rounded-md flex items-center justify-center">
            <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
        </div>

        <div class="flex-1">
          <h3 class="text-xs font-bold text-white mb-0.5">AI 智能诊断</h3>
          <p class="text-[10px] text-text-dim">
            当前选中 <span class="text-accent-primary font-bold">{{ selectedLogCount }}</span> 条日志。
            <span v-if="selectedLogCount > 0" class="text-accent-success cursor-pointer hover:underline" @click="analyzeLogs">点击开始分析</span>
            <span v-else>请在上方筛选或框选日志以进行分析。</span>
          </p>
        </div>

        <button @click="analyzeLogs" :disabled="selectedLogCount === 0"
          class="px-4 py-2 bg-white/5 hover:bg-accent-special hover:text-white border border-white/10 rounded-lg text-xs font-bold text-text-dim transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
          <span>分析原因</span>
          <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Terminal, Gamepad2 } from 'lucide-vue-next'
import AppLogPanel from './utils/AppLogPanel.vue';
import GameLogPanel from './utils/GameLogPanel.vue';



// --- 状态数据 ---
const currentTab = ref('app') // 'app' | 'game'
const tabs = [
  { id: 'app', label: '系统日志', icon: Terminal },
  { id: 'game', label: '游戏日志', icon: Gamepad2 }
]

const currentTabComponent = computed(() => {
  return currentTab.value === 'app' ? AppLogPanel : GameLogPanel
})

const stats = computed(() => {
  const source = currentTab.value === 'app' ? 'app' : 'game'
  return {
    errors: 0,
    warnings: 0,
    total: 0
  }
})

const selectedLogs = computed(() => {
  const source = currentTab.value === 'app' ? 'app' : 'game'
  return []
})

const selectedLogCount = computed(() => {
  // 这里简化处理：如果没有选区，则视为分析当前过滤后的所有（如果数量不多）或者最后50条
  return selectedLogs.value.length
})

</script>

<style scoped>
/* 呼吸灯动画 */
@keyframes pulse-slow {
  0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 15px rgba(139, 92, 246, 0.3); }
  50% { opacity: 0.8; transform: scale(0.98); box-shadow: 0 0 5px rgba(139, 92, 246, 0.1); }
}
.animate-pulse-slow {
  animation: pulse-slow 3s infinite ease-in-out;
}
</style>