<template>
  <!-- =======================
        顶部功能栏 (Navbar)
      ======================= -->
  <header class="m-1 h-14 bg-bg-surface/60 backdrop-blur-md rounded-2xl flex items-center px-3 justify-between border border-text-main/5 shadow-lg shrink-0 z-50">
    <!-- 标题 -->
    <div class="flex items-center gap-4 mx-1 ">
      <h1 class="font-bold tracking-wider text-lg bg-linear-to-r from-text-main to-gray-400 bg-clip-text text-transparent">
        <span class="text-accent-primary animate-breathe ">RIM</span> MODMANAGER
      </h1>
      <span class="px-2 py-0.5 rounded text-xs bg-text-main/5 text-text-dim border border-text-main/5 ">v {{ appStore.appVersion }}</span>
      <!-- 环境切换器 -->
      <ProfileSwitcher />
    </div>

    <div class="flex items-center gap-3">
      <button v-if="appStore.settings.debug_mode" @click="appStore.toggleUiState('showTestDrawer')" v-tooltip="`测试页面`"
          class="p-2 rounded-full hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        测试
      </button>

      <button @click="appStore.toggleUiState('showAiReviewModal')" v-tooltip="`AI生成管理`" :class="{'opacity-30 pointer-events-none': !appStore.aiBatchResults.length}"
        class="p-2 rounded-full relative hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent cursor-pointer">
        <BotMessageSquare class="size-6" />
        <span v-show="appStore.aiBatchResults.length > 0" class="absolute top-0 right-0 p-0.5 leading-none text-xs text-text-main font-bold rounded-full bg-accent-secondary/70">{{ appStore.aiBatchResults.length }}</span>
      </button>
      
      <div v-tooltip="`打开文件夹`" class="p-2 rounded-full group/folder relative hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>
        <div class="absolute top-full right-0 w-30 overflow-hidden rounded-md flex flex-col items-center justify-center bg-glass-medium border border-text-main/10 shadow-2xl backdrop-blur-sm opacity-0 
          invisible transform origin-top-right group-hover/folder:opacity-100 group-hover/folder:visible transition-all duration-300">
          <button @click="appStore.openPath(appStore.settings.user_data_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">用户数据目录</button>
          <button @click="appStore.openPath(appStore.settings.game_saves_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏存档目录</button>
          <button @click="appStore.openPath(appStore.settings.game_config_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏配置目录</button>
          <button @click="appStore.openPath(appStore.settings.game_install_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏安装目录</button>
          <button @click="appStore.openPath(appStore.settings.game_dlc_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏DLC目录</button>
          <button @click="appStore.openPath(appStore.settings.local_mods_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent" >本地Mod目录</button>
          <button @click="appStore.openPath(appStore.settings.workshop_mods_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">工坊Mod目录</button>
        </div>
      </div>

      <!-- <div v-tooltip="`导入导出`" class="p-2 rounded-full group/folder relative hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>
        <div class="absolute top-full right-0 w-30 overflow-hidden rounded-md flex flex-col items-center justify-center bg-glass-medium border border-text-main/10 shadow-2xl backdrop-blur-sm opacity-0 
          invisible transform origin-top-right group-hover/folder:opacity-100 group-hover/folder:visible transition-all duration-300">
          <button @click="appStore.openPath(appStore.settings.game_install_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏安装目录</button>
          <button @click="appStore.openPath(appStore.settings.game_config_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">游戏配置目录</button>
          <button @click="appStore.openPath(appStore.settings.workshop_mods_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent">工坊Mod目录</button>
          <button @click="appStore.openPath(appStore.settings.local_mods_path)" class="m-0.5 p-1 rounded-md hover:bg-accent-primary/10 text-text-dim hover:text-text-main transition bg-transparent" >本地Mod目录</button>
        </div>
      </div> -->

      <button @click="appStore.toggleUiState('showLogDrawer')" v-tooltip="`日志页面`"
        class="p-2 rounded-full hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M16 14v2.2l1.6 1"/><path d="M16 4h2a2 2 0 0 1 2 2v.832"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h2"/><circle cx="16" cy="16" r="6"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>
      </button>

      <button @click="appStore.toggleUiState('showRuleDrawer')" v-tooltip="`规则页面`"
        class="p-2 rounded-full hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M13 7 8.7 2.7a2.41 2.41 0 0 0-3.4 0L2.7 5.3a2.41 2.41 0 0 0 0 3.4L7 13"/><path d="m8 6 2-2"/><path d="m18 16 2-2"/><path d="m17 11 4.3 4.3c.94.94.94 2.46 0 3.4l-2.6 2.6c-.94.94-2.46.94-3.4 0L11 17"/><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/></svg>
      </button>

      <!-- 设置按钮 -->
      <button @click="appStore.openSettingsPanel()" v-tooltip="`设置`"
          class="p-2 rounded-full hover:bg-glow text-text-dim hover:text-text-main transition bg-transparent">
        <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup>
import { useAppStore } from '../stores/appStore'
import { useToast } from "vue-toastification";
import ProfileSwitcher from './utils/ProfileSwitcher.vue';
import { BotMessageSquare } from 'lucide-vue-next';


const toast = useToast();
const appStore = useAppStore()

</script>


<style scoped>
.read-the-docs {
  color: #888;
}

/* 文本呼吸光晕 */
@keyframes breathe {
    0%, 100% { text-shadow: 0 0 5px rgba(59, 130, 246, 0.7), 0 0 10px rgba(59, 130, 246, 0.5); }
    50% { text-shadow: 0 0 15px rgba(59, 130, 246, 0.9), 0 0 30px rgba(59, 130, 246, 0.7), 0 0 45px rgba(59, 130, 246, 0.5); }
}
.animate-breathe { animation: breathe 8s ease-in-out infinite; }

/* 圆形光晕 */
@layer utilities {
  .bg-glow {
    position: relative;
    isolation: isolate;
  }
  .bg-glow::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image: radial-gradient(circle, rgba(59, 130, 246, 0.8) 0%, rgba(59, 130, 246, 0) 70%);
    filter: blur(5px);
    z-index: -1;
    opacity: 0;
    transition: opacity 0.3s ease-in-out;
  }
  .hover\:bg-glow:hover::before {
    opacity: 1;
  }
}
</style>
