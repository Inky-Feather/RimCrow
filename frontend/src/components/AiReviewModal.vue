<!-- frontend/src/components/AiReviewModal.vue -->
<template>
  <transition name="fade">
    <div v-if="appStore.uiState.showAiReviewModal" class="fixed inset-0 z-120 flex items-center justify-center bg-bg-deep/80 backdrop-blur-md">
      
      <!-- 主容器 -->
      <div data-tour="ai-review-modal" class="w-[85%] max-w-6xl h-[85vh] flex flex-col bg-bg-surface/90 border border-accent-special/30 rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.6)] overflow-hidden relative">
        
        <!-- 背景光效 -->
        <div class="absolute -top-32 -left-32 w-96 h-96 bg-accent-special/10 blur-[100px] rounded-full pointer-events-none"></div>

        <!-- Header -->
        <div data-tour="ai-review-summary" class="px-6 py-4 bg-black/40 border-b border-text-main/10 flex items-center justify-between shrink-0 relative z-10">
          <div class="flex items-center gap-4">
            <div class="relative p-2.5 rounded-xl bg-accent-special/20 text-accent-special border border-accent-special/30 shadow-[0_0_15px_rgba(var(--color-accent-special),0.2)]">
              <Cpu class="size-6" :class="{'animate-pulse': appStore.aiState.isLoading}" />
              <div v-if="appStore.aiState.isLoading" class="absolute inset-0 border-2 border-accent-special/50 rounded-xl animate-ping opacity-50"></div>
            </div>
            <div>
              <h2 class="text-xl font-black text-text-main tracking-wide">AI 处理结果检阅</h2>
              <p class="text-xs text-text-dim mt-0.5 flex items-center gap-2">
                共分配 <span class="text-text-main font-bold">{{ appStore.aiBatchResults.length }}</span> 项任务。
                <!-- 计算成功的数量 -->
                <span class="px-1.5 py-0.5 rounded bg-green-500/20 text-green-400">
                  成功: {{ appStore.aiBatchResults.filter(i => i.alias_name || i.notes).length }}
                </span>
                <!-- 计算失败置空的数量 -->
                <span v-if="appStore.aiBatchResults.some(i => !i.alias_name && !i.notes)" class="px-1.5 py-0.5 rounded bg-accent-warn/20 text-accent-warn">
                  需手填/重试: {{ appStore.aiBatchResults.filter(i => !i.alias_name && !i.notes).length }}
                </span>
              </p>
            </div>
          </div>
          <button v-tooltip="'暂时隐藏 (不丢失数据)'" class="p-2 text-text-dim hover:text-accent-special hover:bg-accent-special/10 rounded-lg transition-all" @click="appStore.uiState.showAiReviewModal = false">
            <X class="size-6" />
          </button>
        </div>

        <!-- 列表内容区 -->
        <div data-tour="ai-review-list" class="flex-1 overflow-y-auto p-6 space-y-3 custom-scrollbar relative z-10">
          
          <!-- 正在加载动画 (首批数据未到达时显示) -->
          <div v-if="appStore.aiState.isLoading && appStore.aiBatchResults.length === 0" class="flex flex-col items-center justify-center h-full opacity-60">
            <div class="text-accent-special animate-bounce mb-4"><Cpu class="size-12 opacity-50" /></div>
            <div class="text-sm text-text-dim tracking-widest uppercase font-mono">Connecting to Neural Network...</div>
          </div>

          <transition-group name="list">
            <!-- 单个 Mod 卡片 -->
            <div v-for="(item, index) in appStore.aiBatchResults" :key="item.package_id" data-tour="ai-review-card"
                class="group rounded-xl border overflow-hidden hover:shadow-[0_4px_20px_rgba(var(--color-accent-special),0.1)] transition-all flex flex-col relative"
                :class="(!item.alias_name || !item.notes) ? 'bg-accent-warn/5 border-accent-warn/50 shadow-[0_0_15px_rgba(var(--color-accent-warn),0.15)]' : 'bg-black/30 border-text-main/10 hover:border-accent-special/50'">
              
                <!-- 如果是失败项，右上角加一个绝对定位的警告角标 -->
              <div v-if="!item.alias_name || !item.notes" class="absolute bottom-0 right-0 px-3 py-1 bg-accent-warn/20 text-accent-warn text-[0.6rem] z-50 backdrop-blur-xs font-bold rounded-tl-lg rounded-br-xl border-t border-l border-accent-warn/30">
                ⚠ 生成失败，请手填或重试
              </div>

              <div class="flex flex-1 p-3 gap-4 relative">
                
                <!-- 左侧：原始信息区 (占比 5/12) -->
                <div class="w-4/12 flex gap-3 pr-4 border-r border-text-main/10">
                  <!-- 图标 -->
                  <div class="shrink-0 mt-1">
                    <img v-if="getMod(item.package_id)?.preview_path" :src="appStore.getThumbUrl(item.package_id, getMod(item.package_id).preview_path)" class="size-10 rounded-lg object-cover border border-text-main/10 shadow-md">
                    <div v-else class="size-10 rounded-lg border border-dashed border-text-main/20 flex items-center justify-center bg-black/20 text-text-dim/50">
                      <FolderInput class="size-5" />
                    </div>
                  </div>
                  <!-- 文字 -->
                  <div class="flex-1 min-w-0 flex flex-col">
                    <div class="text-[0.65rem] text-text-dim font-bold tracking-wider mb-0.5 flex justify-between">
                      <span>原始信息</span>
                      <span class="font-mono opacity-50 truncate ml-2">{{ item.package_id }}</span>
                    </div>
                    <!-- 原名 (挂载预览指令) -->
                    <div class="text-xs font-bold text-text-main truncate cursor-help hover:text-accent-primary transition-colors"
                        v-preview="getMod(item.package_id)">
                      {{ getMod(item.package_id)?.name || item.package_id }}
                    </div>
                    <!-- 原描述 -->
                    <div class="text-[0.6rem] text-text-dim mt-1 line-clamp-5 leading-relaxed" :title="getMod(item.package_id)?.description">
                      {{ getMod(item.package_id)?.description || '暂无描述信息...' }}
                    </div>
                  </div>
                </div>

                <!-- 中间：生成信息编辑区 (占比 7/12) -->
                <div class="w-8/12 flex flex-col gap-1">
                  <!-- 别名输入 -->
                  <div class="flex items-center gap-2">
                      <label class="w-12 shrink-0 text-[0.65rem] text-right uppercase text-accent-special font-bold tracking-widest" :class="{'text-accent-warn': !item.alias_name}" >
                        AI 别名
                      </label>
                      <input v-model="item.alias_name" placeholder="请输入或点击重试生成..."
                        class="flex-1 bg-black/40 border rounded-md px-3 py-1.5 text-sm text-accent-cool font-medium focus:outline-none transition-all"
                        :class="!item.alias_name ? 'border-accent-warn/50 focus:border-accent-warn focus:ring-1 focus:ring-accent-warn/30 placeholder-accent-warn/50' : 'border-text-main/10 focus:border-accent-special focus:ring-1 focus:ring-accent-special/30'" />
                  </div>
                  <!-- 备注输入 -->
                  <div class="flex items-start gap-2 flex-1">
                      <label class="w-12 shrink-0 text-[0.65rem] text-right uppercase text-accent-special font-bold tracking-widest mt-2" :class="{'text-accent-warn': !item.notes}" >
                      AI 备注
                      </label>
                      <textarea v-model="item.notes" placeholder="请输入或点击重试生成..."
                        class="flex-1 h-full bg-black/40 border rounded-md px-3 py-2 text-xs text-text-main leading-relaxed focus:outline-none resize-none custom-scrollbar transition-all"
                        :class="!item.notes ? 'border-accent-warn/50 focus:border-accent-warn focus:ring-1 focus:ring-accent-warn/30 placeholder-accent-warn/50' : 'border-text-main/10 focus:border-accent-special focus:ring-1 focus:ring-accent-special/30'">
                      </textarea>
                  </div>
                </div>

                <!-- 右侧绝对定位悬浮操作栏 (默认透明，Hover显现) -->
                <div class="absolute right-1 top-1 flex justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity bg-bg-surface/80 backdrop-blur-sm p-1 rounded-lg border border-text-main/10">
                  <!-- 重新生成按钮 -->
                  <button @click="regenerateItem(item)" v-tooltip="'重新生成此项'" :disabled="regeneratingIds.has(item.package_id)"
                    class="p-2 rounded-md hover:bg-accent-special/20 text-accent-special transition-colors disabled:opacity-50">
                    <Wand2 v-if="!regeneratingIds.has(item.package_id)" class="size-4" />
                    <svg v-else class="animate-spin size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                  </button>
                  <!-- 丢弃按钮 -->
                  <button @click="removeItem(index)" v-tooltip="'丢弃此结果'" 
                    class="p-2 rounded-md hover:bg-accent-danger/20 text-accent-danger transition-colors">
                    <Trash2 class="size-4" />
                  </button>
                </div>

              </div>
            </div>
          </transition-group>
        </div>

        <!-- Footer -->
        <div data-tour="ai-review-footer" class="py-4 px-6 bg-text-main/5 border-t border-text-main/10 flex justify-between items-center shrink-0 relative z-10">
          <div class="flex flex-col">
            <div class="flex items-center gap-2">
              <span class="relative flex h-2 w-2">
                <span v-if="appStore.aiState.isLoading" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-special opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2" :class="appStore.aiState.isLoading ? 'bg-accent-special' : 'bg-green-500'"></span>
              </span>
              <span class="text-sm font-bold" :class="appStore.aiState.isLoading ? 'text-accent-special' : 'text-text-dim'">
                  {{ appStore.aiState.isLoading ? '后台批量处理中...' : '全队列处理完毕' }}
              </span>
            </div>
            <!-- 进度提示 (利用之前已有的进度状态) -->
            <div v-if="appStore.aiState.isLoading" class="text-xs text-text-dim mt-1 ml-4 font-mono">
              {{ appStore.aiState.message }} ({{ appStore.aiState.percent }}%)
            </div>
          </div>
          
          <div class="flex gap-3">
            <button @click="appStore.uiState.showAiReviewModal = false" class="px-6 py-2 rounded-lg text-sm text-text-dim hover:text-text-main hover:bg-text-main/10 transition-colors">
              稍后处理
            </button>
            <button data-tour="ai-review-save" @click="saveAll" :disabled="appStore.aiBatchResults.length === 0"
              class="relative overflow-hidden px-8 py-2 rounded-lg bg-accent-special hover:bg-accent-special/80 text-black text-sm font-black transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_15px_rgba(var(--color-accent-special),0.3)] group">
              <div class="absolute inset-0 bg-white/20 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              确认保存 ({{ appStore.aiBatchResults.length }})
            </button>
          </div>
        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref } from 'vue'
import { Cpu, X, Wand2, Trash2, FolderInput } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useModStore } from '../stores/modStore'
import { useToast } from 'vue-toastification'

const appStore = useAppStore()
const modStore = useModStore()
const toast = useToast()

// 跟踪正在单项重新生成的 ID
const regeneratingIds = ref(new Set())

// 获取完整的 Mod 对象 (用于展示原图、原名、支持 v-preview)
const getMod = (pid) => {
  return modStore.takeModById(pid)
}

// 丢弃单项
const removeItem = (index) => {
  appStore.aiBatchResults.splice(index, 1)
}

// 单项重新生成功能
const regenerateItem = async (item) => {
  const mod = getMod(item.package_id)
  if (!mod) return
  regeneratingIds.value.add(item.package_id)
  try {
    // 调用 appStore 中已封装好的单次 AI 执行方法 (复用 ModDetails 里的逻辑)
    const res = await appStore.useAI('alias_generation', {
      name: mod.name,
      description: mod.description,
    })
    
    if (res) {
      item.alias_name = res.alias_name
      item.notes = res.notes
      toast.success(`[${mod.name || item.package_id}] 已重新生成`)
    }
  } catch (e) {
    toast.error(`重新生成失败: ${e.message}`)
  } finally {
    regeneratingIds.value.delete(item.package_id)
  }
}

// 全部保存
const saveAll = async () => {
  // 1. 组装数据数组
  const updates = appStore.aiBatchResults.map(item => ({
    mod_id: item.package_id,
    alias_name: item.alias_name,
    notes: item.notes
  }))
  // 2. 调用 modStore 的批量更新方法
  const success = await modStore.batchUpdateModsUserData(updates)
  
  if (success) {
    // toast 在 modStore 里已经发过了
    appStore.aiBatchResults = []
    appStore.uiState.showAiReviewModal = false
  }
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.list-enter-active, .list-leave-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.list-enter-from, .list-leave-to { opacity: 0; transform: scale(0.98) translateY(10px); }
.list-leave-active { position: absolute; } /* 确保移除时的平滑过渡 */

.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(var(--color-accent-special), 0.5); }
</style>
