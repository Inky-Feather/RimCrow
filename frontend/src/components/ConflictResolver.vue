<template>
  <transition name="fade">
    <div v-if="visible" class="fixed inset-0 z-100 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div class="w-5/7 max-h-9/10 flex flex-col bg-bg-deep border border-accent-danger/30 rounded-xl shadow-2xl overflow-hidden">
        
        <!-- Header -->
        <div class="px-6 py-4 bg-accent-danger/10 border-b border-accent-danger/20 flex items-center justify-between shrink-0">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-full bg-accent-danger/20 text-accent-danger animate-pulse">
              <svg width="24" height="24" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            </div>
            <div>
              <h2 class="text-lg font-bold text-white">发现模组冲突</h2>
              <p class="text-xs text-text-dim">检测到 {{ conflicts.length }} 组重复的包ID。请为每一组选择一个<span class="text-accent-success font-bold">保留版本</span>。</p>
            </div>
          </div>
        </div>

        <!-- 滚动列表区 -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6">
          
          <!-- 循环每一组冲突 -->
          <div v-for="(group, gIndex) in conflicts" :key="group.package_id" class="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
            
            <!-- 组标题 -->
            <div class="flex-1 bg-black/20 px-4 py-2 border-b border-white/5 flex justify-between items-center">
              <div class="font-mono text-sm font-bold text-accent-highlight truncate">{{ group.package_id }}</div>
              <div class="text-[10px] text-text-dim">发现 {{ group.items.length }} 个版本</div>
            </div>

            <!-- 版本选项列表 -->
            <div class="p-3 grid gap-2 grid-cols-1">
              <div v-for="(mod, mIndex) in group.items" :key="mod.path"
                   @click="selectVersion(gIndex, mod.path)"
                   class="relative flex items-center p-3 rounded-lg border transition-all cursor-pointer group/item"
                   :class="selections[gIndex] === mod.path 
                      ? 'bg-accent-success/10 border-accent-success ring-1 ring-accent-success/50' 
                      : 'bg-black/20 border-white/5 opacity-70 hover:opacity-100 hover:border-white/20'"
              >
                <!-- 选中标记 -->
                <div class="w-5 h-5 rounded-full border flex items-center justify-center mr-4 shrink-0 transition-colors"
                     :class="selections[gIndex] === mod.path ? 'border-accent-success bg-accent-success text-black' : 'border-white/30'">
                  <svg v-if="selections[gIndex] === mod.path" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4"><path d="M20 6L9 17l-5-5"/></svg>
                </div>

                <!-- Mod 信息 -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-sm text-white truncate">{{ mod.name }}</span>
                    <span class="px-1.5 py-0.5 rounded bg-white/10 text-[10px] font-mono text-accent-primary">v{{ mod.version || '?' }}</span>
                    <span class="text-[10px] text-text-dim border border-white/10 px-1 rounded">{{ mod.source }}</span>
                  </div>
                  <div class="text-[10px] text-text-dim mt-1 truncate font-mono" :title="mod.path">{{ mod.path }}</div>
                </div>

                <!-- 未选中时的操作配置 (禁用/删除) -->
                <!-- 只有当此项未被选中时才显示 -->
                <div v-if="selections[gIndex] !== mod.path" 
                     class="ml-4 flex items-center gap-3 px-3 py-1.5 rounded bg-black/40 border border-white/5"
                     @click.stop>
                  <span class="text-[10px] text-text-dim">未保留项:</span>
                  <label class="flex items-center gap-1 cursor-pointer hover:text-white transition-colors">
                    <input type="radio" :name="`act-${gIndex}-${mIndex}`" value="disable" 
                           v-model="actionMap[mod.path]" class="accent-accent-primary w-3 h-3">
                    <span class="text-[10px]">禁用</span>
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer hover:text-accent-danger transition-colors">
                    <input type="radio" :name="`act-${gIndex}-${mIndex}`" value="delete" 
                           v-model="actionMap[mod.path]" class="accent-accent-danger w-3 h-3">
                    <span class="text-[10px]">删除</span>
                  </label>
                </div>
                
                <!-- 选中状态文字 -->
                <div v-else class="ml-4 px-3 py-1.5 rounded bg-accent-success/20 text-accent-success text-[10px] font-bold border border-accent-success/20">
                  将保留并使用
                </div>

              </div>
            </div>
          </div>

        </div>

        <!-- Footer -->
        <div class="p-4 bg-black/20 border-t border-white/5 flex justify-between items-center shrink-0">
          <div class="text-xs text-text-dim">
            <span class="text-accent-warn">注意：</span> 选择删除将直接移除文件至回收站，操作不可逆。
          </div>
          <button @click="submit" :disabled="processing"
            class="px-8 py-2.5 rounded-lg bg-accent-primary hover:bg-accent-primary/80 text-black text-sm font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-lg shadow-accent-primary/20">
            <span v-if="processing" class="animate-spin">⟳</span>
            {{ processing ? '处理中...' : '确认解决所有冲突' }}
          </button>
        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, reactive } from 'vue'
import { useModStore } from '../stores/modStore1'
import { useAppStore } from '../stores/appStore'
import { useToast } from "vue-toastification"

const appStore = useAppStore()
const modStore = useModStore()
const toast = useToast()

const visible = ref(false)
const conflicts = ref([])
const processing = ref(false)

// 状态管理
// selections: { groupIndex: selectedPath }  记录每组选了哪个
const selections = reactive({}) 
// actionMap: { path: 'disable' | 'delete' } 记录每个路径的具体操作
const actionMap = reactive({})

watch(() => modStore.conflictList, (newVal) => {
  if (newVal && newVal.length > 0) {
    conflicts.value = newVal
    
    // 初始化状态
    newVal.forEach((group, index) => {
      // 1. 默认选中第一个 (通常是 session_map 里那个，也就是先扫描到的)
      // 如果想更智能，可以对比 version
      const defaultWinner = group.items[0]
      selections[index] = defaultWinner.path
      
      // 2. 初始化所有项的操作为 'disable'
      group.items.forEach(mod => {
        actionMap[mod.path] = 'disable'
      })
    })
    
    visible.value = true
  }
}, { deep: true })

const selectVersion = (groupIndex, path) => {
  selections[groupIndex] = path
}

const submit = async () => {
  processing.value = true
  
  // 构造操作列表
  const operations = []
  
  conflicts.value.forEach((group, index) => {
    const keepPath = selections[index]
    
    // 这一组的 package_id
    const packageId = group.package_id
    
    // 遍历该组所有项
    group.items.forEach(mod => {
      if (mod.path === keepPath) {
        // 这是要保留的项，不做物理操作
        // 但后端需要知道谁是 Winner，以便把其他项的路径加到它的 shadow_paths 里
        // API 现在的逻辑是处理"被丢弃项"时顺便传入 keep_id，所以这里不需要单独生成 op
      } else {
        // 这是要处理的项
        const action = actionMap[mod.path] // disable 或 delete
        operations.push({
          action: action,
          target_path: mod.path,
          keep_id: packageId, // 告诉后端，这个被禁用的项是属于哪个ID的影分身
          // 如果 keepPath 对应的项还没入库（因为它在冲突列表里），
          // 后端处理完冲突后，前端刷新列表会重新扫描到 keepPath 那个项，
          // 这时它是唯一的，会正常入库。
          // 唯一的问题是 shadow_paths 的写入时机：如果 Mod 还没入库，无法写入 shadow_paths。
          // 
          // 修正：后端 API 处理时，如果 keep_id 在数据库不存在（因为刚扫描还没存），
          // update shadow_paths 会失败。
          // 
          // 解决方案：
          // 我们不依赖 API 里的 update shadow_paths。
          // 而是依赖：只要物理重命名了 About.xml.disabled，
          // 下次扫描（前端刷新触发）时，Scanner 遇到它会自动忽略。
          // 至于 shadow_paths 的记录，可以等 Winner 入库后，再通过一次专门的调用来补充，
          // 或者暂不记录 shadow_paths (目前只做物理隔离)。
          // 
          // 既然你选择了“扫描时拦截”方案，shadow_paths 其实是锦上添花。
          // 最重要的是把多余的文件改名。
        })
      }
    })
  })

  try {
    const res = await window.pywebview.api.resolve_scan_conflicts(operations)
    if (res.status === 'success') {
      toast.success("冲突已解决，正在刷新列表...")
      modStore.conflictList = [] 
      visible.value = false
      // 强制重置扫描状态，确保重新开始
      await appStore.refreshData() // 这会读取数据库，但数据库里现在还没有新Mod
      // 关键：必须重新触发一次扫描，让保留下来的那个Mod（因为没有竞争者了）正常入库
      modStore.scanMods() 
    } else {
      toast.error("处理失败: " + res.message)
    }
  } catch (e) {
    toast.error("API 调用异常")
    console.error(e)
  } finally {
    processing.value = false
  }
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>