<!-- src/components/workspace/WorkspaceOverlay.vue -->
<template>
  <Teleport to="body">
    <Transition name="workspace-zoom">
      <div v-if="appStore.uiState.showWorkspace" 
        class="fixed inset-0 z-200 flex flex-col bg-bg-deep/95 backdrop-blur-2xl overflow-hidden font-sans text-text-main">
        
        <!-- 1. 顶部全局导航栏 (Glowing Segmented Control) -->
        <header class="relative h-16 shrink-0 flex items-center justify-between px-8 border-b border-text-main/10 bg-black/20 z-20">
          <!-- 左侧：返回按钮 -->
          <button @click="appStore.uiState.showWorkspace = false" v-tooltip="'返回主界面 (Esc)'"
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-text-dim hover:text-text-main hover:bg-text-main/10 transition-all cursor-pointer">
            <svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            <span class="font-bold tracking-wider text-sm">主界面</span>
          </button>

          <!-- 中间：水平发光标签页 -->
          <div class="absolute left-1/2 -translate-x-1/2 flex items-center bg-black/40 p-1 rounded-xl border border-text-main/10 shadow-inner" data-tour="workspace-tabs">
            <button v-for="tab in tabs" :key="tab.id" :data-tour="`workspace-tab-${tab.id}`" @click="currentTab = tab.id"
              class="relative px-3 py-1.5 text-sm font-bold rounded-lg transition-all duration-300 z-10"
              :class="currentTab === tab.id ? 'text-text-main text-shadow-md' : 'text-text-dim hover:text-text-main/80'">
              
              <div class="flex items-center gap-2 ">
                <component :is="tab.icon" class="size-4" />
                {{ tab.label }}
              </div>
              
              <!-- 激活时的背景滑块与发光 -->
              <div v-if="currentTab === tab.id" class="absolute inset-0 bg-text-main/10 rounded-lg -z-10 shadow-[0_0_15px_rgba(255,255,255,0.05)] border border-text-main/20"></div>
              <!-- 底部指示灯 -->
              <div v-if="currentTab === tab.id" class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 z-100 w-20 h-1 rounded-b-md" :class="tab.colorClass"></div>
            </button>
          </div>

          <!-- 右侧：全局统计或操作 -->
          <div class="flex items-center gap-4 text-xs font-mono text-text-dim">
            <div class="flex items-center gap-2" v-tooltip="'基于上次启动时间，检测出新变化'">
              <span class="relative flex h-2 w-2">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-special opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-accent-special"></span>
              </span>
              <span>同步就绪</span>
            </div>
          </div>
        </header>

        <!-- 2. 背景装饰光效 (根据 Tab 变色) -->
        <div class="absolute inset-0 pointer-events-none overflow-hidden z-0 transition-colors duration-700" :class="activeBgGlow"></div>

        <!-- 3. 主视图容器 -->
        <main class="flex-1 relative z-10 overflow-hidden">
          <Transition name="fade" mode="out-in">
            <!-- 使用 KeepAlive 保持各页面的状态 -->
            <KeepAlive>
              <component :is="currentComponent" />
            </KeepAlive>
          </Transition>
        </main>

      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent, watch } from 'vue'
import { useAppStore } from '../../stores/appStore'
import { Library, FolderArchive, Globe, CloudDownload, Github } from 'lucide-vue-next'
import { useWorkspaceStore } from '../../stores/workspaceStore'

const workspaceStore = useWorkspaceStore()
const appStore = useAppStore()

const tabs = [
  { id: 'library', label: '全库数据管理', icon: Library, colorClass: 'bg-accent-success shadow-[0_0_10px_var(--color-accent-success)]' },
  { id: 'workshop', label: '创意工坊检索', icon: Globe, colorClass: 'bg-accent-primary shadow-[0_0_10px_var(--color-accent-primary)]' },
  { id: 'collection', label: '合集订阅管理', icon: FolderArchive, colorClass: 'bg-accent-warn shadow-[0_0_10px_var(--color-accent-warn)]' },
  { id: 'github', label: 'GitHub订阅', icon: Github, colorClass: 'bg-text-main shadow-[0_0_10px_rgba(255,255,255,0.8)]' } 
]

const currentTab = ref('library')

// 异步组件加载
const LibraryMatrix = defineAsyncComponent(() => import('./views/LibraryMatrix.vue'))
const CollectionCommand = defineAsyncComponent(() => import('./views/CollectionCommand.vue'))
const WorkshopBrowser = defineAsyncComponent(() => import('./views/WorkshopBrowser.vue'))
const GithubCommand = defineAsyncComponent(() => import('./views/GithubCommand.vue'))

const currentComponent = computed(() => {
  if (currentTab.value === 'library') return LibraryMatrix
  if (currentTab.value === 'collection') return CollectionCommand
  if (currentTab.value === 'workshop') return WorkshopBrowser
  if (currentTab.value === 'github') return GithubCommand 
  return null
})

// 根据当前 Tab 改变背景光晕
const activeBgGlow = computed(() => {
  if (currentTab.value === 'library') return 'bg-[radial-gradient(ellipse_at_bottom_left,_rgba(16,185,129,0.05),_transparent_50%)]'
  if (currentTab.value === 'collection') return 'bg-[radial-gradient(ellipse_at_bottom_left,_rgba(234,179,8,0.05),_transparent_50%)]'
  if (currentTab.value === 'workshop') return 'bg-[radial-gradient(ellipse_at_bottom_left,_rgba(59,130,246,0.05),_transparent_50%)]'
  return ''
})

// 快捷键 Esc 关闭
const handleKeydown = (e) => {
  if (e.key === 'Escape' && appStore.uiState.showWorkspace) {
    appStore.uiState.showWorkspace = false
  }
}
onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  workspaceStore.initData()
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<style scoped>
/* 全屏进入/退出动画 - 带缩放模糊 */
.workspace-zoom-enter-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.workspace-zoom-leave-active { transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
.workspace-zoom-enter-from { opacity: 0; transform: scale(1.05); filter: blur(10px); }
.workspace-zoom-leave-to { opacity: 0; transform: scale(0.95); filter: blur(10px); }

/* 子页面切换渐变 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
