<!-- components/SettingsPanel.vue -->
<template>
  <!-- 遮罩层 (点击背景关闭) -->
  <transition name="fade">
    <div v-if="store.showSettings" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="store.closeSettings()">
      
      <!-- 卡片主体 -->
      <transition name="scale">
        <div class="w-[800px] h-[600px] flex bg-bg-deep/90 border border-white/10 rounded-2xl shadow-2xl overflow-hidden relative" @click.stop>
          
          <!-- 左侧导航栏 -->
          <div class="w-48 bg-black/20 border-r border-white/5 flex flex-col p-4 gap-2">
            <div class="text-xl font-bold text-white mb-6 px-2 flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-accent-primary shadow-[0_0_10px_var(--color-accent-primary)]"></div>
              设置
            </div>
            
            <button v-for="tab in tabs" :key="tab.id"
              @click="currentTab = tab.id"
              :class="[
                'w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200',
                currentTab === tab.id 
                  ? 'bg-accent-primary text-white shadow-lg shadow-accent-primary/20' 
                  : 'text-text-dim hover:bg-white/5 hover:text-white'
              ]"
            >
              {{ tab.label }}
            </button>
          </div>

          <!-- 右侧内容区 -->
          <div class="flex-1 flex flex-col min-w-0">
            <!-- 标题 -->
            <div class="h-16 border-b border-white/5 flex items-center px-8 text-lg font-bold text-white">
              {{ tabs.find(t => t.id === currentTab)?.label }}
            </div>

            <!-- 滚动内容 -->
            <div class="flex-1 overflow-y-auto p-8 space-y-6">
              
              <!-- 1. 路径设置页 -->
              <div v-if="currentTab === 'paths'" class="space-y-6">
                <!-- 自动检测按钮 -->
                <div class="p-4 rounded-xl bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-between">
                  <div class="text-sm text-accent-primary">
                    <div class="font-bold mb-1">自动配置</div>
                    <div class="opacity-80 text-xs">尝试检测注册表自动获取默认路径</div>
                  </div>
                  <button @click="autoDetect" 
                    class="px-4 py-2 bg-accent-primary/70 hover:bg-accent-primary text-white rounded-lg text-sm font-bold shadow-lg shadow-accent-primary/20 transition-transform active:scale-95 flex items-center gap-2">
                    <span v-if="detecting" class="animate-spin">⟳</span>
                    自动检测
                  </button>
                </div>

                <div class="space-y-4">
                  <InputGroup label="游戏安装目录" v-model="formData.game_install_path" @browse="handleBrowse('game_install_path')" :is-path="true"  placeholder="例如: D:\Steam\steamapps\common\RimWorld" />
                  <InputGroup label="配置文件夹 (Config)" v-model="formData.game_config_path" @browse="handleBrowse('game_config_path')" :is-path="true"  placeholder="自动检测通常能找到 LocalLow 下的路径" />
                  <InputGroup label="创意工坊模组目录" v-model="formData.workshop_mods_path" @browse="handleBrowse('workshop_mods_path')" :is-path="true"  placeholder="Steam Workshop content 目录" />
                  <InputGroup label="本地模组目录" v-model="formData.local_mods_path" @browse="handleBrowse('local_mods_path')" :is-path="true"  placeholder="游戏目录下的 Mods 文件夹" />
                </div>
              </div>

              <!-- 2. 常规/界面设置页 -->
              <div v-if="currentTab === 'general'" class="space-y-6">
                 <div class="grid grid-cols-2 gap-6">
                    <InputGroup label="窗口宽度" type="number" v-model.number="formData.window_width" />
                    <InputGroup label="窗口高度" type="number" v-model.number="formData.window_height" />
                 </div>
                 <div>
                  <InputGroup label="语言" v-model="formData.language" />
                  <InputGroup label="主题" v-model="formData.theme" />
                  <InputGroup label="备份保留时间" type="number" v-model.number="formData.backup_retention_days" />
                 </div>
                 
                 <div class="space-y-2">
                    <label class="text-xs text-text-dim uppercase tracking-wider font-bold ml-1">主题色</label>
                    <div class="flex gap-3">
                        <div v-for="color in colors" :key="color" 
                            @click="formData.primary_color = color"
                            class="w-8 h-8 rounded-full cursor-pointer ring-2 ring-offset-2 ring-offset-[#1a1a1a] transition-all"
                            :class="formData.primary_color === color ? 'ring-white scale-110' : 'ring-transparent hover:scale-110'"
                            :style="{ backgroundColor: color }">
                        </div>
                    </div>
                 </div>

                 <div class="p-4 rounded-xl bg-white/5 border border-white/5">
                    <label class="flex items-center justify-between cursor-pointer">
                        <span class="text-sm text-white font-medium">启动时自动扫描</span>
                        <input type="checkbox" v-model="formData.enable_auto_scan" class="accent-accent-primary w-5 h-5 rounded bg-black/50 border-white/20">
                    </label>
                    <label class="flex items-center justify-between cursor-pointer">
                        <span class="text-sm text-white font-medium">自动清理缺失的Mod信息</span>
                        <input type="checkbox" v-model="formData.delete_missing_mods_data" class="accent-accent-primary w-5 h-5 rounded bg-black/50 border-white/20">
                    </label>
                 </div>
              </div>

            </div>

            <!-- 底部按钮 -->
            <div class="h-20 border-t border-white/5 flex items-center justify-end px-8 gap-4 bg-black/20">
              <button @click="store.closeSettings()" class="px-6 py-2 rounded-lg text-text-dim hover:text-white hover:bg-white/5 transition-colors text-sm font-bold">
                取消
              </button>
              <button @click="save" class="px-8 py-2 rounded-lg bg-accent-primary hover:brightness-110 text-white shadow-lg shadow-accent-primary/20 text-sm font-bold transition-all active:scale-95">
                保存并应用
              </button>
            </div>
          </div>

        </div>
      </transition>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useModStore } from '../stores/modStore'

// 简单的输入框子组件
const InputGroup = {
  props: ['label', 'modelValue', 'placeholder', 'type', 'isPath'],
  emits: ['update:modelValue'],
  template: `
    <div class="space-y-1.5">
      <label class="text-xs text-text-dim uppercase tracking-wider font-bold ml-1">{{ label }}</label>
      <div class="relative group flex items-center gap-2">
        <div class="relative flex-1 ">
          <input :type="type || 'text'" :value="modelValue" 
            @input="$emit('update:modelValue', $event.target.value)"
            :placeholder="placeholder"
            class="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-accent-primary focus:bg-black/40 transition-all font-mono"
          />
          <div class="absolute inset-0 rounded-lg ring-1 ring-white/0 group-hover:ring-white/10 pointer-events-none transition-all"></div>
          
        </div>

        <!-- 浏览按钮 (仅当 is-path 为 true 时显示) -->
        <button v-if="isPath"
            @click="$emit('browse')"
            class="px-3 py-2.5 bg-white/5 hover:bg-accent-primary hover:text-white text-text-dim border border-white/10 rounded-lg transition-all active:scale-95"
            title="浏览文件夹">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
        </button>

      </div>

    </div>
  `
}

const store = useModStore()
const currentTab = ref('paths')
const detecting = ref(false)

const tabs = [
  { id: 'paths', label: '路径配置' },
  { id: 'general', label: '界面与常规' },
]

// 预设颜色
const colors = ['#06b6d4', '#8b5cf6', '#f43f5e', '#10b981', '#f59e0b']

// 本地表单数据 (复制一份 Store 数据，避免直接修改 Store)
const formData = ref({})

// 当弹窗打开时，从 Store 同步数据
watch(() => store.showSettings, (val) => {
  if (val) {
    // 深拷贝 settings 防止污染
    formData.value = JSON.parse(JSON.stringify(store.settings))
  }
})

// 自动检测路径
const autoDetect = async () => {
  if(!window.pywebview) return
  detecting.value = true
  try {
    const res = await window.pywebview.api.auto_detect_paths()
    if (res.status === 'success' && res.paths) {
      // 只更新表单，不直接保存，让用户确认
      Object.assign(formData.value, res.paths)
    } else {
      // 可以加个 Toast 提示失败
      alert('未能自动找到所有路径，请手动填写。')
    }
  } finally {
      detecting.value = false
  }
}

// 保存
const save = () => {
    store.applySettings(formData.value)
}

// 打开Mod路径
const openPath = (path) => {
  if(path) store.openPath(path)
}

// 打开Url
const openUrl = (url) => {
  if(url) window.open(url, '_blank')
}

// 浏览文件夹
const handleBrowse = async (fieldKey) => {
    if(!window.pywebview) return
    
    // 调用后端 API
    const path = await window.pywebview.api.select_folder_dialog(formData.value[fieldKey])
    
    // 如果用户选了路径（没点取消），则更新数据
    if (path) {
        formData.value[fieldKey] = path
    }
}

</script>

<style scoped>
/* 动画效果 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.scale-enter-active, .scale-leave-active { transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1); }
.scale-enter-from, .scale-leave-to { transform: scale(0.95); opacity: 0; }
</style>