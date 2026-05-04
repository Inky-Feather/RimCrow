<!-- frontend/src/components/PromptManager.vue -->
<template>
  <transition name="fade">
    <div v-if="appStore.uiState.showPromptManager" class="fixed inset-0 z-130 flex items-center justify-center bg-bg-deep/80 backdrop-blur-md">
      
      <!-- 主容器：大尺度铺满感 -->
      <div class="w-[90%] max-w-7xl h-[85vh] flex flex-col bg-bg-surface/95 border border-accent-special/30 rounded-2xl shadow-[0_0_80px_rgba(0,0,0,0.8)] overflow-hidden relative">
        
        <!-- 背景光效 -->
        <div class="absolute top-0 right-0 w-125 h-125 bg-accent-special/5 blur-[120px] rounded-full pointer-events-none"></div>

        <!-- 头部 -->
        <div class="h-16 px-6 bg-black/40 border-b border-text-main/10 flex items-center justify-between shrink-0 relative z-10">
          <div class="flex items-center gap-4">
            <div class="p-2 rounded-lg bg-accent-special/20 text-accent-special border border-accent-special/30">
              <Drama class="size-5" />
            </div>
            <div>
              <h2 class="text-lg font-black text-text-main tracking-widest">提示词管理中心</h2>
              <p class="text-[0.65rem] text-text-dim uppercase font-mono mt-0.5">管理提示词模板</p>
            </div>
          </div>
          <div class="flex items-center gap-3">
             <button @click="handleReset" class="text-xs text-text-dim hover:text-accent-warn hover:bg-accent-warn/10 px-3 py-1.5 rounded transition-colors flex items-center gap-2">
               <RotateCcw class="size-3.5"/> 恢复系统默认
             </button>
             <button class="p-2 text-text-dim hover:text-accent-special transition-colors" @click="closeModal">
               <X class="size-6" />
             </button>
          </div>
        </div>

        <!-- 主内容区：左右分栏 -->
        <div class="flex-1 flex overflow-hidden relative z-10">
          
          <!-- 左侧列表 -->
          <div class="w-1/4 min-w-60 bg-black/20 border-r border-text-main/10 flex flex-col">
            <!-- 添加按钮 -->
            <!-- <div class="p-4 border-b border-text-main/5">
              <button @click="createNew" class="w-full py-2 bg-accent-special/10 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 rounded-lg text-sm font-bold flex justify-center items-center gap-2 transition-all">
                <Plus class="size-4" /> 创建自定义模板
              </button>
            </div> -->
            
            <!-- 列表滚动区 -->
            <div class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
              <div v-for="(pData, pId) in prompts" :key="pId" 
                @click="selectPrompt(pId)"
                class="group p-3 rounded-lg cursor-pointer transition-all border border-transparent"
                :class="currentId === pId ? 'bg-accent-special/20 border-accent-special/50 shadow-[inset_4px_0_0_rgba(var(--color-accent-special),1)]' : 'hover:bg-text-main/5'">
                <div class="flex justify-between items-start mb-1">
                  <span class="text-sm font-bold text-text-main truncate pr-2" :class="{'text-accent-special': currentId === pId}">{{ pData.name }}</span>
                  <Lock v-if="pData.is_system" class="size-3 text-text-dim shrink-0" v-tooltip="'系统核心模板'" />
                  <User v-else class="size-3 text-accent-primary shrink-0" v-tooltip="'用户自定义模板'" />
                </div>
                <div class="text-[0.65rem] text-text-dim font-mono truncate">{{ pId }}</div>
              </div>
            </div>
          </div>

          <!-- 右侧编辑器 -->
          <div class="flex-1 flex flex-col bg-bg-surface/50 relative" v-if="currentForm">
            <!-- 工具栏 -->
            <div class="h-12 px-6 border-b border-text-main/10 flex justify-between items-center bg-black/10">
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono text-accent-special bg-accent-special/10 px-2 py-0.5 rounded border border-accent-special/20">
                  ID: <input v-model="formId" :disabled="currentForm.is_system || !isNew" class="bg-transparent w-40 outline-none placeholder:text-accent-special/30" placeholder="e.g. my_custom_task" />
                </span>
              </div>
              <div class="flex gap-2">
                <!-- <button v-if="!currentForm.is_system && !isNew" @click="handleDelete" class="px-4 py-1.5 rounded bg-accent-danger/10 hover:bg-accent-danger text-accent-danger hover:text-white border border-accent-danger/30 text-xs font-bold transition-all">
                  删除模板
                </button> -->
                <button @click="handleSave" class="px-6 py-1.5 rounded bg-accent-special hover:bg-accent-special/80 text-black text-xs font-bold shadow-[0_0_10px_rgba(var(--color-accent-special),0.3)] transition-all">
                  保存更改
                </button>
              </div>
            </div>

            <!-- 编辑表单 -->
            <div class="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6">
              
              <!-- 基础信息 -->
              <div class="grid grid-cols-2 gap-6">
                <div class="space-y-2">
                  <label class="text-xs uppercase text-text-dim font-bold tracking-widest flex items-center gap-2">
                    <TextCursorInput class="size-4" /> 模板显示名称
                  </label>
                  <input v-model="currentForm.name" class="w-full bg-black/40 border border-text-main/10 rounded-lg p-2.5 text-sm text-text-main focus:border-accent-special focus:outline-none transition-all"/>
                </div>
                <div class="space-y-2">
                  <label class="text-xs uppercase text-text-dim font-bold tracking-widest flex items-center gap-2">
                    <Info class="size-4" /> 模板功能描述
                  </label>
                  <input v-model="currentForm.description" class="w-full bg-black/40 border border-text-main/10 rounded-lg p-2.5 text-sm text-text-main focus:border-accent-special focus:outline-none transition-all"/>
                </div>
              </div>

              <!-- 动态变量提示 -->
              <div class="bg-accent-primary/5 border border-accent-primary/20 rounded-lg p-3">
                <div class="text-[0.65rem] uppercase text-accent-primary font-bold mb-2 flex items-center gap-1">
                  <Braces class="size-3" /> 侦测到的变量 (点击插入光标处)
                </div>
                <div class="flex flex-wrap gap-2">
                  <button v-for="varName in detectedVariables" :key="varName" @click="insertVar(varName)"
                    class="px-2 py-1 rounded-md bg-black/40 border border-accent-primary/30 text-xs text-accent-primary font-mono hover:bg-accent-primary hover:text-black transition-colors">
                    { {{ varName }} }
                  </button>
                  <span v-if="detectedVariables.length === 0" class="text-xs text-text-dim italic">文本中暂无 {xxx} 格式的变量</span>
                </div>
              </div>

              <!-- System Prompt -->
              <div class="space-y-2 flex-1 flex flex-col">
                <label class="text-xs uppercase text-text-dim font-bold tracking-widest flex items-center justify-between">
                  <span class="flex items-center gap-2"><Bot class="size-4 text-accent-special" /> System Prompt (角色设定)</span>
                  <span class="text-[0.6rem] font-mono opacity-50">Role: System</span>
                </label>
                <textarea v-model="currentForm.system" 
                  class="w-full min-h-30 bg-[#0a0a0a] border border-text-main/10 rounded-lg p-3 text-sm text-accent-cool leading-relaxed focus:border-accent-special focus:ring-1 focus:ring-accent-special/30 focus:outline-none resize-y custom-scrollbar font-mono"></textarea>
              </div>

              <!-- User Template -->
              <div class="space-y-2 flex-1 flex flex-col">
                <label class="text-xs uppercase text-text-dim font-bold tracking-widest flex items-center justify-between">
                  <span class="flex items-center gap-2"><User class="size-4 text-accent-primary" /> User Template (执行模板)</span>
                  <span class="text-[0.6rem] font-mono opacity-50">Role: User</span>
                </label>
                <textarea v-model="currentForm.user_template" id="userTemplateArea"
                  class="w-full min-h-40 bg-[#0a0a0a] border border-text-main/10 rounded-lg p-3 text-sm text-text-main leading-relaxed focus:border-accent-special focus:ring-1 focus:ring-accent-special/30 focus:outline-none resize-y custom-scrollbar font-mono"></textarea>
              </div>

            </div>
          </div>
          
          <!-- 空状态 -->
          <div class="flex-1 flex flex-col items-center justify-center text-text-dim/50" v-else>
             <TerminalSquare class="size-16 mb-4 opacity-20" />
             <p class="tracking-widest uppercase text-sm">Select or Create a Prompt</p>
          </div>

        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { TerminalSquare, Plus, Lock, User, TextCursorInput, Info, Bot, Braces, X, RotateCcw, Drama } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useConfirmStore } from '../stores/confirmStore'
import { useToast } from 'vue-toastification'
import { deepClone } from '../utils/common'

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const toast = useToast()

const prompts = ref({})
const currentId = ref(null)
const currentForm = ref(null)
const formId = ref('')
const isNew = ref(false)

// 加载数据
const loadData = async () => {
  prompts.value = await appStore.fetchPrompts()
  if (!currentId.value && Object.keys(prompts.value).length > 0) {
    selectPrompt(Object.keys(prompts.value)[0])
  }
}

watch(() => appStore.uiState.showPromptManager, (val) => {
  if (val) loadData()
})

const closeModal = () => {
  appStore.uiState.showPromptManager = false
}

// 选择提示词
const selectPrompt = (id) => {
  currentId.value = id
  formId.value = id
  isNew.value = false
  currentForm.value = deepClone(prompts.value[id])
}

// 创建新模板
const createNew = () => {
  currentId.value = null
  formId.value = ''
  isNew.value = true
  currentForm.value = {
    is_system: false,
    name: 'New Custom Task',
    description: '',
    system: 'You are a helpful assistant.',
    user_template: 'Here is my content: {content}'
  }
}

// 动态提取变量：使用正则解析 {} 中的文本
const detectedVariables = computed(() => {
  if (!currentForm.value) return []
  const text = (currentForm.value.system || '') + ' ' + (currentForm.value.user_template || '')
  const matches = text.match(/\{([a-zA-Z0-9_]+)\}/g)
  if (!matches) return []
  // 去重并去掉大括号
  const vars = [...new Set(matches.map(m => m.slice(1, -1)))]
  return vars
})

// 插入变量到 User Template 的光标位置 (简单实现追加)
const insertVar = (varName) => {
  if (currentForm.value) {
    currentForm.value.user_template += ` {${varName}} `
    // 如果想做精细的光标插入，可以操作 DOM，这里为了简洁使用追加
  }
}

const handleSave = async () => {
  if (!formId.value.trim()) return toast.error("ID 不能为空")
  // 英文和下划线校验
  if (!/^[a-zA-Z0-9_]+$/.test(formId.value)) return toast.warning("ID 只能包含字母、数字和下划线")

  const resData = await appStore.savePrompt(formId.value, currentForm.value)
  if (resData) {
    prompts.value = resData
    toast.success("模板保存成功")
    selectPrompt(formId.value) // 重新选中刷新状态
  }
}

const handleDelete = async () => {
  const ok = await confirmStore.confirmAction("危险操作", `确定要删除模板 ${formId.value} 吗？此操作不可逆。`, {type: 'error'})
  if (ok) {
    const resData = await appStore.deletePrompt(formId.value)
    if (resData) {
      prompts.value = resData
      currentForm.value = null
      currentId.value = null
      toast.success("模板已删除")
      if (Object.keys(prompts.value).length > 0) selectPrompt(Object.keys(prompts.value)[0])
    }
  }
}

const handleReset = async () => {
  const ok = await confirmStore.confirmAction("恢复默认", "这将把所有的系统核心模板恢复到出厂版本，您对它们的修改将丢失（不影响您自己新建的模板）。确定继续？", {type: 'warning'})
  if (ok) {
    const resData = await appStore.resetPrompts()
    if (resData) {
      prompts.value = resData
      toast.success("核心模板已恢复出厂设置")
      if (currentId.value) selectPrompt(currentId.value)
    }
  }
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(var(--color-accent-special), 0.5); }
</style>
