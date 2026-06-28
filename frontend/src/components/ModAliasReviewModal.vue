<template>
  <transition name="fade">
    <div v-if="appStore.uiState.showModAliasReviewModal" class="fixed inset-0 z-120 flex items-center justify-center bg-bg-deep/80 backdrop-blur-md">
      <!-- 主容器：批量别名检阅工作台 -->
      <div class="w-[90%] max-w-7xl h-[86vh] flex flex-col bg-bg-surface/92 border border-accent-special/25 rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.6)] overflow-hidden relative">
        <!-- 顶部标题栏：任务总览与关闭入口 -->
        <div class="px-6 py-4 border-b border-text-main/10 flex items-start justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-lg font-black text-text-main">模组别名检阅</h2>
            <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-dim">
              <span>待检阅任务 {{ totalTaskCount }} 组</span>
              <span>待检阅条目 {{ totalPendingItems }} 项</span>
            </div>
          </div>
          <button class="p-2 rounded-lg text-text-dim hover:text-accent-special hover:bg-accent-special/10 transition-all" @click="closeModal">
            <X class="size-5" />
          </button>
        </div>

        <!-- 主滚动区：按任务组展示待检阅结果 -->
        <div class="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
          <div v-if="reviewTasks.length === 0" class="h-full flex items-center justify-center text-sm text-text-dim/70">
            当前没有待检阅的批量结果
          </div>

          <div v-for="group in reviewTasks" :key="group.taskId" class="rounded-2xl border border-text-main/10 bg-black/20 overflow-hidden" >
            <!-- 任务组头部：显示生成轮次、输入规模与状态 -->
            <div class="px-5 py-4 border-b border-text-main/10 bg-black/20">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <div class="text-base font-black text-text-main">{{ group.title || '模组别名生成任务' }}</div>
                  <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-text-dim">
                    <span>任务ID: {{ group.taskId }}</span>
                    <span>创建时间: {{ formatTime(group.meta?.created_at || group.createdAt) }}</span>
                    <span>轮次: {{ Number(group.meta?.attempt_count || 0) }}/{{ Number(group.meta?.max_attempts || 3) }}</span>
                    <span>输入: {{ Number(group.meta?.input_total || group.inputPackageIds?.length || 0) }}</span>
                    <span>成功: {{ Number(group.meta?.resolved_count || countSucceeded(group.items)) }}</span>
                    <span v-if="countFailed(group.items) > 0">失败: {{ countFailed(group.items) }}</span>
                  </div>
                </div>
                <span class="px-2 py-1 rounded text-[0.65rem] font-bold shrink-0" :class="taskStatusClass(group)">
                  {{ taskStatusLabel(group) }}
                </span>
              </div>
            </div>

            <div class="p-4 space-y-3">
              <div v-for="(item, index) in group.items" :key="`${group.taskId}:${item.package_id}`" class="group rounded-xl border overflow-hidden transition-all flex flex-col relative"
                :class="item._failed ? 'bg-accent-warn/5 border-accent-warn/50 shadow-[0_0_15px_rgba(var(--color-accent-warn),0.12)]' : 'bg-black/30 border-text-main/10 hover:border-accent-special/40'" >
                <!-- 单条检阅卡片：左侧原始模组信息，右侧 AI 结果输入区 -->
                <div v-if="item._failed" class="absolute bottom-0 right-0 px-3 py-1 bg-accent-warn/20 text-accent-warn text-[0.6rem] z-50 font-bold rounded-tl-lg rounded-br-xl border-t border-l border-accent-warn/30">
                  ⚠ 生成失败，请手填或重试
                </div>

                <div class="flex flex-1 p-3 gap-4 relative">
                  <div class="w-4/12 flex gap-3 pr-4 border-r border-text-main/10">
                    <div class="shrink-0 mt-1">
                      <img v-if="getMod(item.package_id)?.preview_path" :src="appStore.getThumbUrl(item.package_id, getMod(item.package_id).preview_path)"
                        class="size-10 rounded-lg object-cover border border-text-main/10 shadow-md" >
                      <div v-else class="size-10 rounded-lg border border-dashed border-text-main/20 flex items-center justify-center bg-black/20 text-text-dim/50">
                        <FolderInput class="size-5" />
                      </div>
                    </div>
                    <div class="flex-1 min-w-0 flex flex-col">
                      <div class="text-[0.65rem] text-text-dim font-bold tracking-wider mb-0.5">原始信息</div>
                      <div class="text-xs font-bold text-text-main truncate cursor-help hover:text-accent-primary transition-colors" v-preview="getMod(item.package_id)">
                        {{ getMod(item.package_id)?.name || item.package_id }}
                      </div>
                      <div class="text-[0.6rem] text-text-dim mt-1 line-clamp-5 leading-relaxed" :title="getMod(item.package_id)?.description">
                        {{ getMod(item.package_id)?.description || '暂无描述信息...' }}
                      </div>
                    </div>
                  </div>

                  <div class="w-8/12 flex flex-col gap-1">
                    <div class="flex items-center gap-2">
                      <label class="w-12 shrink-0 text-[0.65rem] text-right uppercase text-accent-special font-bold tracking-widest" :class="{ 'text-accent-warn': !item.alias_name }">
                        AI 别名
                      </label>
                      <input v-model="item.alias_name" placeholder="请输入或点击重试生成..."
                        class="flex-1 bg-black/40 border rounded-md px-3 py-1.5 text-sm text-accent-cool font-medium focus:outline-none transition-all"
                        :class="!item.alias_name ? 'border-accent-warn/50 focus:border-accent-warn focus:ring-1 focus:ring-accent-warn/30 placeholder-accent-warn/50' : 'border-text-main/10 focus:border-accent-special focus:ring-1 focus:ring-accent-special/30'" 
                      />
                    </div>
                    <div class="flex items-start gap-2 flex-1">
                      <label class="w-12 shrink-0 text-[0.65rem] text-right uppercase text-accent-special font-bold tracking-widest mt-2" :class="{ 'text-accent-warn': !item.notes }">
                        AI 备注
                      </label>
                      <textarea v-model="item.notes" placeholder="请输入或点击重新生成..."
                        class="flex-1 h-full bg-black/40 border rounded-md px-3 py-2 text-xs text-text-main leading-relaxed focus:outline-none resize-none transition-all"
                        :class="!item.notes ? 'border-accent-warn/50 focus:border-accent-warn focus:ring-1 focus:ring-accent-warn/30 placeholder-accent-warn/50' : 'border-text-main/10 focus:border-accent-special focus:ring-1 focus:ring-accent-special/30'">
                      </textarea>
                    </div>
                  </div>

                  <div class="absolute right-1 top-1 flex justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity bg-bg-surface/80 backdrop-blur-sm p-1 rounded-lg border border-text-main/10">
                    <button class="p-2 rounded-md hover:bg-accent-special/20 text-accent-special transition-colors disabled:opacity-50"
                      :disabled="regeneratingIds.has(item.package_id)" @click="regenerateItem(group.taskId, item)" >
                      <Wand2 v-if="!regeneratingIds.has(item.package_id)" class="size-4" v-tooltip="'重新生成'" />
                      <svg v-else class="animate-spin size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                    </button>
                    <button class="p-2 rounded-md hover:bg-accent-danger/20 text-accent-danger transition-colors" @click="removeItem(group.taskId, index)">
                      <Trash2 class="size-4" v-tooltip="'移除'" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="px-5 py-3 border-t border-text-main/10 bg-black/15 flex items-center justify-end gap-3">
              <button class="px-4 py-2 rounded-lg text-sm text-accent-danger bg-accent-danger/10 hover:bg-accent-danger/20 transition-colors"
                @click="removeTaskGroup(group.taskId)" >
                移除此组
              </button>
              <button class="px-5 py-2 rounded-lg bg-accent-special text-black text-sm font-black disabled:opacity-40"
                :disabled="!group.items.length" @click="saveTaskGroup(group.taskId)" >
                应用本组 ({{ group.items.length }})
              </button>
            </div>
          </div>
        </div>

        <!-- 底部总操作栏：保留、清空或一次性应用全部结果 -->
        <div class="px-6 py-4 border-t border-text-main/10 flex items-center justify-between gap-4">
          <div class="text-xs text-text-dim">
            未确认应用前，结果会一直保留在这里，可随时回来继续检阅。
          </div>
          <div class="flex items-center gap-3">
            <button class="px-4 py-2 rounded-lg text-sm text-accent-danger bg-accent-danger/10 hover:bg-accent-danger/20 transition-colors disabled:opacity-40"
              :disabled="reviewTasks.length === 0" @click="clearAll" >
              清空全部
            </button>
            <button class="px-5 py-2 rounded-lg bg-text-main/10 text-text-main text-sm font-bold hover:bg-text-main/15 transition-colors"
              @click="closeModal" >
              稍后处理
            </button>
            <button class="px-5 py-2 rounded-lg bg-accent-special text-black text-sm font-black disabled:opacity-40"
              :disabled="reviewTasks.length === 0" @click="applyAll" >
              应用全部 ({{ totalPendingItems }})
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { FolderInput, Trash2, Wand2, X } from 'lucide-vue-next'
import { useAiStore } from '../stores/aiStore'
import { useAppStore } from '../stores/appStore'
import { useModStore } from '../stores/modStore'
import { useToast } from 'vue-toastification'
import { normalizeText } from '../utils/common'

// -----------------------------------------------------------------
// Store 依赖 (Stores)
// -----------------------------------------------------------------
const appStore = useAppStore()
const aiStore = useAiStore()
const modStore = useModStore()
const toast = useToast()

// -----------------------------------------------------------------
// 状态定义 (State / Refs)
// -----------------------------------------------------------------
const regeneratingIds = ref(new Set())

// -----------------------------------------------------------------
// 计算属性 (Computed)
// -----------------------------------------------------------------
const reviewTasks = computed(() => aiStore.modAliasReviewTasks || [])
const totalPendingItems = computed(() => aiStore.modAliasReviewItemCount || 0)
const totalTaskCount = computed(() => reviewTasks.value.length)

// -----------------------------------------------------------------
// 工具方法 (Utils)
// -----------------------------------------------------------------
const getMod = (packageId = '') => modStore.takeModById(packageId)

/** 统计当前任务组中已经产出有效别名或备注的条目数。 */
const countSucceeded = (items = []) => items.filter(item => item && !item._failed && (item.alias_name || item.notes)).length
/** 统计当前任务组中明确生成失败的条目数。 */
const countFailed = (items = []) => items.filter(item => item && item._failed).length

const formatTime = (value) => {
  /** 把任务时间戳转成检阅面板里的人类可读文本。 */
  const numeric = Number(value || 0)
  if (!numeric) return '未知'
  try {
    return new Date(numeric).toLocaleString('zh-CN')
  } catch {
    return '未知'
  }
}

const taskStatusLabel = (group) => {
  /** 把后端任务状态归一化成界面用短标签。 */
  const status = String(group?.status || '').toLowerCase()
  if (status === 'running') return '处理中'
  if (status === 'pending') return '排队中'
  if (status === 'cancelled') return '已取消'
  if (status === 'error' || status === 'failed') return '失败'
  return '待检阅'
}

const taskStatusClass = (group) => {
  /** 根据任务状态返回对应的视觉语义色。 */
  const status = String(group?.status || '').toLowerCase()
  if (status === 'running' || status === 'pending') return 'bg-accent-special/20 text-accent-special'
  if (status === 'cancelled') return 'bg-accent-warn/20 text-accent-warn'
  if (status === 'error' || status === 'failed') return 'bg-accent-danger/20 text-accent-danger'
  return 'bg-accent-success/20 text-accent-success'
}

// -----------------------------------------------------------------
// 业务方法 (Methods)
// -----------------------------------------------------------------
const closeModal = () => {
  /** 关闭检阅弹窗，但不主动丢弃当前待审数据。 */
  appStore.uiState.showModAliasReviewModal = false
}

const removeTaskGroup = (taskId) => {
  /** 从待审池中移除整组任务结果。 */
  aiStore.removeModAliasReviewTask(taskId)
  if (reviewTasks.value.length === 0) {
    closeModal()
  }
}

const removeItem = (taskId, index) => {
  /** 从任务组中移除单个条目。 */
  const group = aiStore.getModAliasReviewTask(taskId)
  if (!group) return
  const item = group.items[index]
  if (!item?.package_id) return
  aiStore.removeModAliasReviewTaskItem(taskId, item.package_id)
  if (reviewTasks.value.length === 0) {
    closeModal()
  }
}

const regenerateItem = async (taskId, item) => {
  const mod = getMod(item.package_id)
  if (!mod) return
  // 单项重生只回填当前条目，避免整组任务重新排队带来额外等待。
  regeneratingIds.value.add(item.package_id)
  try {
    const result = await aiStore.requestSingleModAliasGenerationResult({
      packageId: item.package_id,
      name: mod.name,
      description: mod.description,
      ownerType: 'review_modal',
    })
    if (result) {
      aiStore.updateModAliasReviewTaskItem(taskId, item.package_id, {
        alias_name: String(result.alias_name || ''),
        notes: String(result.notes || ''),
        _failed: false,
        _error: '',
      })
      toast.success(`[${mod.name || item.package_id}] 已重新生成`)
    } else {
      toast.error('重新生成失败')
    }
  } catch (error) {
    toast.error(`重新生成失败: ${error?.message || error}`)
  } finally {
    regeneratingIds.value.delete(item.package_id)
  }
}

const saveTaskGroup = async (taskId) => {
  /**
   * 将当前任务组的有效结果批量写回模组用户数据。
   *
   * 写回后整组会从待审池移除，因为它已经不再处于“需要人工确认”的状态。
   */
  const group = aiStore.getModAliasReviewTask(taskId)
  if (!group || !Array.isArray(group.items) || group.items.length === 0) return
  const updates = group.items
    .map(item => ({
      mod_id: item.package_id,
      alias_name: normalizeText(item.alias_name),
      notes: normalizeText(item.notes),
    }))
    .filter(item => item.alias_name || item.notes)
  // 空字符串不会写回，避免把用户已有别名/备注误清空。
  if (updates.length === 0) {
    toast.warning('当前任务还没有可应用的有效结果')
    return
  }
  const success = await modStore.batchUpdateModsUserData(updates)
  if (success && reviewTasks.value.length === 0) {
    closeModal()
  }
  if (success) {
    aiStore.removeModAliasReviewTask(taskId)
  }
}

const applyAll = async () => {
  // 这里按任务组串行写回，避免一次性堆太多批量更新请求，
  // 也方便在某一组失败时保留其余组的待审状态。
  const taskIds = reviewTasks.value.map(group => group.taskId)
  let appliedCount = 0
  for (const taskId of taskIds) {
    const group = aiStore.getModAliasReviewTask(taskId)
    if (!group || !Array.isArray(group.items) || group.items.length === 0) continue
    const updates = group.items
      .map(item => ({
        mod_id: item.package_id,
        alias_name: normalizeText(item.alias_name),
        notes: normalizeText(item.notes),
      }))
      .filter(item => item.alias_name || item.notes)
    if (updates.length === 0) continue
    const success = await modStore.batchUpdateModsUserData(updates)
    if (success) {
      appliedCount += 1
      aiStore.removeModAliasReviewTask(taskId)
    }
  }
  if (appliedCount > 0 && reviewTasks.value.length === 0) {
    closeModal()
  }
}

const clearAll = () => {
  /** 清空全部待审结果并关闭弹窗。 */
  aiStore.clearModAliasReviewTaskPool()
  closeModal()
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(var(--color-accent-special), 0.5); }
</style>
