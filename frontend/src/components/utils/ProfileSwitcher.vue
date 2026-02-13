<template>
  <div class="relative group/profile" ref="containerRef">
    <!-- 激活状态显示按钮 -->
    <button @click="isOpen = !isOpen"
      class="flex items-center gap-3 px-3 py-1 rounded-xl bg-text-main/5 border border-text-main/10 hover:bg-text-main/10 hover:border-accent-primary/50 transition-all duration-300"
    >
      <!-- 状态图标：Steam 蓝或本地绿 -->
      <div class="relative flex items-center justify-center">
        <div class="absolute inset-0 rounded-full bg-current opacity-20 animate-ping"></div>
      </div>

      <div class="flex flex-col items-start gap-0 ">
        <span class="text-sm font-black text-text-main/90 tracking-wide">{{ profileStore.currentProfile?.name || 'Default' }}</span>
        <div class="flex items-center gap-1">
            <span class="text-[0.6rem] text-text-dim uppercase tracking-tighter opacity-60">当前环境</span>
            <span class="text-[0.6rem] text-accent-tip bg-accent-success/20 px-2 py-0.5 rounded-full uppercase tracking-tighter opacity-60">{{ profileStore.currentProfile?.game_version || '未知版本' }}</span>
        </div>
      </div>

      <ChevronDown class="size-4 text-text-dim group-hover/profile:text-accent-primary transition-transform duration-300" :class="{ 'rotate-180': isOpen }" />
    </button>

    <!-- 下拉列表 -->
    <Transition name="dropdown">
      <div v-if="isOpen" 
        class="absolute top-full mt-2 left-0 w-64 bg-bg-surface/90 backdrop-blur-xl border border-text-main/10 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] overflow-hidden z-100">
        
        <div class="p-1 space-y-1">
          <button v-for="p in profileStore.profiles" :key="p.id" @click="handleSwitch(p.id)"
            class="w-full flex items-center gap-3 px-2 py-1 rounded-xl transition-all duration-200 group/item"
            :class="p.id === profileStore.currentProfileId ? 'bg-accent-primary/10 border border-accent-primary/20' : 'hover:bg-text-main/5 border border-transparent'"
          >
            <component :is="p.use_workshop_mods ? SteamIcon : Folder" class="size-4" :class="p.id === profileStore.currentProfileId ? 'text-accent-primary' : 'text-text-dim'" />
            <div class="flex-1 text-left">
              <div class="text-sm font-bold" :class="p.id === profileStore.currentProfileId ? 'text-accent-primary' : 'text-text-main/80'">{{ p.name }}</div>
              <div class="text-[0.65rem] text-text-dim truncate max-w-50">{{ p.game_version || '未知版本' }}</div>
            </div>
            <Quote v-if="p.description" v-tooltip="p.description" class="size-4 text-text-dim hover:text-accent-primary hover:scale-120 transition-all duration-300" />
            <div :class="{'opacity-5':p.id !== profileStore.currentProfileId}" class="size-2 rounded-full bg-accent-primary shadow-[0_0_8px_#06b6d4]"></div>
          </button>
        </div>

        <div class="p-1 border-t border-text-main/5 bg-text-main/2">
          <button @click="openManager" class="w-full py-2 rounded-lg flex items-center justify-center gap-2 text-xs font-black uppercase text-text-dim hover:text-text-main hover:bg-accent-primary/20 transition-all">
            <Settings2 class="size-3" />
            管理环境中心
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, h } from 'vue'
import { ChevronDown, Settings2, Folder, Quote } from 'lucide-vue-next'
import { useProfileStore } from '../../stores/profileStore'
import { useAppStore } from '../../stores/appStore'
import { onClickOutside } from '@vueuse/core'

const appStore = useAppStore()
const profileStore = useProfileStore()
const isOpen = ref(false)
const containerRef = ref(null)

const SteamIcon = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, [
  h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })
])

const handleSwitch = (id) => {
  profileStore.switchProfile(id)
  isOpen.value = false
}

const openManager = () => {
  // 触发全局事件或修改 appStore 状态打开抽屉
  isOpen.value = false
  appStore.uiState.showProfileDrawer = true
}

onClickOutside(containerRef, () => isOpen.value = false)
</script>

<style scoped>
.dropdown-enter-active, .dropdown-leave-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-10px) scale(0.95); }
</style>