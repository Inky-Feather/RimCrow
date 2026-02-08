<template>
  <Teleport to="body">
    <Transition name="slide-left">
      <div v-if="appStore.uiState.showProfileDrawer" 
        class="fixed inset-y-8 top-18 left-0 w-[420px] z-100 flex flex-col"
      >
        <!-- 1. 上方内凹边角 (对称自 ListDiffView) -->
        <div class="absolute -top-[1.1rem] left-0 w-5 h-5 z-10 ">
          <div class="w-full h-full bg-bg-deep/70 backdrop-blur-xl mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]"></div>
          <svg class="absolute inset-0 w-full h-full text-white/10 fill-none pointer-events-none" viewBox="0 0 20 20">
            <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>

        <!-- 2. 主体容器 -->
        <div class="flex-1 flex flex-col bg-bg-highlight/80 backdrop-blur-xl rounded-l-none rounded-r-2xl border-y border-r border-white/10 shadow-3xl overflow-hidden relative">
          
          <!-- 头部：标题与快速新建 -->
          <header class="p-3 bg-gray-900/80 border-b border-white/5">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-xl font-black italic text-white flex items-center gap-2">
                  <Database class="size-5 text-accent-primary" />
                  环境<span class="text-accent-primary">管理</span>
                </h2>
              </div>
              <button @click="openCreate" v-tooltip="'创建新环境快照'"
                class="p-2 rounded-xl bg-accent-primary/10 text-accent-primary hover:bg-accent-primary hover:text-black transition-all">
                <Plus class="size-5" />
              </button>
            </div>
          </header>

          <!-- 列表区 -->
          <div class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
            <!-- 当前激活标识 -->
            <div class="px-2 text-[0.65rem] font-bold text-text-dim uppercase tracking-tighter opacity-60">已记录环境</div>
            
            <div v-for="p in profileStore.profiles" :key="p.id" 
              @click="profileStore.switchProfile(p.id)"
              class="group relative p-4 rounded-xl border transition-all duration-300 cursor-pointer overflow-hidden"
              :class="p.id === profileStore.currentProfileId 
                ? 'bg-accent-primary/10 border-accent-primary/40 shadow-[0_0_15px_rgba(6,182,212,0.15)]' 
                : 'bg-white/2 border-white/5 hover:border-white/20 hover:bg-white/5'"
            >
              <!-- 激活时的动态流光 -->
              <div v-if="p.id === profileStore.currentProfileId" class="absolute inset-0 bg-linear-to-r from-accent-primary/10 to-transparent animate-pulse-slow"></div>

              <div class="relative flex justify-between items-start">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <div class="size-2 rounded-full" 
                      :class="p.id === profileStore.currentProfileId ? 'bg-accent-primary animate-pulse shadow-[0_0_8px_#06b6d4]' : 'bg-text-dim/30'"></div>
                    <h4 class="font-bold text-sm" :class="p.id === profileStore.currentProfileId ? 'text-white' : 'text-text-main'">{{ p.name }}</h4>
                    <span v-if="p.is_steam" class="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/10 uppercase">Steam</span>
                  </div>
                  <p class="text-[10px] text-text-dim mt-2 font-mono opacity-50 truncate">{{ p.game_install_path }}</p>
                  <p class="text-[10px] text-text-dim mt-2 font-mono opacity-50 truncate">{{ p.user_data_path }}</p>
                </div>

                <!-- 操作组 -->
                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button @click.stop="handleEdit(p)" class="p-1.5 rounded-lg hover:bg-white/10 text-text-dim hover:text-white transition-all"><Settings2 class="size-3.5" /></button>
                  <button v-if="p.id !== 'default'" @click.stop="handleDelete(p)" class="p-1.5 rounded-lg hover:bg-accent-danger/20 text-text-dim hover:text-accent-danger transition-all"><Trash2 class="size-3.5" /></button>
                </div>
              </div>
            </div>

            <!-- 待恢复/孤立环境 -->
            <div v-if="profileStore.orphanedProfiles.length > 0" class="mt-8 space-y-3">
              <div class="px-2 text-[0.65rem] font-bold text-accent-warn uppercase tracking-tighter">待恢复节点</div>
              <div v-for="orphan in profileStore.orphanedProfiles" :key="orphan.id"
                class="p-4 rounded-xl border border-dashed border-accent-warn/30 bg-accent-warn/5 flex items-center justify-between group">
                <div class="min-w-0">
                  <div class="text-sm font-bold text-accent-warn/80">{{ orphan.name }}</div>
                  <div class="text-[10px] text-text-dim truncate w-48 mt-1">{{ orphan._folder_path }}</div>
                </div>
                <button @click="profileStore.importOrphan(orphan)" class="px-3 py-1.5 rounded-lg bg-accent-warn/20 hover:bg-accent-warn text-accent-warn hover:text-black text-[10px] font-black transition-all">
                  接入
                </button>
              </div>
            </div>
          </div>

          <!-- 底部工具栏 -->
          <footer class="p-4 bg-black/20 border-t border-white/5 flex items-center justify-between">
            <button @click="appStore.performDatabaseCleanup" class="flex items-center gap-2 text-[10px] font-black text-text-dim hover:text-accent-danger transition-colors uppercase">
              <ZapOff class="size-3" /> 深度清理孤立数据
            </button>
            <button @click="appStore.uiState.showProfileDrawer = false" class="px-4 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-text-main text-xs font-bold transition-all">
              收起
            </button>
          </footer>

        </div>

        <!-- 3. 下方内凹边角 -->
        <div class="absolute -bottom-[1.2rem] left-0 w-5 h-5 z-10 rotate-90">
          <div class="w-full h-full bg-bg-surface/80 mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]"></div>
          <svg class="absolute inset-0 w-full h-full text-white/10 fill-none pointer-events-none" viewBox="0 0 20 20">
            <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 4. 编辑/创建 模态框 (标准 RulePanel 风格) -->
  <Transition name="fade">
    <div v-if="showModal" class="fixed inset-0 z-150 flex items-center justify-center bg-black/60 backdrop-blur-md">
      <div class="w-full max-w-md bg-bg-surface border border-white/10 rounded-2xl shadow-3xl overflow-hidden animate-scale-in">
        <header class="px-6 py-4 border-b border-white/5 bg-white/2 flex justify-between items-center">
          <h3 class="text-lg font-bold text-white">{{ isEditing ? '编辑环境属性' : '创建新环境快照' }}</h3>
          <button @click="showModal = false" class="text-text-dim hover:text-white"><X class="size-5" /></button>
        </header>

        <div class="p-6 space-y-5">
          <CommonInput label="显示名称" v-model="form.name" placeholder="例如: 1.5 极难生存" />

          <CommonPathInput label="游戏执行目录" v-model="form.game_install_path" @browse="browsePath" />
          <CommonPathInput label="用户数据目录" v-model="form.user_data_path" @browse="browsePath" />
          <CommonSwitch label="使用工作坊 Mod" v-model="form.use_workshop_mods" description="是否在启动时加载工作坊 Mod" />
          
          <div v-if="!isEditing" class="p-4 rounded-xl bg-accent-primary/5 border border-accent-primary/10">
            <CommonSwitch label="继承当前配置" v-model="form.copy_current_data" 
              description="自动复制当前的 ModsConfig 和存档至新环境" />
          </div>

          <div class="text-[10px] text-text-dim/60 leading-relaxed">
            * 每一个环境都拥有完全独立的存档、设置和 Mod 排序文件。系统将通过启动参数自动执行数据隔离。
          </div>
        </div>

        <footer class="px-6 py-4 border-t border-white/5 bg-black/20 flex justify-end gap-3">
          <button @click="showModal = false" class="px-4 py-2 text-sm text-text-dim hover:text-white">取消</button>
          <button @click="submitForm" class="px-6 py-2 rounded-xl bg-accent-primary text-black font-black text-sm shadow-lg shadow-accent-primary/20 transition-all hover:scale-105 active:scale-95">
            {{ isEditing ? '保存变更' : '确认创建' }}
          </button>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Database, Plus, Trash2, Settings2, ZapOff, X } from 'lucide-vue-next'
import { useProfileStore } from '../stores/profileStore'
import { useAppStore } from '../stores/appStore'
import { useConfirmStore } from '../stores/confirmStore'
import CommonInput from './common/input/CommonInput.vue'
import CommonPathInput from './common/input/CommonPathInput.vue'
import CommonSwitch from './common/input/CommonSwitch.vue'

const profileStore = useProfileStore()
const appStore = useAppStore()
const confirmStore = useConfirmStore()

// --- 状态 ---
const showModal = ref(false)
const isEditing = ref(false)
const form = reactive({
  id: '',
  name: '',
  description: '',
  game_install_path: '',
  user_data_path: '',
  use_workshop_mods: false,
  copy_current_data: false
})

// --- 逻辑 ---
watch(() => appStore.uiState.showProfileDrawer, (val) => {
  if (val) profileStore.scanOrphans()
})

const openCreate = () => {
  form.id = ''
  form.name = ''
  form.description = ''
  form.game_install_path = appStore.settings.game_install_path
  form.user_data_path = appStore.settings.user_data_path
  form.use_workshop_mods = appStore.settings.use_workshop_mods
  form.copy_current_data = true
  isEditing.value = false
  showModal.value = true
}

const handleEdit = (p) => {
  form.id = p.id
  form.name = p.name
  form.description = p.description
  form.game_install_path = p.game_install_path
  form.user_data_path = p.user_data_path
  form.use_workshop_mods = p.use_workshop_mods
  isEditing.value = true
  showModal.value = true
}

const browsePath = async () => {
  const path = await appStore.getFolderPath(form.game_install_path)
  if (path) form.game_install_path = path
}

const submitForm = async () => {
  if (isEditing.value) {
    const cleanForm = { ...form }
    delete cleanForm.copy_current_data
    await profileStore.updateProfile(form.id, cleanForm)
  } else {
    const cleanForm = { ...form }
    delete cleanForm.copy_current_data
    await profileStore.createProfile(cleanForm, form.copy_current_data)
  }
  showModal.value = false
}

const handleDelete = async (p) => {
  const ok = await confirmStore.confirmAction('危险操作', `确定要删除环境 "${p.name}" 吗？此操作将永久抹除其隔离区的存档数据。`, { type: 'error' })
  if (ok) await profileStore.deleteProfile(p.id)
}
</script>

<style scoped>
.slide-left-enter-active, .slide-left-leave-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }

.animate-scale-in { animation: scaleIn 0.2s ease-out; }
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

.custom-scrollbar::-webkit-scrollbar { width: 3px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
</style>