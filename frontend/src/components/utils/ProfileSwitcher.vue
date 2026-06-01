<template>
  <div class="relative group/profile" ref="containerRef">
    <!-- 激活状态显示按钮 -->
    <button @click="isOpen = !isOpen"
      class="flex items-center gap-3 px-3 py-1 rounded-xl bg-bg-overlay/5 border border-border-base/10 hover:bg-bg-overlay/10 hover:border-accent-primary/50 transition-all duration-300"
    >
      <!-- 状态图标：Steam 蓝或本地绿 -->
      <div class="relative flex items-center justify-center">
        <div class="absolute inset-0 rounded-full bg-current opacity-20 animate-ping"></div>
      </div>

      <div class="flex flex-col items-start gap-0 ">
        <span class="text-sm font-black text-text-soft tracking-wide">{{ profileStore.currentProfile?.name || 'Default' }}</span>
        <div class="flex items-center gap-1">
            <span class="text-[0.6rem] text-text-dim uppercase tracking-tighter opacity-60">当前环境</span>
            <span class="text-[0.6rem] text-accent-tip bg-accent-success/20 px-2 py-0.5 rounded-full uppercase tracking-tighter opacity-60">{{ profileStore.currentProfile?.game_version || '未知版本' }}</span>
            <span v-if="runtimeProfileId && runtimeProfileId === profileStore.currentProfileId && appStore.runtimeSession?.state === 'running'" class="text-[0.6rem] text-accent-primary bg-accent-primary/15 px-2 py-0.5 rounded-full uppercase tracking-tighter opacity-80">运行中</span>
        </div>
      </div>

      <ChevronDown class="size-4 text-text-dim group-hover/profile:text-accent-primary transition-transform duration-300" :class="{ 'rotate-180': isOpen }" />
    </button>

    <!-- 下拉列表 -->
    <FixedPopover :is-open="isOpen" :trigger-ref="containerRef" :offset="6">
      <div class="w-64 bg-glass-medium backdrop-blur-2xl  border border-border-base/10 rounded-2xl shadow-[0_20px_50px_var(--shadow-color)] overflow-hidden z-100">

        <div class="p-1 space-y-1">
          <button v-for="p in profileStore.profiles" :key="p.id" @click="p.check ? handleSwitch(p.id) : null"
            class="w-full flex items-center gap-3 px-2 py-1 rounded-xl transition-all duration-200 group/item"
            :class="p.check ? (p.id === profileStore.currentProfileId ? 'bg-accent-primary/10 border border-accent-primary/20 cursor-pointer'
            : 'hover:bg-bg-overlay/5 border border-transparent cursor-pointer')
            : 'bg-accent-danger/10 border border-accent-danger/20 cursor-not-allowed'"
          >
            <component :is="p.is_steam ? SteamIcon : Folder" class="size-4" :class="p.id === profileStore.currentProfileId ? 'text-accent-primary' : 'text-text-dim'" />
            <div class="flex-1 text-left">
              <div class="flex items-center gap-2">
                <div class="text-sm font-bold" :class="p.id === profileStore.currentProfileId ? 'text-accent-primary' : 'text-text-soft'">{{ p.name }}</div>
                <span v-if="p.id === runtimeProfileId && appStore.runtimeSession?.state === 'running'" class="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-accent-primary/15 text-accent-primary uppercase tracking-tighter">运行中</span>
              </div>
              <div class="text-[0.65rem] text-text-dim truncate max-w-50">{{ p.game_version || '未知版本' }}</div>
            </div>
            <Quote v-if="p.description && p.check" v-tooltip="p.description" class="size-4 text-text-dim hover:text-accent-primary hover:scale-120 transition-all duration-300" />
            <AlertOctagon v-if="!p.check" v-tooltip="`当前环境不可用：\n^^${p.msg}^^`" class="size-4 text-accent-danger hover:scale-120 transition-all duration-300 cursor-help" />
            <div class="size-2 rounded-full bg-accent-primary shadow-[0_0_8px_rgba(var(--rgb-accent-primary),0.75)]" :class="{'opacity-5':p.id !== profileStore.currentProfileId}"></div>
          </button>
        </div>

        <div class="modal-footer p-1">
          <button @click="openManager" class="w-full py-2 rounded-lg flex items-center justify-center gap-2 text-xs font-black uppercase text-text-dim hover:text-text-main hover:bg-accent-primary/20 transition-all cursor-pointer">
            <Settings2 class="size-3" />
            管理环境中心
          </button>
        </div>
      </div>
    </FixedPopover>
  </div>
</template>

<script setup>
import { computed, ref, h } from 'vue'
import { ChevronDown, Settings2, Folder, Quote, AlertOctagon } from 'lucide-vue-next'
import { useProfileStore } from '../../stores/profileStore'
import { useAppStore } from '../../stores/appStore'
import { onClickOutside } from '@vueuse/core'
import FixedPopover from '../common/FixedPopover.vue'

const appStore = useAppStore()
const profileStore = useProfileStore()
const isOpen = ref(false)
const containerRef = ref(null)
const runtimeProfileId = computed(() => String(appStore.runtimeSession?.profile_id || '').trim())

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
