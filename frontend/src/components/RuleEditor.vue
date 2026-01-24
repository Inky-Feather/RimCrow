<template>
  <Transition name="scale">
    <div v-if="visible" class="fixed inset-0 z-100 flex items-center justify-center bg-black/80 backdrop-blur-md p-6" @click.self="close">
      
      <div class="w-full max-w-7xl h-full max-h-[850px] flex bg-bg-deep border border-white/10 rounded-2xl shadow-3xl overflow-hidden relative">
        
        <!-- ================= 左侧：规则矩阵 (Matrix) ================= -->
        <div class="flex-1 flex flex-col min-w-0 bg-black/20">
          
          <!-- 头部：当前编辑目标 -->
          <header class="h-20 px-6 border-b border-white/5 flex items-center justify-between bg-bg-surface/50">
            <div class="flex items-center gap-4">
              <div class="w-12 h-12 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center overflow-hidden shadow-lg">
                <img v-if="targetMod?.icon_url" :src="targetMod.icon_url" class="w-full h-full object-cover">
                <span v-else class="text-xs text-text-dim font-bold font-mono">MOD</span>
              </div>
              <div>
                <div class="text-[10px] uppercase font-bold text-text-dim tracking-wider mb-0.5">正在编辑规则</div>
                <h2 class="text-xl font-bold text-white truncate max-w-lg">{{ targetMod?.name || 'Unknown Mod' }}</h2>
                <div class="text-xs font-mono text-text-dim/60">{{ targetId }}</div>
              </div>
            </div>
            
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/5 text-[10px] text-text-dim">
                <span class="w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_5px_rgba(59,130,246,0.5)]"></span> 原生
                <span class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)] ml-2"></span> 社区
                <span class="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_5px_rgba(245,158,11,0.5)] ml-2"></span> 用户
              </div>
              <button @click="close" class="p-2 rounded-lg hover:bg-white/10 text-text-dim hover:text-white transition-colors">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </header>

          <!-- 矩阵主体 -->
          <div class="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
            
            <!-- 循环渲染三种类型: LoadAfter, LoadBefore, Incompatible -->
            <section v-for="type in ruleTypes" :key="type.key" class="space-y-2">
              <div class="flex items-center gap-2 px-1">
                <component :is="type.icon" class="w-4 h-4" :class="type.colorClass" />
                <h3 class="text-xs font-bold uppercase tracking-wider text-white">{{ type.label }}</h3>
                <span class="text-[10px] text-text-dim opacity-60">({{ type.desc }})</span>
              </div>

              <div class="grid grid-cols-3 gap-4 h-64">
                
                <!-- 1. 原生规则 (Native) -->
                <div class="bg-blue-500/5 border border-blue-500/10 rounded-xl p-3 flex flex-col relative group/panel">
                  <div class="text-[10px] font-bold text-blue-400/50 mb-2 uppercase flex justify-between">About.xml <span class="opacity-50">Read-only</span></div>
                  <div class="flex-1 overflow-y-auto custom-scrollbar space-y-1">
                    <div v-for="item in getNativeRules(type.key)" :key="item" 
                      class="px-2 py-1.5 rounded bg-blue-500/10 border border-blue-500/20 text-xs text-blue-100 truncate flex items-center gap-2">
                      <span class="w-1 h-4 rounded-full bg-blue-500/50 shrink-0"></span>
                      <span class="truncate" :title="item">{{ getModName(item) }}</span>
                    </div>
                    <div v-if="!getNativeRules(type.key).length" class="h-full flex items-center justify-center text-[10px] text-blue-400/20 italic">无定义</div>
                  </div>
                </div>

                <!-- 2. 社区规则 (Community) -->
                <div class="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-3 flex flex-col relative">
                  <div class="text-[10px] font-bold text-emerald-400/50 mb-2 uppercase flex justify-between">RimSort DB <span class="opacity-50">Read-only</span></div>
                  <div class="flex-1 overflow-y-auto custom-scrollbar space-y-1">
                    <div v-for="(info, id) in getCommunityRules(type.key)" :key="id" 
                      v-tooltip="formatCommTooltip(info)"
                      class="px-2 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-100 truncate flex items-center gap-2 cursor-help group/item">
                      <span class="w-1 h-4 rounded-full bg-emerald-500/50 shrink-0"></span>
                      <span class="truncate">{{ getModName(id) }}</span>
                      <svg v-if="info.comment" class="w-3 h-3 ml-auto opacity-50 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                    </div>
                    <div v-if="Object.keys(getCommunityRules(type.key)).length === 0" class="h-full flex items-center justify-center text-[10px] text-emerald-400/20 italic">无建议</div>
                  </div>
                </div>

                <!-- 3. 用户规则 (User) - 可拖入区域 -->
                <div 
                  class="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3 flex flex-col relative transition-colors"
                  :class="{'ring-2 ring-amber-500/50 bg-amber-500/10': isDraggingOver === type.key}"
                  @dragover.prevent="isDraggingOver = type.key"
                  @dragleave.prevent="isDraggingOver = null"
                  @drop="onDrop($event, type.key)"
                >
                  <div class="text-[10px] font-bold text-amber-400/60 mb-2 uppercase flex justify-between">
                    User Rule <span class="text-amber-500 font-normal normal-case opacity-80">拖拽 Mod 至此添加</span>
                  </div>
                  
                  <div class="flex-1 overflow-y-auto custom-scrollbar space-y-1">
                    <TransitionGroup name="list">
                      <div v-for="(val, id) in getUserRules(type.key)" :key="id" 
                        class="group/uitem px-2 py-1.5 rounded bg-amber-500/10 border border-amber-500/20 text-xs text-amber-100 flex items-center gap-2 hover:bg-amber-500/20 transition-colors">
                        <span class="w-1 h-4 rounded-full bg-amber-500/50 shrink-0"></span>
                        <div class="flex-1 min-w-0">
                          <div class="truncate font-medium">{{ getModName(id) }}</div>
                          <div class="truncate text-[9px] opacity-50 font-mono">{{ id }}</div>
                        </div>
                        <button @click="removeUserRule(type.key, id)" class="p-1 rounded hover:bg-amber-500/30 text-amber-300 opacity-0 group-hover/uitem:opacity-100 transition-opacity">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                        </button>
                      </div>
                    </TransitionGroup>
                    
                    <div v-if="Object.keys(getUserRules(type.key)).length === 0" class="h-full flex flex-col items-center justify-center text-amber-400/20 pointer-events-none">
                      <svg class="w-8 h-8 mb-2 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4"/></svg>
                      <span class="text-[10px] italic">拖拽 Mod 到这里</span>
                    </div>
                  </div>
                </div>

              </div>
            </section>

          </div>
        </div>

        <!-- ================= 右侧：Mod 资源库 (Source List) ================= -->
        <div class="w-80 border-l border-white/5 bg-black/10 flex flex-col">
          <div class="p-4 border-b border-white/5 bg-white/2">
            <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider mb-2">模组库</h3>
            <div class="relative">
              <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
              <input v-model="searchQuery" placeholder="搜索 Mod..." class="w-full bg-black/30 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-xs text-white focus:border-accent-primary outline-none transition-all" />
            </div>
          </div>

          <div class="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            <div v-for="mod in filteredSourceList" :key="mod.package_id"
              draggable="true"
              @dragstart="onDragStart($event, mod)"
              class="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 border border-transparent hover:border-white/10 cursor-grab active:cursor-grabbing transition-all group"
            >
              <!-- 图标 -->
              <div class="w-8 h-8 rounded bg-black/30 border border-white/10 flex items-center justify-center overflow-hidden shrink-0">
                 <img v-if="mod.icon_url" :src="mod.icon_url" class="w-full h-full object-cover">
                 <div v-else class="text-[8px] text-text-dim font-bold">{{ mod.name.substring(0,2) }}</div>
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-xs font-bold text-text-main truncate group-hover:text-white">{{ mod.name }}</div>
                <div class="text-[10px] text-text-dim font-mono truncate opacity-60">{{ mod.package_id }}</div>
              </div>
              <div class="opacity-0 group-hover:opacity-100 text-text-dim">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 9l4 0l0-4"/><path d="M3 3l6 6"/><path d="M5 15l4 0l0 4"/><path d="M3 21l6-6"/><path d="M19 9l-4 0l0-4"/><path d="M21 3l-6 6"/><path d="M19 15l-4 0l0 4"/><path d="M21 21l-6-6"/></svg>
              </div>
            </div>
            
            <div v-if="filteredSourceList.length === 0" class="p-4 text-center text-xs text-text-dim opacity-50">
              未找到相关 Mod
            </div>
          </div>
        </div>

      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useModStore } from '../stores/modStore'
import { useRuleStore } from '../stores/ruleStore'
import { useConfirmStore } from '../stores/confirmStore'
import { ArrowDownToLine, ArrowUpToLine, AlertTriangle } from 'lucide-vue-next'

const props = defineProps(['modelValue', 'targetId']) // v-model:visible, targetId
const emit = defineEmits(['update:modelValue', 'close'])

const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const close = () => emit('update:modelValue', false)

// --- 状态 ---
const targetMod = computed(() => modStore.takeModById(props.targetId))
const searchQuery = ref('')
const isDraggingOver = ref(null) // 'loadAfter' | 'loadBefore' | 'incompatibleWith' | null

const ruleTypes = [
  { key: 'loadAfter', label: 'Load After', desc: '此 Mod 必须在下列 Mod 之后加载', icon: ArrowDownToLine, colorClass: 'text-accent-warn' },
  { key: 'loadBefore', label: 'Load Before', desc: '此 Mod 必须在下列 Mod 之前加载', icon: ArrowUpToLine, colorClass: 'text-accent-primary' },
  { key: 'incompatibleWith', label: 'Incompatible', desc: '此 Mod 与下列 Mod 冲突', icon: AlertTriangle, colorClass: 'text-accent-danger' }
]

// --- 数据获取器 ---
// 1. Native
const getNativeRules = (type) => {
  if (!targetMod.value) return []
  if (type === 'loadAfter') return targetMod.value.load_after_mods || []
  if (type === 'loadBefore') return targetMod.value.load_before_mods || []
  if (type === 'incompatibleWith') return targetMod.value.incompatible_mods || []
  return []
}

// 2. Community
const getCommunityRules = (type) => {
  const rules = ruleStore.communityModRules[props.targetId?.toLowerCase()]
  if (!rules) return {}
  return rules[type] || {}
}

// 3. User
const getUserRules = (type) => {
  const rules = ruleStore.userModRules[props.targetId?.toLowerCase()]
  if (!rules) return {}
  return rules[type] || {}
}

// --- 辅助 ---
const getModName = (id) => modStore.displayModName(id)

const formatCommTooltip = (info) => {
  if (!info.comment) return null
  return Array.isArray(info.comment) ? info.comment.join('\n') : info.comment
}

const filteredSourceList = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  const selfId = props.targetId?.toLowerCase()
  
  return Array.from(modStore.allModsMap.values())
    .filter(m => !m.is_missing && m.package_id.toLowerCase() !== selfId) // 排除自身和缺失项
    .filter(m => m.name.toLowerCase().includes(q) || m.package_id.toLowerCase().includes(q))
    .slice(0, 50) // 性能优化：只显示前50个结果
})

// --- 拖拽交互 ---
const onDragStart = (e, mod) => {
  e.dataTransfer.setData('text/plain', mod.package_id)
  e.dataTransfer.effectAllowed = 'copy'
}

const onDrop = async (e, ruleType) => {
  isDraggingOver.value = null
  const sourceId = e.dataTransfer.getData('text/plain')
  if (!sourceId || sourceId === props.targetId) return
  
  // 调用 RuleStore 添加规则
  await ruleStore.addUserModRule(props.targetId, ruleType, sourceId)
}

const removeUserRule = async (ruleType, otherId) => {
  await ruleStore.removeUserModRuleItem(props.targetId, ruleType, otherId)
}

// 每次打开时重新获取规则，确保最新
watch(visible, (val) => {
  if (val) {
    ruleStore.fetchRules()
  }
})

</script>

<style scoped>
.scale-enter-active, .scale-leave-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.scale-enter-from, .scale-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

.list-enter-active,
.list-leave-active {
  transition: all 0.2s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}
</style>